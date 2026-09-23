# Candidate Ranking Service

Scores resumes against a job description on **skill coverage**, **experience
fit** and **resume-text similarity**, and returns a ranked list where every
score arrives with the component breakdown behind it.

The service **ranks; it does not decide**. No endpoint returns a hire/reject
recommendation, a "good fit" label or a pass mark. That judgement belongs to a
person who can see the things a model cannot.

## Stack

| Layer | Choice |
|---|---|
| API | FastAPI, Pydantic v2 validation, async lifespan |
| Default ranking | TF-IDF (`scikit-learn` `TfidfVectorizer` + cosine similarity) |
| Optional ranking | Sentence embeddings (`sentence-transformers`, opt-in extra) |
| Document parsing | `pypdf`, content-sniffed — never trusts the filename |
| Storage | In-memory, hard-capped, no database |
| Config | `pydantic-settings`, env-bound, weights validated at load |
| Tests | pytest, **161 tests**, no network, no model download |

## How a score is built

```
job description + candidate
   |
   +--> skill coverage      weight 0.50
   |      required skills weighted 0.8, preferred 0.2
   |
   +--> experience fit      weight 0.30
   |      below band: linear ramp
   |      inside band: 1.0
   |      above band: -0.1/yr, floor 0.7
   |
   +--> text similarity     weight 0.20
          contact details stripped first
          TF-IDF cosine, or embedding cosine
                |
                v
      overall score, clamped to [0, 1]
                |
                v
      tier A/B/C/D + full breakdown
```

Weights are configurable and **must sum to 1.0** — the service refuses to start
otherwise, rather than silently normalising and producing scores nobody can
reconcile.

### Tiers are deliberately coarse

Four bands (A ≥ 0.75, B ≥ 0.50, C ≥ 0.25, D below). The difference between 0.61
and 0.63 is not meaningful, and presenting a fine-grained ordering invites more
confidence than the score can support.

## Fairness measurement

`POST /fairness` computes selection-rate metrics from outcomes **you supply**:

| Metric | What it answers |
|---|---|
| Demographic parity difference | Highest minus lowest selection rate across groups |
| Demographic parity ratio | Lowest ÷ highest |
| Four-fifths rule | Whether that ratio reaches 0.8 (US EEOC Uniform Guidelines) |
| Equal opportunity difference | Selection-rate spread among *qualified* candidates only |

Two rules this module holds to:

- **Group membership is always caller-supplied.** It never infers a protected
  attribute from a name, a school or a location.
- **An unmeasurable metric returns `null` with a note explaining why**, never a
  plausible-looking substitute. A fairness figure that was not measured is worse
  than no figure, because it invites reliance it cannot support.

The four-fifths result is a flag for review. It is not a legal verdict.

## Redaction before scoring

Email addresses, phone numbers and profile URLs are stripped from resume text
before it reaches a vectoriser or an embedding model. They carry no signal about
whether someone can do the job, but they do carry signal about who they are — a
personal domain, a country dialling code.

Phone detection counts digits rather than matching formats, because `+44 20 7946
0958` and `(415) 555-0123` share no shape. The threshold is 9 digits, so
`2019 - 2024` survives — employment dates are signal.

**This is a mitigation, not anonymisation.** Names remain in the text. See
[docs/ROADMAP.md](docs/ROADMAP.md).

## Run it

```bash
pip install -e ".[dev]"
uvicorn src.api.main:app --reload      # → http://localhost:8000
```

Interactive docs at `/docs`.

For semantic ranking:

```bash
pip install -e ".[embeddings]"
RANKING_METHOD=embedding uvicorn src.api.main:app
```

## API

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness, active backend, store occupancy and capacity |
| `POST` | `/candidates` | Store a candidate as JSON |
| `POST` | `/candidates/upload` | Store a candidate from a PDF or text upload |
| `GET` | `/candidates` | List stored ids — resume text is never returned in bulk |
| `DELETE` | `/candidates/{id}` | Remove a candidate |
| `POST` | `/rank` | Rank every stored candidate against a job |
| `POST` | `/rank/inline` | Rank candidates supplied in the request, storing nothing |
| `POST` | `/fairness` | Selection-rate fairness report |

### Example

```bash
curl -X POST http://localhost:8000/rank/inline \
  -H "Content-Type: application/json" \
  -d '{
    "job": {
      "title": "Backend Engineer",
      "required_skills": ["Python", "PostgreSQL"],
      "preferred_skills": ["Kubernetes"],
      "min_years_experience": 3
    },
    "candidates": [
      {"candidate_id": "c1", "resume_text": "Python and Postgres services.",
       "skills": ["Python", "PostgreSQL"], "years_experience": 5}
    ]
  }'
```

```json
{
  "scoring_method": "tfidf",
  "model": "TfidfVectorizer",
  "candidates_considered": 1,
  "results": [
    {
      "candidate_id": "c1",
      "overall_score": 0.8,
      "rank": 1,
      "tier": "A",
      "breakdown": {
        "skill_match": 1.0,
        "experience_match": 1.0,
        "text_similarity": 0.0
      }
    }
  ]
}
```

Note `text_similarity: 0.0` on a single-candidate request: TF-IDF is fitted per
request, and a term appearing in every document carries no discriminating
weight. This is a real property of the backend, not a bug — see
[docs/DECISIONS.md](docs/DECISIONS.md).

## Ordering is total and stable

Ties break on `candidate_id`, never on insertion order. Two candidates scoring
identically rank the same way whichever order they were uploaded in.

## Tests

```bash
pytest -q
```

161 tests. No network, no model download, no PDF fixtures — the embedding
backend is exercised through an injected stub encoder, and the document parser
against generated bytes.

## Repository layout

```
src/api/main.py            FastAPI routes and lifespan
src/api/schemas.py         request/response models
src/ranking/base.py        Ranker ABC, weighting, tiering, ordering
src/ranking/lexical.py     TF-IDF backend (default)
src/ranking/embedding.py   sentence-transformers backend (opt-in)
src/ranking/features.py    pure skill-coverage and experience-fit functions
src/ranking/redaction.py   contact-detail stripping
src/monitoring/fairness.py selection-rate metrics
src/processing/            document parsing, batch quality checks
src/data_generation/       synthetic resume generator for local testing
src/storage/memory.py      capped in-memory candidate store
src/models/                domain models
src/utils/config.py        env-bound settings
```

## Known limits

Storage is in-memory and lost on restart. The API is open by default —
`API_KEY` gates the write endpoints only when set. Redaction removes contact
details but not names. There is no offline evaluation of ranking quality
against labelled hiring outcomes. All tracked in
[docs/ROADMAP.md](docs/ROADMAP.md) and [docs/SECURITY.md](docs/SECURITY.md).

## Licence

MIT — see [LICENSE](LICENSE).
