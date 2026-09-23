# Architecture

## Request flow

```
┌──────────────┐   HTTP    ┌────────────────────────────────────────────────┐
│  client      │ ────────► │  FastAPI (src/api/main.py)                     │
└──────────────┘           │                                                │
                           │  POST /candidates        ─► InMemoryCandidateStore
                           │  POST /candidates/upload ─► extract_text        │
                           │                             └─ parse_skills     │
                           │                                                 │
                           │  POST /rank        ─┐                           │
                           │  POST /rank/inline ─┴─► Ranker.rank()           │
                           │                          ├─ skill_coverage      │
                           │                          ├─ experience_fit      │
                           │                          └─ text_similarities   │
                           │                              └─ strip_contact_details
                           │                                                 │
                           │  POST /fairness    ─► fairness_report           │
                           └────────────────────────────────────────────────┘
```

Everything is built once in the `lifespan` handler: settings, the candidate
store, and the ranker. The embedding backend loads its model there rather than
on first request, so the cost is paid before the service reports itself ready
instead of landing on one unlucky caller.

## The ranking contract

A backend supplies exactly one thing: **text similarity** between a job and a
set of candidates. Everything else — skill coverage, experience fit, weighting,
ordering, tiering, clamping — lives in `Ranker` on the base class.

```
Ranker (ABC)                      src/ranking/base.py
  ├─ text_similarities()          ABSTRACT — the only thing a backend implements
  ├─ skill_component()            shared
  ├─ rank()                       shared: score, clamp, sort, tier, number
  └─ describe()                   shared

  ├── LexicalRanker               src/ranking/lexical.py   method="tfidf"
  └── EmbeddingRanker             src/ranking/embedding.py method="embedding"
```

Swapping TF-IDF for embeddings therefore changes **one component of the score
and nothing about how the result is assembled**. Both backends call the same
pure functions in `features.py` for the skill and experience components, and
both call `strip_contact_details` before vectorising.

`build_ranker(settings)` is the factory; nothing else constructs a backend.

## Module map

| Module | File | Responsibility |
|---|---|---|
| API | `src/api/main.py` | Routes, dependencies, lifespan, optional API-key guard |
| Schemas | `src/api/schemas.py` | Request/response shapes distinct from domain models |
| Ranking contract | `src/ranking/base.py` | `Ranker`, `RankingWeights`, tiering, ordering |
| Lexical backend | `src/ranking/lexical.py` | TF-IDF fitted per request |
| Embedding backend | `src/ranking/embedding.py` | Sentence embeddings behind an `Encoder` protocol |
| Features | `src/ranking/features.py` | Pure `skill_coverage`, `experience_fit`, `parse_skills` |
| Redaction | `src/ranking/redaction.py` | Contact-detail stripping before scoring |
| Fairness | `src/monitoring/fairness.py` | Selection-rate metrics, all caller-supplied |
| Parsing | `src/processing/document_parser.py` | PDF/text extraction, content-sniffed |
| Quality | `src/processing/quality_checker.py` | Batch data-quality reporting (off the ranking path) |
| Generation | `src/data_generation/resume_generator.py` | Synthetic resumes for local testing |
| Storage | `src/storage/memory.py` | Capped in-memory store |
| Config | `src/utils/config.py` | `Settings`, weights validated at load |

## Score composition

```
overall = skill_match      × skill_weight       (default 0.50)
        + experience_match × experience_weight  (default 0.30)
        + text_similarity  × similarity_weight  (default 0.20)
```

Each component is clamped to `[0, 1]` **before** weighting, and the overall
score clamped again after. Cosine similarity over embeddings can be negative;
without the clamp a negative component would pull an overall score below the
range the API publishes.

### Skill coverage

Fraction of the target skills the candidate holds, compared case-insensitively
with whitespace collapsed.

When a job states **both** required and preferred skills, the component is
`0.8 × required + 0.2 × preferred`. When it states only one of the two, that
list carries the whole component — otherwise a job with no preferred skills
would cap every candidate at 0.8.

An empty target list scores **0.0**, not 1.0: a role that states no skills
provides no evidence either way, and awarding full marks for absent
requirements would inflate every candidate identically.

### Experience fit

| Case | Score |
|---|---|
| Below the minimum | `years / min_years` — a linear ramp |
| Inside the band | `1.0` |
| Above the maximum | `1.0 - 0.1 × excess_years`, floored at `0.7` |
| Not stated (`None`) | `0.0` |

Over-qualification is a weak negative signal, not a disqualification, hence the
0.7 floor. An unstated figure scores 0.0 rather than a guessed value, so it can
never outrank a stated one.

### Text similarity

Both backends redact contact details first, then compute cosine similarity
between the job text and each resume.

**The lexical backend fits its vectoriser per request**, over the job plus the
candidates in that request. Scores are therefore comparable *within* one
response and **not across responses**. This is a documented consequence of
having no corpus to fit against — see [DECISIONS.md](DECISIONS.md).

## Ordering

```python
scored.sort(key=lambda row: (-overall, candidate_id))
```

Descending by score, then ascending by `candidate_id`. Ties never break on
insertion order, which would make results depend on upload sequence. The
ordering is total and stable.

## Storage

`InMemoryCandidateStore` with a hard cap (`MAX_CANDIDATES`, default 1000).
Uploads beyond the cap are **rejected with 507**, never silently evicted — a
caller who is dropping data should be told, not discover it from a short result
list.

`GET /candidates` returns ids only. Resume text is never returned in bulk.

## Error contract

| Status | When |
|---|---|
| 400 | Document cannot be parsed, or skills cannot be parsed |
| 401 | `API_KEY` is configured and the `X-API-Key` header does not match |
| 404 | Ranking with no candidates stored; deleting an unknown candidate |
| 413 | Resume text or extracted text exceeds `MAX_RESUME_CHARS` |
| 422 | Fairness outcome sequences do not line up |
| 507 | Candidate store is at capacity |

## Testable contracts

Invariants the suite pins:

- **Weights** — must sum to 1.0; `RankingWeights` and `Settings` both reject otherwise.
- **Ranking** — ties break on id; ranks are 1-based and contiguous; a backend returning the wrong number of similarities raises rather than mis-pairing.
- **Skill coverage** — empty target list scores 0.0; required/preferred blending; single-list jobs carry the full component.
- **Experience fit** — every branch including the 0.7 over-qualification floor and the `None` case.
- **Redaction** — emails, URLs and phones removed; year ranges survive; line structure preserved.
- **Fairness** — parity maths; the all-zero-selection case holds trivially rather than dividing by zero; equal opportunity returns `None` with a note when fewer than two groups have qualified candidates.
- **Parsing** — `parse_skills` accepts list literals and CSV, and raises on a crafted literal rather than executing it.
- **Store** — capacity rejection, delete semantics, id listing.

## What the tests never do

No network call, no model download, no PDF fixture files. The embedding backend
depends on an `Encoder` **protocol**, not the concrete `SentenceTransformer`, so
tests inject a deterministic stub and verify the ranking maths without loading a
model. `sentence_transformers` is imported inside the constructor rather than at
module scope, so the module stays importable when the extra is not installed.
