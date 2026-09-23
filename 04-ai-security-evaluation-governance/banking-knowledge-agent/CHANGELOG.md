# Changelog

All notable changes to this project are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), with one
departure: this project was built in **15 planned stages**, each implemented, tested and
approved before the next began, so entries are grouped by stage rather than by release.
There has been one version throughout (`0.1.0`) and no published release.

Every entry names the commit that delivered it. Design reasoning is **not** repeated here —
it lives in `docs/architecture-guide.html` §20 (65 numbered decision records). This file
answers *what changed and when*; the guide answers *why*.

All data in this project is **synthetic**. No real banking system, customer or transaction
is represented.

---

## [0.1.0] — 2026-09-18

The 15 planned stages are complete. Nothing is outstanding except a run against a real
(paid) language model, which has deliberately never been done.

### Licensing

**No licence is granted.** Copyright © 2026 Zuleikha, all rights reserved. This is a
demonstration project, published to be read and assessed, not offered for reuse.

An MIT `LICENSE` file was briefly added on 2026-09-18 (`9854226`) and removed the same day.
That MIT grant still applies to that one commit for anyone who obtained a copy while it was
live — a published licence cannot be retroactively revoked. Every later commit carries no
licence.

---

### Stage 15 — Final Engineering Review — 2026-09-18 · `d738d6c`

A full review against a fixed checklist, then the fixes it produced.

**Removed**
- Dead code: `index_directory()` in `app/rag/pipeline.py`, referenced by nothing.

**Changed**
- **Money guard deduplicated.** `_warn_if_paid` had been copy-pasted into two CLIs and the
  copies' wording had already drifted. Now one `warn_if_paid` in `app/llm/factory.py`; a test
  asserts both CLIs reference that same function object.
- `Retry-After` reader deduplicated into `app/llm/base.py` as `read_retry_after` — reading
  that header is HTTP behaviour, not vendor behaviour.
- `RULE = "=" * 78` collapsed from four copies into a new `app/core/cli.py`.
- The container image and Compose now set `BKA_LOG_FORMAT=json` (§20.63). The documentation
  had advised JSON "in Docker / production" while nothing applied it, so every container
  logged console format.
- Declared Python support tightened to `>=3.12`, ruff target `py312` (§20.64). Nothing was
  ever built, type-checked or tested on 3.11.
- Repository-hygiene tests now skip when there is no git checkout (§20.65).

**Fixed**
- **17 tests had been failing inside the container image.** Tests added in Stages 13 and 14
  read `.gitignore` / `.gitattributes`, which `.dockerignore` deliberately excludes. Neither
  stage re-ran the image, so the recorded Docker result had been stale since Stage 12.
- Stale facts in `docs/HANDOVER.md` (test counts, decision-record range, a superseded pointer).
- `.gitattributes` now covers `*.toml` and `.gitignore`.

**Verified**
- Host: 1412 passed, 4 skipped · ruff, format and mypy strict clean · `app.eval` PASS.
- Image: `docker run --rm bka-test` → 1395 passed, 21 skipped, 0 failed.
- Live container: healthy, smoke tests pass, JSON logs, non-root `uid=999`, offline.

---

### Stage 14 — Production Architecture — 2026-09-17 · `e38f967`

**Added**
- `python -m app`, which starts the server from validated settings so `BKA_HOST` / `BKA_PORT`
  finally apply (§20.58). The image's `CMD` uses it.
- Runtime citation check: an answer citing evidence that was never sent is **withheld**, not
  returned (§20.59). Counted, logged, and surfaced as a 502.
- `app/api/errors.py` — 422 validation bodies keep an allow-list of `type`, `loc`, `msg`, so
  caller input is never echoed back (§20.61).
- Guide §17, *Production architecture*: local vs production, scaling, vector DB, provider
  abstraction, service boundaries, failure modes, and what was deliberately not built.

**Changed**
- Upper bounds on `BKA_LLM_TIMEOUT_SECONDS` (≤120) and `BKA_LLM_MAX_RETRIES` (≤3) (§20.60).
- Evaluation scores a withheld answer as a failed citation check instead of stopping the run
  (§20.62).

