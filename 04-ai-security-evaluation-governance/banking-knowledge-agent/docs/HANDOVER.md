# HANDOVER — Banking Knowledge Agent

> **Read this first in any new Claude Code session.**
> This file, not conversation history, is the record of project progress.
> Never assume a previous session completed work unless the repository confirms it.

**A decision is not recorded until it is written here.** If a decision is made mid-stage,
before implementation begins, write it down immediately — not at stage completion.

📦 **History lives in [`HANDOVER-archive.md`](HANDOVER-archive.md).** This file was trimmed
from 2934 lines to current state on 2026-09-16. Everything removed — Stage 5–11 decision
sections, resolved problems, superseded Next Actions, long-form architecture/files/testing —
is preserved there verbatim. At Stage 13 close the Stage 12 decision table, the Stage 10/11 lists and
the Stage 13 step log were moved there too. Design decisions are also committed in
`docs/architecture-guide.html` §20. **Do not read the archive unless you need history.**

---

## ⏱️ SESSION CHECKPOINT — start here

**Stage 15 — Final Engineering Review — is APPROVED (2026-09-18) and committed** as one
`feat(stage-15)` commit `d738d6c` (22 files) — **pushed** `dc0b317..d738d6c`, verified
`origin/main == local HEAD`.
Decisions 15.A–15.B at kickoff, 15.C after the container suite was actually run. Findings and
fixes in *Current Work*; full record in guide §22. **Docker verified this session** — see *Testing*.

**Stage 15 was the last planned stage. The project is complete as specified in
`docs/PROJECT_PLAN.md`.** There is no Stage 16.

**Previous: Stage 14 — Production Architecture — is APPROVED (2026-09-17) and committed** as one
`feat(stage-14)` commit `e38f967` — **pushed** `f109758..e38f967`, verified `origin/main == local HEAD`. Decisions 14.A–14.F below.

**Previous: Stage 13 — Security and Production Readiness — APPROVED (2026-09-16) and committed**
as two commits: `bc9f69d` (`style:` — the 24 formatting-only files, 13.D) and the
`feat(stage-13)` commit `e29bbae` on top — **pushed**, verified `origin/main == local HEAD`. At approval the user chose:
keep `HEALTHCHECK` on `/health` (**13.G**), add `--no-access-log` (**13.H**), two commits.

| | |
|---|---|
| Last **approved** stage | **Stage 15 — Final Engineering Review** (2026-09-18), `d738d6c` |
| Current stage | **None** — Stage 15 was the final stage, and it is approved and committed |
| Tests | **1412 passed, 4 skipped** · ruff clean · format clean (118 files) · mypy strict clean (76 source files) · `app.eval` PASS |
| Next | **Nothing outstanding.** Only `--paid` remains unrun, by design (needs explicit confirmation) |

### Stage 13 outcome

| | |
|---|---|
| **13.G** | Docker `HEALTHCHECK` **stays on `/health`** (liveness); `/ready` is for orchestrators — guide §20.56 |
| **13.H** | **`--no-access-log` added** to the runtime `CMD`, with a new test written first (`test_the_server_disables_uvicorn_access_log`, seen failing, then passing) — guide §20.57 |
| **Commit split** | `bc9f69d` `style:` = all **24** files the formatter changed. **3 of them** (`app/llm/anthropic_provider.py`, `openai_provider.py`, `prompts.py`) also had real Stage 13 changes, so only their *formatting* went in the style commit (formatted `HEAD` version staged); their real changes are in `e29bbae` `feat(stage-13)` (37 files) |
| **Checks passed** | **1363 passed, 4 skipped** · ruff clean · format clean · mypy clean (72 files) · `app.eval` PASS · **no secrets** (only the marked fake `test-only-not-a-secret`) · **`.env` not tracked** · no nested directory |
| **Guide status** | Stage 13 marked complete: header pill, footer, §1 table (BUILT), §1 diagram (Guardrails ✅) |
| **Push** | `ed46ae1..e29bbae`, then handover commits; `origin/main == local HEAD` verified |

### Stage 14 decisions (2026-09-17)

