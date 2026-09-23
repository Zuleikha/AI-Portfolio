# Roadmap

Known gaps, ordered by what would break first under real use. Each entry names
the files involved so the work is actionable rather than aspirational.

## Blocking any real deployment

### No evaluation of ranking quality

There is no labelled dataset, no offline harness, and no measurement of whether
the ranking correlates with anything. 161 tests pin the **mechanics** — that
weights combine as specified, that ties break on id, that coverage maths is
right — and none of them establish that a higher score means a better
candidate.

For a system that orders people, this is the most serious gap in the repository.

- **Files:** a new `src/evaluation/`, `data/eval/`
- **Approach:** a small labelled set of job/candidate pairs with expert
  relevance judgements; report NDCG and precision@k against it; make it a CI
  gate the way project 02's drift metrics are, so a scoring change that degrades
  quality fails the build.
- **Watch out for:** the labels are themselves opinions. The harness must
  measure agreement with a stated rubric, not pretend to measure truth.

### Authentication covers only the write endpoints

`API_KEY` gates writes when set, and nothing gates `GET /candidates`,
`POST /rank`, `POST /rank/inline` or `POST /fairness`.

- **Files:** `src/api/main.py`, `src/utils/config.py`
- **Approach:** apply `require_api_key` to every route except `/health`; keep
  `/health` open so a container probe can reach it.

### No rate limiting

`POST /rank` with the embedding backend runs a model over every stored
candidate. Unauthenticated and unlimited, that is a cheap way to saturate the
host.

- **Files:** `src/api/main.py`
- **Approach:** per-key token bucket, in-memory to match the storage model.

### Upload size is unbounded before the cap applies

The extracted-text cap returns 413, but `await file.read()` has already pulled
the whole upload into memory.

- **Files:** `src/api/main.py`
- **Approach:** check `Content-Length`, and stream the read with a running byte
  cap, rejecting with 413 before the allocation completes.

### CORS defaults to `*`

- **Files:** `src/utils/config.py`
- **Approach:** default to `http://localhost:8000`, require an explicit
  environment override to widen.

## Fairness and transparency

### Redaction stops at contact details

Names remain in the resume text that reaches the vectoriser, and names are the
strongest demographic proxy a resume carries. The service therefore cannot be
described as blind screening.

- **Files:** `src/ranking/redaction.py`
- **Approach:** optional name redaction using a NER model, off by default and
  clearly labelled as lossy — a name in a project title ("Nielsen normalisation")
  is signal, and stripping it costs accuracy.
- **Watch out for:** name detection is culturally biased in its own right. Worse
  detection for non-Western names would mean unequal redaction, which is a new
  fairness problem rather than a fix for the old one.

### Fairness is measured on demand, never recorded

`POST /fairness` computes a report and returns it. Nothing stores outcomes,
nothing trends them over time, and nothing alerts when parity degrades.

- **Files:** `src/monitoring/fairness.py`, new persistence
- **Approach:** an outcome log and a scheduled report. This is the difference
  between being able to measure fairness and actually monitoring it.

### No per-decision audit record

Nothing records what was ranked, against what job, with which weights and which
backend. Reproducing a past ranking after a config change is impossible.

- **Files:** `src/api/main.py`, new storage
- **Approach:** an append-only record of `(job hash, candidate ids, weights,
  backend, model, timestamp, results)`. This is what an EU AI Act record-keeping
  obligation would need, and it is also just good engineering.

### The four-fifths rule is US-specific

`passes_four_fifths_rule` is presented alongside metrics that are jurisdiction
neutral, which can read as more authoritative than it is.

- **Files:** `src/monitoring/fairness.py`
- **Approach:** rename to make the provenance explicit, or return it under a
  `us_eeoc` key so its scope is visible in the response shape.

## Correctness and scale

### TF-IDF scores are not comparable across responses

The vectoriser is fitted per request, so a candidate's `text_similarity` depends
on who else was in that request. Ranking one candidate alone yields 0.0.

- **Files:** `src/ranking/lexical.py`
- **Approach:** fit once against a stable corpus and persist the vocabulary, or
  document the property in the response itself (a `comparable_within_response:
  true` field) so a caller cannot mistake it.

### Storage is in-memory and single-process

Everything is lost on restart, and the service cannot run more than one replica.

- **Files:** `src/storage/memory.py`
- **Approach:** a `CandidateStore` protocol with a Postgres implementation
  behind it. The in-memory store already has the right shape for this.

### Ranking is O(candidates) per request with no batching cap

`POST /rank` scores every stored candidate. At the 1000-candidate cap with the
embedding backend, that is 1000 encodes per request on the event loop.

- **Files:** `src/api/main.py`, `src/ranking/embedding.py`
- **Approach:** the handler is `def`, so FastAPI already runs it in a
  threadpool — but the work itself should be batched and bounded, and results
  cached by `(job hash, candidate id)` since a candidate's score only changes
  when the job or the weights do.

## Quality

| Item | Files | Approach |
|---|---|---|
| Error handlers return exception text | `src/api/main.py` | Log server-side with a request id, return the id and a generic message |
| No request-id correlation in logs | `src/api/main.py` | Middleware assigning `X-Request-ID`, bound to a `ContextVar` |
| No structured logging | `src/api/main.py` | `structlog` JSON output, matching the other services in the showcase |
| `get_settings()` is uncached and re-reads the environment per call | `src/utils/config.py` | Deliberate, so tests can override — but the API calls it at module scope for CORS, which reads settings before the lifespan builds them |
| Dependencies use `>=` constraints | `pyproject.toml` | A lockfile would make builds reproducible |
| No Dockerfile | — | The other showcase services ship one; this does not |

## Longer term

- **Skill matching is exact-string.** "PostgreSQL" and "Postgres" are different
  skills, and "React" does not match "React.js". A synonym table or an
  embedding-based skill match would fix it, and would need its own evaluation to
  show it did not make things worse.
- **No explanation beyond the numeric breakdown.** The score says skill coverage
  was 0.4; it does not say which required skills were missing. That list exists
  inside `skill_coverage` and is discarded.
- **Batch quality reporting is off the ranking path.**
  `src/processing/quality_checker.py` produces a data-quality report that
  nothing in the request path consumes.
- **The synthetic resume generator has no distributional grounding.**
  `src/data_generation/resume_generator.py` produces plausible test data, not
  data whose distribution resembles real applicants — fine for testing
  mechanics, unsuitable for evaluating quality.
