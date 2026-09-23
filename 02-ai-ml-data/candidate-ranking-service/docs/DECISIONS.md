# Decisions

Why the system is built this way, and what each choice costs. A decision with
no cost is usually a decision that was never made.

## ADR-0001 — The service ranks, it does not decide

No endpoint returns a hire/reject recommendation, a "good fit" label, or a pass
mark. The response carries a score, a coarse band, and the component breakdown
behind them.

Automated candidate screening is a high-stakes use of ML: it affects people's
livelihoods, the ground truth is contested, and the training signal available
in practice is past hiring decisions — which encode past bias. A system that
outputs "reject" invites the reviewer to stop thinking. One that outputs
"skill coverage 0.4, experience fit 1.0, similarity 0.2" invites them to look.

**Cost:** the service is less immediately useful. A caller who wanted a
shortlist has to define their own cut-off, and nothing stops them thresholding
the score and treating it as a decision anyway. The boundary is a design
posture, not an enforcement mechanism.

## ADR-0002 — TF-IDF as the default backend

Deterministic, no model download, no network, milliseconds on CPU, and a
fresh clone runs the full test suite with no setup.

It measures **vocabulary overlap, not meaning**: a resume saying "PostgreSQL"
scores nothing against a job asking for "relational databases". That is a real
limitation, stated plainly rather than papered over.

**Cost:** the semantic gap above, plus a subtler one — the vectoriser is fitted
**per request** over the job plus that request's candidates, because there is no
corpus to fit against. Scores are comparable *within* one response and **not
across responses**. Ranking one candidate alone yields `text_similarity: 0.0`,
because a term present in every document carries no discriminating weight. That
surprises people, so it is called out in the README's own example.

## ADR-0003 — Sentence embeddings as an optional extra, not a dependency

`sentence-transformers` closes the semantic gap, at the cost of a
multi-hundred-megabyte dependency tree (PyTorch) and a model download on first
use. Making that the default would mean a fresh clone cannot run the tests
without a network connection and several minutes of waiting.

So it is an extra: `pip install -e ".[embeddings]"` plus
`RANKING_METHOD=embedding`.

Two implementation details make the split hold:

- `sentence_transformers` is imported **inside the constructor**, never at
  module scope, so `src/ranking/embedding.py` stays importable — and the rest of
  the service testable — when the extra is absent.
- The backend depends on an `Encoder` **Protocol** describing the one method it
  uses, not on the concrete `SentenceTransformer` class. Tests inject a
  deterministic stub and verify the ranking maths with no model and no network.

**Cost:** two code paths to keep correct, and a backend whose default-path
behaviour most users will never exercise. Selecting `embedding` without the
extra installed raises `ImportError` with the install command in the message,
rather than silently falling back to TF-IDF — a silent fallback would mean
nobody notices they are not getting the ranking they configured.

## ADR-0004 — Redaction before vectorising, not anonymisation

Emails, phone numbers and profile URLs are stripped from resume text before it
reaches a vectoriser or an embedding model. They carry no signal about whether
someone can do the job, and they do carry signal about who they are.

Phone detection **counts digits rather than matching formats**, because
`+44 20 7946 0958` and `(415) 555-0123` share no shape. The threshold is nine
digits, chosen so that `2019 - 2024` (eight digits) survives — employment dates
are signal and must not be redacted away.

**Cost:** this is a mitigation, not anonymisation. **Names remain in the text**,
and names are the strongest demographic proxy in a resume. Claiming this
delivers blind screening would be false. It narrows what the score can be
derived from; it does not make the score identity-blind. Tracked in
[ROADMAP.md](ROADMAP.md).

## ADR-0005 — Fairness metrics are measured, never inferred

Group membership is **always supplied by the caller**. The module never infers
a protected attribute from a name, a school or a location.

Inferring demographics in order to measure fairness means building exactly the
classifier that causes the harm being measured, and being wrong about
individuals while claiming to help them.