| # | Decision |
|---|---|
| 14.A | **Wire `BKA_HOST` / `BKA_PORT`** — add `python -m app`, which starts uvicorn with `settings.host` / `settings.port`, so the Settings validation really applies; Dockerfile `CMD` uses it — user, at kickoff (guide §20.58). Rejected: drop the fields; leave and document |
| 14.B | **Withhold an answer that cites evidence never sent** — a `[n]` / `[Tn]` outside the passages/tool results supplied raises `LLMResponseError` (→ 502), counted and logged, like a truncated answer — user, at kickoff (guide §20.59). Rejected: flag and still answer; strip the markers |
| 14.C | **LLM wait capped:** `BKA_LLM_TIMEOUT_SECONDS` ≤ 120, `BKA_LLM_MAX_RETRIES` ≤ 3 → worst case 480 s per call (guide §20.60). Default choice, not asked. Rejected: no bound; a total-deadline setting (Stage 14 design note instead) |
| 14.D | **422 bodies keep an allow-list** — `type`, `loc`, `msg` only; `input`, `ctx`, `url` and any future field dropped. New `app/api/errors.py` (guide §20.61). Default choice, not asked. Rejected: deleting just `input`/`ctx` (a deny-list lets new fields through) |
| 14.E | **Evaluation scores a withheld answer, does not crash** — new `LLMInvalidCitationError(LLMResponseError)` with `markers` + `route` (set by the agent); runner catches only it → `path` + failed `citations` check, run continues. Other errors still stop the run — user, at Stage 14 review (guide §20.62). Rejected: catch all `LLMResponseError`; guess the route in the runner |
| 14.F | **No exemption for markers found in the user's question** — a `[9]` quoted from the question and repeated by the model stays withheld. User text is untrusted; an exemption would be exploitable like prompt injection. Documented as a known limitation (guide §20.59) — user, at approval |

### Stage 15 decisions (2026-09-18)

| # | Decision |
|---|---|
| 15.A | **The container defaults to JSON logs** — `ENV BKA_LOG_FORMAT=json` in the Dockerfile runtime stage and `BKA_LOG_FORMAT: ${BKA_LOG_FORMAT:-json}` in `compose.yaml`, still overridable from the shell — user, at kickoff (guide §20.63). `.env.example` and `README.md` both advised JSON "in Docker / production", but nothing applied it, so every container logged `console`. Rejected: auto-switch on `BKA_ENVIRONMENT=production` inside `config.py` (changes local production runs too, and hides the setting from the file that documents it); soften the docs instead |
| 15.C | **Repository-hygiene tests skip when there is no git checkout** — the 12 `.gitattributes` LF cases and the 5 `.gitignore` secret-pattern cases are marked `skipif` on the file being absent. Found by actually building and running the image (guide §20.65). `.dockerignore` deliberately excludes `.git`, `.gitignore` and `.gitattributes`, so inside the container those tests asserted something correctly absent and **17 tests failed in the image**. Pre-existing since Stage 13/14, undetected because neither stage re-ran the image. Rejected: un-ignoring the git files so they reach the build context (weakens a deliberate, security-adjacent exclusion to satisfy a test); copying them into the test stage only (same weakening, and the test stage is meant to mirror runtime) |
| 15.B | **Declared Python support tightened to `>=3.12`** — `requires-python = ">=3.12"` and ruff `target-version = "py312"`; mypy was already `3.12` — user, at kickoff (guide §20.64). The venv, the Dockerfile, the README and mypy are all 3.12, so 3.11 was never built, type-checked or tested: an unverified claim. Rejected: point mypy at 3.11 (the suite still would not run on 3.11, so the claim stays unverified); leave as a deliberate lower bound |

### Carried to Stage 14 — ✅ all five done in Stage 14 (see *Current Work*)

1. **Upper limits on LLM timeout and retry settings** — `BKA_LLM_TIMEOUT_SECONDS` / `BKA_LLM_MAX_RETRIES` have no `le` bound (worst case ≈180 s+ holding a worker and the session lock)
2. **`BKA_HOST` / `BKA_PORT` are not read by the app** (12.G) — only uvicorn's flags apply; wire them or drop them
3. **Stop 422 errors echoing caller input** — FastAPI's default validation body includes `input`; add a `RequestValidationError` handler that strips `input`/`ctx`
4. **Verify `[n]` / `[Tn]` citations match the passages sent** — inline markers in answer text are not checked against the evidence given to the model
5. **Add `Dockerfile`, `*.js`, `*.css`, `.dockerignore`, `.env.example` to `.gitattributes`** (`text eol=lf`) — they are LF today, but git warns on every commit

### Commits, 2026-09-16 session

| Commit | What |
|---|---|
| `27739f2` | **Stage 12 — Containerisation** (9 files) |
| `e60335c` | Handover: Stage 12 hash and push result |
| `ed46ae1` | Handover split into current state + archive |
| `bc9f69d` | `style:` ruff format, 24 files (13.D) |
| `e29bbae` | **Stage 13 — Security and Production Readiness** (37 files) |
| `3e3b524` | Handover: Stage 13 hashes and push result |
| *(latest)* | Handover: session-close refresh, history moved to archive |

---

## Current Stage

| | |
|---|---|
| **Stage number** | 14 |
| **Stage name** | Production Architecture |
| **Status** | ✅ **APPROVED 2026-09-17 — committed `e38f967`, pushed** |
| **Last completed step** | Implemented and tested (incl. review fix 14.E): 1396 passed / 4 skipped, ruff, format and mypy clean, `app.eval` PASS, `python -m app` live-checked. Guide §17 rewritten, §20.58–§20.62 added. Re-verified after approval (same results, `git add -An` = 28 files, no secrets, `.env` untracked, no nested directory). Guide status markers set to Stage 14 (pill, footer, §1 table, §1 diagram) |
| **Next step** | Stage 15 — Final Engineering Review — begins when the user asks |