---

### Stage 13 — Security and Production Readiness — 2026-09-16 · `bc9f69d`, `e29bbae`

**Added**
- Optional shared API key on `/api/*` and `/metrics`; production refuses to start without one.
- Per-client rate limiting (429 + `Retry-After`).
- `/ready` readiness probe, separate from `/health` liveness.
- Input length limits, prompt-injection hardening, and a structlog processor that redacts
  sensitive fields from logs.
- `--no-access-log` in the container: uvicorn's access log prints client IP and path and
  bypasses redaction.

---

### Stage 12 — Containerisation — 2026-09-16 · `27739f2`

**Added**
- `Dockerfile` (runtime + test targets), `compose.yaml`, `.dockerignore`.
- The embedding model and the vector index are **baked into the image**, so the running
  container needs no network (`HF_HUB_OFFLINE=1`).
- Non-root `app` user; health check implemented in Python because the slim image has no curl.

---

### Stage 11 — Testing and Evaluation — 2026-09-15 · `7b8c85e`

**Added**
- A 49-question evaluation dataset across knowledge, paraphrase, tool, hybrid, failure,
  off-topic and injection categories, each naming its expected route, documents and facts.
- Retrieval and answer metrics: recall@5, MRR, path accuracy, citation validity.
- `python -m app.eval` scorecard CLI, free by default.

---

### Stage 10 — Observability — 2026-09-15 · `c627358`, `42788e8`

**Added**
- Request ids threaded through every log line, per-step latency, in-process counters and
  latency histograms at `GET /metrics`.

**Changed**
- The retriever logs a question **fingerprint and length**, never the question text.

---

### Stage 9 — Web Interface — 2026-09-14 · `2484b73`

**Added**
- Conversation API and a no-build web page showing the answer, its sources, tool activity and
  the decision route taken.

---

### Stage 8 — Conversation Context — 2026-09-14 · `2abbb39`

**Added**
- Session store and rule-based follow-up resolution ("is it healthy?"). Earlier **questions**
  are sent as context — never earlier answers, which would compound a mistake.

---

### Stage 7 — Agent Decision and Tool Selection — 2026-09-14 · `a3728d9`

**Added**
- Five explicit decision paths and a rule-based tool selector. The agent decides what a
  question needs before any model is called.

---

### Stage 6 — MCP Tools — 2026-09-11 · `93eeb22`

**Added**
- Six synthetic support tools, an in-process registry, and a real MCP server over stdio
  JSON-RPC. Built with parallel sub-agents against a frozen contract (guide §21).

---

### Stage 5 — Knowledge Agent and LLM Adapters — 2026-09-10 · `1478631`, `6ebe947`

**Added**
- The agent loop: decide → retrieve → ground → answer, refusing when evidence is insufficient.
- Two vendor adapters (Anthropic, OpenAI). Two, deliberately: one adapter proves an adapter
  can be written, two prove the abstraction. Neither is "the" chosen vendor.

---

### Stage 4 — LLM Abstraction — 2026-09-09 · `bee4b22`

**Added**
- The `LLMProvider` protocol, the error taxonomy every provider maps onto, prompt assembly
  and context injection. Documents and tool results are treated as untrusted input.

---

### Stage 3 — RAG Pipeline — 2026-09-09 · `be9297c`

**Added**
- Heading-aware chunking budgeted in the model's own tokens, local embeddings, an exact
  cosine vector store, and retrieval with a score floor below which the agent must refuse.

---

### Stage 2 — Domain Knowledge — 2026-09-08 · `cca70af`

**Added**
- 15 synthetic banking documents across 8 domains, and a deliberately strict loader: a
  malformed, mislabelled or empty document raises rather than being silently skipped.

---

### Stage 1 — Project Foundation — 2026-09-03 · `d448cc1`

**Added**
- Settings (`BKA_*`), structured logging, tracing, a health endpoint, and the test harness.

[0.1.0]: https://github.com/Zuleikha/banking-knowledge-agent