Where a metric is undefined for the data given, the report returns `null` **and
a note explaining why**, rather than a plausible-looking substitute. A fairness
number that was not really measured is worse than no number, because it invites
reliance it cannot support.

**Cost:** the endpoint is useless to anyone who does not already have labelled
outcome data, which is most callers. That is the correct trade — the
alternative is a fairness score that means nothing.

## ADR-0006 — One abstract method on the ranking contract

`Ranker` exposes exactly one abstract method: `text_similarities()`. Skill
coverage, experience fit, weighting, clamping, ordering and tiering all live on
the base class and are shared.

A backend therefore changes **one component of the score and nothing about how
the result is assembled**, which is what makes TF-IDF and embeddings genuinely
comparable rather than two parallel implementations that drift.

**Cost:** a backend that wanted to influence the skill or experience components
cannot, without changing the base class. That constraint is deliberate.

## ADR-0007 — Coarse tiers, four bands

A ≥ 0.75, B ≥ 0.50, C ≥ 0.25, D below. The difference between 0.61 and 0.63 is
not meaningful given the inputs, and presenting a fine-grained ordering invites
more confidence than the score supports.

**Cost:** two candidates either side of a boundary look further apart than they
are — the classic threshold artefact. The raw `overall_score` is published
alongside the tier precisely so a caller can see when a band edge is doing more
work than the score is.

## ADR-0008 — Weights must sum to 1.0, enforced twice

Validated in `RankingWeights.__post_init__` **and** in `Settings`, so a bad
configuration fails at startup rather than producing scores nobody can
reconcile.

The alternative — normalising silently — means the effective weights differ
from the configured ones, and nobody finds out.

**Cost:** changing one weight means changing another. That friction is the
point: the components trade against each other, and pretending otherwise hides
the trade.

## ADR-0009 — In-memory storage, capacity rejected not evicted

No database. A capped dict, default 1000 candidates. Uploads beyond the cap are
rejected with **507**, never silently evicted.

A caller who is losing data should be told, not discover it from a short result
list.

**Cost:** everything is lost on restart, and the service cannot scale beyond
one process. Correct for a ranking service that is demonstrating scoring logic;
wrong the moment it holds anything real.

## ADR-0010 — `ast.literal_eval` for skills parsing, never `eval`

A CSV round-trip turns `["Python", "SQL"]` into the *string* `"['Python',
'SQL']"`. Parsing that back needs literal evaluation.

`ast.literal_eval` evaluates Python literals only, so a crafted cell such as
`__import__('os').system('...')` raises `ValueError` instead of executing.
`eval` on data read from a file is remote code execution with extra steps.

**Cost:** none worth stating. This is the correct call, and it is documented
here because the *reason* matters more than the line of code.

## Choices made without a formal ADR

| Choice | Reasoning |
|---|---|
| Ties break on `candidate_id` | Ordering must be total and stable. Breaking on insertion order makes results depend on upload sequence. |
| Empty skill list scores 0.0, not 1.0 | A role stating no skills gives no evidence either way; full marks would inflate every candidate identically. |
| Unstated experience scores 0.0 | So an unstated figure can never outrank a stated one. Guessing a value would be inventing evidence. |
| Over-qualification floors at 0.7 | A weak negative signal, not a disqualification. |
| Components clamped before *and* after weighting | Embedding cosine can be negative; without the clamp an overall score could fall below the range the API publishes. |
| Model loaded in `lifespan`, not on first request | The cost is paid before the service reports ready, instead of landing on one unlucky caller. |
| Content-sniffed document type | The filename is caller-controlled and therefore not evidence of anything. |
| `GET /candidates` returns ids only | Resume text is personal data; there is no reason to return it in bulk. |
| `pydantic-settings` over `os.getenv` | Type validation and fail-fast startup, including the weights-sum check. |
| `ruff` for lint and format | One tool replacing black plus flake8. |