| Stage | Name | Status |
|---|---|---|
| 15 | Final Engineering Review | ✅ 2026-09-18, `d738d6c` |
| 14 | Production Architecture | ✅ 2026-09-17, `e38f967` |
| 13 | Security and Production Readiness | ✅ 2026-09-16, `bc9f69d` + `e29bbae` |
| 12 | Containerisation | ✅ 2026-09-16, `27739f2` |
| 11 | Testing and Evaluation | ✅ 2026-09-15, `7b8c85e` |
| 10 | Observability | ✅ 2026-09-15, `c627358` (+ `42788e8`) |
| 9 | Web Interface | ✅ 2026-09-14, `2484b73` |
| 8 | Conversation Context | ✅ 2026-09-14, `2abbb39` |
| 7 | Agent Decision and Tool Selection | ✅ 2026-09-14, `a3728d9` |
| 6 | MCP Tools | ✅ 2026-09-11, `93eeb22` |
| 1–5 | Foundation → LLM abstraction → Knowledge agent | ✅ all approved (hashes in *Git*) |

---

## Current Work

### Post-Stage-15 — project documentation (2026-09-18)

Not a stage. Asked for by the user after Stage 15 was committed, following a documentation
audit against the set expected of an AI-assisted project from scratch.

**Audit result:** README ✅ · `CLAUDE.md` ✅ · architecture + decision records ✅ (guide, 65
records) · **CHANGELOG ❌ missing** · **testing/verification doc ⚠️ scattered** across README,
handover and guide §15 · **LICENSE ❌ missing** (README claimed "personal portfolio project"
with no file, i.e. all-rights-reserved by default) · the only run guide was
`docs/HOW_TO_RUN.html`, which is **git-ignored** and so shipped to nobody.

| Added | What |
|---|---|
| ~~`LICENSE`~~ | MIT was added in `9854226`, then **removed the same day** at the user's request — see *Licence reversal* below |
| `CHANGELOG.md` | All 15 stages, grouped by stage rather than release (one version, `0.1.0`, no release). Every cited commit hash verified against `git cat-file` |
| `docs/HOW_TO_RUN.md` | **Tracked** run + end-to-end verification guide: setup, the 4-rung verification ladder, what it still does not prove, using your own corpus, troubleshooting |
| `docs/HOW_TO_RUN.html` | Rewritten (was stale by 4 stages — still told you to use `uvicorn app.main:app`, which ignores `BKA_HOST`/`BKA_PORT`). Git-ignored, personal copy |
| `README.md` | Licence section → **no licence granted, all rights reserved**; Run section → points at the run guide; Repository Structure → the new files |

**Corpus portability, tested not assumed.** A non-banking corpus was built and run end to end.
Retrieval is corpus-agnostic (a baking question scored 0.806 against a baking document, correct
passage first), but four gates block a drop-in corpus: front matter required; six required
fields; `domain` and `doc_type` are **hardcoded `Literal` sets** in `app/knowledge/models.py`;
`document_id` must equal the filename. The six MCP tools, the nine component names and the 49
evaluation questions do not transfer at all.

### Licence reversal (2026-09-18) — decision D.1

**The project grants no licence. Copyright reserved.** `LICENSE` (MIT) was added in `9854226`
and removed in the next commit, at the user's request: this is a demonstration project and is
not offered for reuse.

**What the removal does and does not do** — the user stated this correctly and it is recorded
so no future session re-adds a licence thinking it is a gap:

| | |
|---|---|
| Going forward | New clones carry no licence, so default copyright applies: nobody may reuse it without asking |
| **Not undone** | The MIT grant on commit `9854226` **cannot be retroactively revoked**. Anyone who took a copy while it was live keeps those rights for that version. Removing a file does not reach code already distributed |
| Exposure at the time | Repository is **public**; `9854226` was live roughly 30 minutes. **0 forks, 0 stars.** Clone traffic was not readable with the available token, so zero clones is likely but not proven — GitHub *Insights → Traffic* shows it |
| Deliberately not done | **No history rewrite.** Force-pushing `9854226` away would not revoke anything already granted, would break any existing clone, and would destroy the Stage 15 commit's parentage. The honest record is worth more than a cosmetically clean history |

> ⚠️ **For future sessions: the absence of a `LICENSE` file is intentional.** It is not an
> oversight to be "fixed". A documentation audit will flag it as missing; it should stay missing.

### Stage 15 — Final Engineering Review (2026-09-18, all tested)

Single reviewer, no sub-agents (`CLAUDE.md` §2). Full record: guide **§22**.

**Verified before changing anything:** 1396 passed / 4 skipped, ruff, format and mypy strict clean ·
37/37 settings in `.env.example`, no drift, README names no setting that does not exist · all five
documented CLIs run · index rebuilds to 115 chunks · all six documented URLs answer · live ask flow
returns 5 sources with citations · 422 allow-list, question limit and rate limit each fire · server log
carries a query fingerprint and length, never the question text · no import cycles · no secrets · no
nested directory · all 152 tracked files LF.

**Ten findings — eight fixed, two were decisions (15.A/15.B, above).**

| Finding | Fix |
|---|---|
| Dead code: `index_directory()` referenced by nothing | Deleted, with the `pathlib.Path` import that only typed it — `app/rag/pipeline.py` |
| **Money guard duplicated** — `_warn_if_paid` in both CLIs, wording already drifted | One `warn_if_paid` in `app/llm/factory.py` beside `PAID_PROVIDERS`; a test asserts both CLIs reference that same function object |
| `_retry_after` byte-identical in both adapters (it is HTTP, not vendor behaviour) | One `read_retry_after` in `app/llm/base.py` · 5 tests |
| `RULE = "=" * 78` in four modules | New `app/core/cli.py` |
| 15.A container log format | `BKA_LOG_FORMAT=json` in `Dockerfile` + `compose.yaml` · 2 tests |
| 15.B declared Python | `requires-python = ">=3.12"`, ruff `py312` · 3 tests |
| HANDOVER *Testing* table quoted Stage 13 numbers | Corrected to the measured run |
| HANDOVER said records `20.1–20.57` | Now `20.1–20.64` |
| HANDOVER pointed at a Stage 14 that had happened | Reworded |
| `.gitattributes` missed `*.toml` and `.gitignore` | Both added · existing test parametrised |

**Not changed, deliberately** (reasoning in guide §22.3): the adapters' `_translate` methods stay
parallel (they name different vendors' exception types); the six MCP tools' repeated shape is the
protocol being satisfied six times; `ValueError` stays for Pydantic validators, which require it;
the mock's question-matching quirk stays cosmetic; everything §16/§17 mark as production work.

**16 tests written first and watched to fail** before any code changed. New total **1412 passed, 4 skipped**.

### Stage 14 — what was built (2026-09-17, all tested)

| Item | Result |
|---|---|
| Production architecture doc | Guide **§17 rewritten** as *Production architecture*: local vs production diagrams + table, scaling, vector DB, LLM abstraction, MCP, service boundaries, deployment, observability, failure modes, data privacy, HA, "deliberately not built". README gets a short *Production Architecture* section |
| Carried 1 — LLM caps (14.C) | `LLM_TIMEOUT_MAX_SECONDS=120`, `LLM_MAX_RETRIES_MAX=3` in `app/core/config.py` · 5 tests |
| Carried 2 — host/port (14.A) | New `app/__main__.py` (`python -m app [--reload] [--no-access-log]`); Dockerfile `CMD ["python", "-m", "app", "--no-access-log"]` · `tests/test_server_entrypoint.py` (7) · container test updated to the new spec · **live-checked**: started on `BKA_PORT=8002`, `/health` 200 |
| Carried 3 — 422 echo (14.D) | New `app/api/errors.py` allow-list handler, registered in `create_app` · 4 tests · **live-checked**: 422 body has no `input` |
| Carried 4 — citations (14.B) | New `app/llm/citations.py` (moved from `app/eval/metrics.py`, shared); `LLMService._check_citations` → `LLMResponseError`; metric `llm_invalid_citations_total` · 6 tests |
| Carried 5 — `.gitattributes` | `*.js`, `*.css`, `Dockerfile`, `.dockerignore`, `.env.example`, `.gitattributes` → LF · `tests/test_repository.py` (10) |

**Tests changed because the spec changed — flag for review:**
- `test_container_config.py::test_the_server_binds_all_interfaces_from_settings` — now asserts `python -m app` (14.A) instead of shell `$BKA_HOST`.
- `test_eval_metrics.py::test_an_invented_citation_is_caught` and `test_eval_runner.py::test_an_invented_citation_fails_even_with_zero_floors` — assertions unchanged; they now use `UnguardedLLMService` (new, `tests/conftest.py`) because 14.B stops invented citations inside the service. New test pins that the real service stops the eval run.

**Consequence noted (guide §20.59):** a user question containing `[9]` that a model repeats is also withheld — accepted, fails safe. Exempting markers found in the question was **rejected** (14.F) — known limitation, documented.

**Review fix (14.E, 2026-09-17):** eval now scores a withheld answer as a failed `citations` check instead of stopping. Files: `app/llm/base.py`, `app/llm/__init__.py`, `app/llm/service.py`, `app/agent/agent.py`, `app/eval/metrics.py`, `app/eval/runner.py`; tests in `test_eval_runner.py` (3 replace the "stops the run" test), `test_agent.py` (1), `test_llm_service.py` (assertions extended).

**Other session work (not stage work):** a PR for `Zuleikha/production-llm-platform` branch `chore/security-dep-bumps` (anthropic SDK 1.6.0) **failed** — `gh` token lacks `createPullRequest` permission on that repo. Not retried.

---

**Stage 13 record (previous stage) follows.**

**Stage 13 — Security and Production Readiness (2026-09-16).**
Built with parallel sub-agents, at the user's request at kickoff. Shared contract frozen
first by the main session: `docs/stage13-contract.md`.

### Stage 13 decisions (13.A–13.F) — A–D at kickoff, E–F at integration, 2026-09-16 — guide §20.50–§20.55

| # | Decision |
|---|---|
| 13.A | **Optional shared API key.** `BKA_API_KEY` (SecretStr). When set, `/api/*` and `/metrics` require header `X-API-Key`; `/health`, `/ready` and the static page stay open. **`environment=production` refuses to start without it.** The web page gets a key box |
| 13.B | **In-process rate limiter** on `/api/*` — per client, fixed one-minute window, `BKA_RATE_LIMIT_PER_MINUTE`, `429` + `Retry-After`. No Redis; a shared store is a Stage 14 note |
| 13.C | **`off-006`/`off-007` refusal gap deferred** — documented as a known risk (retrieval quality, not a security control) |
| 13.E | **Unhandled 500 is sent by the middleware with `X-Request-ID`, then re-raised** (guide §20.54) — accepted at integration |
| 13.F | **Hard input limits:** question ≤ `BKA_QUESTION_MAX_CHARS` (2000), `session_id` ≤ 64 URL-safe, tool argument ≤ 256 (guide §20.55) |
| 13.G | **Docker `HEALTHCHECK` stays on `/health`** (liveness); `/ready` is for traffic routing — user, at approval (guide §20.56) |
| 13.H | **`--no-access-log` added to the runtime `CMD`** — uvicorn's access log bypassed redaction; the middleware already logs each request — user, at approval (guide §20.57) |
| 13.D | **`ruff format` the 24 files first**, before sub-agents run, so no agent edits an unformatted file. Proposed at commit time: a separate `style:` commit ahead of the Stage 13 commit (keeps guide §20.49's "one thing per commit") |

How it was built (contract, six sub-agents, interruption, integration): guide §21.8; step log in the archive.

### What Stage 13 built (all tested)

| Unit | Result |
|---|---|
| U1 Auth | `app/api/security.py` — `X-API-Key`, `hmac.compare_digest`, identical 401s, metric + reason-only log · web page key box (`sessionStorage`) · 29 tests |
| U2 Rate limit | `app/api/rate_limit.py` — per-client fixed window, thread-safe, pruned, 429 + `Retry-After`, runs before auth · 23 tests |
| U3 Readiness + input | `GET /ready` (manifest/header checks only; no model load, no network) · question length 422 · `session_id` ≤64 URL-safe · `EmbeddingError` → 502 · 42 tests |
| U4 Injection + MCP | fence tags escaped in any case/spacing · current question escaped · `MAX_ARGUMENT_CHARS=256` · unknown-tool calls counted · client-safe MCP errors · non-`ToolResult` caught · stale Stage 7 wording fixed · 56 tests |
| U5 Failures | 500 carries `X-Request-ID` (send, then re-raise — 20.54) · LLM error messages type+status only · malformed reply / `stop_reason=error` → `LLMResponseError` · 29 tests |
| U6 Secrets/logs/privacy/deps | `redact_sensitive_fields` structlog processor · `.dockerignore` secret patterns at any depth · 34 tests |

### Resolved carried items

Stage 10 item 4 (500 without request id) ✅ · Stage 10 item 6 (stale MCP wording) ✅ · 12.D `/ready` ✅ ·
12.H formatting ✅ · Stage 10 item 1 / Stage 13 `/metrics` auth ✅ · Stage 3 question logging (already
closed in Stage 10) ✅

Answered at approval: HEALTHCHECK → 13.G · access log → 13.H · two commits → 13.D.
Unanswered items → *Carried to Stage 14* (checkpoint, top of file).

### Stage 14 items recorded (guide §16)

Per-user identity (OAuth2/OIDC), session ownership, scopes · TLS · shared rate-limit store, proxy
`X-Forwarded-For` handling · secrets manager + rotation · request body size limit · circuit breaker,
provider fallback, request deadline · hashed lock file, digest-pinned base image, `pip-audit` + image
scan in CI · log retention, vendor DPA, PII detection · MCP network transport auth · adversarial
injection evaluation against a real model (paid — needs confirmation).

**Mock-only quirk (not fixed):** `app/llm/mock.py` `_QUESTION_PATTERN` matches the first line starting
`Question: `, so an earlier question beginning that way is echoed instead of the current one. Cosmetic.

Found at kickoff: the Stage 3 carried item "`retriever.py` logs the question text" is
**already resolved** — Stage 10 changed it to a fingerprint and a length.

### Still open from earlier stages (history moved to the archive)

| From | Item |
|---|---|
| Stage 11 | **`off-006`/`off-007` answered instead of refused** — deferred (13.C) · `know-018` evidence lacks `TransactionSwitch` · **paid mode never run** (needs confirmation) · free-mode mentions checked against evidence, not wording · same author wrote corpus, rules and dataset |
| Stage 10 | Metrics per-process, JSON not Prometheus → Stage 14 · untraced by deliberate exception (10.F): `Metrics`/`_Histogram` methods, `elapsed_ms`, `get_metrics`, `reset_metrics`, middleware internals |
| 12.G | `BKA_HOST`/`BKA_PORT` read by no app code (uvicorn flags only) |

Resolved in Stage 13: Stage 10 items 1 (`/metrics` auth), 4 (500 request id), 6 (stale MCP wording) · 12.D (`/ready`) · 12.H (formatting).

### Guide readability pass (plain English, `CLAUDE.md` §4)

§1–§19 done · §20 intro and Stage 3 records done (`889585d`) · **remaining: §20 Stage 4–6
records, then §21.** Stage 7–12 records were written to the standard when made.
Readability-only edits go in their own `docs(guide)` commit, never while another stage's
guide edits are uncommitted.

---

## Architecture

Full reference: **`docs/architecture-guide.html`** (§1 overview and diagram, §20 decision
records 20.1–20.64). Subsystem summaries: `README.md`.

```
User → Web Interface (9) → API/FastAPI (1) → Agent/LLM (4,5,7)
                                                 ├─▶ RAG retrieval      (2,3)
                                                 ├─▶ MCP tools          (6)
                                                 ├─▶ Conversation ctx   (8)
                                                 ├─▶ Observability      (10)
                                                 └─▶ Guardrails         (13) — rate limit → API key → input limits
                                              → Source-backed answer
```

Key properties, all load-bearing:

- **Seams are protocols, not ABCs** — `LLMProvider`, `Embedder`, `VectorStore`, `Tool`.
- **Two LLM adapters (Anthropic, OpenAI), no vendor chosen**; default provider `mock`.
- **The MCP registry is the source of truth**; `app/mcp/server.py` is a thin protocol wrapper over the same six tools.
- **Documents and tool results are untrusted input** — fenced, escaped, declared untrusted in the system prompt, question placed last outside the fence.
- **Containerised (Stage 12)** — model and index baked in, non-root, offline at runtime, `--no-access-log`.
- **Guarded (Stage 13)** — optional API key (required in production), per-process rate limit, `/ready`, input limits, log redaction. Full review: guide §16.
- **Reviewed (Stage 15)** — dead code removed, the money guard and the `Retry-After` reader deduplicated, container logs JSON (15.A), declared Python tightened to 3.12 (15.B).

---

## Files

Repository layout: `README.md` → *Repository Structure*. Orientation only:

| Path | Purpose |
|---|---|
| `app/core/` | Config (`BKA_*` settings), logging, tracing, observability |
| `app/rag/` | Chunker, embedder, vector store, retriever |
| `app/llm/` | Provider seam, prompts, service, mock + two adapters |
| `app/agent/` | Decision paths, policy, the agent loop |
| `app/mcp/` | Six synthetic tools, registry, MCP server |
| `app/conversation/` | Sessions, follow-up rules |
| `app/api/` | Routes (`/health`, `/ready`, `/metrics`, sessions), middleware, `security.py` (API key), `rate_limit.py` |
| `app/eval/` | Dataset, metrics, runner, scorecard CLI |
| `data/knowledge/` | 15 synthetic documents (in git) |
| `data/eval/questions.yaml` | 49 evaluation cases (in git) |
| `data/vectorstore/` | 115-chunk index — **git-ignored**, rebuilt by `python -m app.rag build` |
| `Dockerfile` · `compose.yaml` · `.dockerignore` | Stage 12 containerisation |
| `docs/stage13-contract.md` | The frozen contract Stage 13's sub-agents built against — the shape to reuse if a future stage runs sub-agents |

---

## Testing

| Command | Expected |
|---|---|
| `./.venv/Scripts/python.exe -m pytest` | **1412 passed, 4 skipped** (~115–180 s) |
| `./.venv/Scripts/python.exe -m ruff check .` | All checks passed! |
| `./.venv/Scripts/python.exe -m ruff format --check .` | 118 files already formatted |
| `./.venv/Scripts/python.exe -m mypy` | no issues in 76 source files |
| `./.venv/Scripts/python.exe -m app.eval` | Result: PASS (free, mock provider) |

The 4 skips are `tests/test_docker_smoke.py` — skipped unless `BKA_SMOKE_BASE_URL` is set.

> ⚠️ **Do not pass `-q` to pytest.** `pyproject.toml` already sets `-q` in `addopts`; a
> second one makes `-qq`, which silently suppresses the `N passed` summary line.

**Measured 2026-09-15** (real `all-MiniLM-L6-v2`, mock provider, k=5): recall@5 **1.000** ·
MRR **0.927** · path accuracy **0.959** (47/49) · citations 49/49 · median 12.9 ms/question.

**In Docker (re-measured 2026-09-18, Stage 15):** `docker build --target test -t bka-test .` then
`docker run --rm bka-test` → **1395 passed, 21 skipped, 0 failed**. The totals agree with the host
(1412 + 4 = 1395 + 21 = 1416); the extra 17 skips are the repository-hygiene tests that need a git
checkout (15.C), plus the 4 smoke tests. Live container via
`BKA_HOST_PORT=8001 docker compose up --build -d --wait` → healthy; smoke **4 passed**; a real ask
returned 5 cited sources; `/ready` ok. Verified **inside** the container: `BKA_LOG_FORMAT=json`
(15.A), `uid=999(app)` non-root, `HF_HUB_OFFLINE=1`, command `python -m app --no-access-log`.

> ⚠️ **Always pass `--build` to `docker compose up`.** Without it Compose reuses the existing
> `banking-knowledge-agent:local` tag: a Stage 12 image (still running `sh -c 'exec uvicorn…'`)
> came up *healthy* in this session and would have "verified" nothing.

**Host port 8000 is taken by another local project** — use `BKA_HOST_PORT=8001`.

---

## Problems and Decisions

### Environment — live, machine-specific

- **System `python -m venv` is BROKEN on this machine.** Use `uv venv .venv --python 3.12`, then `uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt`.
- **`pip` is not available inside the uv venv** — use `uv pip install --python .venv/Scripts/python.exe …`.
- **Never bare `python` or `pip`** — system Python lacks `structlog`, `torch`, `mcp`, etc., and fails at collection with misleading import errors.
- **`--basetemp=.pytest_tmp`** is load-bearing in `addopts`, not cosmetic. pytest's default temp root was created by an *elevated* process and locked the user's own non-elevated runs out with 96 `PermissionError`s. Residual risk: if a future run creates it under a token owned by Administrators the lockout can recur — now limited to one session, since pytest wipes the directory each run.
- A stale `.git/HEAD.lock` can block a commit — check for a running `git.exe` first.

> ⚠️ **Process lesson.** A green run inside the Claude Code session is not proof the suite
> passes for the user — elevation differs. State the context results were measured in.

### Dependency pins — do not drift

> ⚠️ **`mcp` must stay pinned at `1.12.4`.** Upgrading pulls `starlette>=1.0`, which breaks
> `fastapi==0.115.6` at *import* and takes the whole suite down at collection (6.B).

`sentence-transformers==5.7.0` and `torch==2.14.0` are pinned exactly; the Docker image
installs the same torch version from the CPU wheel index (12.B).

### Money guard — live

> 💸 **Spending is possible and guarded in four places.** `BKA_LLM_PROVIDER` defaults to
> `mock` (free). Setting it to `anthropic`/`openai` **and** setting `BKA_LLM_API_KEY` makes
> every answered question a **paid** call. **No live call has ever been made from this
> repository.**

✅ Default `mock` asserted by a test that clears the environment first · ✅ neither adapter
constructs without `BKA_LLM_API_KEY`, and neither falls through to `ANTHROPIC_API_KEY` /
`OPENAI_API_KEY` · ✅ every adapter test injects a fake client · ✅ both CLIs refuse a
multi-question `demo` against a paid provider without `--paid`.

### Security posture — after Stage 13 (full review: guide §16)

- ✅ `retriever.py` logs a question fingerprint and length, never the text (since Stage 10).
- ✅ `/api/*` and `/metrics` need `X-API-Key` when `BKA_API_KEY` is set; production refuses to start without it. `/health`, `/ready` open by design.
- ✅ Per-client rate limit, input limits, fence escaping (any case, current question too), log redaction, `--no-access-log` in the container.
- ✅ No secrets, keys or credentials anywhere; no real `.env`; `.env`/`.env.*` git-ignored (`.env.example` excepted).
- ✅ `logs/` and `data/vectorstore/` git-ignored; traced arguments never logged.
- ✅ Embedding runs **locally** — no document text or question leaves the machine.
- ✅ Corpus scanned by the suite for secret-shaped values and card-number-shaped digit runs.
- ✅ `yaml.safe_load` only; index load validates format, model, dimension, consistency.
- ✅ No nested `banking-knowledge-agent/` directory.

### Known limitations

- **Prompt quality is unproven.** Tests assert prompt *structure*, not that a real model answers well — no real model has run. `--paid` exists for this and has not been run.
- **The mock is a wiring check, not a language model.** It proves nothing about grounding under a real model, which is where hallucination happens.
- **Context budget is in characters, not tokens** — a deliberate over-approximation; revisit now that adapters exist.
- Retrieval is **dense-only**; hybrid (BM25 + vector) is the most likely next quality win.
- `data/vectorstore/` must be rebuilt after any document edit — `get_retriever()` does it automatically, `load_retriever()` refuses instead.

### Assumptions

- `CLAUDE.md` is the **sole authority** for rules and workflow; stage detail in `docs/PROJECT_PLAN.md`; `prompt.md` / `ccp.txt` archived unchanged in `docs/legacy/` (git-ignored).
- `@traced` on new functions, with documented exceptions for hot-path private helpers, Pydantic property accessors, and the observability internals (10.F).
- The embedding model downloads from Hugging Face on first use — a free public download, not a paid API call.

### Local files NOT in the remote (deliberately)

`docs/legacy/` · `ai-dev-token-efficiency-workflow.md` · `docs/decisions/auto-changes.log` ·
`.venv/` · `logs/` · `data/vectorstore/` · `.pytest_tmp/` · caches · `docs/HOW_TO_RUN.html`
(the user's personal run-through sheet — **not stage work, do not edit it as part of a stage**).

---

## Git

| | |
|---|---|
| **Branch** | `main` |
| **Remote** | `origin` → `https://github.com/Zuleikha/banking-knowledge-agent.git` |
| **Stage 15 commit** | `d738d6c` — `feat(stage-15): final engineering review - dedupe money guard, remove dead code, JSON container logs` — 22 files |
| **Stage 15 push** | ✅ `dc0b317..d738d6c`; verified `origin/main == local HEAD` |
| **Stage 14 commit** | `e38f967` — `feat(stage-14): production architecture - design doc, runtime citation check, safe 422s, python -m app` — 28 files | `bc9f69d` — `style: apply ruff format to the 24 files carried from Stage 12` — 24 files |
| **Stage 13 commit** | `e29bbae` — `feat(stage-13): security and production readiness - API key, rate limit, readiness, input limits, log redaction` — 37 files |
| **Stage 13 push** | ✅ `ed46ae1..e29bbae`; verified `origin/main == local HEAD` |
| **`HEAD`** | latest `docs(handover)` commit on top of `3e3b524` → `e29bbae` = `origin/main` |
| **Working tree** | Clean |

Earlier per-stage commit hashes: *Current Stage* table above, and
[`HANDOVER-archive.md`](HANDOVER-archive.md) → *Git* for the full list.

**Before every commit:** `git add -An` (dry run) — `git status` collapses untracked
directories and can hide what is really being staged. Never commit `.env`, keys, tokens or
credentials. Never commit or push an unapproved stage.

---

## Next Action

**Stage 15 — Final Engineering Review is approved, committed and pushed. The project is
complete.** All 15 planned stages are done; `docs/PROJECT_PLAN.md` defines no further work.

**Docker was verified in this session** (image rebuilt, suite run inside it, live container
checked) — so nothing is left outstanding except:
- **`--paid` has still never been run.** It needs explicit confirmation and costs money. This is
  the one claim the project cannot make about itself: no real model has ever answered a question
  here, so prompt quality remains unproven (see *Known limitations*).

If work resumes, it is new work, not a remaining stage. The most likely candidates are in guide
§18 (extension points) and §17 (production architecture, documented but deliberately not built).

The *Stage 14 items recorded* list and Stage 11/13 open items stay **documented as design**
in guide §17, not built — per the plan. Stage 15 judged them and left them (guide §22.3).

### To resume — run this before trusting anything in this file

```bash
cd <project-root>

git log --oneline -5        # expect d738d6c (stage 15) on top of dc0b317
git status --short          # expect clean

./.venv/Scripts/python.exe -m pytest        # expect 1412 passed, 4 skipped
./.venv/Scripts/python.exe -m ruff check .  # expect All checks passed!
./.venv/Scripts/python.exe -m mypy          # expect no issues in 76 source files
./.venv/Scripts/python.exe -m app.eval      # expect Result: PASS (free)

# Rebuild the index if data/vectorstore/ is missing (git-ignored)
./.venv/Scripts/python.exe -m app.rag build     # expect: Indexed 115 chunks

# See it working, entirely FREE (mock LLM, local embeddings)
./.venv/Scripts/python.exe -m app.agent demo
./.venv/Scripts/python.exe -m app.agent conversation-demo
./.venv/Scripts/python.exe -m uvicorn app.main:app   # http://127.0.0.1:8000/
```

---

## Constraints carried forward (all stages)

- Synthetic content only. No proprietary, confidential or copyrighted material.
- Documents and tool results are data, not instructions — untrusted LLM input. Reviewed in Stage 13 (guide §16); the current question is escaped too.
- No secrets in documents, tests, logs or this handover.
- **Never spend money or call a paid external API without the user's explicit confirmation.**
- Do not create a nested `banking-knowledge-agent/` directory.
- Approval cycle: IMPLEMENT → TEST → UPDATE HANDOVER → SHOW → **STOP** → APPROVAL → VERIFY → COMMIT → PUSH → VERIFY PUSH → NEXT STAGE. **Never commit an unapproved stage.** The only thing that lifts a stop is the literal word `APPROVED`.
