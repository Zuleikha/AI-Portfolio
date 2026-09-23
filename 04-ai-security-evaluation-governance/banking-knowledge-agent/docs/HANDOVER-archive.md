# HANDOVER — Banking Knowledge Agent
A decision is not recorded until it is written into docs/HANDOVER.md.
Do not let a decision live only in conversation history. 
If a decision is made mid-stage, before implementation begins, 
update HANDOVER.md immediately, not at stage completion.
> **Read this first in any new Claude Code session.**
> This file, not conversation history, is the record of project progress.
> Never assume a previous session completed work unless the repository confirms it.

Last updated: **2026-09-15, Stage 12 session** · **Stages 1–11 approved, committed and pushed.**
Stage 11 — Testing and Evaluation — `7b8c85e`. Chore `691c393` (`.gitattributes` LF, `.claude/` ignored).
**Stage 12 — Containerisation — ✅ APPROVED BY THE USER 2026-09-16 — committed `27739f2` and pushed**
(verified `origin/main == local HEAD == 27739f2`).

### Stage 12 — current state (supersedes the checkpoint table below until committed)

| | |
|---|---|
| Status | ✅ **Approved by the user 2026-09-16** — committed and pushed. Decisions 12.A–12.H recorded below (*Decisions made (Stage 12)*) and in guide §20.43–§20.49 |
| New files | `Dockerfile` (targets `runtime`, `test`) · `compose.yaml` · `.dockerignore` · `tests/test_container_config.py` (22 static contract tests) · `tests/test_docker_smoke.py` (4 tests, skipped unless `BKA_SMOKE_BASE_URL`) |
| Changed | `README.md` (Status, Requirements, new Docker section, Configuration note, Structure) · guide §15 rewritten as BUILT, §11 `/ready` → Stage 13, §20.43–§20.48 · this file |
| Local | `pytest` **1141 passed, 4 skipped** · ruff check clean · mypy strict clean (70 files) |
| In image | `docker run --rm bka-test` → **1141 passed, 4 skipped** (Linux, CPU torch `2.14.0+cpu`, no nvidia packages, user `app`) |
| Live container | `BKA_HOST_PORT=8001 docker compose up -d --wait` → **healthy**; smoke test **4 passed**; uid 999 `app`; `HF_HUB_OFFLINE=1`; provider `mock`; `app.log`/`traces.log` written to host `./logs` |
| Image size | runtime **2.24 GB** (deps layer 1.48 GB · model + index 92 MB · rest base); test image 2.35 GB |
| Found during the stage | (1) First in-image run failed 22 container tests: `.dockerignore` excluded the files they read — fixed by keeping them in the context and copying them only into the `test` target. (2) Host port 8000 is taken by another local project's container (`production-llm-platform-api-1`) — smoke run used `BKA_HOST_PORT=8001`; nothing stopped. (3) **Pre-existing:** `ruff format --check .` reports 24 files at HEAD (none touched by Stage 12) — not fixed; **decided 2026-09-16 (12.H) — left as-is, carried to Stage 13**. (4) `BKA_HOST`/`BKA_PORT` unused by app code (12.G) — Stage 13 candidate. (5) `docs/HOW_TO_RUN.html` (git-ignored, local) has no Docker section — not edited |
| Next | **Stage 13 — Security and Production Readiness**, when the user asks. Carried in: `GET /ready` (12.D) · `BKA_HOST`/`BKA_PORT` unused by app code (12.G) · `ruff format` on the 24 pre-existing files (12.H) |

**Rules live in `CLAUDE.md`** (sole authority). Stage requirements live in
`docs/PROJECT_PLAN.md` — read only the Stage 12 section. This file is state and decisions.

---

## ⏱️ SESSION CHECKPOINT — start here

**Session state (2026-09-16):** **Stage 12 — Containerisation — is APPROVED, committed and pushed.**
The user approved it on 2026-09-16 after the one open question — the 24 pre-existing `ruff format`
files — was answered: **leave them as they are, carry to Stage 13**, recorded as decision **12.H**
and guide **§20.49**. Before committing, the suite was re-verified (**1141 passed, 4 skipped**, ruff
and mypy clean), the guide status markers were set to Stage 12 (pill, footer, §1 table; the §1 diagram
was deliberately left alone — containerisation is not a component on the request path), and
`git add -An` confirmed exactly 9 files, no secrets, no nested directory, `.env` untracked.

*Previous:* **Stage 11 — Testing and Evaluation — approved by the user 2026-09-15**,
committed `7b8c85e` and pushed (verified). Chore `691c393` (LF `.gitattributes`, `.claude/`
ignored) was approved, committed and pushed at the start of the Stage 12 session.

### State at checkpoint

| | |
|---|---|
| Last **approved** stage | **Stage 12 — Containerisation** (approved 2026-09-16; hash in *Git*) |
| Current stage | **None in progress** — Stage 13 not started |
| `HEAD` | `27739f2` — Stage 12, on top of `691c393` (LF `.gitattributes`, `.claude/` ignored) = `origin/main` |
| Working tree | Clean, apart from git-ignored local files |
| Tests | **1141 passed, 4 skipped** · ruff clean · mypy strict clean (70 source files) · in-image pytest 1141 passed · container smoke 4 passed |
| Next | **Stage 13 — Security and Production Readiness** when the user asks. Carried in: `GET /ready` (12.D) · `BKA_HOST`/`BKA_PORT` unused by app code (12.G) · `ruff format` on the 24 pre-existing files (12.H) · Stage 11's `off-006`/`off-007` refusal gap and whether to run `--paid` |

### Commits made this session (2026-09-16, Stage 12 approval session), oldest first

| Commit | What |
|---|---|
| `27739f2` | **Stage 12 — Containerisation** (9 files: `Dockerfile`, `compose.yaml`, `.dockerignore`, 2 test files, `README.md`, guide, this file, `.gitignore`) |
| *(this commit)* | Handover: Stage 12 hash and push result |

### Commits made in the previous session (2026-09-15, Stage 10–11 session), oldest first

| Commit | What |
|---|---|
| `26592b6` | `CLAUDE.md` §2: steps for when a stage uses parallel sub-agents |
| `889585d` | Guide readability pass: §20 intro and Stage 3 decision records |
| `c627358` | **Stage 10** — observability (16 files) |
| `b633b15` | Handover: Stage 10 hash and push result |
| `42788e8` | Stage 10 follow-up — `httpx` logging to `warning` (10.E), untraced helpers recorded (10.F) |
| `25ebdc9` | Handover: follow-up hash and push result |
| `7b8c85e` | **Stage 11** — evaluation (16 files) |
| `86c2bd1` | Handover: Stage 11 hash and push result |
| `a99f5f7` | End of session: handover checkpoint, Stage 12 starting notes, README status, guide counts |
| `cecaf60` | `chore(gitignore)`: ignore local `docs/HOW_TO_RUN.html` (not stage work) |
| *(this commit)* | Handover refresh before Stage 12: `HEAD`, commit list, local files |

### Documentation-only changes after Stage 9 (2026-09-14, docs session) — no application code

| Commit | What |
|---|---|
| `85c849c` | Guide: Stage 8/9 status markers (header, footer, §1 ticks and table), stale claims corrected against the code, four terms explained. `CLAUDE.md` §4 gains three guide rules: accuracy against the code, status markers on stage commit, one editor at a time |
| *(this commit)* | **`README.md` restructured** to a fixed, concise shape (Status · Architecture · Stack · Requirements · Setup · Run · Test · one short section per subsystem · Configuration · Structure · Engineering Focus · Licence); stale content dropped (old stage diagram, "mock is the only constructible value", prompt v1.0.0, "six typed errors"). **New `CLAUDE.md` §4a README rule:** keep that structure; at the end of each stage update only the changed sections (Status, the relevant subsystem, Configuration, Repository Structure, test count); never grow it into a changelog |

**Every stage end:** update `README.md` per `CLAUDE.md` §4a — Status, the relevant subsystem
section, any new `BKA_*` variables under Configuration, Repository Structure, and the test count.

**Stale "Stage 7 … a model" docstrings:** the three carried ones were **fixed in Stage 10**
(`c627358`). Similar wording remains in `app/mcp/models.py` (`ToolSpec`, `input_schema`,
`ToolInvocation`) and `app/mcp/base.py` (module docstring, `ToolInputError`) — Stage 10
unfinished #6; fix in the next stage that touches `app/mcp/`, or a docs-only change.

**Guide readability pass (plain English, `CLAUDE.md` §4):** §1–§19 done; §20 intro and Stage 3
records done (`889585d`). Continues with the §20 Stage 4–6 decision records, then §21. Stage 7–10
records were written to the standard when made. Readability-only edits go in their own
`docs(guide)` commit, and never while another stage's guide edits are uncommitted.

**Open question (not a wording fix — needs a decision):** guide §11 lists `GET /ready`
(readiness: vector store and LLM reachable) as planned for **Stage 12**, but neither
`docs/PROJECT_PLAN.md` nor this file records that decision; the nearest plan item is Stage 13,
"Security and production readiness". Confirm the stage (or drop the row) when planning Stage 12/13.
**Resolved 2026-09-15 (Stage 12 decision 12.D):** `/ready` moves to **Stage 13**; guide §11 row updated.

### Commits made in the last session (2026-09-14, Stage 9 session), oldest first

| Commit | What |
|---|---|
| `ca5449c` | Handover: stale Stage 8 status fields corrected |
| `2484b73` | **Stage 9** — web interface |
| `4c2bc97` | Handover: Stage 9 hash and push result |
| *(this commit)* | Handover: end-of-session checkpoint and Stage 10 starting notes |

### Commits made in the session before (2026-09-14, Stage 8 session), oldest first

| Commit | What |
|---|---|
| `d47f522` | Instruction files restructured: `CLAUDE.md` (sole authority), `docs/PROJECT_PLAN.md` |
| `249f04e` | Guide readability pass §1–§5 (the separate improve.md session's edits) |
| `2abbb39` | **Stage 8** — conversation context |
| `9cd43c1` | Handover: Stage 8 hashes |
| `3fe5ea4` | `CLAUDE.md`: readability rule absorbed, `/usage` habit, archived path fixed |
| `0e04b77` | `.gitignore`: `docs/legacy/` |

### Stage 12 — starting notes (read before planning Stage 12)

`PROJECT_PLAN.md` Stage 12 = **Containerisation**: Dockerfile · Docker Compose where appropriate ·
environment configuration · health checks · local startup instructions. Must run locally with no
cloud infrastructure; synthetic data must remain available locally; **test the complete system
through Docker**; handover.

**What exists today (checked 2026-09-15):**

| Area | State |
|---|---|
| Docker on this machine | ✅ Docker **29.6.1**, Docker Compose **v5.2.0** installed |
| Docker files | None yet — no `Dockerfile`, `compose.yaml`, `.dockerignore` |
| App entry point | `uvicorn app.main:app` (FastAPI factory `create_app`); settings default `BKA_HOST=127.0.0.1` — a container must bind `0.0.0.0`; check whether uvicorn's `--host` or `BKA_HOST` is what actually applies |
| Health | `GET /health` (liveness, `app/api/routes/health.py`) and `GET /metrics`. **No `GET /ready`** — see the open question in *Documentation-only changes after Stage 9* (guide §11 lists it for Stage 12; the plan does not) |
| Heavy dependencies | `torch==2.14.0` (default wheel is large — a CPU-only wheel is a likely image-size decision), `sentence-transformers==5.7.0`, `uvicorn[standard]==0.34.0`; `mcp==1.12.4` and `fastapi==0.115.6` pins must hold (6.B) |
| Data | `data/knowledge/` (15 docs, in git) · `data/eval/questions.yaml` (in git) · `data/vectorstore/` **git-ignored**, built by `python -m app.rag build` (115 chunks); `get_retriever()` rebuilds a missing/stale index |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2`, ~90 MB, downloaded from Hugging Face on first use — needs network once |
| Logs | `BKA_LOG_DIR=logs`, file logging on by default; `.gitignore` covers `logs/` |
| Secrets | `BKA_LLM_API_KEY` from the environment only; default provider `mock` needs no key. A `.env` must never be copied into an image |

**Build method:** `CLAUDE.md` §2 marks Stage 12 ❌ for sub-agents — **single build**.

**Decisions Stage 12 will likely need (ask the user one at a time; record here and in guide §20 when made):**
1. **Model and index** — baked into the image at build time (offline at runtime, bigger image) ·
   downloaded/built at container start (smaller image, needs network, slow first start) · a volume.
2. **Image size** — CPU-only PyTorch wheel vs the default wheel; base image (e.g. `python:3.12-slim`).
3. **Compose shape** — one `app` service only · plus a one-shot index-build service · volumes for
   `logs/` and the index.
4. **Health checks** — Docker `HEALTHCHECK` on `/health` (slim images lack `curl`; a Python one-liner
   works) · and whether `GET /ready` is added here or left to Stage 13.
5. **"Test through Docker"** — run pytest inside the image · a smoke test against the running
   container (`/health`, one question via `/api/sessions`, `/metrics`) · both.
6. **Run as non-root** in the container (likely yes; confirm).

**Decisions made (Stage 12):**

| # | Decision | Why | Rejected |
|---|---|---|---|
| 12.A | **Model and index baked into the image** at `docker build`: download `all-MiniLM-L6-v2` and run `python -m app.rag build` in the Dockerfile (2026-09-15, user chose) | Container runs fully offline and starts fast; meets "no cloud infrastructure" and "synthetic data available locally"; index always matches the docs in the image | Fetch at container start (network needed on every fresh container, slow first start) · named volume (the index can go stale after the knowledge docs change) |
| 12.B | **CPU-only PyTorch on `python:3.12-slim`** (venv is 3.12.13; mypy `python_version = "3.12"`): install `torch==2.14.0` from PyTorch's CPU wheel index, same pinned version (2026-09-15, user chose) | Embedding runs on CPU; the default Linux wheel pulls in several GB of CUDA libraries the app never uses | Default wheel on slim (several GB larger) · default wheel on the full base image (largest) |
| 12.C | **`compose.yaml` = one `app` service**: port 8000, `BKA_LLM_PROVIDER` defaults to `mock`, `./logs` bind-mounted to the container's log directory (2026-09-15, user chose) | No index-build service needed (12.A); logs are readable on the host and survive container removal | One service with no mounts (logs lost with the container) · no Compose, `docker run` only |
| 12.D | **Docker `HEALTHCHECK` on `GET /health` only**, via a Python one-liner (slim has no `curl`). **`GET /ready` is not built in Stage 12** — moved to Stage 13; guide §11 row updated, which closes the open question above (2026-09-15, user chose) | Liveness is all the stage asks for; `/ready` is new app code the plan does not list for Stage 12 and fits Stage 13 "production readiness" | Adding `/ready` now (out of plan scope) · no `HEALTHCHECK` (Docker never reports unhealthy) |
| 12.E | **"Test through Docker" = both**: (1) full pytest suite inside the image, via a separate `test` build target that adds `requirements-dev.txt` on top of the runtime image (the runtime image carries no dev tools); (2) smoke test against the running Compose container on `mock`: `GET /health`, one question via `/api/sessions`, `GET /metrics`, container reports `healthy` (2026-09-15, user chose) | pytest-in-image proves the Linux image matches the venv; the smoke test proves port, env, mount and `HEALTHCHECK` work. Both free, no key | Smoke test only (Linux-only dependency breaks slip through) · pytest in image only (the running container is never checked) |
| 12.F | **Run as a dedicated non-root user** (`app`), which owns the model cache, the index and the log directory (2026-09-15, user chose) | A compromised app process gets no root inside the container; standard practice Stage 13 would otherwise flag | Root (image default) |
| 12.G | **Implementation choices (made during build, 2026-09-15):** (1) **Finding:** `Settings.host`/`port` (`BKA_HOST`/`BKA_PORT`) are read by nothing in `app/`; uvicorn's `--host`/`--port` are what apply. The image sets `BKA_HOST=0.0.0.0`, `BKA_PORT=8000` and the `CMD` passes them to uvicorn, so the settings mean something in the container; app code unchanged. (2) Smoke test is `tests/test_docker_smoke.py`, **skipped unless `BKA_SMOKE_BASE_URL` is set**, using an eval `knowledge_required` question. (3) Static contract tests `tests/test_container_config.py` pin 12.A–12.F. (4) `.dockerignore` excludes all of `docs/` and `*.md` (the image runs none of it). (5) `compose.yaml` carries no `BKA_LLM_API_KEY` at all. (6) `HF_HUB_OFFLINE=1` at runtime | (1) avoids a cross-module app change in a config stage; (2) the normal suite stays Docker-free; (5) nothing secret-shaped in a committed file; (6) proves 12.A — a missing baked model fails loudly instead of downloading | Wiring `BKA_HOST` into app code (out of Stage 12 scope — candidate for Stage 13) · a shell smoke script (not repeatable under pytest) · passing `BKA_LLM_API_KEY: ${BKA_LLM_API_KEY}` through compose |
| 12.H | **The 24 files `ruff format --check .` would reformat are left unchanged**; formatting them is carried to **Stage 13** (2026-09-16, user chose) | All 24 were already unformatted before Stage 12 and **none is a Stage 12 file** (verified 2026-09-16); reformatting 24 unrelated files would bury the containerisation diff, and `CLAUDE.md` Discipline says not to refactor outside the current task's scope. This is formatting only — `ruff check` (lint) is clean | Fixing them now in a separate `style` commit ahead of the Stage 12 commit |

**Constraints to carry in:**
- No paid LLM call without the user's explicit confirmation at the time. Container default stays `mock`.
- No secrets in the image or in `compose.yaml`; `.dockerignore` must exclude `.env`, `.venv/`, `logs/`,
  caches, `docs/legacy/`.
- `@traced` on every new non-route function, except hot-path helpers (10.F).
- Never log question text, answer text, tool argument values or raw session ids (10.A).
- README: add a short Docker section and update Run/Setup, Configuration, Repository Structure (`CLAUDE.md` §4a).
- Guide: the "PLANNED - Stage 12" section (containerisation) is the one to fill in; status markers on commit.
- Still open from Stage 11 (not Stage 12 work unless the user says so): `off-006`/`off-007` refusal gap;
  whether to run `python -m app.eval --paid`.

> 💸 **Spending is now possible and is guarded in four places.** `BKA_LLM_PROVIDER`
> defaults to `mock` (free). Setting it to `anthropic` or `openai` **and** setting
> `BKA_LLM_API_KEY` makes every answered question a **paid** call. No live call has ever
> been made from this repository.

### To resume — run this before trusting anything in this file

```bash
cd <project-root>

# 1. Confirm the repository matches this file
git log --oneline -3        # expect docs(handover) end-of-session on top of 86c2bd1, 7b8c85e feat(stage-11)
git status --short          # expect clean

# 2. If the venv is missing or stale (see "If the venv is missing" below)
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt

# 3. Re-establish the baseline
./.venv/Scripts/python.exe -m pytest        # expect 1119 passed (~78 s)
./.venv/Scripts/python.exe -m ruff check .  # expect All checks passed!
./.venv/Scripts/python.exe -m mypy          # expect no issues in 70 source files
./.venv/Scripts/python.exe -m app.eval      # expect Result: PASS (free; mock provider)

# 4. Rebuild the vector index if data/vectorstore/ is missing (it is git-ignored)
./.venv/Scripts/python.exe -m app.rag build     # expect: Indexed 115 chunks

# 5. See Stages 6-9 working, entirely FREE (mock LLM, local embeddings)
./.venv/Scripts/python.exe -m app.agent demo               # routes, RAG + MCP
./.venv/Scripts/python.exe -m app.agent conversation-demo  # 7 turns, all follow-up rules
./.venv/Scripts/python.exe -m uvicorn app.main:app         # then open http://127.0.0.1:8000/
                                                           # and http://127.0.0.1:8000/metrics

# 6. Then read "Stage 12 — starting notes" above and "Next Action" at the bottom.
```

> ⚠️ **`mcp` must stay pinned at `1.12.4`.** Upgrading it pulls `starlette>=1.0`, which
> breaks `fastapi==0.115.6` at import and takes the entire suite down at collection.
> See *Stage 6 decisions* §6.B.

> If the venv is missing, recreate it per the Stage 4 instructions below — note that
> `requirements.txt` now also installs `anthropic`, `openai` and `mcp` (small pure-Python
> packages; the large artefact is still PyTorch).

### Stage 5 is split into two approval checkpoints

| | Scope | Status |
|---|---|---|
| **Checkpoint A** | The knowledge agent itself (`prompt.md` §13), tested entirely against `MockLLMProvider`. No vendor involved | ✅ **Approved 2026-09-10, committed `1478631`, pushed** |
| **Checkpoint B** | Two concrete adapters — `AnthropicProvider` **and** `OpenAIProvider` — offline-tested, default still `mock` | ✅ **Approved 2026-09-10, committed `6ebe947`, pushed** |

**Stage 5 is therefore complete and fully approved.** Next stage: **Stage 6 — MCP tools**
(`prompt.md` §14). It has **not** been started, and must not be started without the
user's instruction.

### To resume

```bash
cd <project-root>

# 1. Confirm the state matches this file before trusting it
git log --oneline -3          # expect docs(stage-4) on top of bee4b22
git status                    # expect clean

# 2. Re-establish the baseline
./.venv/Scripts/python.exe -m pytest        # expect 385 passed
./.venv/Scripts/python.exe -m ruff check .  # expect All checks passed!
./.venv/Scripts/python.exe -m mypy          # expect Success: no issues found in 29 source files

# 3. Rebuild the vector index if data/vectorstore/ is missing (it is git-ignored)
./.venv/Scripts/python.exe -m app.rag build     # expect: Indexed 115 chunks

# 4. See Stage 4 working, entirely offline
./.venv/Scripts/python.exe -m app.llm demo      # 5 grounded answers + 1 refusal
./.venv/Scripts/python.exe -m app.llm prompt "What component handles card authentication?"

# 5. Then read "Next Action" at the bottom of this file.
```

> ⚠️ **If the venv is missing**, recreate it — system `python -m venv` is BROKEN on this
> machine (Problems §4):
> ```
> uv venv .venv --python 3.12
> uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
> ```
> This now installs PyTorch (~250 MB). The first `app.rag build` also downloads the
> ~90 MB embedding model from Hugging Face and needs network access; later runs use the
> local cache.

### Local files that are NOT in the remote (deliberately)

`docs/legacy/prompt.md` · `docs/legacy/ccp.txt` · `prompt1.md` ·
`ai-dev-token-efficiency-workflow.md` · `docs/decisions/auto-changes.log` · `.venv/` · `logs/` ·
`data/vectorstore/` · caches · `docs/HOW_TO_RUN.html` (the user's personal run-and-click-through
cheat sheet; not stage work — do not edit it as part of a stage). Verified 2026-09-15: none of these
has ever been committed.

---

## Current Stage

| | |
|---|---|
| **Stage number** | 12 |
| **Stage name** | Containerisation |
| **Status** | ✅ **APPROVED BY THE USER 2026-09-16 — committed and pushed** (hash in *Git*) |
| **Last completed step** | Re-verified after approval: 1141 passed / 4 skipped, ruff and mypy clean, `git add -An` = 9 files, no secrets, no nested directory, `.env` untracked. Guide status markers updated (pill, footer, §1 table; §1 diagram unchanged — containerisation is not on the request path) |
| **Next step** | Stage 13 — Security and Production Readiness — begins when the user asks. See *Next Action* |

| Stage | Name | Status |
|---|---|---|
| 11 | Testing and Evaluation | ✅ Approved 2026-09-15, committed `7b8c85e`, pushed |
| 10 | Observability | ✅ Approved 2026-09-15, committed `c627358` (+ follow-up `42788e8`), pushed |
| 9 | Web Interface | ✅ Approved 2026-09-14, committed `2484b73`, pushed |
| 8 | Conversation Context | ✅ Approved 2026-09-14, committed `2abbb39`, pushed |
| 7 | Agent Decision and Tool Selection | ✅ Approved 2026-09-14, committed `a3728d9`, pushed |

| Stage | Name | Status |
|---|---|---|
| 6 | MCP Tools | ✅ Approved 2026-09-11, committed `93eeb22`, pushed |

### Previous stage

| | |
|---|---|
| **Stage number** | 5 |
| **Stage name** | Knowledge Agent + concrete LLM adapters |
| **Status** | ✅ **COMPLETE AND APPROVED — both checkpoints committed and pushed** |
| **Last completed step** | Checkpoint B approved 2026-09-10; committed `6ebe947` and pushed to `origin/main`, push verified |

> ⛔ Each Stage 5 checkpoint must STOP after implementation and testing, and wait for
> explicit approval before any commit or push. Checkpoint B must not begin until
> Checkpoint A is approved.

### Previous stages

| Stage | Name | Status |
|---|---|---|
| 1 | Project Foundation | ✅ Approved 2026-09-03, committed `d448cc1`, pushed |
| 2 | Domain Knowledge | ✅ Approved 2026-09-08, committed `cca70af`, pushed |
| 3 | RAG Pipeline | ✅ Approved 2026-09-09, committed `be9297c`, pushed |
| 4 | LLM Abstraction | ✅ Approved 2026-09-09, committed `bee4b22`, pushed |

---

## Stage 5 decision — the concrete LLM provider (previously deferred, now RESOLVED)

**Decided by the user, 2026-09-10.** This resolves the question left open at the end of
Stage 4 (*"which vendor, and is a live key ever wired in?"*) and supersedes the
"decision required before Stage 5" note that previously stood in *Next Action*.

| | |
|---|---|
| **How many adapters** | **Two, not one** — `AnthropicProvider` and `OpenAIProvider` |
| **Which vendor is "the" vendor** | **None.** No vendor is exclusively chosen; the seam is proved rather than asserted |
| **Default provider** | **`mock`, unchanged.** Nothing calls a real API unless someone deliberately sets `BKA_LLM_PROVIDER` |
| **API key** | `BKA_LLM_API_KEY` stays environment-only, optional, **unset**. Not wired in, not hardcoded, not committed |
| **Live calls** | **None.** No live call in Checkpoint A, in Checkpoint B, in the test suite, or by hand. Building two adapters does **not** authorise a live call, now or later |
| **Adapter tests** | Offline — the SDK client / HTTP layer is mocked. No network, no cost, in CI or locally |
| **The AST guard** | **Narrowed, not deleted.** `base.py` · `prompts.py` · `service.py` · `factory.py` · `mock.py` must stay vendor-free; only the two adapter modules are exempt |

**Why two adapters rather than one.** One adapter proves an adapter can be written. Two
prove the *abstraction* — that a vendor swap is a configuration change and nothing else.
It also retires the vendor question permanently instead of re-litigating it at Stage 9 or
Stage 14. Full record with rejected alternatives goes in
`docs/architecture-guide.html` §20.6.

> ⚠️ This reverses the Stage 4 rejected-alternative *"Two adapters, to 'prove' the seam"*
> (guide §20.4.1), which was rejected on the grounds that a second implementation means a
> second paid vendor account. That objection does not survive the "no live call" rule:
> both adapters are offline-tested, so neither requires an account. Recorded because the
> file must show what was reversed, not only what was decided.

---

## Stage 6 decisions — recorded BEFORE implementation began

**Decided by the user, 2026-09-11**, in the kickoff instruction and one clarifying
question. Written here before any Stage 6 code existed, per `prompt.md` §2: *"If a
decision is made mid-stage, before implementation begins, update HANDOVER.md
immediately."*

### 6.A — MCP depth: build BOTH layers

The kickoff said *"Introduce MCP"*, which admits two materially different builds. The
question was put to the user explicitly and answered.

| | |
|---|---|
| **In-process tool layer** | ✅ Built. `app/mcp/registry.py` — the thing `KnowledgeAgent` talks to directly. Fast, offline, deterministic |
| **Real MCP protocol server** | ✅ Built. `app/mcp/server.py` — the official `mcp` SDK over stdio, exposing the **same six tools through the same registry** |
| **Which is the source of truth** | The registry. The server is a thin protocol wrapper, not a second implementation of the tools |
| **Which the test suite targets** | The registry — the full suite, same standard as Stages 3–5. The server gets a small number of protocol-level smoke tests only |
| **Rejected** | A mock-only / MCP-shaped-but-not-MCP layer. It would have been cheaper and entirely defensible in the code, but "we implemented an interface that looks like MCP" is a materially weaker claim than "we ran the protocol" — and the protocol is the part with the surprises in it |

### 6.B — Dependency resolution: `mcp` had to be pinned DOWN, not up

Found while installing, before any tool code was written. Recorded because it is a real
constraint on this repository, not an anecdote.

- `uv pip install mcp` resolves to **`mcp==2.2.0`**, which requires `starlette>=1.0`.
- That upgrade **breaks `fastapi==0.115.6`**: `TypeError: Router.__init__() got an
  unexpected keyword argument 'on_startup'` — raised at *import* of `app.main`, so the
  entire 601-test suite fails to collect, not merely the health tests.
- Resolving `mcp` **against the existing pins** instead yields **`mcp==1.12.4`**, which is
  compatible with `starlette==0.41.3` and `pydantic==2.10.4`. Suite re-verified with it
  installed: 601 passed, unchanged.
- **Decision: pin `mcp==1.12.4`.** Upgrading FastAPI to chase the newest MCP SDK was
  rejected — that is a Stage 1 infrastructure change smuggled into Stage 6, and Stage 6
  has no requirement the newer SDK satisfies.
- The failed `mcp==2.2.0` attempt also left six orphan packages in `.venv`
  (`mcp-types`, `cryptography`, `pyjwt`, `opentelemetry-api`, `pycparser`,
  `typing-inspection`); they were uninstalled so the venv matches `requirements.txt`.

### 6.C — The shared tool contract, written by the main session before any sub-agent ran

This is the one piece of shared state in Stage 6, so it was written **once, first, by the
main session**, and every sub-agent was handed it as a fixed input rather than asked to
agree on one.

| Contract point | Decision | Why |
|---|---|---|
| **Tool seam** | A `Tool` **protocol** (`app/mcp/base.py`), not an ABC | Same choice as `LLMProvider`, `Embedder` and `VectorStore`. A tool qualifies structurally; a test double needs no inheritance |
| **Error taxonomy** | `ToolError` base carrying `retryable`, plus `ToolNotFoundError`, `ToolInputError`, `ToolExecutionError`, `ToolUnavailableError` | Mirrors Stage 4's LLM taxonomy deliberately, including the "no silent fallback" rule |
| **"Not found" is data; "malformed" is an error** | An unknown transaction id / error code / component returns `ToolResult(ok=False, error_code=…)`. A missing or malformed *argument* raises `ToolInputError` | A question about a transaction that does not exist is a legitimate question with a legitimate answer. A caller that omits a required argument has a bug. Collapsing the two would either hide the bug or turn an ordinary answer into an exception |
| **Arguments are `Mapping[str, str]`** | Every tool argument is a string | Every argument this domain has is an identifier, a code or a config key. Stage 7 will have an LLM emitting these, and an LLM emits strings; a richer type would only move the parsing somewhere less testable |
| **Deterministic synthetic clock** | `SYNTHETIC_OBSERVED_AT`, one fixed instant, stamped on every result | The data is synthetic; a real `datetime.now()` would make every assertion non-deterministic for no benefit. Honest and testable beats realistic and flaky |
| **Each tool owns its own synthetic dataset** | No shared fixture module | This is precisely what made the six tools independent and therefore parallelisable. The cost is duplicated component names across modules — accepted knowingly, and it is the friction discussed in 6.E |

### 6.D — Tool results are untrusted input, and reuse Stage 4's defence

Carried forward from Stage 4 and required by the kickoff. **No second defence scheme was
invented.** `app/llm/prompts.py` already fences, escapes and declares retrieved passages
untrusted; Stage 6 extends that same machinery to tool results:

- a second fence, `<tool_results>` … `</tool_results>`, rendered beside the existing
  `<retrieved_documentation>` block;
- the **same** `_fence_safe` escaping, extended to cover the new delimiters, so a tool
  result containing a literal closing tag cannot break out of its fence;
- the system prompt gains a rule naming the tool fence as untrusted data, and a rule
  distinguishing **documentation** (how the platform is designed) from **live tool
  results** (what it is reportedly doing now).
- `SYSTEM_PROMPT_VERSION` therefore bumps **`1.0.0` → `1.1.0`**.

### 6.E — Build methodology: six parallel sub-agents, one per tool

Chosen deliberately by the user as an exercise in agentic engineering, and recorded here
as an architectural decision because it shaped the module layout.

| | |
|---|---|
| **What the main session did first** | Wrote the entire shared contract (6.C): `models.py`, `base.py`, `registry.py`. Nothing was delegated until the interface was frozen |
| **What each sub-agent received** | A self-contained brief: the frozen contract verbatim, the synthetic-data-only rule, the corpus facts its tool had to stay consistent with, its own single file to write, and an explicit instruction to touch no other file |
| **How many ran in parallel** | Six, one per tool, dispatched in a single batch |
| **What the main session did afterwards** | Integration: registration, cross-tool consistency, the agent/prompt/policy wiring, and every test that spans more than one tool |
| **Why this stage suited it** | Six genuinely independent tools, no shared state until registration, and a contract that could be frozen up front. That combination is rarer than it sounds |
| **Why the agent's own decision logic was NOT delegated** | It is shared state throughout — `policy.py`, `models.py`, `agent.py` and `prompts.py` all had to change together and agree. Parallel sub-agents there would have produced four reasonable, mutually incompatible designs |
| **Rejected** | One sub-agent for all six tools (no parallelism, and no test of whether the contract was clear enough to hand over); and delegating the contract itself (it is the shared state — the one thing that must have a single author) |

Integration friction actually encountered is recorded in *Stage 6 — integration notes*
below, and explained at length for future reference in
`docs/architecture-guide.html` §21.

### 6.F — `DecisionReason` is extended, not replaced

Stage 5 left `DecisionReason` with two values and a docstring saying Stage 6 would extend
it. It is extended rather than joined by a parallel tool-decision type, on the user's
explicit instruction and for the reason Stage 5 gave: one question produces **one**
routing decision, and two decision objects would be two things that must agree about the
same question.

---

## Stage 7 decisions — recorded BEFORE implementation began

**Decided by the user, 2026-09-14**, in the kickoff instruction and one clarifying
question. Written here before any Stage 7 code existed, per `prompt.md` §2.

### 7.A — Kickoff constraints (the user's instruction, verbatim in substance)

| | |
|---|---|
| **Scope** | `prompt.md` §15: choose between answer-from-knowledge, retrieve-more, call a tool, use both, refuse. Expose the decision, not chain-of-thought: retrieval performed, documents used, tool used, tool result, final answer |
| **Build on Stage 6, don't rebuild** | `DecisionReason` is **extended**, not replaced. `tool_policy.py`'s identifier rule is **replaced by a real selector**, not patched. `AgentAnswer` gains decisions; its existing fields are not re-plumbed |
| **Build method** | **Single cohesive decision logic. No parallel sub-agents** — the opposite of Stage 6 §6.E, for the reason §6.E itself gave: the decision logic is shared state |
| **Paid calls** | A live LLM call still needs explicit confirmation given separately at the time. This instruction does not imply it |
| **Tests** | One test per decision path, at minimum |
| **Docs** | Handover updated before any commit, mid-stage decisions included. Tool-selection reasoning in `docs/architecture-guide.html` §20 (chosen / rejected / why) |
| **Tooling (§18)** | Always `./.venv/Scripts/python.exe -m pytest` / `-m ruff check .` / `-m mypy`. Never bare `python` or `pip` |
| **Stop** | After implementation and tests. No commit or push without explicit approval |

### 7.B — The tool selector: RULES ONLY, spec-driven

The question was put to the user explicitly with three options and answered.

| | |
|---|---|
| **Chosen** | A deterministic `ToolSelector` protocol with **one** implementation, a rule selector that is driven by the registry's `ToolSpec`s rather than a hardcoded tool table. Free, offline, deterministic, fully testable |
| **Rejected — LLM-only selector** | Every question becomes an extra model call, which is a **paid** call in real use, and routing becomes non-deterministic and untestable without a provider |
| **Rejected — both (rules default + LLM selector behind a setting)** | Offered as the recommended option and declined. Recorded honestly: the LLM selector could only have been proven against the mock, i.e. proven to parse, not to choose well |
| **Where the reasoning is recorded** | `docs/architecture-guide.html` §20 (Stage 7 records) |

### 7.C — Design, decided mid-stage BEFORE implementation (2026-09-14)

Written after reading the Stage 6 code and **measuring** the real embedding model (free,
local), before any Stage 7 code.

**Measured evidence** (real `all-MiniLM-L6-v2`, real corpus, floor 0.25):

| Question | Passages | Top | Rank-1 document |
|---|---|---|---|
| What does limits.atm.velocity_window_minutes do? | 5 | 0.717 | transaction-limits-configuration ✅ |
| Is CoreBankingAdapter healthy? | 5 | 0.641 | core-banking-integration ✅ |
| What does LIM-4001 mean? | 5 | 0.573 | platform-component-overview |
| What version is CardSecurityModule running? | 5 | 0.492 | error-code-reference ❌ |
| What is the status of transaction TXN-20260911-004473? | 5 | 0.462 | error-code-reference |
| Status of TXN-19990101-000001? | 5 | 0.365 | error-code-reference |
| COR-5015 | 3 | 0.340 | error-code-reference |
| What is the capital of France? | 0 | — (raw 0.086) | — |
| *LIM-4001? → + "LimitService"* | 5 | 0.557 → **0.674** | error-code-reference |
| *SWX-7001 → + "TransactionSwitch"* | 5 | 0.425 → **0.630** | error-code-reference |

Identifier-heavy questions clear the floor but rank weakly; appending the component a
tool names lifts the top score by ~0.1–0.2. A component **filter** cannot help: it only
removes passages, so it can never raise a score above the unfiltered pass.

**The decision paths** — `DecisionReason` extended from 3 to 6 values:

| §15 path | `DecisionReason` | Retrieve | Tools |
|---|---|---|---|
| Answer from knowledge | `knowledge_required` *(kept)* | 1 pass | — |
| Retrieve additional knowledge | `additional_knowledge_required` *(new)* | 2 passes | — |
| Call an MCP tool | `live_status_only` *(new)* | — | ✅ |
| Use both | `knowledge_and_live_status_required` *(kept)* | 1–2 passes | ✅ |
| Refuse — nothing to search | `no_searchable_content` *(kept)* | — | — |
| Refuse — evidence insufficient | `insufficient_evidence` *(new)* | ✅ | — |

**The rules** (all deterministic, no model call):

1. **Plan.** No alphanumeric character → `no_searchable_content`. Else the selector
   proposes tool calls. No calls → knowledge. Calls **and** the question asks for an
   *explanation* (why / how / mean / cause / troubleshoot / fix / default …) → both.
   Calls and it asks only for a *reading* → `live_status_only`, no retrieval.
2. **A tool that finds nothing pulls in documentation.** If a `live_status_only` plan
   gets any `ok=False` result, the agent searches the documentation too (final route:
   both). Guards the costly direction of a form-classifier mistake.
3. **Retrieve more** when a search ran **and** its top score is below
   `BKA_AGENT_CONFIDENT_SCORE` (default **0.50**, from the table above) **and** a
   refinement exists: a component named by a selected tool call or by a successful tool
   result, not already in the question. Second query = question + component(s); passes
   merged by chunk id, best score kept, capped at `retrieval_top_k`. No refinement → no
   second pass (an identical re-search is pointless).
4. **Refuse** through Stage 4's single guard, unchanged: no passage and no tool result.
   The final reason becomes `insufficient_evidence`.

**The selector** (`app/agent/tool_policy.py`, rewritten, not patched): a `ToolSelector`
protocol and `RuleToolSelector`, built from `registry.specs()`. Argument extractors are
keyed by **parameter name** (`error_code`, `transaction_reference`, `key`, `component`),
not by tool. A tool is callable when all its *required* parameters are extracted and at
least one argument was found; tools that share an argument (the three component tools)
additionally need a question-form cue. A registered tool with a parameter no extractor
understands **raises at construction** — a tool the selector cannot reach must be loud.
`select_tools()` is removed.

**The record.** `AgentAnswer.decision` becomes the **final** route (what actually ran).
New `AgentAnswer.decisions: tuple[DecisionStep, ...]` — the ordered choice points
(`plan`, `consult_documentation`, `retrieve_more`, `evidence`), each with a fixed
outcome and a fixed sentence. Rules' outcomes, not reasoning prose: no chain-of-thought.
`RetrievalSummary.passes` (0, 1 or 2) added.

### 7.D — Refinement for knowledge-only questions: pseudo-relevance feedback (measured)

Rule 3 as first written could never fire on a knowledge-only plan: with no tool call,
nothing names a component. Resolved **by measurement**, before code:

| Weak question (real model) | Top | + component of best documented passage | Top after |
|---|---|---|---|
| Why did the withdrawal reverse? | 0.490 | TransactionSwitch | **0.640** |
| PIN? | 0.421 | AuthorizationService | **0.601** |
| What caused that failure? | 0.489 | TransactionSwitch | **0.651** |
| COR-5015 | 0.340 | TransactionSwitch | **0.515** |
| What does SWX-7004 mean? | 0.442 | TransactionSwitch | **0.603** |
| What is the capital of France? / sourdough | — | *0 passages → nothing to expand* | refused ✅ |

**Rule 3, final.** Refinement terms, in priority order: (a) components named by the
selected tool calls or by **successful** tool results (max 2); else (b) the component of
the **highest-ranked passage that cleared the floor** whose component is a documented
component (`Platform` is skipped). If that component is already named in the question
there is nothing to add and no second pass runs. Every term must be a member of the
documented component vocabulary, so tool-payload text can never reach a search query or
the `rag.retrieved` log line. Exactly **one** second pass, never a loop.

Off-topic questions are protected by construction: (b) only reads passages that already
cleared the calibrated 0.25 floor, and an off-topic question has none.

**Test impact, recorded before it happens.** The hashing embedder the offline suite uses
tops out at 0.31–0.46, below 0.50, so two Stage 5 wiring tests (`test_the_question_is_
passed_to_the_retriever_verbatim`, `test_one_question_triggers_exactly_one_retrieval…`)
would see a second pass. Their guarantee is really "a *confident* first pass is one
retrieval"; they are given `agent_confident_score=0.0` and say so. The second-pass
behaviour itself is tested in the new `tests/test_agent_decisions.py`.

**One contract changes, deliberately.** Stage 6 raised `RuntimeError` when an agent
without a registry was handed a tool question. With a spec-driven selector an agent with
no registry has **no tools to select**, so that question is answered from documentation
exactly as in Stage 5. A selector passed *without* a registry still raises, at
construction. The Stage 6 test is rewritten to assert the new contract — a design change,
not a test edited to pass.

---

## Stage 8 decisions — recorded BEFORE implementation began

**Decided by the user, 2026-09-14**, in the kickoff instruction and one clarifying
question. Written here before any Stage 8 code existed, per `prompt.md` §2.

### 8.A — Kickoff constraints

| | |
|---|---|
| **Scope** | `prompt.md` Stage 8: session handling, context management, context limits, separation of conversation context from retrieved knowledge, follow-up tests. Avoid sending unnecessary history to the LLM. Guide + handover updated |
| **Build method** | **Single cohesive build. No parallel sub-agents** (user's instruction) |
| **Reconciled state** | HEAD `1d7d6c3` (Stage 7 docs commit) = `origin/main`. Stage 7 approved. Working tree carries the separate readability session's uncommitted guide edits (+187/−66) and untracked `docs/improve.md` — **not Stage 8's**; see Problems §20 |
| **Paid calls** | None. Stage 8 adds no model call: follow-up resolution is rule-based, like Stage 7 |
| **Stop** | After implementation and tests. No commit or push without explicit approval |

### 8.B — What the LLM sees from earlier turns: PAST QUESTIONS ONLY

The question was put to the user with three options and answered.

| | |
|---|---|
| **Chosen** | A follow-up is rewritten by deterministic rules (e.g. carries `LIM-4001` forward) so tools and search work on it. The LLM additionally receives the last few **past questions** in their own fence, `<conversation_history>`, declared **not evidence**. **Past answers are never sent** |
| **Rejected — past questions + answers as real message turns** | Most natural for a chat model, but a previous answer would read as evidence, and its `[1]` citations point at passages that are no longer in the prompt and clash with the new numbering |
| **Rejected — rewritten question only, no history** | Smallest prompt, but the model cannot see what "it" referred to except through the rewrite |

### 8.C — Design (decided before implementation)

- **New package `app/conversation/`** — it *wraps* `KnowledgeAgent`; the agent stays a
  single-question component and does not import the conversation layer. The agent gains
  one appended parameter, `ask(question, history=())`, which it passes to `LLMService`.
- **Session store** — `SessionStore` protocol + `InMemorySessionStore`: random
  `secrets` ids, idle TTL, a cap on sessions (least-recently-used evicted), a cap on stored
  turns per session (oldest dropped), an injectable clock for tests, a lock for Stage 9's
  threaded server. An unknown or expired id **raises** `SessionNotFoundError` — never a
  silent new session.
- **Follow-up resolution (rules, no model)** — reuses Stage 7's argument extractors
  (error code, transaction reference, config key, component). Only earlier **questions**
  are read, never answers or tool payloads, so no generated or untrusted text can be
  carried into a search query:
  1. *Standalone* — first turn, or the question names its own identifiers → unchanged.
  2. *Substitution* — an elliptical "what about / how about / and / same for X?" naming
     one identifier of the same kind the previous question had → the previous question
     with that identifier swapped.
  3. *Carried identifiers* — a reference word (it, that, this, they, …) and no identifier
     of its own → identifiers from the **previous** question (as resolved) are appended,
     at most 3.
  4. *Carried topic* — a reference word, and the previous question has no identifiers →
     the previous turn's *topic* (its standalone question) is appended. A turn stores its
     topic, so a chain of topic follow-ups never grows the query.

  > **Refined mid-stage, before code (2026-09-14):** rules 3–4 first said "the most recent
  > earlier question in the window". Tracing the demo showed "what should I check first on
  > that?" after a withdrawal question would carry a component from two turns back. "It"
  > refers to the latest thing, so both rules read the previous turn only; the window
  > bounds the history *sent*, not what is carried.
- **Context limits** — `BKA_CONVERSATION_MAX_HISTORY_TURNS` (window, default 3) and
  `BKA_CONVERSATION_MAX_HISTORY_CHARS` (default 1000; oldest questions dropped **whole**,
  like passages). Plus store limits `BKA_CONVERSATION_MAX_TURNS`,
  `BKA_CONVERSATION_MAX_SESSIONS`, `BKA_CONVERSATION_TTL_SECONDS`.
- **Unnecessary history is not sent** — a *standalone* question gets **no** history
  block at all. History goes to the LLM only when the question was resolved from it.
- **Separation from knowledge** — history has its own fence, escaped by the **same**
  `_fence_safe` and `_DELIMITERS`; a system-prompt rule says it is not evidence and must
  never be cited. History does **not** count as evidence for Stage 4's refusal guard: a
  follow-up with no passage and no tool result still refuses with zero model calls.
  `SYSTEM_PROMPT_VERSION` `1.1.0` → `1.2.0`.
- **The record** — `ConversationAnswer` = session id, turn number, the unchanged
  `AgentAnswer`, and a `ContextSummary` (resolution kind, carried identifiers, history
  questions sent / dropped). Logged: resolution kind and counts only, plus a hashed
  session fingerprint — never question text or the raw session id.
- **Atomic turns** — if the agent raises, the turn is not stored.
- **CLI** — `python -m app.agent chat` (interactive) and `conversation-demo` (scripted
  follow-ups), reusing the existing paid-provider guard.

---

## Stage 9 decisions — recorded BEFORE implementation began

**Decided by the user, 2026-09-14**, answering the four questions listed in *Stage 9 —
starting notes*. Each was put with options and a recommendation; all four recommendations
were chosen. Written here before any Stage 9 code existed.

### 9.A — Session-store lifetime: ONE service per application

| | |
|---|---|
| **Chosen** | One `ConversationService` per app, kept on `app.state.conversation`. `create_app()` accepts an injected service (tests use a mock-provider agent); otherwise the dependency builds it **once, on first use**, under a lock, and every later request reuses it. Built lazily so `GET /health`, `import app.main` and the existing test app never load the embedding model or index. Sessions are lost on restart (acceptable: local, short-lived state, §20.26) |
| **Rejected — module-level cached singleton** | Tests could not build an app with overridden settings or a stub service without patching a global |

### 9.B — Concurrent requests on one session: PER-SESSION LOCK

| | |
|---|---|
| **Chosen** | `ConversationService.ask` holds a lock per session id around *read turns → agent → append*, so two requests on one session run one after the other and cannot record a duplicate turn number. Different sessions still run in parallel. Locks are held in a `weakref.WeakValueDictionary`, so an expired session's lock does not leak. Closes Stage 8 unfinished #3 |
| **Rejected — accept and document** | Leaves a known data defect in place; a double-click or a retry would reproduce it |

### 9.C — Session id transport: JSON REQUEST BODY

| | |
|---|---|
| **Chosen** | `POST /api/sessions` returns `{session_id}`. Every other call carries the id **in the JSON body**, never in the URL: `POST /api/sessions/ask {session_id, question}`, `POST /api/sessions/turns {session_id}`, `POST /api/sessions/end {session_id}`. Keeping it out of the path keeps it out of URLs and access logs — the same stance as `SessionNotFoundError` never repeating the id. Unknown/expired id → **404** with the fixed message, never a new session |
| **Clarified** | The option text offered `/api/sessions/{id}/questions`; the label chosen was *JSON request body*. Implemented as body-only for the reason above — flagged to the user in the Stage 9 report |
| **Rejected — HTTP-only cookie** | Hides the id from page JS but adds cookie and CSRF handling to a local demo |
| **Rejected — custom header** | Works, but less visible in tests and docs than a body field |

### 9.D — UI technology: NO-BUILD STATIC PAGE

| | |
|---|---|
| **Chosen** | One `index.html` + vanilla `app.js` + `styles.css` under `app/web/static/`, served by FastAPI `StaticFiles` at `/`. No Node, no build step. The page renders only what the API returns (§ starting notes table): answer, sources, tool activity, RAG/MCP/insufficient badges, conversation turns, error states. All text inserted with `textContent`, never `innerHTML` (model and tool text is untrusted) |
| **Rejected — Jinja2 templates** | Full-page reloads or extra JS for a chat flow; a second rendering path to test |
| **Rejected — React/Vite** | Node toolchain, build step and a second test stack for a page whose purpose is to show the backend |

### 9.E — Design consequences (decided with the above)

- **Route handlers are plain `def`** — the agent is synchronous; FastAPI runs `def`
  handlers in its threadpool, so one slow answer does not block the event loop. Handlers
  are **not** `@traced` (Problems §2); request tracing is Stage 10.
- **Error mapping** — blank question → 422 (request validation); `SessionNotFoundError` →
  404; `ToolError` / `LLMError` → 502 with a fixed message. Exception text from tools or
  providers is never returned to the browser.
- **Response model** — an API view built from `ConversationAnswer`, exposing flags the UI
  needs directly (`rag_used`, `mcp_used`, `sources_consulted`, `insufficient`) so the page
  does not re-derive them.

---

## Stage 10 decisions — recorded BEFORE implementation began

**Decided by the user, 2026-09-15**, answering the four questions listed in *Stage 10 —
starting notes*. Each was put with options and a recommendation; all four recommendations
were chosen. Written here before any Stage 10 code existed. **Build method: single build,
no sub-agents** (user's choice, 2026-09-15 — the project default; the change is small and
touches the same event contract everywhere).

### 10.A — "Question" tracking: HASH + LENGTH ONLY

| | |
|---|---|
| **Chosen** | Log a short one-way hash of the question and its character count — never the text. Same stance as Stage 8's hashed session fingerprint (`app/conversation/service.py`). Lets two log lines be matched as "the same question" without storing what was asked |
| **Rejected — redacted text** | Pattern-based masking can miss customer data; one miss puts PII in a log file |
| **Rejected — full text behind an off-by-default setting** | One wrong setting in a deployed environment logs every customer question |

### 10.B — Metrics: IN-PROCESS COUNTERS/HISTOGRAMS + `GET /metrics`

| | |
|---|---|
| **Chosen** | Small in-process counters and latency histograms, served at `GET /metrics`. **No new dependency** — the `mcp==1.12.4` / `fastapi==0.115.6` pins (6.B) are untouched |
| **Rejected — `prometheus_client`** | Standard format, but a new dependency to check against the pins for a local demo |
| **Rejected — OpenTelemetry** | Heaviest: many packages, and a real risk to the `starlette`/`mcp` pins |
| **Rejected — logs only** | The plan asks for metrics "where practical"; an endpoint is cheap |

### 10.C — Tracing depth: REQUEST ID ONLY

| | |
|---|---|
| **Chosen** | One `request_id` bound with `structlog.contextvars` in request middleware, so it appears on every log event and every `@traced` line for that request. No span ids |
| **Rejected — parent/child span ids** | A hand-built version of spans; more code for little gain in a single-process app |
| **Rejected — OpenTelemetry spans** | Only sensible with OpenTelemetry metrics, which 10.B rejected |

### 10.D — Request-id source: ACCEPT INCOMING IF VALID, ELSE GENERATE

| | |
|---|---|
| **Chosen** | Accept an incoming `X-Request-ID` only if it is short and safe (letters, digits and dashes, at most 64 characters); otherwise generate a new one. Always returned in the `X-Request-ID` response header |
| **Rejected — always generate** | Cannot join up with an upstream proxy's id |
| **Rejected — accept any incoming value** | Untrusted header text would be written into logs (log injection) |

### 10.E — `httpx` logging: QUIETENED TO WARNING (decided after Stage 10 was committed)

**Decided by the user, 2026-09-15**, answering Stage 10 unfinished #3. Recorded before the
change was made.

| | |
|---|---|
| **Chosen** | `configure_logging` sets the `httpx` logger to `WARNING`; `reset_logging` restores it. Its `info` line per request (full URL) no longer reaches `app.log`; its warnings and errors still do. The server side is already covered by `http.request` (path only) |
| **Rejected — leave at `info`** | Full URLs, query strings included, in `app.log`; one noise line per LLM vendor call |
| **Rejected — redact the URL** | A processor tied to one library's message format; breaks silently if the wording changes |

### 10.F — Hot-path helpers stay UNTRACED (decided after Stage 10 was committed)

**Decided by the user, 2026-09-15**, answering Stage 10 unfinished #5.

| | |
|---|---|
| **Chosen** | A deliberate, documented exception to the global `@traced` rule: `Metrics` and `_Histogram` methods, `elapsed_ms`, `get_metrics`, `reset_metrics` and the middleware's inner response wrapper are not traced |
| **Why** | They run inside the measurements, several times per request; tracing them writes a trace line per counter update and adds to the latency being measured |
| **Rejected — trace them all** | Trace-log noise and inflated timings, for functions with no branching worth a trace |

---

## Stage 11 decisions — recorded BEFORE implementation began

**Stage 11 kicked off by the user, 2026-09-15**, after the 10.E/10.F follow-up was approved and
committed (`42788e8`). The four questions in *Stage 11 — starting notes* are put one at a time,
each with options and a recommendation, and recorded here as they are answered. **Build method:
single build, no sub-agents** (project default; the user did not ask for sub-agents at kickoff).

### 11.A — Dataset: YAML IN `data/eval/`

**Decided by the user, 2026-09-15** (recommendation chosen).

| | |
|---|---|
| **Chosen** | One hand-reviewed file, `data/eval/questions.yaml`, about 40 realistic banking questions. Each entry has an `id`, the `question`, the expected decision path (knowledge answer, tool call or refusal — names to match the agent's real paths), the expected source documents (paths under `data/knowledge/`), the expected tool where one applies, and short facts the answer must mention. Claude drafts it; the user reviews it. **No new dependency** — `PyYAML==6.0.2` and `types-PyYAML` are already pinned |
| **Rejected — JSON in `data/eval/`** | Same content, but no comments and harder to read and edit by hand |
| **Rejected — Python module in `tests/`** | Mixes data with code; a CLI report could not reuse it cleanly |

### 11.B — Answer quality: FREE RULE CHECKS BY DEFAULT + OPT-IN PAID RUN

**Decided by the user, 2026-09-15** (recommendation chosen).

| | |
|---|---|
| **Chosen** | **Default, free:** rule-based checks on every run using the `mock` provider — cites the expected documents, refuses when there is no evidence, no citation numbers that point at nothing. **Opt-in, paid:** real-model answers only when a provider and `BKA_LLM_API_KEY` are set **and** an explicit `--paid` flag is passed; it prints the question count first. Claude never runs the paid mode without the user's confirmation at the time |
| **Rejected — free only** | Real answer quality stays unmeasured, with no way to measure it later without new code |
| **Rejected — paid LLM-as-judge** | Costs money on every run, and the judge's scores vary between runs |

### 11.C — Retrieval metrics: RECALL@K + MRR, GATED BY A SOFT FLOOR

**Decided by the user, 2026-09-15** (recommendation chosen).

| | |
|---|---|
| **Chosen** | **recall@k** (share of questions with at least one expected document in the top k, k = the retriever's default `retrieval_top_k`) and **MRR** (mean reciprocal rank of the first expected document). Both reported, with the ids of missed questions. An `integration`-marked pytest fails only if a score drops below a floor set **a little under the value measured in Stage 11** — floors come from a real run, not from the example numbers shown at decision time. Real local embedding model, free |
| **Rejected — report only** | A retrieval regression could slip through unnoticed |
| **Rejected — add precision@k and nDCG** | With 1–2 expected documents per question they add little over recall and MRR, and more gated numbers means a more fragile suite |

### 11.D — How it runs: ONE ENGINE, BOTH PYTEST AND A CLI SCORECARD

**Decided by the user, 2026-09-15** (recommendation chosen). All four Stage 11 decisions made.

| | |
|---|---|
| **Chosen** | One shared engine in a new `app/eval/` package (dataset loading and validation, metrics and rule checks, a runner over the agent), used by both: **pytest** (free mock checks on every run; retrieval floors under the existing `integration` marker) and **`python -m app.eval`** (a readable scorecard; `--paid` is the opt-in real-model mode from 11.B). No evaluation logic duplicated between the two |
| **Rejected — pytest only** | Scores only visible in test output; the paid mode has no natural home |
| **Rejected — CLI only** | Nothing fails automatically; regressions depend on someone remembering to run it |

### 11.E — Refused-when-expected is a SCORE; honest refusal and citations are INVARIANTS (decided during implementation)

**Decided by Claude during implementation, 2026-09-15** — a correction to Claude's own
contract, not a user decision; flagged in the stage report. The first real-model run showed two
banking-adjacent off-topic questions (`off-006` mortgage rate, `off-007` savings account) clearing
the retrieval floor and being answered.

| | |
|---|---|
| **Chosen** | Split the refusal check. `refusal` (refused exactly when expected) is reported and counts through **path accuracy** and its soft floor. `refusal_honest` (a refusal used no model and says the fixed sentence) and `citations` (no citation to unsupplied evidence) are **invariants**: any failure fails the run whatever the floors say |
| **Why** | Whether a question is refused depends on retrieval scores, which vary with the model and corpus; how a refusal behaves does not |
| **Test changed** | `test_a_broken_invariant_fails_even_with_zero_floors` (gated a wrong refusal as an invariant) replaced by `test_an_invented_citation_fails_even_with_zero_floors` + `test_a_wrong_refusal_is_a_score_not_an_invariant` — the design was wrong, not the code |
| **Rejected — keep refusal as an invariant** | A known retrieval finding would keep the suite red and hide every other regression |
| **Rejected — drop `off-006`/`off-007`** | Fits the dataset to the system; they are the best hallucination-resistance cases |

---

## Current Work

### Implemented in Stage 11 (approved, committed, pushed — hash in *Git*)

Single build, no sub-agents. Test-first: the four test files ran red (`No module named
'app.eval'`) before any `app/eval/` code existed.

| Part | What it does |
|---|---|
| `data/eval/questions.yaml` | 49 cases (decision asked ~40): knowledge 20 · paraphrase 6 · tool 6 · hybrid 5 · failure 4 · off_topic 7 · injection 1. Every tool and every fixed route expected at least once. Floors 0.90 / 0.85 / 0.90 with the measured values in a comment |
| `app/eval/dataset.py` | `EvalCase` / `Thresholds` / `EvalDataset`; impossible expectations refused at load; `load_dataset` → `DatasetError` naming the file; `check_references` against the corpus and registry |
| `app/eval/metrics.py` | `ranked_documents`, `reciprocal_rank`, `hit_at_k`, `recall_at_k`, `mean_reciprocal_rank`, `invalid_citations`, `path_matches` (a refined search = a knowledge answer), `missing_mentions`, `check_answer` (7 checks) |
| `app/eval/runner.py` | `run_evaluation` / `run_case` / `score`; `EvalReport.failed_floors()` (floors + invariants 11.E); `eval.case` log line — ids, routes, numbers, never text (10.A) |
| `app/eval/report.py` | Plain-ASCII scorecard: scores vs floors, check tallies, latency, one line per case |
| `app/eval/__main__.py` | `python -m app.eval [--dataset] [-k] [--paid]`; free mode always mock; `--paid` refused (exit 2) without a paid provider or key, prints the question count before building a provider; exit 1 on a failed gate |
| `app/core/config.py` · `.env.example` | `BKA_EVAL_DATASET_PATH` |

**Measured 2026-09-15** (real `all-MiniLM-L6-v2`, mock provider, k=5, free): recall@5 **1.000**
(33 retrieval cases) · MRR **0.927** · path accuracy **0.959** (47/49) · tools 13/13 · documents
33/33 · refusal 47/49 · refusal_honest 49/49 · citations 49/49 · mentions 29/30 · median 12.9 ms
per question.

### Stage 11 — what remains deliberately unfinished

1. **`off-006`, `off-007` answered instead of refused** — banking-adjacent questions clear the
   0.25 floor (top scores ~0.28–0.37 after refinement). A real hallucination-resistance gap in
   retrieval, not fixed here (out of scope): candidates are a higher floor for refined searches,
   hybrid search, or a reranker. Needs a user decision in a later stage.
2. **`know-018` evidence lacks `TransactionSwitch`** — the top-5 chunks for "runtime components"
   miss the components table's first row. Reported, not gated (mentions are not floored).
3. **Paid mode never run.** `--paid` is implemented and its guards tested; no real-model answer
   has been scored. Running it needs the user's explicit confirmation at the time.
4. **Mentions in free mode are checked against retrieved evidence**, not answer wording — the
   mock cannot phrase facts. Answer wording is measured only by `--paid`.
5. **Same author** wrote the corpus, the routing rules and the dataset; expectations were written
   from the documents and rules, not fitted — but an independent reviewer would strengthen it.
6. **API behaviour** is covered by the existing Stage 9/10 API tests, not re-scored by the
   evaluation (the evaluation drives the agent directly).

### Implemented in Stage 10 (approved, committed, pushed — hash in *Git*)

Single build by the main session (user's choice). Decisions 10.A–10.D asked and recorded
before code. Tests written first and run red (collection failed: no `app.core.observability`).

| File | What changed |
|---|---|
| `app/core/observability.py` — **new** | `resolve_request_id` (incoming `X-Request-ID` kept only if `[A-Za-z0-9-]{1,64}`, else `uuid4().hex`) · `fingerprint` (SHA-256, 12 hex chars) · `Metrics` (thread-safe counters + histograms; cumulative buckets 5…10000 ms + `le_inf`; negative latency raises) · `get_metrics` / `reset_metrics` · metric-name constants · `elapsed_ms` |
| `app/api/middleware.py` — **new** | Plain ASGI `RequestContextMiddleware`: resolves the id, `bound_contextvars(request_id=…)`, sets the response header, logs `http.request` (method, **path only**, status, `latency_ms`); unhandled exception → `http.request_failed` (type only), re-raised; request metrics |
| `app/api/routes/metrics.py` — **new** | `GET /metrics` → `Metrics.snapshot()` JSON. Not `@traced` (route handler) |
| `app/main.py` | Adds the middleware and the metrics router |
| `app/rag/retriever.py` | `rag.retrieved`: **`query` text removed** → `query_hash`, `query_length`, `latency_ms`; retrieval counter + histogram |
| `app/llm/service.py` | Provider call + validation timed: `llm.answered` gains `latency_ms`; new `llm.failed` (provider, `error_type`, `retryable`, `latency_ms`); call/error/token counters + histogram |
| `app/mcp/registry.py` | `mcp.tool_called` gains `latency_ms`; new `mcp.tool_failed` (tool, argument names, `error_type`, `latency_ms`); call/error counters + histogram. Typed/untyped error behaviour unchanged |
| `app/agent/agent.py` | `agent.answered` gains `question_hash`, `question_length` (so tool-only answers are traceable) |
| `app/conversation/service.py` | `session_fingerprint` now delegates to the shared `fingerprint` (same output) |
| `app/mcp/base.py` · `app/mcp/models.py` · `tests/test_mcp_tools.py` | The three stale "Stage 7 shows this to a model" docstrings fixed (the handover's carried note) |
| `tests/test_observability.py` — **new** (35) | See *Testing* |

### Stage 10 follow-up — 10.E and 10.F (approved 2026-09-15, committed, pushed — hash in *Git*)

Decided by the user after the Stage 10 commit. Test-first: the two new/tightened tests ran red
(2 failed — the `httpx` line and the query string both reached `app.log`), then green.

| File | What changed |
|---|---|
| `app/core/logging.py` | `QUIETENED_LOGGERS = ("httpx",)`: `configure_logging` sets each to `WARNING`; `reset_logging` restores `NOTSET` |
| `tests/test_logging.py` | +2: an `httpx` info line with a query string stays out of `app.log` while a warning gets in; reset restores the level |
| `tests/test_observability.py` | `test_the_query_string_is_not_logged` checks the **whole** `app.log` again (the Stage 10 narrowing to `app.*` loggers is undone) |
| `docs/architecture-guide.html` | §13 "known gap" note replaced; §14 `test_logging.py` row; §20.36 (`httpx`) and §20.37 (untraced helpers) decision records |
| `README.md` | Test count 1040 → 1042 |
| `docs/HANDOVER.md` | 10.E, 10.F; this section; checkpoint |

### Stage 10 — what remains deliberately unfinished

1. **`GET /metrics` is unauthenticated** (like `/health`); holds names and numbers only. Stage 13.
2. **Metrics are per-process and reset on restart**; JSON, not Prometheus text. Stage 14.
3. **`httpx` logs every outgoing request's full URL at `info` into `app.log`** (found by a test:
   the test client's own request). In a deployment that is the vendor SDKs' API URLs — no
   question text or keys. **Decided 2026-09-15 (10.E): raised to `warning`.**
4. **A 500 from an unhandled exception has no `X-Request-ID` header** — Starlette builds it
   outside the middleware. The `http.request_failed` log line does carry the id.
5. **Not `@traced`, deliberately** (exception to the global rule, flagged to the user):
   `Metrics` and `_Histogram` methods, `elapsed_ms`, `get_metrics`, `reset_metrics`, and the
   middleware's inner response wrapper — they run inside the measurements, several times per
   request. `resolve_request_id`, `fingerprint` and the middleware `__call__` are traced.
   **Decided 2026-09-15 (10.F): kept untraced.**
6. **Other stale "Stage 7 … a model" wording** remains in `app/mcp/models.py` (`ToolSpec`,
   `input_schema`, `ToolInvocation` docstrings) and `app/mcp/base.py` (module docstring,
   `ToolInputError`). Not in the carried list of three; left for a docs-only fix.
7. **No live `uvicorn` smoke test this session** — end to end is covered through
   `TestClient` (real agent, real tools, mock provider).

### Implemented in Stage 9 (approved, committed, pushed — hash in *Git*)

Single build by the main session. Decisions 9.A–9.E asked and recorded before code. Tests
written first and run red (every API test errored on `create_app()` lacking
`conversation_service`; the concurrency test recorded a duplicate turn number).

| File | What changed |
|---|---|
| `app/api/routes/conversation.py` — **new** | `POST /api/sessions` (201), `/ask`, `/turns`, `/end` (204). Session id in the JSON body only. `extra="forbid"` bodies; blank question → 422. `AnswerResponse` flattens `ConversationAnswer` with `rag_used`, `mcp_used`, `sources_consulted`, `insufficient`, route, steps, retrieval summary, full tool results. `SessionNotFoundError` → 404 (fixed message); `ToolError`/`LLMError` → 502 fixed sentence, logged by type only. Plain `def` handlers, not `@traced` |
| `app/api/dependencies.py` | `get_conversation` / `ConversationDep`: one service per app on `app.state.conversation`, built once on first use under `app.state.conversation_lock` |
| `app/main.py` | `create_app(settings, conversation_service=None)`; state + lock; conversation router; `StaticFiles` mounted at `/` **last** so API and docs routes win |
| `app/conversation/service.py` | Per-session lock around read turns → agent → append, held in a `WeakValueDictionary`. Blank-question check stays before the lock |
| `app/web/static/index.html` · `app.js` · `styles.css` — **new** | No-build page: question input, conversation, badges (RAG / MCP / sources / insufficient / follow-up), sources, tool activity, "how this answer was produced", error box. `textContent` only; no network assets. On 404 it tells the user the conversation ended and starts fresh on the next question |

### Stage 9 — what remains deliberately unfinished

1. **No authentication or rate limiting** — local demo. Stage 12 (guardrails) / Stage 14.
2. **No streaming** — the page waits for the full answer; the first question is slow while
   the embedding model loads.
3. **Sessions are still process-local** (one worker). Stage 14 documents a shared store.
4. **No browser-automation test** of the page — the page is checked statically (required
   markers, no HTML sinks, no network assets) and the API end to end; JS behaviour was not
   exercised in a real browser this session.
5. ~~**No request tracing** on routes — Stage 10 middleware.~~ Done in Stage 10.

### Implemented in Stage 8 (approved, committed `2abbb39`, pushed)

Single cohesive build, no sub-agents (§8.A). Tests written first and run red (collection
failed on the missing `app.conversation`) before any implementation.

| File | What |
|---|---|
| `app/conversation/models.py` — **new** | `ResolutionKind` (4 values), `ConversationTurn` (stores `topic`; `answer_text` display-only), `ConversationContext` (the Stage 8 record), `ConversationAnswer` wrapping the unchanged `AgentAnswer` |
| `app/conversation/context.py` — **new** | `find_identifiers` (Stage 7's extractors, question order) and `resolve_follow_up`: standalone / substituted / carried identifiers (max 3) / carried topic; history window + char budget, oldest dropped whole; standalone sends none |
| `app/conversation/store.py` — **new** | `SessionStore` protocol, `InMemorySessionStore` (`secrets` ids, TTL, LRU cap, per-session turn cap via `deque(maxlen)`, lock, injectable clock), `SessionNotFoundError` (id-free message) |
| `app/conversation/service.py` — **new** | `ConversationService.start/ask/turns/end`; turn stored only after success; `conversation.turn` log = shape + `session_fingerprint` (SHA-256, 12 hex) |
| `app/conversation/factory.py` · `__init__.py` — **new** | `get_conversation_service()`; exports |
| `app/llm/prompts.py` | `<conversation_history>` / `<earlier_question>` fences in the shared `_DELIMITERS`; `render_history`; `history` appended to `build_user_turn` / `build_request`; system prompt history rule; `SYSTEM_PROMPT_VERSION` → `1.2.0` |
| `app/llm/service.py` | `answer(..., history=())`; refusal guard unchanged (history is not evidence); logs `history_questions` |
| `app/agent/agent.py` | `ask(question, history=())` passed to the service; logs `history_questions`. No routing change |
| `app/agent/__main__.py` | `chat` and `conversation-demo` (paid guard reused) |
| `app/core/config.py` · `.env.example` | 5 `BKA_CONVERSATION_*` settings |

**Measured, free (real `all-MiniLM-L6-v2`, mock LLM):** `conversation-demo` — turn 2
carried `LIM-4001` → `look_up_error_code`; turn 4 substituted → `retrieve_system_version`
for CardSecurityModule; turn 5 carried CSM → health + status tools; turn 7 carried topic →
search top score 0.762 (confident, one pass).

### Stage 8 — what remains deliberately unfinished

1. **Rules are English word lists** (reference and ellipsis cues). A follow-up without a
   cue word ("healthy?") is treated as standalone. Stage 11 measures it.
2. **Identifiers are never carried from tool results** — by design (untrusted), so "why did
   it fail?" after a transaction lookup does not carry the error code the tool reported.
3. **Two concurrent asks on one session** can both read the same earlier turns and record
   the same turn number. Harmless for the CLI; Stage 9 decides request serialisation.
   *(Stage 9: closed by a per-session lock, §9.B.)*
4. **The store is process-local**: sessions vanish on restart and are not shared between
   workers. Stage 9 decides its lifetime; Stage 14 documents a shared store.
   *(Stage 9: one service per app, §9.A; shared store still Stage 14.)*
5. **No live LLM call** — whether a real model uses the history fence well is unmeasured.

### Implemented in Stage 7 (approved, committed `a3728d9`, pushed)

Built by the main session alone, **no sub-agents**, per the user's instruction (§7.A).
Tests were written first and run red (collection failed on the missing
`RuleToolSelector`) before any implementation.

| File | What changed |
|---|---|
| `app/agent/tool_policy.py` — **rewritten** | `ToolSelector` protocol + `RuleToolSelector`, built from `registry.specs()`. Argument extractors keyed by **parameter name**. Refuses at construction a spec with no parameters, a parameter no extractor understands, or a component-only tool with no cue. Identifiers fan out; a component takes the first named. Registry order, capped at 4. `select_tools()` **removed** |
| `app/agent/policy.py` — **rewritten** | `decide(question, selector)` = the plan. `asks_for_explanation`, `retrieval_is_weak`, `refinement_terms` (vocabulary-vetted), `record_step` (fixed sentence per outcome, `STEP_EXPLANATIONS`), `conclude` (route actually taken). `decide_retrieval` alias kept |
| `app/agent/models.py` | `DecisionReason` **extended** 3 → 6. New `DecisionStep` with `DecisionStepName` / `DecisionOutcome` literals. `RetrievalSummary.passes`. `AgentAnswer.decisions` + `retrieved_more`. `decision` now records the route *taken*; the plan is `decisions[0]` |
| `app/agent/agent.py` | Plan → tools → consult docs if a tool-only reading missed → search → at most **one** refined second search, merged by chunk id at best score, capped at `retrieval_top_k` → answer → conclude. `selector=` appended to the constructor; a selector without a registry raises `ValueError`. `agent.answered` log gains `plan`, `route`, `retrieval_passes` — step names and outcomes only |
| `app/core/config.py` · `.env.example` | `BKA_AGENT_CONFIDENT_SCORE`, default **0.50**, measured (§7.C) |
| `app/llm/mock.py` | Cites `[T1]` tool results when the prompt has any, so the tool-only route is not answered with a refusal-shaped sentence. No-tool behaviour byte-identical |
| `app/agent/__main__.py` | Prints `[route: …]` and `N search(es)`; two retrieve-more demo questions; the stale "7 billed calls" help text corrected |
| `app/agent/__init__.py` | Exports `AgentDecision`, `DecisionStep`, `RuleToolSelector`, `ToolSelector`, `decide` |

### Stage 7 — what remains deliberately unfinished

1. ~~Architecture guide Stage 7 sections~~ — **done** (§20.17–§20.22 and the section
   updates), written in plain English with `.note` callouts per `docs/improve.md`.
2. **No fleet-wide tool call.** A tool with only optional parameters still needs one
   extracted argument; "is anything down?" is answered from documentation.
3. **The explanation cue is an English word list.** Misreading an explanation as a reading
   is guarded (a missed reading pulls in documentation); the other direction costs one
   unnecessary search.
4. **The 0.50 threshold is calibrated on ~20 questions by the corpus author.** Stage 11.
5. **Answer quality is still unmeasured** — no live model call has been made. Stage 11.

### Implemented in Stage 6 (approved, committed `93eeb22`, pushed)

**The shared contract — written by the main session before any sub-agent ran**

- **`app/mcp/models.py`** — `ToolName` (a closed literal of all six, fixed *before* the
  tools were written so six independent modules could not disagree about their own
  names), `ToolSpec` (+ `input_schema()` emitting real JSON Schema for the protocol
  layer), `ToolParameter`, `ToolResult`, `ToolInvocation`, `SYNTHETIC_OBSERVED_AT` (one
  fixed clock), and `TOOL_FAILURE_CODES` (added at integration — see below).
- **`app/mcp/base.py`** — the `Tool` **protocol** (structural, like `LLMProvider`), the
  `ToolError` taxonomy with `retryable`, and the shared `require_argument` /
  `reject_unknown_arguments` helpers that keep six independently-written tools failing
  identically.
- **`app/mcp/registry.py`** — `ToolRegistry`: `register` / `specs` / `get` / `call` /
  `invoke` / `invoke_all`. Explicit registration, never discovery. Wraps an untyped tool
  exception in `ToolExecutionError`. Logs tool and argument **names**, never values.

**The six tools — six sub-agents, one file each, in parallel**

Every tool owns its own synthetic dataset and imports nothing from its siblings. All six
are pure: no clock, no I/O, no randomness.

| Tool | Notable |
|---|---|
| `get_system_configuration` | Effective value + precedence level + documented default, so a *disagreement* with the docs is visible. Refuses credential-shaped keys **before** validating the component, so the refusal is not a component-existence oracle |
| `check_transaction_status` | Eight real lifecycle stages, eight synthetic transactions covering a clean completion, three rejection classes, a jam, an **unacknowledged** reversal, a `PAY-8003` wrapper decline carrying its real cause, and one in progress |
| `get_component_status` | All nine components. `TransactionSwitch` is DEGRADED with **6/6 instances healthy** — the health-is-not-status case. One incident id links origin to impacted |
| `look_up_error_code` | All 40 documented codes. `PAY-8003` and `SWX-7001` flagged as wrappers; `SWX-7004` recorded as *being* a reversal rather than triggering one. A known prefix with an unknown number says so specifically |
| `retrieve_system_version` | Optional argument: fleet view or one component. Models real drift — CSM on `4.1.9`, LIM on `4.2.2`, platform build `4.2.3` |
| `check_service_health` | Optional argument. Liveness + dependency checks only. `CoreBankingAdapter`'s failing pool check is the documented cause of the switch's `SWX-7001`s |

**The protocol layer**

- **`app/mcp/server.py`** — a genuine MCP server on the official SDK, stdio JSON-RPC,
  exposing the same registry. No tool logic, no data (asserted by a test). A `ok=False`
  result crosses the wire as a **result**; a malformed call crosses as an **error**.
- **`app/mcp/factory.py`** — `build_tool_registry()` / `get_tool_registry()`. No
  settings: there is nothing to configure that would not be inventing a knob for a
  system that does not exist yet.
- **`app/mcp/__main__.py`** — `list | call | demo | serve`. Free and offline; the tool
  layer has no LLM in it, so it needs none of the paid-provider guards.

**Integration — the main session's own work**

- **`app/llm/prompts.py`** — the injection defence extended (§6.D): `<tool_results>`
  fence, four new delimiters in the **same** `_DELIMITERS` tuple, the **same**
  `_fence_safe`, `render_tool_results()`, `[T1]` citations, two new system-prompt rules,
  `SYSTEM_PROMPT_VERSION` → `1.1.0`.
- **`app/llm/service.py`** — `answer()` takes `tool_results`. The refusal guard now asks
  "is there evidence of *either* kind?"; its shape is otherwise unchanged, and it still
  makes zero provider calls when the answer is no.
- **`app/llm/models.py`** — `GroundedAnswer.tools_used`, counted **separately** from
  `chunks_used` rather than summed.
- **`app/agent/models.py`** — `DecisionReason` extended with
  `knowledge_and_live_status_required`; `RetrievalDecision` renamed `AgentDecision` with
  the old name kept as an alias; new `ToolCallSummary`; `AgentAnswer` gains `tools`,
  `tool_results` and `used_live_information`.
- **`app/agent/tool_policy.py`** (new) — `select_tools()`: route on identifiers, not
  topics. Selection and argument extraction are one step.
- **`app/agent/policy.py`** — `decide()` (with `decide_retrieval` kept as an alias).
- **`app/agent/agent.py`** — `_run_tools()`; tools injected, `None` by default so the
  Stage 5 composition is unchanged; a tool failure propagates rather than silently
  dropping the live half of an answer.
- **`app/agent/factory.py`** — two lines: the agent gains a third collaborator.
- **`app/agent/__main__.py`** — five tool questions added to `demo`, and tool activity
  rendered as `[T1]`, `[T2]` beside the document citations.

### Stage 6 — integration notes (what the parallel build actually cost)

Recorded because §6.E promised it, and because this is the reusable part.

| # | Friction | Resolution |
|---|---|---|
| 1 | **A real contradiction.** `check_service_health` reported the platform line `4.2` as every service's running version; `retrieve_system_version`, built in parallel from the same corpus, knew two components had not reached the current build. Two tools answering the same question differently | Health now carries a per-service `reported_version` matching the version tool, and a cross-tool test asserts agreement. **The first fix was incomplete** — it updated the payload and not the summary prose beside it, so the test was tightened to cover both |
| 2 | **Divergent failure vocabulary.** The brief said "a stable UPPER_SNAKE code, e.g. `NOT_FOUND`". Four tools used exactly that; two invented richer sets | Resolved **upward**, not flattened: the specific codes are better answers. The real defect was that the set was unbounded, so `TOOL_FAILURE_CODES` now closes it and a test asserts every not-found path uses a member |
| 3 | **A house convention no brief mentioned.** Four tools used em dashes in runtime strings; two deliberately kept them ASCII for a Windows console. Neither could know the project already reconfigures stdout to UTF-8 in every `__main__.py` | Nothing to fix — the new CLI follows the existing convention. The lesson is that the brief should have named it |
| 4 | **Cosmetic inconsistency.** Three spellings of the same constant (`ERROR_NOT_FOUND: Final`, `_ERROR_NOT_FOUND`, none at all); disagreement on whether to accept three-letter component codes | Left alone deliberately. Harmless, and normalising it means editing six files to satisfy symmetry |
| 5 | **Over-delivery.** Several tools returned more payload fields than asked for (`role` on incidents, `reversal_role`, `drift`, `warrants_incident`) | Kept. All of it was good — the upside of briefs that state intent rather than dictate a schema |
| 6 | **A leak the main session wrote, caught by its own test.** `ToolCallSummary` — the object whose stated purpose is being safe to log — carried the policy's `reason` string, which names the very identifier the argument list omits | `reason` removed from the summary; it lives on `AgentDecision.tools`, which is returned and displayed but never logged |

**Dependency resolution** (§6.B) also happened before any tool code: `mcp` had to be
pinned **down** to `1.12.4`, because 2.x forces a Starlette that breaks the pinned
FastAPI at import and takes the whole suite with it.

### Currently being worked on

**Nothing in progress.** Stage 9 is approved, committed and pushed. Stage 10 has not
started.

### What remains deliberately unfinished in Stage 6

1. **LLM-driven tool selection.** Routing is deterministic and identifier-based. Weighing
   a model-driven selector against it is Stage 7's explicit subject; building it here
   would spend that decision early and make the tool layer untestable without a provider.
2. **No tool reaches a real system.** Every tool reads a dictionary in its own module.
   `ToolUnavailableError` and `SYNTHETIC_OBSERVED_AT` exist as the two named seams for
   the day one does.
3. **The MCP server is stdio only.** `build_server()` is transport-agnostic; `serve()` is
   the handful of lines that choose stdio. HTTP/SSE is a Stage 14 question.
4. **Tool results are not yet on an HTTP surface.** The agent is still CLI-only. Stage 9.
5. **Answer quality with tool context is still unmeasured** — as in Stage 5, because no
   live model call has been made. Stage 11.

### Implemented in Stage 5 — Checkpoint B (approved, committed `6ebe947`, pushed)

- **`AnthropicProvider`** — `app/llm/anthropic_provider.py`. Official `anthropic` SDK.
  Translates request, response and the whole exception hierarchy. Reads text from the
  **text blocks**, not `content[0]` — with thinking on, the first block is reasoning, and
  reading it positionally would put reasoning where the answer belongs.
- **`OpenAIProvider`** — `app/llm/openai_provider.py`. Official `openai` SDK. Same seam,
  different shape: system prompt as a message, `max_completion_tokens` (not the
  deprecated `max_tokens`, which reasoning models reject), and a refusal reported on
  `message.refusal` **while `finish_reason` still says `"stop"`**.
- **Pinned** — `anthropic==1.4.0`, `openai==3.11.0` in `requirements.txt`, with a comment
  stating that installing them does not enable spending.
- **Factory extended** — `AVAILABLE_PROVIDERS = ("mock", "anthropic", "openai")`, plus
  `PAID_PROVIDERS` and `is_paid_provider()`. **The default is unchanged: `mock`.** The
  SDK import is *deferred into the branch that needs it*, so the app still starts, still
  serves `/health` and still runs on the mock with neither SDK installed; a missing SDK
  becomes a typed configuration error, not an `ImportError`.
- **AST guard narrowed, not deleted** — `ADAPTER_MODULES` is an explicit two-name
  allow-list; every other module in `app/llm/` is default-denied. The five seam modules
  named in the instruction are asserted to exist, so a rename cannot empty the guarded
  set. The adapters stay bound by the secrets rule (no hardcoded URL, no key literal).
- **Cost guard** — both CLIs warn when a paid provider is configured, and `demo` (7
  questions in `app.agent`, 6 in `app.llm`) **refuses** without `--paid`, checking before
  an index or a client is built. `ask` only warns: one call is a proportionate mistake.
- **Tests** — 112 new (489 → **601**): `tests/test_llm_adapters.py` (99) plus the
  rewritten guard and default-provider tests in `tests/test_llm_provider.py`. **Entirely
  offline** — every test injects a fake SDK client. No network call, no key, no cost.
- **Docs** — guide §20.6–§20.9 (four records), §2, §3, §4, §9, §12, §14, §16, §19;
  README gained an "LLM providers — two adapters, and why" section.

> ⚠️ **No live API call has been made** — not in the suite, not by hand. Building the
> adapters did not authorise one, and it still needs the user's explicit confirmation at
> the time.

#### One thing was added beyond the stated Checkpoint B scope, deliberately

`LLMConnectionError` was added to `app/llm/base.py` (a seam module). **Why:** Stage 4
designed the error taxonomy with no adapter to test it against, and it had a gap — the
only retryable types were a timeout and a rate limit. Both SDKs raise a plain
`APIConnectionError` and an `InternalServerError` that are neither. The two available
mappings were each wrong in the one field callers branch on: `LLMTimeoutError` would
misname a connection reset, and `LLMProviderError` would mark a transient 502 permanently
broken. Shipping a knowingly-wrong `retryable` flag is worse than adding a class, so the
class was added — additive, nothing else changed. Recorded in guide §20.9, and it is the
clearest evidence that building a real adapter was worth doing: Stage 4's own tests could
never have found this, because a mock raises whatever a test tells it to.

### Implemented in Stage 5 — Checkpoint A (approved, committed `1478631`, pushed)

- **Routing decision** — `app/agent/policy.py`. `decide_retrieval(question)` returns a
  frozen `RetrievalDecision` carrying the rule that produced it. Two reasons:
  `knowledge_required` (search) and `no_searchable_content` (a question with no
  alphanumeric character at all — skip the search, say so). Every real question takes the
  first branch, and the module states plainly why a second substantive branch would be
  fiction in Stage 5: retrieval is the agent's only evidence until MCP lands in Stage 6.
- **The agent** — `app/agent/agent.py`. `KnowledgeAgent.ask` = decide → retrieve →
  generate → record. Both collaborators injected as in Stages 3 and 4, so the tests run
  it with a hashing embedder and `MockLLMProvider` and production changes nothing.
- **One refusal path, and it is Stage 4's.** A question the agent declines to search is
  turned into an empty `RetrievalResult` and handed to `LLMService.answer()`, which takes
  the guard it already had: the fixed sentence, and **zero** provider calls. The agent
  writes no refusal of its own. This is the user's Checkpoint A requirement 2 — build on
  the existing guard, do not replace it — and it is asserted by a test that both routes
  produce the identical string.
- **Execution record as a returned value** — `app/agent/models.py`. `AgentAnswer` wraps
  the LLM layer's `GroundedAnswer` unmodified and adds `RetrievalDecision` +
  `RetrievalSummary` (performed, candidates, returned, top score, floor, document ids).
  Stage 9 renders provenance rather than scraping its own logs. The summary carries
  *shape* only — passage text stays out of the object that is safe to log and display.
- **Failures propagate.** A timeout, rate limit or truncated generation raises out of
  `ask()` as its typed `LLMError`. Turning an outage into "the knowledge base does not
  contain enough information" would send the reader to fix the wrong thing and would fold
  infrastructure noise into the refusal rate Stage 11 measures grounding with.
- **Factory** — `app/agent/factory.py`. `get_agent()` composes retriever + service. It
  does **not** choose a provider; that stays in `app/llm/factory.py`, so
  `BKA_LLM_PROVIDER` is interpreted in exactly one place.
- **CLI** — `python -m app.agent ask | demo`. The demo runs the five seed questions plus
  two controls that must be declined for two *different* reasons.
- **Tests** — 104 new tests across 2 files (385 → **489**). No new dependency, no new
  setting: Checkpoint A adds no configuration surface.
- **Docs** — architecture guide §7 rewritten as BUILT, new §20.5 (five decision records
  in the Stage 3/4 what–why–rejected form), plus §1 stage table, §2 structure, §4
  components, §5 data flow, §14 testing, §16 security, header and footer. README gained a
  "Knowledge agent" section.

### Implemented in Stage 4

- **`LLMProvider` protocol** — `app/llm/base.py`. The vendor-agnostic seam, plus the
  six-type error taxonomy (`LLMConfigurationError`, `LLMTimeoutError`,
  `LLMRateLimitError`, `LLMResponseError`, `LLMRefusalError`, `LLMProviderError`), each
  carrying a `retryable` flag. A protocol, not an ABC, so an implementation qualifies
  structurally — the same choice as `Embedder` and `VectorStore` in Stage 3.
- **Prompt management** — `app/llm/prompts.py`. `SYSTEM_PROMPT_VERSION = "1.0.0"`, one
  frozen system prompt recorded on every answer. Grounding rules, mandatory citations,
  the exact refusal sentence, and an explicit statement that fenced text is untrusted.
- **Context injection** — `select_context` (budget) → `render_context` (fence + number +
  label) → `build_user_turn` (context first, question last) → `build_request`.
- **Injection defence** — passages are fenced in `<retrieved_documentation>`, and any
  occurrence of the delimiters *inside* a passage's own text is escaped, so a document
  cannot close the fence early. Without that step the fence would be decorative.
- **Response generation and error handling** — `app/llm/service.py`. Truncated, refused
  and empty generations **raise** rather than being returned as answers; an untyped
  provider exception is wrapped in `LLMProviderError` with the cause preserved.
- **The refusal guard** — when retrieval is empty, the service returns the fixed
  insufficient-evidence sentence and **does not call the provider at all**.
- **Mock provider** — `app/llm/mock.py`. Deterministic and in-process, with three modes
  (synthesise from the injected passages / scripted responses / a handler that may
  raise), and it records every request for assertion.
- **Configuration** — 7 new `BKA_LLM_*` settings, documented in `.env.example`. The API
  key is a `SecretStr`, environment-only, unset.
- **Factory** — `app/llm/factory.py`. An unavailable provider raises; it never falls
  back to the mock.
- **CLI** — `python -m app.llm prompt | ask | demo`.
- **Tests** — 145 new tests across 3 files (240 → **385**).
- **Docs** — architecture guide §20.4 (nine decision records in the Stage 3 form), §9
  rewritten, plus §2, §4, §5, §12, §14, §16, §18, §19 and the stage table. README
  updated with a new "LLM abstraction" section.

### Implemented in Stage 3

- **Chunking** — `app/rag/chunker.py`. Splits on Markdown `##` headings, budgeting size
  in the *embedding model's own tokens*. Oversized sections split at paragraph or
  table-row boundaries; a split table repeats its header row. Code fences are not
  mistaken for headings. Result: 15 documents → 108 sections → **115 chunks**, max 251
  of a 256-token window, zero over.
- **Metadata handling** — every `Chunk` carries the complete `DocumentMetadata` of its
  source plus `source_path`, so retrieval can cite and filter.
- **Embedding generation** — `app/rag/embeddings.py`. `Embedder` protocol with two
  implementations: `SentenceTransformerEmbedder` (all-MiniLM-L6-v2, local, lazy-loaded,
  384-dim) and `HashingEmbedder` (deterministic, offline, for fast tests).
- **Vector storage** — `app/rag/vectorstore.py`. `VectorStore` protocol +
  `InMemoryVectorStore`: exact cosine search over one NumPy matrix, persisted as
  `vectors.npy` + `chunks.json` + `manifest.json`.
- **Retrieval and similarity search** — `app/rag/retriever.py`. Question → embed →
  optional metadata pre-filter → top-k cosine → score floor → `RetrievalResult`.
- **Source metadata** — `RetrievalResult.sources`, deduplicated by document.
- **Pipeline + freshness** — `app/rag/pipeline.py`. `build_index`, `load_retriever`,
  `get_retriever`, and a SHA-256 corpus fingerprint so a stale index is refused.
- **CLI** — `app/rag/__main__.py`: `build`, `search`, `demo`, `calibrate`.
- **Configuration** — 8 new `BKA_*` settings, documented in `.env.example`.
- **Tests** — 168 new tests across 5 files (72 → **240**).
- **Docs** — `docs/architecture-guide.html` substantially rewritten, including a new
  **§20 Decision records** section carrying the full reasoning for every Stage 3 choice
  (what was chosen, why, what was rejected and why). `README.md` updated.

### What remained unfinished in Stage 5 Checkpoint B (still true)

Nothing the instruction requires. Deliberately absent, recorded as deferred rather than
missed:

1. **Answer quality evidence — still unmeasured, and now for a different reason.** Real
   adapters exist, but no live call has been made, so nothing proves a real model answers
   *well* from these prompts. The adapters are proven correct in what they **send, parse
   and translate**, not in what comes back. Measuring the rest needs a key, a budget and
   explicit confirmation; it is Stage 11's evaluation set.
2. **Streaming and async** — neither adapter streams. `CompletionRequest` carries no
   streaming flag and the protocol is synchronous (Stage 4, guide §20.4.9). Adding either
   now would be an untested interface with no caller until Stage 9.
3. **Retry policy** — the errors carry `retryable`, and both SDK clients are constructed
   with `BKA_LLM_MAX_RETRIES`, but nothing above the seam acts on the flag. Choosing a
   backoff belongs with a real deadline, which arrives with the HTTP layer.
4. **HTTP exposure** — the agent is still CLI-only. Stage 9.

### Not yet implemented (later stages)

Tool selection (7) · Conversation context (8) · Web interface (9) ·
Request observability (10) · Evaluation framework (11) · Docker (12) ·
Security review (13) · Production architecture (14) · Final review (15)

---

## Architecture

### Current

```
INDEXING (offline build step — python -m app.rag build)

data/knowledge/**/*.md                              15 documents
   │
   ▼  loader (Stage 2) — front matter → validated metadata
KnowledgeDocument(metadata, content, source_path)
   │
   ▼  chunker — split on ##; budget = embedder.max_tokens
   │            oversized sections split; tables keep their header
   │            each chunk prefixed "Title — Heading" for embedding
Chunk × 115                                         max 251 / 256 tokens
   │
   ▼  embed_chunks — one batched call, L2-normalised
EmbeddedChunk × 115                                 (115, 384) float32
   │
   ▼  InMemoryVectorStore.save()
data/vectorstore/  vectors.npy · chunks.json · manifest.json
                   manifest pins model id + dimension + corpus fingerprint

RETRIEVAL (per question — no LLM involved)

Question
   │
   ▼  embedder.embed_query          SAME model as indexing (manifest-enforced)
Query vector (384,)
   │
   ▼  metadata pre-filter (optional)   domain / component / doc_type / version
   ▼  cosine = matrix @ query          one BLAS matvec
   ▼  top-k via argpartition
   ▼  min_score floor ── below ──▶ EMPTY RESULT → agent must refuse (Stage 5)
RetrievalResult(chunks, sources, candidates_considered, min_score, top_score)
   │
   └──▶ logs/app.log  "rag.retrieved"

MCP TOOLS (Stage 6 — live information, kept separate from documentation)

Question
   │
   ▼  select_tools            tool_policy.py — identifiers, not topics
   │                          PREFIX-NNNN · TXN-YYYYMMDD-NNNNNN ·
   │                          dotted.config.key · a component name
   │                          max 4 calls, deterministic order
   │
   ├── no identifier ──▶ no tool call (the common case, not a failure)
   └── identifier    ──▶ ToolRegistry.invoke_all()
                              │
        ┌─────────────────────┼─────────────────────┬───────────────┐
        ▼                     ▼                     ▼               ▼
  get_system_          check_transaction_    get_component_    look_up_
  configuration        status                status            error_code
        ▼                     ▼                     ▼               ▼
  retrieve_system_     check_service_        (each tool owns its own synthetic
  version              health                 dataset; pure — no clock, no I/O)
        │
        ▼
  ToolResult × n    tool · ok · summary · data · observed_at · source
        │
        ├──▶ logs/app.log  "mcp.tool_called"   tool + argument NAMES only —
        │                                       never argument values or payloads
        ▼
  (into the GENERATION block below, in its OWN fence)

  ok=False is a FINDING, not an error: "no transaction has that reference" is
  a true answer. A malformed call raises instead. A DOWN service is ok=True.

MCP PROTOCOL SERVER (the same tools, over the wire)

  any MCP client ──stdio JSON-RPC──▶ app/mcp/server.py ──▶ the SAME ToolRegistry
                                     (no tool logic, no data of its own)
  python -m app.mcp serve

AGENT (Stage 5, extended in Stage 6 — the seam across rag/, mcp/ and llm/)

Question
   │
   ▼  KnowledgeAgent.ask        blank ──▶ ValueError, nothing is called
   ▼  decide                    AgentDecision(retrieve, tools, reason, explanation)
   │
   ├── retrieve=False ──▶ empty RetrievalResult      no embedding, no search
   │   "no_searchable_content"                       e.g. "!!! ???"
   ├── retrieve=True  ──▶ Retriever.retrieve()       DOCUMENTATION
   └── tools=(...)    ──▶ ToolRegistry.invoke_all()  LIVE READINGS
   │
   ▼  LLMService.answer(question, retrieval, tool_results)
   ▼
AgentAnswer   text · sources · decision · RetrievalSummary
              · ToolCallSummary × n (safe to log — argument NAMES only)
              · ToolResult × n      (full, for display — never logged)
              · used_live_information
   │
   └──▶ logs/app.log  "agent.answered"   route, counts, top score, document ids,
                                         tool names — never the question,
                                         passages, tool payloads or answer text

GENERATION (Stage 4, extended in Stage 6 — TWO fences, one escaping function)

RetrievalResult + ToolResult × n
   │
   ▼  select_context      max 5 passages / 12,000 chars; dropped WHOLE, never cut
   │                      NEITHER kind of evidence ──▶ refuse, NO provider call
   ▼  build_request       frozen system prompt v1.1.0
   │                      + <retrieved_documentation> fenced, numbered, escaped
   │                      + <tool_results>            fenced, numbered, escaped
   │                        ^^ the SAME _fence_safe; one _DELIMITERS tuple
   │                      + the question, last and outside both fences
CompletionRequest         system · messages · max_tokens      (no sampling params)
   │
   ▼  LLMProvider.complete()          ← the seam; no vendor above this line
   │        └── MockLLMProvider       deterministic, in-process, free
LLMResponse               text · stop_reason · usage · provider/model id
   │
   ▼  validate            refusal / max_tokens / empty  ──▶ RAISE, never shown
GroundedAnswer            text + sources + chunks_used + tools_used
   │                      + llm_called + prompt_version
   └──▶ logs/app.log  "llm.answered"   shape and cost only — never the prompt or
                                       the answer, both of which embed content

  Documentation cites as [1][2]; tool readings cite as [T1][T2]. They are kept
  apart because they can DISAGREE — a documented default of 500.00 against an
  effective 250.00 — and that disagreement is usually the answer.

HTTP (unchanged from Stage 1 — the agent is reachable from the CLI only; wiring it
to an endpoint is Stage 9)
GET /health → FastAPI router → HealthResponse
```

### Components implemented

| Component | Responsibility |
|---|---|
| `app/main.py` | App factory, router mounting, lifespan logging |
| `app/core/config.py` | Typed, frozen, env-based `Settings`; cached `get_settings()` |
| `app/core/logging.py` | structlog + stdlib bridge; app sink and separate trace sink |
| `app/core/tracing.py` | `@traced` / `@traced_async` structured trace decorators |
| `app/api/dependencies.py` | `SettingsDep` — resolves settings from `app.state` |
| `app/api/routes/health.py` | `GET /health` liveness endpoint |
| `app/knowledge/models.py` | `DocumentMetadata`, `KnowledgeDocument`, `Domain`, `DocType` |
| `app/knowledge/loader.py` | Front-matter parsing, validation, corpus loading |
| `app/rag/models.py` | `Chunk`, `EmbeddedChunk`, `ScoredChunk`, `RetrievalResult` |
| `app/rag/chunker.py` | `split_sections`, `chunk_document`, `chunk_documents` |
| `app/rag/embeddings.py` | `Embedder` protocol, sentence-transformers + hashing impls |
| `app/rag/vectorstore.py` | `VectorStore` protocol, `InMemoryVectorStore`, persistence |
| `app/rag/retriever.py` | `Retriever.retrieve` / `retrieve_many` |
| `app/rag/pipeline.py` | `build_index`, `load_retriever`, `get_retriever`, fingerprint |
| `app/rag/__main__.py` | CLI: build / search / demo / calibrate |
| `app/llm/models.py` | `CompletionRequest`, `LLMResponse`, `TokenUsage`, `GroundedAnswer` |
| `app/llm/base.py` | `LLMProvider` protocol + the six-type error taxonomy |
| `app/llm/prompts.py` | Versioned instructions, context budget, fencing and escaping |
| `app/llm/mock.py` | `MockLLMProvider` — the only provider that ships |
| `app/llm/service.py` | `LLMService.answer` — inject, generate, validate, attribute |
| `app/llm/factory.py` | `get_provider`, `get_llm_service` — configuration → provider |
| `app/llm/__main__.py` | CLI: prompt / ask / demo |
| `app/mcp/models.py` | `ToolSpec`, `ToolResult`, `ToolInvocation`, the closed `ToolName` |
| `app/mcp/base.py` | `Tool` protocol + `ToolError` taxonomy + argument helpers |
| `app/mcp/registry.py` | `ToolRegistry` — register / specs / call / invoke_all |
| `app/mcp/factory.py` | `get_tool_registry` — explicit registration of all six |
| `app/mcp/server.py` | The real MCP server over stdio; a wrapper on the registry |
| `app/mcp/__main__.py` | CLI: list / call / demo / serve |
| `app/mcp/tools/*.py` | Six tools, one per module, each owning its synthetic data |
| `app/agent/tool_policy.py` | `select_tools` — which tools, with which arguments |
| `app/agent/models.py` | `AgentDecision`, `RetrievalSummary`, `ToolCallSummary`, `AgentAnswer` |
| `app/agent/policy.py` | `decide` — search? tools? neither? |
| `app/agent/agent.py` | `KnowledgeAgent.ask` — decide, retrieve, call tools, generate |
| `app/agent/factory.py` | `get_agent` — composition from configuration |
| `app/agent/__main__.py` | CLI: ask / demo |
| `app/llm/anthropic_provider.py` | Anthropic adapter — **paid**; one of two vendor modules |
| `app/llm/openai_provider.py` | OpenAI adapter — **paid**; the other |

### Important design decisions (Stage 5 — Checkpoint B)

Summary only — the **full reasoning, with rejected alternatives, is in
`docs/architecture-guide.html` §20.6–§20.9**, which is the authoritative record.

| Decision | Reasoning (short) |
|---|---|
| **Two adapters, not one; no vendor chosen** (5.6) | One adapter proves an adapter can be written; two prove the *abstraction*. Writing the second is what forces the first's assumptions out of shared code — the two APIs disagree on system-prompt placement, the token-ceiling parameter, stop reasons, where a refusal is reported, how text is returned and every usage field name. It also closes the vendor question instead of leaving it to return at Stage 9 and Stage 14 |
| **Default stays `mock`; four independent guards** (5.7) | Spending needs two deliberate acts. The provider default is the guard that does not depend on the environment — "the key isn't set" fails the moment a contributor exports one for another project. `demo` refuses rather than warns because it is 7 calls with no undo; `ask` warns because 1 is proportionate |
| **AST guard narrowed, not deleted** (5.8) | Adding adapters is exactly when that guard starts earning its keep. Explicit two-name allow-list, everything else default-denied. Narrowing also exposed a real bug: the old substring match on `"import anthropic"` would have failed the factory's own honest `from app.llm.anthropic_provider import …`, and the tempting fix was to hide the import behind `importlib` — defeating the guard to satisfy it. The test was wrong; the test was fixed |
| **`LLMConnectionError` added to the taxonomy** (5.9) | Stage 4 wrote the taxonomy with nothing to test it against and left a gap: no retryable type for a connection failure or a 5xx. Both mappings available were wrong in the one field callers read. A concrete adapter found it in an hour; a mock never could |

### Important design decisions (Stage 5 — Checkpoint A)

Summary only — the **full reasoning, with rejected alternatives, is in
`docs/architecture-guide.html` §20.5**, which is the authoritative record.

| Decision | Reasoning (short) |
|---|---|
| **The decision has one substantive branch, and says so** (5.1) | Retrieval is the agent's only evidence until Stage 6, so "always yes" is the honest answer. A keyword classifier fails in both directions — *"why did the withdrawal reverse?"* has no keyword and retrieves fine; *"what is a payment in cricket?"* has one and shouldn't. The floor already answers relevance, with calibration behind it |
| **One refusal path, and it is Stage 4's** (5.2) | The refusal sentence is load-bearing: the API, the web UI and Stage 11 all detect "no answer" by matching it exactly. A second branch is a second thing that must agree, and drift would be invisible until a harness stopped counting refusals |
| **Execution record is a returned value, not a log line** (5.3) | `prompt.md` §15 requires the interface to show what happened. If it only exists in `app.log`, Stage 9 parses its own logs to render a page. Summary and passages are split on a *security* line: shape is safe to log and display, document text is not |
| **A provider failure raises; it never becomes a refusal** (5.4) | An agent that never fails sounds good and is a defect. "Undocumented" means *write the document*; "timeout" means *fix the provider*. Collapsing them also folds infrastructure noise into the grounding metric |
| **The agent is a seam, not a layer of logic** (5.5) | The retriever still has no LLM dependency and the service still does not retrieve. Absorbing either job would end that separation exactly when it became useful — and injection is what keeps 104 agent tests offline and free |

### Important design decisions (Stage 4)

Summary only — the **full reasoning, with rejected alternatives, is in
`docs/architecture-guide.html` §20.4**, which is the authoritative record.

| Decision | Reasoning (short) |
|---|---|
| **No concrete provider in Stage 4** (4.1) | An abstraction is proved by what it is independent of. Everything the stage must show is exercisable without a vendor — and it makes the no-paid-call property *structural*: no code path calls anything |
| **An unavailable provider raises** (4.2) | The alternative failure — an app that starts, answers, and looks healthy while running a stub — is the one nobody notices |
| **Passages fenced, escaped, declared untrusted** (4.3) | Without the escaping step the fence is theatre: a document containing the closing tag would break out of it. Written while the corpus is synthetic and the risk is nil, because the day a real document arrives the architecture must already be right |
| **No evidence → no model call** (4.4) | A generation with zero context can only refuse or invent. Removing the request removes the only path to an ungrounded answer — and is free, fast and deterministic |
| **Truncated / refused generations raise** (4.5) | A cut-off answer about a transaction limit reads as complete. An error is loud and recoverable; a plausible half-sentence is neither |
| **Error taxonomy at the seam, not in adapters** (4.6) | Callers need one distinction — retry or broken. Vendor hierarchies leaking upward would put an SDK's name in every call site |
| **Passages dropped whole, never truncated** (4.7) | Half a configuration table reads as complete and is wrong. A single oversized passage is always kept, so a budget can never turn a valid answer into a refusal |
| **`SecretStr` API key, provider-neutral name** (4.8) | "Never log secrets" enforced by the type, not by memory — and asserted in the suite. No fall-through to an SDK's ambient variable, which would turn a config mistake into a silent paid call |
| **No sampling params; messages already a tuple** (4.9) | Opposite calls, deliberately: sampling is omitted (several current models reject it, and faithfulness beats variety here) while the message tuple is paid for now so Stage 8 appends rather than reshapes every call site |

### Important design decisions (Stage 3)

Summary only — the **full reasoning, with rejected alternatives, is in
`docs/architecture-guide.html` §20**, which is the authoritative record.

| Decision | Reasoning (short) |
|---|---|
| **Local `all-MiniLM-L6-v2`** over a hosted embedding API | Free, offline, no key, no data leaves the machine. A hosted API is a paid per-query call and needs explicit sign-off |
| **Embeddings over lexical TF-IDF** | Paraphrase: *"money left the account but no cash came out"* must find *"Troubleshooting a Failed Cash Withdrawal"*. Lexical cannot |
| **Split on `##` headings** | The author already marked where topics change. Measured: 108 sections, 32–411 tokens, median 99 — already chunk-sized |
| **Budget in the model's tokens, never words** | Measured 1.13–2.82 tokens/word; one 146-word section = 411 tokens. MiniLM truncates **silently** at 256, so a word budget would have amputated the densest sections invisibly |
| **Tables split row-wise, header repeated** | 6 sections exceed the window, mostly config-key/error-code tables. A table fragment without its header is unreadable |
| **`embedding_text` ≠ `content`** | A chunk about reversals never says "ATM". A `"Title — Heading"` prefix restores the entity names without polluting the cited text |
| **Brute-force NumPy, not FAISS/Chroma** | 115×384 is one BLAS matvec. ANN trades recall for scaling that is not needed. The protocol makes it replaceable |
| **Cosine via normalised dot product** | MiniLM is trained with a cosine objective — the metric the space was built for, not merely convenient |
| **Pre-filter, not post-filter** | Post-filtering top-k can return zero results despite ample matching material |
| **min_score = 0.25, calibrated** | Measured: on-topic min 0.388, off-topic max 0.122, midpoint 0.255. Without a floor, an off-topic question still yields five banking passages |
| **Index is an offline build artefact** | Startup stays fast, replicas share one index, and a document edit is not invisible until restart. Git-ignored: it is derived, not source |
| **Manifest pins model + fingerprint** | Both failure modes are *silent* — a foreign model returns plausible nonsense; a stale index returns fluent, resolvable, outdated answers |
| **Two embedders behind one protocol** | Fast offline tests, and it *proves* the decoupling rather than claiming it. A mock would prove neither |

---

## Files

### Added in Stage 11 (11 files, committed)

`app/eval/__init__.py` · `app/eval/dataset.py` · `app/eval/metrics.py` · `app/eval/runner.py` ·
`app/eval/report.py` · `app/eval/__main__.py` · `data/eval/questions.yaml` ·
`tests/test_eval_dataset.py` (23) · `tests/test_eval_metrics.py` (29) · `tests/test_eval_runner.py`
(19) · `tests/test_eval_integration.py` (6, `integration`).

### Modified in Stage 11 (5 files, committed)

`app/core/config.py` (`eval_dataset_path`) · `.env.example` (`BKA_EVAL_DATASET_PATH`) ·
`README.md` (Status, Run, Test count, new Evaluation section, Configuration, Structure, Engineering
Focus) · `docs/architecture-guide.html` (§14 rows + evaluation note + counts; §20.38–§20.42) ·
`docs/HANDOVER.md`.

### Added in Stage 10 (4 files, committed)

`app/core/observability.py` · `app/api/middleware.py` · `app/api/routes/metrics.py` ·
`tests/test_observability.py` (35).

### Modified in Stage 10 (12 files, committed)

`app/main.py` · `app/rag/retriever.py` · `app/llm/service.py` · `app/mcp/registry.py` ·
`app/mcp/base.py` · `app/mcp/models.py` · `app/agent/agent.py` · `app/conversation/service.py` ·
`tests/test_mcp_tools.py` · `README.md` · `docs/architecture-guide.html` (§13 rewritten; §2, §3,
§4, §5, §9, §11, §14, §16, §19 rows; §20.32–§20.35) · `docs/HANDOVER.md`.

### Added in Stage 9 (6 files, committed)

`app/api/routes/conversation.py` · `app/web/static/index.html` · `app/web/static/app.js` ·
`app/web/static/styles.css` · `tests/test_api_conversation.py` (31) ·
`tests/test_conversation_concurrency.py` (3).

### Modified in Stage 9 (committed)

`app/main.py` · `app/api/dependencies.py` · `app/conversation/service.py` · `README.md` ·
`docs/architecture-guide.html` (§11 API layer rewritten, §20.28–§20.31, stale Stage 9
mentions) · `docs/HANDOVER.md`.

### Added in Stage 8 (9 files, committed in `2abbb39`)

`app/conversation/__init__.py` · `models.py` · `context.py` · `store.py` · `service.py` ·
`factory.py` · `tests/test_conversation_context.py` (24) · `tests/test_conversation_store.py`
(22) · `tests/test_conversation_service.py` (34).

### Modified in Stage 8 (NOT committed)

`app/llm/prompts.py` · `app/llm/service.py` · `app/agent/agent.py` ·
`app/agent/__main__.py` · `app/core/config.py` · `.env.example` · `README.md` ·
`docs/architecture-guide.html` (§1 table, §7 Stage 8 subsection, §7 "not here" row, §12,
§14 count, §18 row, §20.23–§20.27) · `docs/HANDOVER.md`.

### Committed separately — instruction-file restructuring (`d47f522`, pushed)

`CLAUDE.md` (new, sole authority) · `docs/PROJECT_PLAN.md` (new, verbatim stage detail) ·
`.gitignore` (+ `ai-dev-token-efficiency-workflow.md`). `prompt.md` and `ccp.txt` moved to
`docs/legacy/` (git-ignored, not committed).

### Added in Stage 7 (1 file, committed in `a3728d9`)

| File | Purpose |
|---|---|
| `tests/test_agent_decisions.py` (104) | One class per §15 path, the plan, the refinement rules, the selector, the decision record, construction, and the rules-only boundary |

### Modified in Stage 7 (12 files, NOT committed)

| File | Change |
|---|---|
| `app/agent/tool_policy.py` | Rewritten: `ToolSelector` + `RuleToolSelector`; `select_tools` removed |
| `app/agent/policy.py` | Rewritten: plan, refinement, step records, conclusion |
| `app/agent/models.py` | `DecisionReason` 3 → 6; `DecisionStep`; `passes`; `decisions` |
| `app/agent/agent.py` | Orchestration of the five paths; `selector=`; merge |
| `app/agent/__main__.py` | Route display; retrieve-more demo questions |
| `app/agent/__init__.py` | Exports |
| `app/core/config.py` | `agent_confident_score` |
| `app/llm/mock.py` | `[T1]` citations for tool results |
| `.env.example` | `BKA_AGENT_CONFIDENT_SCORE` |
| `tests/test_agent.py` | Boundary guards moved forward to Stage 7 (six values; tool-only branch now exists); two wiring tests given `agent_confident_score=0.0` (§7.D) |
| `tests/test_mcp_agent.py` | Routing tests reach the same assertions through `RuleToolSelector`; the no-registry test rewritten for the §7.C contract change, plus a new selector-without-registry test |
| `README.md` · `docs/HANDOVER.md` | Documentation |

> **In the working tree but NOT part of Stage 7:** `docs/improve.md` (untracked) and the
> readability rewording in `docs/architecture-guide.html` — both from the separate
> "Improve.md" session. Whether they go into the Stage 7 commit, a separate commit, or
> neither is the user's decision.

### Added in Stage 6 (20 files, committed in `93eeb22`)

| File | Purpose | Written by |
|---|---|---|
| `app/mcp/__init__.py` | Package exports and the layer overview docstring | main session |
| `app/mcp/models.py` | `ToolSpec`, `ToolResult`, `ToolInvocation`, `ToolName`, `TOOL_FAILURE_CODES` | main session |
| `app/mcp/base.py` | `Tool` protocol, `ToolError` taxonomy, argument helpers | main session |
| `app/mcp/registry.py` | `ToolRegistry` — the MCP layer the agent talks to | main session |
| `app/mcp/factory.py` | `build_tool_registry` / `get_tool_registry` | main session |
| `app/mcp/server.py` | The real MCP server over stdio, on the official SDK | main session |
| `app/mcp/__main__.py` | CLI: list / call / demo / serve | main session |
| `app/mcp/tools/__init__.py` | Tool exports + why there is no shared fixture module | main session |
| `app/mcp/tools/system_configuration.py` | `get_system_configuration` | **sub-agent 1** |
| `app/mcp/tools/transaction_status.py` | `check_transaction_status` | **sub-agent 2** |
| `app/mcp/tools/component_status.py` | `get_component_status` | **sub-agent 3** |
| `app/mcp/tools/error_code.py` | `look_up_error_code` | **sub-agent 4** |
| `app/mcp/tools/system_version.py` | `retrieve_system_version` | **sub-agent 5** |
| `app/mcp/tools/service_health.py` | `check_service_health` | **sub-agent 6** |
| `app/agent/tool_policy.py` | `select_tools` — route on identifiers, not topics | main session |
| `tests/test_mcp_registry.py` (44) | Tool contract, registry, error taxonomy, closed failure vocabulary | main session |
| `tests/test_mcp_tools.py` (43) | The six tools + the cross-tool consistency guards | main session |
| `tests/test_mcp_injection.py` (23) | Hostile tool results cannot break either fence | main session |
| `tests/test_mcp_agent.py` (51) | Routing, wiring, documentation-vs-live, the execution record | main session |
| `tests/test_mcp_server.py` (12) | The real MCP protocol, over an in-memory client session | main session |

> **Exactly one sub-agent file was edited afterwards by the main session**, at
> integration: `service_health.py`, to carry a per-service `reported_version` instead of
> the platform line — in the payload, and then in the summary prose, which the first
> attempt at the fix missed. The other five ship exactly as delivered.

### Modified in Stage 6 (14 files, committed in `93eeb22`)

| File | Change |
|---|---|
| `app/llm/prompts.py` | `<tool_results>` fence; four delimiters added to the **same** `_DELIMITERS`; `render_tool_results`; `[T1]` citations; two new system-prompt rules; version `1.0.0` → `1.1.0` |
| `app/llm/service.py` | `answer()` takes `tool_results`; the refusal guard now asks for evidence of *either* kind |
| `app/llm/models.py` | `GroundedAnswer.tools_used`, counted separately from `chunks_used` |
| `app/agent/models.py` | `DecisionReason` extended; `AgentDecision` (alias `RetrievalDecision`); `ToolCallSummary`; `AgentAnswer.tools` / `.tool_results` / `.used_live_information` |
| `app/agent/policy.py` | `decide()` (alias `decide_retrieval`); the tool branch |
| `app/agent/agent.py` | `tools` injected (default `None`); `_run_tools()`; tool record on the answer; tool names in the log line |
| `app/agent/factory.py` | Two lines: `tools=get_tool_registry()` |
| `app/agent/__main__.py` | Five tool questions in `demo`; `[T1]` tool activity rendered |
| `tests/conftest.py` | New `tool_registry` and `tool_agent` fixtures |
| `tests/test_agent.py` | Two Stage 5 boundary guards moved forward one stage (they fired as designed), plus a new guard that there is still no tool-only branch |
| `requirements.txt` | `mcp==1.12.4`, pinned **down**, with the reason |
| `README.md` · `docs/architecture-guide.html` · `docs/HANDOVER.md` | See below |

> `app/core/config.py` and `.env.example` are **unchanged**. Stage 6 adds no
> configuration surface at all: there is no `BKA_MCP_*` variable, because every tool is
> synthetic and in-process and a knob for choosing between them would be inventing
> configuration for a system that does not exist yet.

### Documentation changed in Stage 6

| File | Change |
|---|---|
| `docs/architecture-guide.html` | §8 **MCP flow** rewritten as BUILT (two layers, the six tools, the documentation-vs-live separation, the error contract, the injection defence, the commands); new **§21 — how the parallel sub-agent build actually worked**, written as personal reference; §20.10–§20.16 (seven decision records); plus §1 stage table, §2 structure, §4 components, §5 data flow, §14 testing, §16 security, §18 extension points, header and footer |
| `README.md` | Status, stack (`mcp` and why it is pinned down), layout, test count, and a new **MCP tools** section — including one factual line recording that parallel sub-agent development was used |
| `docs/HANDOVER.md` | This file, updated continuously: §6.A–§6.F were written **before** any code |

### Added in Stage 5 Checkpoint B (3 files, committed in `6ebe947`)

| File | Purpose |
|---|---|
| `app/llm/anthropic_provider.py` | Anthropic adapter — request/response/error translation |
| `app/llm/openai_provider.py` | OpenAI adapter — the same seam, a different vendor |
| `tests/test_llm_adapters.py` | 99 tests — both adapters, offline against a fake client |

### Modified in Stage 5 Checkpoint B (8 files, committed in `6ebe947`)

| File | Change |
|---|---|
| `app/llm/base.py` | Added `LLMConnectionError` (retryable) — the gap the adapters exposed |
| `app/llm/factory.py` | 3 providers, `PAID_PROVIDERS`, `is_paid_provider()`, deferred SDK import |
| `app/llm/__init__.py` | Exports `LLMConnectionError`; docstring rewritten for two adapters |
| `app/llm/__main__.py` | Paid-provider warning; `demo --paid` guard |
| `app/agent/__main__.py` | Paid-provider warning; `demo --paid` guard |
| `app/core/config.py` | Comments only — `llm_provider`, `llm_api_key`, transport |
| `requirements.txt` | `anthropic==1.4.0`, `openai==3.11.0`, pinned, with a no-spend note |
| `.env.example` | LLM and secrets sections rewritten for three providers |
| `tests/test_llm_provider.py` | Guard narrowed to seam modules; new no-paid-call-by-default class |
| `README.md` | Status, stack, layout, test count, new "LLM providers" section |
| `docs/architecture-guide.html` | §20.6–§20.9 added; §2, §3, §4, §9, §12, §14, §16, §19 |
| `docs/HANDOVER.md` | This file |

> The venv gained `anthropic`, `openai` and 5 transitive packages
> (`httpx2`, `httpcore2`, `jiter`, `docstring-parser`, `truststore`). This is a package
> download, not an API call — the same category as Stage 3's model download.

### Added in Stage 5 Checkpoint A (8 files, committed in `1478631`)

| File | Purpose |
|---|---|
| `app/agent/__init__.py` | Package exports and the layer overview docstring |
| `app/agent/models.py` | `RetrievalDecision`, `RetrievalSummary`, `AgentAnswer` |
| `app/agent/policy.py` | `decide_retrieval` + the reasoning against a classifier/router |
| `app/agent/agent.py` | `KnowledgeAgent` — the seam between `rag/` and `llm/` |
| `app/agent/factory.py` | `get_agent` |
| `app/agent/__main__.py` | CLI: ask / demo |
| `tests/test_agent.py` | 77 tests — policy, wiring, both refusal routes, record, errors |
| `tests/test_agent_integration.py` | 27 tests — real model, the 5 seed questions + controls |

### Modified in Stage 5 Checkpoint A (4 files, committed in `1478631`)

| File | Change |
|---|---|
| `tests/conftest.py` | `KnowledgeAgent` import; new `agent` fixture |
| `README.md` | Status, architecture, layout, test count, new "Knowledge agent" section |
| `docs/architecture-guide.html` | §7 rewritten as BUILT; §20.5 added (5 records); §1, §2, §4, §5, §14, §16, header, footer |
| `docs/HANDOVER.md` | This file |

> `requirements.txt`, `app/core/config.py` and `.env.example` are **unchanged** by
> Checkpoint A. The agent added no dependency and no setting — it composes what Stages 3
> and 4 already configured, which is the point of it being a seam.

### Added in Stage 4 (11 files, committed in `bee4b22`)

| File | Purpose |
|---|---|
| `app/llm/__init__.py` | Package exports and the layer overview docstring |
| `app/llm/models.py` | `CompletionRequest`, `LLMResponse`, `TokenUsage`, `GroundedAnswer` |
| `app/llm/base.py` | `LLMProvider` protocol; six-typed errors with `retryable` |
| `app/llm/prompts.py` | System instructions v1.0.0, budget, fencing, escaping |
| `app/llm/mock.py` | `MockLLMProvider` — synthesise / script / raise, records calls |
| `app/llm/service.py` | `LLMService.answer` — the orchestration |
| `app/llm/factory.py` | `get_provider`, `get_llm_service`, `AVAILABLE_PROVIDERS` |
| `app/llm/__main__.py` | CLI: prompt / ask / demo |
| `tests/test_llm_prompts.py` | 38 tests — instructions, budget, rendering, injection |
| `tests/test_llm_provider.py` | 61 tests — protocol, errors, mock, factory, no-network |
| `tests/test_llm_service.py` | 46 tests — injection, refusal, errors, provenance |

### Modified in Stage 4 (7 files, committed in `bee4b22`)

| File | Change |
|---|---|
| `app/core/config.py` | 7 LLM settings; `SecretStr` import |
| `.gitignore` | `prompt1.md` added beside `prompt.md` — see the Git section |
| `.env.example` | New LLM section; the secrets section rewritten |
| `tests/conftest.py` | `llm_settings`, `mock_provider`, `llm_service`, `retrieval`, `empty_retrieval` |
| `README.md` | Status, layout, configuration table, new "LLM abstraction" section, test count |
| `docs/architecture-guide.html` | §9 rewritten; §20.4 added (9 records); §2, §4, §5, §12, §14, §16, §18, §19, stage table, header, footer |
| `docs/HANDOVER.md` | This file |

> `requirements.txt` is **unchanged** — Stage 4 added no dependency. That is a
> consequence of shipping no vendor adapter, and it is worth noticing.

### Added in Stage 3

| File | Purpose |
|---|---|
| `app/rag/__init__.py` | Package exports and the pipeline overview docstring |
| `app/rag/models.py` | `Chunk`, `EmbeddedChunk`, `ScoredChunk`, `RetrievalResult` |
| `app/rag/chunker.py` | Heading-aware, token-budgeted chunking; table splitting |
| `app/rag/embeddings.py` | `Embedder` protocol; sentence-transformers + hashing impls |
| `app/rag/vectorstore.py` | `VectorStore` protocol; NumPy store; persistence + guards |
| `app/rag/retriever.py` | `Retriever` — embed, filter, search, threshold |
| `app/rag/pipeline.py` | `build_index`, `load_retriever`, `get_retriever`, fingerprint |
| `app/rag/__main__.py` | CLI: build / search / demo / calibrate |
| `tests/test_chunker.py` | 36 tests — boundaries, tables, the no-truncation invariant |
| `tests/test_embeddings.py` | 19 tests — the `Embedder` protocol contract |
| `tests/test_vectorstore.py` | 37 tests — ranking, filtering, persistence, guards |
| `tests/test_retriever.py` | 43 tests — end-to-end, threshold, sources, staleness |
| `tests/test_rag_integration.py` | 33 tests — retrieval **quality** with the real model |

### Modified in Stage 3

| File | Change |
|---|---|
| `app/core/config.py` | 8 RAG settings: vectorstore dir, embedding model/device/batch, chunk max/overlap tokens, top-k, min score |
| `requirements.txt` | `sentence-transformers==5.7.0`, `torch==2.14.0`, `numpy==2.5.3` |
| `pyproject.toml` | Registered the `integration` pytest marker; added `--basetemp=.pytest_tmp` (Problems §15) |
| `.env.example` | Documented every new `BKA_*` variable |
| `tests/conftest.py` | Added `rag_settings`, `real_settings`, `corpus`, `retriever` fixtures |
| `README.md` | Status, stack, layout, configuration, new "RAG pipeline" section, test commands |
| `docs/architecture-guide.html` | §1 stages, §2 structure, §3 stack, §4 components, §5 data flow, §6 RAG flow (rewritten with measurements), §10 vector database (rewritten), §12 config, §14 testing, §16 security, §18 extension points, and **new §20 Decision records** |

### Unchanged from Stages 1–2

`app/main.py` · `app/core/logging.py` · `app/core/tracing.py` ·
`app/api/**` · `app/knowledge/**` · `data/knowledge/**` ·
`tests/test_config.py` · `tests/test_health.py` · `tests/test_logging.py` ·
`tests/test_loader.py` · `.gitignore`

---

## Testing

### Result (Stage 11)

**1119 passed** (1042 → 1119, +77) in ~79 s · **77 `integration`** (71 + 6) · `ruff check .` clean
· `mypy` strict clean, 70 source files · `python -m app.eval` exit 0, Result PASS. Red first:
4 collection errors before `app/eval/` existed. Commands: `./.venv/Scripts/python.exe -m pytest`
/ `-m ruff check .` / `-m mypy` / `-m app.eval` (free). `ruff format` applied to the new files only
(repo-wide format still disagrees — problem 17).

### Result (Stage 10 follow-up, committed `42788e8`)

**1042 passed** (1040 → 1042, +2) in ~67 s · 71 `integration` · ruff clean · mypy strict clean,
64 source files. Red first: 2 failed as intended before `app/core/logging.py` changed.

### Result (Stage 10)

**1040 passed** (1005 → 1040, +35) in ~65 s · 71 `integration` · `ruff check .` clean · `mypy`
strict clean, 64 source files. Commands: `./.venv/Scripts/python.exe -m pytest` /
`-m pytest -m integration --collect-only` / `-m ruff check .` / `-m mypy`.

First full run: 1039 passed, 1 failed — `test_the_query_string_is_not_logged` found the query
string in `app.log`, written by the **test client's `httpx` logger**, not by the app. The test
was narrowed to `app.*` loggers and the `httpx` behaviour recorded as unfinished #3.

| Required (`PROJECT_PLAN.md` Stage 10) | Evidence (`tests/test_observability.py`) |
|---|---|
| Request ID | `TestResolveRequestId` (kept / 8 unsafe forms replaced / unique); middleware header generated + echoed + unsafe replaced and never logged; same id on `rag.retrieved`, `llm.answered`, `agent.answered` and the `KnowledgeAgent.ask` trace line; id does not leak past the request |
| Question | `agent.answered` `question_hash == fingerprint(q)`, `question_length`; `rag.retrieved` has no `query`; question text absent from `app.log` and `traces.log` |
| Retrieval / LLM / tool latency | `latency_ms >= 0` on `rag.retrieved`, `llm.answered`, `mcp.tool_called` |
| Retrieved documents · tool calls | Existing `documents` / `mcp.tool_called` fields, unchanged |
| Errors | `http.request_failed` (500, type only, counted); `llm.failed` (type, no provider text, counted); `mcp.tool_failed` (type, no argument values, counted) |
| Overall latency | `http.request` `latency_ms`, method, path, status |
| Metrics | `TestMetrics` (counters, cumulative buckets, copy, negative rejected, 8 threads × 2000 not lost, reset); `GET /metrics` counters + 4 histograms after real questions; no question, identifier or answer text in it |
| No secrets / sensitive data | Query string, question, tool argument values and exception messages asserted absent |

### Result (Stage 9)

**1005 passed** (971 → 1005, +34) in ~63 s · `ruff check .` clean · `mypy` strict clean, 61
source files. Commands: `./.venv/Scripts/python.exe -m pytest` / `-m ruff check .` / `-m mypy`.

| Required (`PROJECT_PLAN.md` Stage 9) | Evidence |
|---|---|
| Question input · conversation display | `TestWebPage` markers; `TestSessions` turns endpoint |
| Answer · sources · tool activity | `TestAsk` — text, sources, full tool results, route + steps |
| Basic error states | 404 unknown/ended session (id never echoed) · 422 blank/missing/extra · 502 tool/LLM with no leaked detail · failed turn not recorded |
| RAG / MCP / sources / insufficient obvious | `rag_used`, `mcp_used`, `sources_consulted`, `insufficient` asserted; page renders each as a badge |
| One service per app (§9.A) | built once and shared; not built by `create_app()` alone |
| Per-session lock (§9.B) | 3 concurrent asks → turns 1,2,3; other sessions not blocked; lock released after failure |

**Live smoke test (FREE — mock provider, real embedding model), 2026-09-14:**
`uvicorn app.main:app` on 127.0.0.1 → health 200 · create 201 (43-char id) · knowledge
question: RAG, 5 sources · `Status of TXN-19990101-000001?`: RAG + MCP · `what about
TXN-19990101-000002?`: `substituted_identifier`, turn 3 · "capital of France": insufficient,
0 sources · turns [1–4] · unknown id 404 · end 204 · `GET /` page 200.

### Result (Stage 8)

**971 passed** (891 → 971, +80) · `ruff check .` clean · `mypy` strict clean, 58 source
files. Commands: `./.venv/Scripts/python.exe -m pytest` / `-m ruff check .` / `-m mypy`;
free manual check `-m app.agent conversation-demo`.

| Required coverage (`PROJECT_PLAN.md` Stage 8) | Evidence |
|---|---|
| Session handling | `test_conversation_store.py` — lifecycle, unknown id raises, isolation, concurrency |
| Context management | `test_conversation_context.py` — all four rules, previous-turn only, answers never read |
| Context limits | window, char budget (oldest dropped whole), TTL, LRU eviction, turn cap |
| Separation from retrieved knowledge | own fence; escaped; standalone sends none; earlier answers and tool results never resent; history is not evidence (refusal, 0 model calls) |
| Follow-up questions | `test_conversation_service.py::TestFollowUps` — pronoun → tool, "is it healthy?", "what about X?", 3-turn chain, topic search |

### Result (Stage 7)

**891 passed, 0 failed** (775 from Stages 1–6, **116 new**: 104 in the new file, 11 real-model
decision-path tests in `test_agent_integration.py`, and one new test in
`test_mcp_agent.py`; four existing tests rewritten for recorded design changes). Runtime ~67 s. `ruff check .` → *All checks passed!* · `mypy` (strict) →
*Success: no issues found in 52 source files*.

> ⚠️ Measured inside the Claude Code session, which is **elevated** (Problems §15).
> Please confirm 891 in your own shell before approving.

| File | Tests | Covers |
|---|---|---|
| `tests/test_agent_integration.py` | 38 (+11) | **The five paths with the real model** — seven measured questions pinned to their route and pass count; a refined search landing above the 0.50 bar it missed; every off-topic control refused after one search with `no_refinement_available` |
| `tests/test_agent_decisions.py` | 104 | **Each §15 path** — knowledge (a confident search is one pass), retrieve-more (weak → refined query, merge dedupes at best score, cap, never a third search, no refinement when the question already names it), tool-only (no search at all, `[T1]` cited, a miss pulls in documentation), both (separate fences, a weak search refined with the tool's component), refuse (after searching and without, one sentence, a tool reading prevents it). **The plan** — seven routed questions, explanation vs reading cues. **Refinement** — tool terms preferred, failed readings ignored, only documented components allowed (a hostile payload cannot reach the query), `Platform` skipped. **The selector** — protocol, spec-driven arguments, registered tools only, loud construction failures, cues, fan-out, cap, order. **The record** — plan first/evidence last, same route same words, no argument value in any step, and the `agent.answered` log line carrying the route but no identifier and no explanation sentence. **Construction** and the **rules-only boundary** |
| `tests/test_agent.py` | 78 | Stage 5 suite. Changed: literal guard → six values; tool-only guard inverted; two wiring tests pinned to a confident first pass |
| `tests/test_mcp_agent.py` | 52 | Stage 6 suite through `RuleToolSelector`; no-registry contract rewritten; selector-without-registry added |

### Commands used (Stage 7)

```bash
./.venv/Scripts/python.exe -m pytest                                  # 891 passed, ~67 s
./.venv/Scripts/python.exe -m pytest tests/test_agent_decisions.py    # 104 passed
./.venv/Scripts/python.exe -m pytest tests/test_agent_integration.py  # 38 passed (real model)
./.venv/Scripts/python.exe -m ruff check .                            # All checks passed!
./.venv/Scripts/python.exe -m mypy                                    # 52 source files
./.venv/Scripts/python.exe -m app.agent demo                          # free: mock + local model
```

### Verified by hand (2026-09-14) — real embedding model, mock provider, FREE

```
§15 path          question                                         route
knowledge         What component handles card authentication?      plan=knowledge_required → retrieve_more=not_needed
                                                                   1 search · top 0.804
retrieve more     Why did the withdrawal reverse?                  plan=knowledge_required → retrieve_more=performed
                                                                   decision additional_knowledge_required · 2 searches · top 0.640
tool only         Is CoreBankingAdapter healthy?                   plan=live_status_only → consult_documentation=not_needed
                                                                   retrieval not performed · [T1] status · [T2] health
tool miss → both  Status of TXN-19990101-000001?                   plan=live_status_only → consult_documentation=performed
                                                                   → retrieve_more=performed · 2 searches · top 0.572
both              What does error code LIM-4001 mean?              plan=knowledge_and_live_status_required · top 0.669
both + refine     What does SWX-7004 mean?                         retrieve_more=performed · 2 searches · top 0.603
refuse            What is the capital of France?                   plan=knowledge_required → no_refinement_available
                                                                   decision insufficient_evidence · 0 model calls
refuse            !!! ???                                          plan=no_searchable_content · 0 searches · 0 calls
```

**No live API call was made.** `BKA_LLM_PROVIDER` unset → mock; no `.env` file exists.

### Stage 7 required coverage (`prompt.md` §15)

| Requirement | Status |
|---|---|
| Answer from knowledge | ✅ `knowledge_required` |
| Retrieve additional knowledge | ✅ `additional_knowledge_required` — one refined search, measured threshold |
| Call an MCP tool | ✅ `live_status_only` — no search at all |
| Use both | ✅ `knowledge_and_live_status_required` |
| Refuse when evidence is insufficient | ✅ `insufficient_evidence` / `no_searchable_content`, through Stage 4's single guard |
| Clear tool-selection behaviour | ✅ `RuleToolSelector`, spec-driven, loud at construction |
| No hidden chain-of-thought | ✅ `DecisionStep` = rule outcome + fixed sentence; asserted identical for identical routes |
| Expose retrieval performed · documents · tool · tool result · answer | ✅ `retrieval` · `retrieval.documents` + `sources` · `tools` · `tool_results` · `text`, plus `decision` and `decisions` — asserted together in one test |
| Tests for each decision path | ✅ One class per path in `test_agent_decisions.py` |
| Handover updated, mid-stage decisions included | ✅ §7.A–§7.D written before code |
| Guide tool-selection reasoning (chosen / rejected / why) | ✅ Guide §20.17–§20.22 (six records), plus §1, §4, §5, §7, §14, §19, header and footer — written after the other session paused (Problems §19) |
| No sub-agents | ✅ Main session only |
| No paid call | ✅ None |

### Result (Stage 6)

**775 passed, 0 failed** (601 from Stages 1–5, **174 new**: 173 across five new files
plus one new Stage 5 boundary guard). Runtime ~53 s.
`ruff check .` → *All checks passed!*
`mypy` (strict) → *Success: no issues found in 52 source files*

> ⚠️ Measured inside the Claude Code session, which is **elevated** (Problems §15).
> Please confirm 775 in your own shell before approving.

| Stage 6 test file | Tests | Covers |
|---|---|---|
| `tests/test_mcp_registry.py` | 44 | **The contract and the registry.** A tool qualifying structurally with no inheritance; the error taxonomy and its `retryable` flags; the shared argument helpers failing identically for every tool; a duplicate registration refused; an unknown tool naming what *does* exist; an untyped tool exception wrapped with its cause preserved; explicit registration proven by importing a tool module and asserting nothing self-registered. Every spec's JSON Schema typed `string` with `additionalProperties: false`. Ends with the **closed failure vocabulary** — nine miss-paths across all six tools, every code a member of `TOOL_FAILURE_CODES`, at least four distinct |
| `tests/test_mcp_tools.py` | 43 | **The six tools, and the consistency between them.** *Per tool:* purity (same arguments, same result), undeclared arguments rejected, blank required arguments rejected, optional arguments genuinely optional, no credential-shaped field in any payload, and **every documented `example` in every spec actually resolving** — Stage 7 shows those examples to a model as the format to imitate. *Cross-tool:* the three component tools accepting the same nine components and echoing the same canonical spelling; every error code a transaction reports being explainable by the lookup tool; a component's recent codes carrying that component's own prefix; and **the version agreement that encodes the contradiction two sub-agents actually shipped** — asserted on the payload *and* the summary prose, because the first fix updated only the payload. Plus the domain facts each tool exists to get right: the `LIM-4001` → config-key mapping, `PAY-8003` flagged as a wrapper, `SWX-7004` recorded as *being* a reversal rather than triggering one, the effective limit differing from the documented default, the secret refusal not being a component oracle, and health-is-not-status asserted in both directions |
| `tests/test_mcp_injection.py` | 23 | **Stage 4's defence, re-aimed at tool results.** A hostile summary, payload value, payload **key** and error message each failing to close the fence; a tool result failing to forge a *documentation* fence or a passage; every delimiter parametrised; the escape asserted to be **visible** rather than silent; the system prompt asserted to name the tool fence, declare it untrusted and separate designed-behaviour from reported-behaviour; the prompt version asserted to have been bumped; the question asserted to stay outside every fence even under attack. One **structural** test walks the AST of `prompts.py` and requires exactly one escaping function to exist — because two that agree today are two that can drift |
| `tests/test_mcp_agent.py` | 51 | **Routing, wiring and the separation.** An identifier selects the tool that can act on it; plain prose selects none; ordinary text is not mistaken for an error code; a config key with no component is left to documentation; duplicates collapsed; the call count capped; selection deterministic. Then the flow end to end, and §14's requirement asserted **on the real prompt**: documentation and tool results in different fences, documentation first. Then the execution record — including the test that caught a genuine leak, that the loggable summary carries argument *names* and not values. Ends with evidence handling (a successful tool call alone prevents a refusal; nothing at all still refuses with Stage 4's exact sentence) and failures propagating rather than silently dropping the live half of an answer |
| `tests/test_mcp_server.py` | 12 | **The real protocol, not the handler functions.** A genuine client session over the SDK's in-memory transport — real `initialize`, `tools/list`, `tools/call`, real JSON-RPC framing. Every listed tool carries a usable schema; a not-found crosses the wire as a **result** while a malformed call crosses as an **error**; and the point of the whole wrapper: six calls returning payloads *identical* to the in-process registry's. Ends by proving delegation — give the server a one-tool registry and it exposes one tool, and the module is asserted to contain no domain data and to import no tool module |

### Commands used (Stage 6)

```bash
./.venv/Scripts/python.exe -m pytest                          # 775 passed, ~53 s
./.venv/Scripts/python.exe -m pytest tests/test_mcp_*.py      # 173 passed, ~5 s
./.venv/Scripts/python.exe -m ruff check .                    # All checks passed!
./.venv/Scripts/python.exe -m mypy                            # 52 source files

./.venv/Scripts/python.exe -m app.mcp list
./.venv/Scripts/python.exe -m app.mcp demo
./.venv/Scripts/python.exe -m app.agent demo
```

### Verified by hand (2026-09-11)

**The MCP server really is an MCP server.** Driven as a *subprocess* over stdio by a real
`mcp` client — not the in-memory transport the tests use:

```
connected to: banking-knowledge-agent 1.12.4
tools/list -> 6 tools
   - get_system_configuration · check_transaction_status · get_component_status
   - look_up_error_code · retrieve_system_version · check_service_health
tools/call look_up_error_code {"error_code": "SWX-7006"}
   isError = False
   {"data": {"component": "TransactionSwitch", "error_class": "Fault", ...}}
```

**The two tools that once contradicted each other now agree**, all nine components:

```
AuthorizationService  4.2.3 = 4.2.3     DeviceManager       4.2.3 = 4.2.3
CardSecurityModule    4.1.9 = 4.1.9     DigitalGateway      4.2.3 = 4.2.3
ConfigurationStore    4.2.3 = 4.2.3     LimitService        4.2.2 = 4.2.2
CoreBankingAdapter    4.2.3 = 4.2.3     PaymentEngine       4.2.3 = 4.2.3
                                        TransactionSwitch   4.2.3 = 4.2.3
        retrieve_system_version  =  check_service_health
```

**The agent reaches the tools, and keeps the two evidence kinds apart:**

```
python -m app.agent demo   (real corpus, real embedding model, mock provider)

  "What does error code LIM-4001 mean?"
     decision  knowledge_and_live_status_required
     retrieval 5 of 115 passages · top 0.669
     tool      look_up_error_code -> ok
     [1]..[5]  documentation   [T1] live reading

  "Is CoreBankingAdapter healthy?"
     tool      check_service_health -> ok      (probe + dependency checks)
     tool      get_component_status -> ok      (instances, error rate, incident)
     [T1] DEGRADED: /core/v1/health answered in 312.5 ms, failing:
          core_banking_connection_pool
     [T2] DEGRADED: 3/6 instances, 7.40% errors, queue 1874, INC-4417 origin

  "What component handles card authentication?"
     decision  knowledge_required        tools: none — no identifier to act on

  "!!! ???"
     decision  no_searchable_content     REFUSED, zero retriever and provider calls
```

**No live API call was made at any point, and no code path in `app/mcp/` can make one.**

### Stage 6 required coverage (`prompt.md` §14)

| Requirement | Status |
|---|---|
| Introduce MCP | ✅ Both layers: an in-process registry **and** a real `mcp`-SDK server over stdio, verified against a real client |
| Get system configuration | ✅ `get_system_configuration` |
| Check transaction status | ✅ `check_transaction_status` |
| Get component status | ✅ `get_component_status` |
| Look up error code | ✅ `look_up_error_code` |
| Retrieve system version | ✅ `retrieve_system_version` |
| Check service health | ✅ `check_service_health` |
| Synthetic data only | ✅ Each tool reads a dictionary in its own module. No socket, clock or filesystem anywhere in `app/mcp/tools/` — asserted by an AST test |
| Demonstrate Agent → MCP → Tool → Result | ✅ `python -m app.agent demo` and `python -m app.mcp demo`; guide §8.1; asserted in `test_mcp_agent.py` |
| Clearly separate knowledge retrieval from live/tool information | ✅ Separate collection, separate prompt fences, separate citation forms (`[1]` vs `[T1]`), separate answer fields, and `AgentAnswer.used_live_information` |
| Add MCP tests | ✅ 173 new tests across five files, all offline and deterministic |
| Tool results treated as untrusted (carried from Stage 4) | ✅ The **same** fencing and escaping, extended — not a second scheme. 23 dedicated tests |
| Sub-agent build method documented | ✅ `HANDOVER.md` §6.E + integration notes; guide **§21**; one line in `README.md` |
| Handover updated continuously | ✅ §6.A–§6.F written **before** implementation began |
| STAGE COMPLETE report, then STOP | ✅ Below |

### Result (Stage 5 — Checkpoint B)

**601 passed, 0 failed** (489 from Stages 1–5A, **112 new**). Runtime ~52 s.
`ruff check .` → *All checks passed!*
`mypy` (strict) → *Success: no issues found in 37 source files*

> ⚠️ Measured inside the Claude Code session, which is **elevated** (Problems §15).
> Please confirm 601 in your own shell before approving.

| Checkpoint B test file | Tests | Covers |
|---|---|---|
| `tests/test_llm_adapters.py` | 99 | **Both adapters, entirely offline** — every test injects a fake SDK client. **Construction**: a missing key refuses before a client exists; an injected client needs no key; each adapter owns its own default model. **What is sent**: system prompt placement (top-level vs a message), `max_tokens` vs `max_completion_tokens`, the user turn verbatim, and *no* sampling or thinking parameters. **What is parsed**: every stop-reason and finish-reason value including unknown and `None`; a leading thinking block not mistaken for the answer; an OpenAI refusal arriving labelled `"stop"`; null content; a reply with no choices raising; usage translated from differently-named fields; the *answering* model recorded rather than the requested one. **Error translation**: all nine mappings per vendor with the right `retryable` flag, the ordering traps asserted (`APITimeoutError` **is** an `APIConnectionError`), `retry-after` parsed, absent and HTTP-date forms both degrading to `None`, the cause preserved, and a 401 message asserted not to echo the key. **The cost guard**: `demo` refuses before building anything; the free path is not blocked. **The seam is proved**: identical assertions run against *both* adapters, through `LLMService` and through `KnowledgeAgent` |
| `tests/test_llm_provider.py` | 13 changed / added | The guard narrowed to seam modules with an explicit two-name exemption; the seam module names asserted to exist; the factory asserted to *name* vendors while importing none; both adapters asserted free of hardcoded URLs and key literals; and a new `TestNoPaidCallByDefault` class — `mock` is the default with the env var cleared, the registry lists it first, `PAID_PROVIDERS` excludes it, and each paid provider without a key raises naming `BKA_LLM_API_KEY` and the word `PAID` |

### Commands used (Checkpoint B)

```bash
./.venv/Scripts/python.exe -m pytest                            # 601 passed, ~52 s
./.venv/Scripts/python.exe -m pytest tests/test_llm_adapters.py # 99 passed, ~4 s
./.venv/Scripts/python.exe -m ruff check .                      # All checks passed!
./.venv/Scripts/python.exe -m mypy                              # 37 source files
```

### The no-spend properties, verified by hand (2026-09-10)

```
1. default, no env set
   -> llm.provider_selected  paid=False provider=mock
   -> grounded answer, 5 passages, free

2. BKA_LLM_PROVIDER=anthropic, python -m app.agent demo
   -> "!! BKA_LLM_PROVIDER=anthropic - this is a PAID API."
   -> "REFUSED: demo would make up to 7 paid calls. Re-run with --paid"
   -> exit code 2, no agent built, no call made

3. BKA_LLM_PROVIDER=anthropic, python -m app.agent ask "test"   (no key)
   -> warning printed, then LLMConfigurationError:
      "needs BKA_LLM_API_KEY, which is unset ... a real call is a PAID call"
   -> no SDK client was ever constructed

4. env restored
   -> provider = mock | key set = False
```

**No live API call was made at any point.**

### Checkpoint B required coverage (the user's instruction)

| Requirement | Status |
|---|---|
| 1. `AnthropicProvider` using the official `anthropic` SDK | ✅ `app/llm/anthropic_provider.py` |
| 2. `OpenAIProvider` using the official `openai` SDK | ✅ `app/llm/openai_provider.py` |
| 3. Both pinned in `requirements.txt` | ✅ `anthropic==1.4.0`, `openai==3.11.0` |
| 4. Factory + `AVAILABLE_PROVIDERS` accept `anthropic`/`openai`; **default stays `mock`** | ✅ Default unchanged and asserted with the env var cleared |
| 5. `BKA_LLM_API_KEY` environment-only, optional, unset; no key wired in; no live call | ✅ Verified by hand and by test; nothing hardcoded anywhere |
| 6. AST guard **narrowed, not deleted**; seam modules vendor-free; only adapters exempt | ✅ Explicit two-name allow-list, everything else default-denied |
| 6b. Test that `mock` is still the default when `BKA_LLM_PROVIDER` is unset | ✅ `test_mock_is_the_default_provider_when_the_env_var_is_unset` |
| 7. Adapter tests offline; SDK/HTTP mocked; no paid call in CI or here | ✅ 99 tests, fake client injected throughout |
| 8. Guide §20.6 — why two adapters, what/why/rejected | ✅ §20.6, plus §20.7–§20.9 |
| 9. Handover updated, decision recorded as previously deferred → resolved | ✅ *Stage 5 decision* near the top, written **before** any code |
| 10. STAGE COMPLETE report, then STOP | ✅ Below |

---

### Result (Stage 5 — Checkpoint A, for reference)

**489 passed, 0 failed** (385 from Stages 1–4, **104 new**). Runtime ~51 s.
`ruff check .` → *All checks passed!*
`mypy` (strict) → *Success: no issues found in 35 source files*

> ⚠️ **Context this was measured in** (Problems §15 lesson, applied again): run inside
> the Claude Code session, which is **elevated**. `--basetemp=.pytest_tmp` means a
> non-elevated run should behave identically, but the user should confirm 489 passed in
> their own shell before approving.

| Checkpoint A test file | Tests | Covers |
|---|---|---|
| `tests/test_agent.py` | 77 | **The policy** — every seed question retrieves; six no-searchable-content inputs do not; a one-character question still retrieves; blank raises; and the two cases a keyword classifier would get wrong are asserted as passing. **The wiring** — the question reaches the retriever verbatim; one question is exactly one retrieval and one generation; the passages reach the prompt and the knowledge base does not; the agent adds no prompt of its own. **Both refusal routes** — after searching and without searching — producing the identical sentence with **zero** provider calls, and the no-search route making zero *retriever* calls too. **The record** — chunks used never exceeds chunks returned, documents deduplicated, and the summary asserted to contain no passage text. **Errors** — timeout, rate limit, malformed and truncated all propagate; a broken retriever propagates. **The boundary** — no tools, no history, the `DecisionReason` literal pinned to its two Stage 5 values, and an AST walk over `app/agent/` asserting no vendor SDK |
| `tests/test_agent_integration.py` | 27 | **Real model, real corpus.** Each of the five seed questions is answered from its own document, cites that document, and scores > 0.5; all five retrieve and generate. Three off-topic controls are refused *after* being searched, with a provider call count of 0 — the agent does not pre-judge relevance, the calibrated floor does. Two paraphrases with no shared vocabulary still find the right document. One module-scoped index shared across the file; a fresh mock provider per test so call counts stay meaningful (227 s → 18 s) |

### Commands used (Checkpoint A)

```bash
./.venv/Scripts/python.exe -m pytest                          # 489 passed, ~51 s
./.venv/Scripts/python.exe -m pytest tests/test_agent.py      # 77 passed, ~5 s
./.venv/Scripts/python.exe -m pytest tests/test_agent_integration.py  # 27, ~18 s
./.venv/Scripts/python.exe -m ruff check .                    # All checks passed!
./.venv/Scripts/python.exe -m mypy                            # 35 source files

./.venv/Scripts/python.exe -m app.agent demo
./.venv/Scripts/python.exe -m app.agent ask "Why would an ATM transaction fail after card authentication?"
```

### Measured results worth keeping (Checkpoint A)

```
python -m app.agent demo   (real corpus, real embedding model, mock provider)

  seed question                            passages  top score  document (rank 1)
  ATM fail after card auth                  5 / 115    0.790     atm-transaction-lifecycle
  what component handles card auth          5 / 115    0.804     card-authentication
  which API for payment authorisation       5 / 115    0.784     payment-authorisation-api
  troubleshoot a failed cash withdrawal     5 / 115    0.819     atm-cash-withdrawal-troubleshooting
  what config controls transaction limits   5 / 115    0.775     transaction-limits-configuration

  controls
  "What is the capital of France?"   0 / 115 cleared 0.25
                                     REFUSED after searching · provider calls 0
  "!!! ???"                          retrieval not performed
                                     REFUSED without searching · provider calls 0

Note: the card-authentication question cites card-pin-verification at [5] as well —
correct, and visible because the summary deduplicates documents rather than passages.
```

### Checkpoint A required coverage (`prompt.md` §13)

| Requirement | Status |
|---|---|
| Receive a technical question | ✅ `KnowledgeAgent.ask` |
| Determine whether knowledge retrieval is required | ✅ `app/agent/policy.py` → `RetrievalDecision`, returned to the caller. Reasoning and rejected alternatives in guide §20.5.1 |
| Retrieve relevant information | ✅ Stage 3's `Retriever`, injected |
| Pass context to the LLM | ✅ Stage 4's `LLMService`, unchanged |
| Produce a source-backed answer | ✅ `AgentAnswer.sources` + `chunks_used` + prompt version |
| Clearly indicate when information is insufficient | ✅ Two routes, one fixed sentence, both asserted identical |
| Must avoid inventing technical facts | ✅ Three enforcement points: score floor (S3), no-evidence-no-call (S4), system prompt (S4). None is a prompt instruction alone |
| Five example questions | ✅ Worked examples in the CLI demo, the guide §7, the README, and asserted in both test files |
| Agent tests | ✅ 104 new tests, offline, deterministic, free |
| Handover updated | ✅ This file, continuously — the provider decision was written **before** any code |
| Architecture guide §7 + §20.5 | ✅ §7 rewritten as BUILT; §20.5 = five records in the what/why/rejected form |

---

### Result (Stage 4, for reference)

**385 passed, 0 failed** (240 from Stages 1–3, **145 new**). Runtime ~36 s.
`ruff check .` → *All checks passed!*
`mypy` (strict) → *Success: no issues found in 29 source files*

> ⚠️ **Context this was measured in** (Problems §15 lesson): run inside the Claude Code
> session, which is **elevated**. The `--basetemp=.pytest_tmp` fix means a non-elevated
> run should behave identically, but the user should confirm 385 passed in their own
> shell before approving.

| Stage 4 test file | Tests | Covers |
|---|---|---|
| `tests/test_llm_prompts.py` | 38 | System instructions (grounding, citations, the exact refusal sentence, no vendor or proprietary name in the text); context budget (chunk and char limits, order preserved, never truncated, always ≥1 passage); rendering and citation metadata; **injection defence** — attribute escaping and a passage containing the literal closing fence failing to escape it; and the central claim asserted against the real corpus — only selected passages reach the prompt, every other document is absent |
| `tests/test_llm_provider.py` | 61 | Protocol conformance including a structurally-typed implementation that inherits nothing; the full error taxonomy and its `retryable` flags; the mock's three modes and its call recording; the factory refusing an unavailable provider **without falling back**; configuration including a key that appears in neither a repr nor a dump; and an **AST walk over every module in `app/llm/`** asserting no vendor SDK, no HTTP client, no URL |
| `tests/test_llm_service.py` | 46 | What actually reaches the provider (versioned system prompt, question present once, passages fenced, knowledge base absent, budgets honoured); the refusal path making **zero** provider calls; error handling — timeout and rate limit propagate with retry hints, an untyped exception is wrapped with its cause preserved, refused/truncated/empty generations raise; the five seed questions end to end; and the Stage 4/5 boundary — the service does not retrieve |

### Commands used (Stage 4)

```bash
./.venv/Scripts/python.exe -m pytest                        # 385 passed
./.venv/Scripts/python.exe -m pytest tests/test_llm_*.py    # 145 passed, ~4 s
./.venv/Scripts/python.exe -m ruff check .                  # All checks passed!
./.venv/Scripts/python.exe -m mypy                          # 29 source files

./.venv/Scripts/python.exe -m app.llm demo                  # 5 grounded + 1 refusal
./.venv/Scripts/python.exe -m app.llm prompt "What component handles card authentication?"
./.venv/Scripts/python.exe -m app.llm ask "How would I troubleshoot a failed cash withdrawal?"
```

### Measured results worth keeping (Stage 4)

```
python -m app.llm demo   (mock provider, real corpus, real retrieval)

  5 seed questions   → all grounded, 5 of 5 passages used, correct document cited
                       e.g. "troubleshoot a failed cash withdrawal" → all 5 passages
                       from atm-cash-withdrawal-troubleshooting.md
  1 off-topic        → "What is the capital of France?"
                       REFUSED, provider call count = 0

python -m app.llm prompt "What component handles card authentication?"

  system  1,826 characters   (frozen, identical for every request)
  user    3,034 characters   (5 fenced passages + the question)
  Corpus is ~55,000 characters — the prompt carries ~5% of it, and the test suite
  asserts every non-cited document is absent from the prompt.
```

### Stage 4 required coverage (prompt.md §12)

| Requirement | Status |
|---|---|
| LLM service abstraction | ✅ `app/llm/base.py` — `LLMProvider` protocol |
| Not tightly coupled to one provider | ✅ No vendor named anywhere in `app/llm/`; asserted by an AST test |
| Implementation replaceable | ✅ One class + one factory branch; the service, CLI and callers are untouched |
| Prompt management | ✅ `app/llm/prompts.py`, versioned `1.0.0`, recorded on every answer |
| System instructions | ✅ `SYSTEM_INSTRUCTIONS`, frozen and identical per request |
| User question handling | ✅ `build_user_turn`; blank questions rejected before any call |
| Context injection | ✅ Fenced, numbered, labelled, escaped; budgeted |
| Response generation | ✅ `LLMService.answer` → `GroundedAnswer` |
| Error handling | ✅ 6 typed errors; timeouts, rate limits, malformed/truncated/refused responses |
| Environment configuration | ✅ 7 `BKA_LLM_*` settings; key is environment-only `SecretStr` |
| **LLM receives retrieved context, not the whole KB** | ✅ Enforced by two configured limits; asserted against the real corpus |
| Mocked LLM tests | ✅ 145 tests; the suite is offline and free *by construction* |
| Handover updated | ✅ This file, continuously through the stage |
| Architecture guide reasoning (§20) | ✅ §20.4 — nine records in the Stage 3 what/why/rejected form |

---

### Result (Stage 3, for reference)

**240 passed, 0 failed** (72 from Stages 1–2, 168 new). Runtime ~33 s.
`ruff check .` → *All checks passed!*
`mypy` (strict) → *Success: no issues found in 21 source files*

| Test file | Tests | Covers |
|---|---|---|
| `tests/test_config.py` | 6 | Defaults, env overrides, invalid values, caching, immutability |
| `tests/test_health.py` | 5 | 200 + payload, schema, OpenAPI, 404, settings wiring |
| `tests/test_logging.py` | 9 | Disk sinks, trace separation, sync/async paths, arguments never logged |
| `tests/test_loader.py` | 52 | Loader behaviour, failure modes, corpus validity, corpus security |
| `tests/test_chunker.py` | 36 | Heading splitting, H1 dropped, code fences, metadata carried, `content` vs `embedding_text`, oversized splitting, overlap, table header repetition, no row lost, **no chunk over budget** |
| `tests/test_embeddings.py` | 19 | Protocol conformance, width, unit length, float32, determinism, token counting, lazy load, blank-input failure, config selection |
| `tests/test_vectorstore.py` | 37 | Ranking, cosine bounds, k handling, **pre-filter vs post-filter**, duplicate/width rejection, save-load round trip, foreign-model / wrong-dimension / old-format / inconsistent-index refusal |
| `tests/test_retriever.py` | 43 | Whole corpus indexed, unique ids, ordering, top-k, filters, score floor, empty-result reporting, source dedup, persistence, **staleness detection**, fingerprint behaviour |
| `tests/test_rag_integration.py` | 33 | **Real model.** Each of the 5 brief questions retrieves its own document first and scores > 0.5; paraphrases find the right domain; all 5 off-topic questions return nothing; distributions separate and the floor sits between them; no chunk silently truncated |

### Commands used

```bash
./.venv/Scripts/python.exe -m pytest                       # 240 passed
./.venv/Scripts/python.exe -m pytest -m "not integration"  # skip the real model
./.venv/Scripts/python.exe -m ruff check .                 # All checks passed!
./.venv/Scripts/python.exe -m mypy                         # Success: 21 source files

./.venv/Scripts/python.exe -m app.rag build                # Indexed 115 chunks
./.venv/Scripts/python.exe -m app.rag demo                 # representative examples
./.venv/Scripts/python.exe -m app.rag calibrate            # threshold evidence
./.venv/Scripts/python.exe -m app.rag search "what error code means the cassette is empty"
```

### Measured results worth keeping

```
Chunking       15 documents → 108 sections → 115 chunks
               tokens: min 31 · median 104 · mean 116 · max 251   (limit 256, 0 over)
               tokens per word across the corpus: 1.13 – 2.82

Calibration    on-topic  (10 questions)  min 0.388  median 0.775  max 0.819
               off-topic ( 5 questions)  min 0.032  median 0.104  max 0.122
               separation +0.266 · midpoint 0.255 · configured 0.250

Seed questions all 5 retrieve their own document at rank 1:
   ATM fail after card auth        0.790  atm-transaction-lifecycle
   what handles card auth          0.804  card-authentication
   payment authorisation API       0.784  payment-authorisation-api
   troubleshoot cash withdrawal    0.819  atm-cash-withdrawal-troubleshooting
   config for transaction limits   —      transaction-limits-configuration

Off-topic      all 5 return NO MATCH
```

### Stage 3 required coverage (prompt.md §11)

| Requirement | Status |
|---|---|
| Document chunking | ✅ `app/rag/chunker.py` |
| Metadata handling | ✅ Full `DocumentMetadata` on every chunk, filterable |
| Embedding generation | ✅ `app/rag/embeddings.py`, behind a protocol |
| Vector storage | ✅ `app/rag/vectorstore.py` + on-disk index |
| Retrieval | ✅ `app/rag/retriever.py` |
| Similarity search | ✅ Exact cosine, top-k, pre-filtering |
| Source metadata | ✅ `RetrievalResult.sources`, deduplicated by document |
| Clean vector-store abstraction | ✅ `VectorStore` protocol; store is injected, not imported |
| Question → Embedding → Search → Docs → Sources demonstrated | ✅ `python -m app.rag demo`, guide §6, README |
| Retrieval layer independently testable | ✅ No LLM anywhere; 4 test files run without the real model |
| Retrieval tests | ✅ 168 new tests |
| Representative retrieval examples | ✅ `python -m app.rag demo`; output in guide §6 and README |
| Handover updated | ✅ This file |
| Architecture guide updated with reasoning | ✅ New §20 decision record (user's additional requirement) |

---

## Problems and Decisions

### 20. Uncommitted guide edits from the readability session sit under Stage 8 — RESOLVED

**Resolution (user, 2026-09-14): committed separately first**, as `249f04e`
(`docs(guide): plain-English readability pass over sections 1-5`, +187/−66). The Stage 8
guide edits were stripped by a script into a readability-only copy (verified: +187/−66 vs
HEAD, zero Stage 8 markers), committed, then the full guide restored byte-identical, so
the Stage 8 commit carries only Stage 8's +198/−4.

At Stage 8 kickoff `docs/architecture-guide.html` already carried +187/−66 lines of
uncommitted edits from the separate "Improve.md" readability session, and
`docs/improve.md` is untracked. They are **not Stage 8's**. Stage 8 must also edit the
guide, so before the Stage 8 commit the user decides: commit the readability edits
separately first (preferred — memory note says they get their own commit), or commit the
guide whole as in Stage 7.

### 19. A second Claude Code session was editing the architecture guide — RESOLVED

**What was found (2026-09-14, mid-Stage 7).** `git status` showed
`docs/architecture-guide.html` modified before this session had touched it, and a new
untracked `docs/improve.md`. `improve.md` is a user-written brief asking for a
plain-English readability pass over the guide (no redesign, reuse `.note`, and a
permanent rule that new sections explain their terms). `ListAgents` showed a peer
session named **"Improve.md" — running**; the guide's mtime was seconds old and its diff
grew from 126 to 147 lines between two checks.

**What was done.** Nothing was written to the guide while the other session was active.
The user said to leave the guide until the end. The "Improve.md" session then messaged
that it had **paused** and would not touch the file until Stage 7's sections were in;
the file was re-read and the Stage 7 sections were added by targeted edits only, leaving
its wording edits (§1–§4) intact. **RESOLVED.** Still stale and not Stage 7's: §9 says
"six-type error taxonomy" (it is seven since §20.5.9) — left for the readability pass.

**For the commit.** The guide's readability edits and `improve.md` are not Stage 7 work.
Staging them is the user's call.

### 18. Bare `python` / `pip` resolve to system Python — ALWAYS use the venv

Recorded at the user's instruction, 2026-09-14. System Python lacks the project's pinned
dependencies: `structlog` fails first, and `sentence-transformers`, `torch`, `mcp`,
`anthropic` and `openai` are right behind it. It happened at the start of this session —
a bare `python -m pytest` failed at collection with `ModuleNotFoundError: structlog`.

```bash
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m mypy
```

Never bare `python` or `pip` (and see §7: `pip` is not in the uv venv — use
`uv pip install --python .venv/Scripts/python.exe …`).

### 16. The provider decision changed mid-stage, and the venv had to be reverted

**What happened.** The session opened with an instruction to record a decision as
*"Anthropic, key optional, adapter tested against a mock"*. That was written into this
file before any code, and the Anthropic SDK (`anthropic==1.4.0` plus six transitive
packages) was installed into `.venv` to support the adapter. The user then revised the
decision mid-turn: **no concrete provider at all in Stage 4.**

**What was done.** The SDK and its transitive packages were uninstalled with
`uv pip uninstall`. It was never added to `requirements.txt`, never imported, and no
adapter code was written. The decision section in this file was rewritten to the new
decision, with the reversal recorded rather than erased.

**Why the record keeps the reversal.** A handover that shows only the final decision
hides that an alternative was seriously considered and why it was dropped — which is
exactly the context a future session needs when the question comes back before Stage 5.

**Verification that the environment is clean:** `pytest` (385 passed), `ruff`, and
`mypy` all pass with the SDK absent, and a test walks every import in `app/llm/` to
assert no vendor package is reachable. `requirements.txt` is untouched by Stage 4.

### 17. `ruff format --check` disagrees with the repository — NOT a defect

`ruff format --check` reports that `app/llm/prompts.py` and `app/knowledge/loader.py`
(committed and approved in Stage 2) "would be reformatted". The project's Definition of
Done uses `ruff check` (lint) and `mypy`, not `ruff format`; the formatter has never been
applied to this repository. No formatting change was made, to avoid a large unrelated
diff across previously-approved files. **Decision for a later stage:** either adopt
`ruff format` repo-wide in one deliberate commit, or drop the `ruff format` line from
`README.md`'s test section. Flagged for Stage 15.

### 10. `sentence-transformers` 5.x renamed a method — RESOLVED

`get_sentence_embedding_dimension()` is deprecated in favour of
`get_embedding_dimension()` and emits a `FutureWarning` that printed source lines into
the CLI output. Switched to the new name. The dependency is pinned exactly
(`sentence-transformers==5.7.0`), so this is a fixed contract, not a guess.

### 11. The tokenizer warned on text the chunker deliberately over-feeds — RESOLVED

`tokenizer.encode()` warns *"sequence longer than the maximum"* whenever the chunker
measures an oversized section — which is precisely what it exists to do. The warning
made correct behaviour look like a bug. Fixed with `verbose=False` on that one call,
with a comment explaining why. Not a suppressed lint warning; a library warning that is
wrong in this context.

### 12. mypy strict caught two `int | None` model properties — RESOLVED

`get_embedding_dimension()` and `max_seq_length` are typed `int | None`. Coercing with
`int(...)` would have crashed on `None` at an unhelpful place. Both now raise a typed
`EmbeddingError` naming the model, because the whole pipeline is sized from those two
numbers and a wrong size fails as *bad search results*, not as an exception.

### 13. Windows console mangled em dashes in CLI output — RESOLVED

Citations contain `—` and `·`; a cp1252 console rendered them as `?`. `main()` now
reconfigures stdout to UTF-8 rather than degrading the output to ASCII everywhere.

### 14. A test assumption was wrong and the test was corrected, not the code

A test asserted that a punctuation-only query (`"!!! ???"`) raises `EmbeddingError`. It
does not — the string is non-blank, so the hashing embedder returns a zero vector, every
score is 0.0 and the floor rejects everything. That outcome is *better* than raising: it
routes into the agent's "no documented answer" path. The test now asserts the real,
safer behaviour.

### 15. `tmp_path` failed with 96 `PermissionError` for the user — RESOLVED

**Symptom.** The user ran `pytest` in their own shell and got **96 errors**, all
`PermissionError: [WinError 5] Access is denied` on
`C:\Users\<user>\AppData\Local\Temp\pytest-of-<user>`, from the `tmp_path` fixture.
The same suite passed 240/240 in the Claude Code session.

**Root cause — three facts combined:**

1. Claude Code's shell tools run **elevated** (`IsInRole(Administrator) = True`); the
   user's interactive shell does not.
2. pytest hardens its temp root: `pytest-of-<user>` was created with inheritance
   stripped, holding only `SYSTEM:(F)`, `BUILTIN\Administrators:(F)` and
   `OWNER RIGHTS:(F)`. The parent `Temp` folder *does* carry
   `ZULU\zk:(I)(OI)(CI)(F)`, but none of it was inherited.
3. That directory's **owner was `BUILTIN\Administrators`**, so `OWNER RIGHTS:(F)`
   resolved to Administrators, not to `zk`. There was no ACE for `zk` at all.

Result: an elevated run had access via the Administrators ACE and passed; a
non-elevated run of the same user was denied outright. Because pytest **reuses**
`pytest-of-<user>` across runs, the broken state persisted indefinitely — and was
invisible to whoever created it.

> ⚠️ **Process lesson.** A green test run inside the Claude Code session is not
> evidence the suite passes for the user. The elevation differs. Stage 3's first
> "STAGE COMPLETE" report claimed 240 passed as a project fact when it was only
> true in the elevated context. Verify environment-sensitive results, or state the
> context they were measured in.

**Fix.** `--basetemp=.pytest_tmp` added to `addopts` in `pyproject.toml`, so
`tmp_path` / `tmp_path_factory` no longer touch the Windows user Temp folder at all.
Two properties make this robust rather than a relocation:

- `nodefaultadminowner` is unset (Windows default), so an elevated `zk` process
  creates directories **owned by `zk`** — verified: `.pytest_tmp` owner is `ZULU\zk`,
  and `OWNER RIGHTS:(F)` therefore grants `zk` Full Control.
- pytest **deletes and recreates** an explicit basetemp at the start of every
  session, so a bad state cannot survive a run the way `pytest-of-<user>` did.

**Verified empirically**, not just by reading the ACL: a non-elevated restricted
token (`runas /trustlevel:0x20000`) wrote into `.pytest_tmp` successfully
(`WRITE_OK`). The stale `pytest-of-<user>` was deleted, and is no longer recreated.

`.pytest_tmp/` was already git-ignored (added in Stage 2 — see §9).

**Residual risk.** The fix depends on the basetemp being owned by the invoking user.
If a future run creates it under a token whose default owner is the Administrators
group, the same lockout could recur — now limited to a single session, since the
directory is wiped each run. How the original `pytest-of-<user>` acquired Administrators
ownership was not determined.

### 9 (revised). `.pytest_tmp/` in the repo root — CAUSE NOW KNOWN

Stage 2 recorded 33 pytest temp files appearing in a `.pytest_tmp/` directory that
"could not be reproduced" and whose cause was "unexplained". It is the same
phenomenon as §15: pytest's temp root resolution behaving differently between an
elevated and a non-elevated context. The directory is now the *deliberate* basetemp,
and the entry that was added to `.gitignore` defensively is now load-bearing.

The process lesson recorded then still stands and applied again this stage:
**always list the exact file set `git add` would stage before committing.**

### Known limitations (updated by Stage 11)

- **Stage 11 measured what was promised here** — recall@5 1.000, MRR 0.927, path accuracy
  0.959 on 49 reviewed questions (*Current Work*). It also found **two off-topic questions
  answered instead of refused** (`off-006`, `off-007`), which makes the single 0.25 floor's
  weakness concrete rather than theoretical. See *Stage 11 — what remains deliberately
  unfinished*.
- **Prompt quality is unproven.** The Stage 4 tests assert prompt *structure* — what is
  sent, what is not, what is escaped, what is refused. They cannot assert that a real
  model answers well from these instructions, because no real model has run. Stage 11 built
  the opt-in `--paid` evaluation for this; it has not been run (§20.4.1, §20.39).
- **The context budget is in characters, not tokens.** A deliberate over-approximation:
  owning a tokenizer for a provider not yet chosen is not possible, and every provider
  tokenizes differently. Revisit when the first adapter lands (§20.4.7).
- **The mock is a wiring check, not a language model.** It proves context injection,
  citation numbering, error handling and provenance. It proves nothing about grounding
  behaviour under a real model, which is where hallucination actually happens.
- The threshold is calibrated on 10 on-topic and 5 off-topic questions, written by the
  same author as the corpus. Defensible, not proven. Stage 11's evaluation set is where
  it is tested properly.
- Retrieval is dense-only. Hybrid (BM25 + vector) search is the most likely next
  quality improvement and is noted as an extension point.
- `data/vectorstore/` must be rebuilt after any document edit. `get_retriever()` does
  this automatically; `load_retriever()` refuses instead.

### Carried forward from Stages 1–2

- **§1** Health endpoint settings resolution — fixed, `SettingsDep` reads `app.state`.
- **§2** `@traced` cannot decorate FastAPI route handlers — request tracing is Stage 10.
- **§3** Stale `.git/HEAD.lock` blocked a commit — check for a running `git.exe` first.
- **§4** System `python -m venv` is broken on this machine — use `uv venv`.
- **§5** `docs/decisions/auto-changes.log` is written by a local hook — git-ignored.
- **§6** `PyYAML` was an undeclared transitive dependency — now pinned directly.
- **§7** `pip` is unavailable inside the uv venv — use `uv pip install --python ...`.
- **§8** `pytest.raises(Exception)` rejected by ruff `B017` — use the specific type.
- **§9** `.pytest_tmp/` almost got committed — **always list the exact file set
  `git add` would stage before committing.** Applies again this stage. Its
  previously-unexplained cause is now identified: see §9 (revised) and §15.

### Assumptions

- `CLAUDE.md` is now the sole authority for rules and workflow. `prompt.md` and
  `ccp.txt` are archived, unchanged, in `docs/legacy/`; stage detail lives in
  `docs/PROJECT_PLAN.md`.
- Global rules require `@traced` on new functions. Applied to public RAG functions, with
  documented exceptions: private helpers on hot paths inside an already-traced call
  (`chunker._split_blocks`, `_pack`, `vectorstore._matching_indices`), Pydantic property
  accessors, and `HashingEmbedder` methods used in tight test loops — tracing those
  would emit thousands of events per index build for no diagnostic value.
- The embedding model is downloaded from Hugging Face on first use. This is a free
  public model download, not a paid API call.

### Open questions for the user

**None.** The provider question that blocked Stage 5 was answered on 2026-09-10 and is
recorded under *Stage 5 decision* near the top of this file.

The only thing outstanding is **approval of Checkpoint A**, which is a stop in the
workflow, not an open question.

Decisions already taken with the user's explicit answer:

1. **The embedding model** (Stage 3) — local `sentence-transformers` /
   `all-MiniLM-L6-v2`, chosen over a lexical embedder or a paid hosted API.
2. **The LLM provider** (Stage 4) — **no concrete provider this stage; build and test
   against a mock only. The real adapter and any live key are deferred to a decision
   before Stage 5.** Full record in *Next Action → Decision taken before Stage 4
   implementation begins*. Superseded an earlier instruction in the same session
   (Problems §16).
3. **The concrete provider** (Stage 5, 2026-09-10) — **two adapters, Anthropic and
   OpenAI; no vendor exclusively chosen; default stays `mock`; no live key and no live
   call.** Full record in *Stage 5 decision* near the top of this file. It reverses a
   Stage 4 rejected alternative, and says why.
4. **Stage 5 is split into two approval checkpoints** (2026-09-10) — A: the agent, tested
   against the mock only; B: the two adapters. B does not begin until A is approved.

### Assumptions added in Stage 4

- `@traced` is applied to the public functions of the LLM layer. Deliberate exceptions,
  consistent with Stage 3: Pydantic property accessors on the models, and the private
  helpers `prompts._attribute` / `prompts._fence_safe` and `mock._build` /
  `_next_scripted` / `_synthesise`, which run inside an already-traced call.
- The mock's token counts are a crude `len(text) // 4` estimate, named as an estimate in
  the source. They exist so usage accounting is exercised end to end, not to be accurate.

### Security check (Stage 5 — Checkpoint B)

⚠️ **The "no code path can make a paid call" property is deliberately gone.** Two real
adapters exist now. It is replaced by four independent guards, all tested:
✅ **`BKA_LLM_PROVIDER` still defaults to `mock`** — asserted by a test that clears the
environment variable first. This is the guard that does not depend on the environment.
✅ **Neither adapter can be constructed without `BKA_LLM_API_KEY`** — it raises before an
SDK client object exists, and it does **not** fall through to `ANTHROPIC_API_KEY` or
`OPENAI_API_KEY`, which both SDKs would read silently. That fall-through would turn a
forgotten setting into a working, billing configuration.
✅ **Every adapter test injects a fake client.** The test settings carry no key, so a test
that forgot would fail rather than reach the internet.
✅ **Both CLIs refuse a multi-question `demo` against a paid provider** without `--paid`,
checking *before* an index or a client is built. Verified by hand and by test.
✅ **No key anywhere.** No `sk-`/`sk-ant-` prefixes, no `.env`, nothing hardcoded. The one
secret-shaped literal in the suite is the synthetic `"not-a-real-key-for-tests"`, which
exists so a test can assert a 401 message does **not** contain it.
✅ **The no-vendor AST guard survives, narrowed.** Seam modules stay vendor-free by an
explicit two-name allow-list; `app/agent/` is guarded whole.
✅ **Neither adapter hardcodes a URL** — asserted by test. Endpoints come from the SDKs.
✅ **Adapter logs record shape and cost only** — model, stop reason, token counts. Never
the prompt or the answer, both of which embed document text.
✅ **No live API call has been made**, in the suite or by hand.

### Security check (Stage 4)

✅ **No paid API call is possible.** The only provider is in-process. A test parses every
import in `app/llm/` and asserts no vendor SDK, no HTTP client and no URL is reachable
from the package. This is structural, not procedural.
✅ **No API key anywhere.** `BKA_LLM_API_KEY` is unset, environment-only, and typed
`SecretStr` — asserted to appear in neither `repr(settings)` nor `settings.model_dump()`.
✅ **No vendor name in the system prompt** and no proprietary reference (CR2, BankWorld) —
both asserted by tests.
✅ **Prompt-injection guards implemented, not just documented:** passages fenced in
`<retrieved_documentation>`, declared untrusted in the system prompt before the model sees
them, delimiters occurring inside a passage escaped so a document cannot break out, and
the question placed last, outside the fence. The escape is a passing test using hostile
content.
✅ **Neither the prompt nor the answer text is logged.** Both embed document content;
`llm.answered` records provider, model, prompt version, counts, tokens and stop reason
only. What a request record should contain is decided deliberately in Stage 10.
⚠️ **Carried forward, unchanged:** `retriever.py` still logs the question text —
deliberate, flagged in Stage 3 for reassessment in Stage 13.

### Security check (all stages)

✅ No secrets, keys, tokens or credentials anywhere in the repository.
✅ No real `.env` file exists. `.env` and `.env.*` are git-ignored (`.env.example` excepted).
✅ `logs/` and `data/vectorstore/` are git-ignored. Traced arguments are never logged.
✅ The embedding model runs **locally** — no document text and no question leaves the
machine during indexing or retrieval.
✅ Corpus still scanned by the test suite for secret-shaped values and card-number-shaped
digit runs; no matches.
✅ `yaml.safe_load` only. Index load validates format, model, dimension and consistency.
✅ No nested `banking-knowledge-agent/` directory.
⚠️ **Noted, not a defect:** `retriever.py` logs the question text. Deliberate — these are
technical support queries about a synthetic platform, not customer data. Flagged in the
source for reassessment in Stage 13.

---

## Git

| | |
|---|---|
| **Branch** | `main` |
| **Remote** | `origin` → `https://github.com/Zuleikha/banking-knowledge-agent.git` |
| **Stage 1 commit** | `d448cc1` — `feat(stage-1): project foundation — config, logging, tracing, health` |
| **Stage 2 commit** | `cca70af` — `feat(stage-2): synthetic banking knowledge base and document loader` |
| **Stage 3 commit** | `be9297c` — `feat(stage-3): RAG pipeline — chunking, embeddings, vector store, retrieval` |
| **Stage 3 docs commit** | `docs(stage-3): record commit hash and push result in handover` — this file's own commit, directly on top of `be9297c` |
| **Stage 4 commit** | `bee4b22` — `feat(stage-4): LLM abstraction — provider seam, prompts, context injection` |
| **Stage 4 docs commit** | `9a0b462` — `docs(stage-4): record commit hash and push result in handover` |
| **Stage 5 Checkpoint A commit** | `1478631` — `feat(stage-5a): knowledge agent - decide, retrieve, ground, answer` |
| **Stage 5 Checkpoint B commit** | `6ebe947` — `feat(stage-5b): two concrete LLM adapters - Anthropic and OpenAI` |
| **Stage 5 docs commits** | `26fa239`, then `96204f1` — both pushed |
| **Stage 6 commit** | `93eeb22` — `feat(stage-6): MCP tools - six synthetic support tools, registry and server` |
| **Stage 7 commit** | `a3728d9` — `feat(stage-7): agent decision and tool selection - five paths, rule-based selector` |
| **Restructuring commit** | `d47f522` — `docs: restructure instruction files for token efficiency` — pushed |
| **Guide readability commit** | `249f04e` — `docs(guide): plain-English readability pass over sections 1-5` (+187/−66, the separate improve.md session's edits) — pushed |
| **Stage 8 commit** | `2abbb39` — `feat(stage-8): conversation context - sessions and rule-based follow-ups` — 18 files, 2,418 insertions, 34 deletions |
| **Stage 8 push** | ✅ `d47f522..2abbb39` pushed; verified `origin/main == local HEAD == 2abbb39` |
| **Handover fix** | `ca5449c` — `docs(handover): correct stale Stage 8 status fields` — pushed |
| **Stage 9 commit** | `2484b73` — `feat(stage-9): web interface - conversation API and no-build page` — 12 files (6 added, 6 modified), 1,409 insertions, 43 deletions |
| **Stage 9 push** | ✅ `ca5449c..2484b73` pushed; verified `origin/main == local HEAD == 2484b73` |
| **Push status** | ✅ Pushed to `origin/main` (`6c930f5..a3728d9`); verified `origin/main == local HEAD == a3728d9` |
| **Committed in Stage 7** | 16 files: 1 added, 15 modified — 3,208 insertions, 620 deletions. The guide was committed whole, including the separate improve.md readability edits (user's choice, 2026-09-14). `docs/improve.md` deliberately **not** committed |
| **Stage 10 commit** | `c627358` — `feat(stage-10): observability - request ids, latency logging and in-process metrics` — 16 files (4 added, 12 modified), 1,285 insertions, 79 deletions |
| **Stage 10 push** | ✅ `889585d..c627358` pushed; verified `origin/main == local HEAD == c627358` |
| **Stage 10 follow-up commit** | `42788e8` — `fix(stage-10): quieten httpx logging to warning; record untraced helpers` — 6 files, 200 insertions, 96 deletions |
| **Stage 10 follow-up push** | ✅ `b633b15..42788e8` pushed; verified `origin/main == local HEAD == 42788e8` |
| **Stage 11 commit** | `7b8c85e` — `feat(stage-11): evaluation - dataset, retrieval and answer metrics, scorecard` — 16 files (11 added, 5 modified), 2,385 insertions, 30 deletions |
| **Stage 11 push** | ✅ `25ebdc9..7b8c85e` pushed; verified `origin/main == local HEAD == 7b8c85e` |
| **Gitignore commit (not stage work)** | `cecaf60` — `chore(gitignore): ignore local how-to-run sheet` — pushed `a99f5f7..cecaf60`; verified `origin/main == local HEAD` |
| **Stage 12 commit** | `27739f2` — `feat(stage-12): containerisation - Dockerfile, Compose, baked model and index, health check` — 9 files (5 added, 4 modified), 680 insertions, 37 deletions |
| **Stage 12 push** | ✅ `691c393..27739f2` pushed; verified `origin/main == local HEAD == 27739f2` |
| **Working tree** | Clean, apart from git-ignored local files |
| **Committed in Stage 6** | 34 files: 20 added, 14 modified — 9,132 insertions, 215 deletions |
| **Committed in Checkpoint A** | 12 files: 8 added, 4 modified — 2,199 insertions, 159 deletions |
| **Committed in Checkpoint B** | 15 files: 3 added, 12 modified — 2,533 insertions, 245 deletions |
| **Committed in Stage 4** | 18 files: 11 added, 7 modified — 3,574 insertions, 205 deletions |
| **Committed in Stage 3** | 21 files: 13 added, 8 modified — 4,816 insertions, 302 deletions |
| **Deliberately not committed** | `docs/legacy/prompt.md`, `prompt1.md`, `docs/legacy/ccp.txt`, `ai-dev-token-efficiency-workflow.md`, `docs/decisions/auto-changes.log`, `.venv/`, `logs/`, `data/vectorstore/`, `.pytest_tmp/`, caches |

### The exact Stage 5 Checkpoint B file set — verified with `git add -An`, 2026-09-10

15 paths, and **no others**. `data/vectorstore/`, `logs/`, `.venv/`, `.pytest_tmp/`,
`prompt.md`, `prompt1.md` and `ccp.txt` are all absent from the listing.

```
add '.env.example'                    add 'app/llm/anthropic_provider.py'
add 'README.md'                       add 'app/llm/openai_provider.py'
add 'app/agent/__main__.py'           add 'tests/test_llm_adapters.py'
add 'app/core/config.py'
add 'app/llm/__init__.py'             add 'app/llm/base.py'
add 'app/llm/__main__.py'             add 'app/llm/factory.py'
add 'docs/HANDOVER.md'                add 'requirements.txt'
add 'docs/architecture-guide.html'    add 'tests/test_llm_provider.py'
```

**Secret scan.** No vendor key prefixes (`sk-`, `sk-ant-`), no base64/hex literals over
40 characters, no card-number-shaped digit runs, no `.env` file. **One deliberate hit,
reviewed and kept:** `tests/test_llm_adapters.py:158` assigns
`llm_api_key = "not-a-real-key-for-tests"`. It is a synthetic, self-labelling placeholder
whose only purpose is the test asserting that a 401 error message cannot echo the key —
the test would be meaningless without a value to look for. **Git locks:** none; no
`git.exe` running. **No nested `banking-knowledge-agent/` directory.**

### The exact Stage 5 Checkpoint A file set — verified with `git add -An`, 2026-09-10

12 paths, and **no others**. `data/vectorstore/`, `logs/`, `.venv/`, `.pytest_tmp/`,
`prompt.md`, `prompt1.md` and `ccp.txt` are all absent from the listing, confirmed by
reading it rather than by assuming.

```
add 'README.md'                       add 'app/agent/__init__.py'
add 'docs/HANDOVER.md'                add 'app/agent/__main__.py'
add 'docs/architecture-guide.html'    add 'app/agent/agent.py'
add 'tests/conftest.py'               add 'app/agent/factory.py'
                                      add 'app/agent/models.py'
add 'tests/test_agent.py'             add 'app/agent/policy.py'
add 'tests/test_agent_integration.py'
```

**Secret scan of the new files:** no secret-shaped assignments, no base64/hex literals
over 40 characters, no card-number-shaped digit runs. **Git locks:** none; no `git.exe`
running.

### The exact Stage 4 file set — verified with `git add -An`, 2026-09-09

18 paths, and **no others**:

```
add '.env.example'                    add 'app/llm/__init__.py'
add '.gitignore'                      add 'app/llm/__main__.py'
add 'README.md'                       add 'app/llm/base.py'
add 'app/core/config.py'              add 'app/llm/factory.py'
add 'docs/HANDOVER.md'                add 'app/llm/mock.py'
add 'docs/architecture-guide.html'    add 'app/llm/models.py'
add 'tests/conftest.py'               add 'app/llm/prompts.py'
                                      add 'app/llm/service.py'
add 'tests/test_llm_prompts.py'
add 'tests/test_llm_provider.py'
add 'tests/test_llm_service.py'
```

### `prompt1.md` — RESOLVED, and why `.gitignore` is in the Stage 4 commit

`prompt1.md` appeared as a new untracked local file this session. It was **not** in
`.gitignore`, so `git add -An` confirmed it would have been staged — the exact trap
Problems §9 was written about, caught by running the checklist rather than by assuming.

**Fix.** `prompt1.md` added to `.gitignore` beside `prompt.md`, in the *Local working
files* section. Re-ran `git add -An` and confirmed it no longer appears. That is why
`.gitignore` is a modified file in the Stage 4 set: it is a Stage 4 change, not a stray
edit.

> **Process note.** The listing was produced *before* the commit, which is what made this
> visible. `git status` alone would not have shown it as clearly — it collapses untracked
> directories into one line. Third stage running, third time this step has earned itself.

### Pre-commit checklist (worked for Stages 3 and 4; reuse it)

1. `git add -An` — list the **exact** file set. `git status` collapses untracked
   directories into a single line and will hide what is really being staged
   (Problems §9).
2. Confirm `data/vectorstore/`, `logs/`, `.venv/`, `.pytest_tmp/`, `prompt.md`,
   `prompt1.md`, `docs/legacy/`, `ai-dev-token-efficiency-workflow.md` are **not** in that list. Grep precisely — a loose
   `vectorstore` pattern matches the legitimate `app/rag/vectorstore.py` source file.
3. Scan the staged set for secret-shaped assignments, long base64/hex literals and
   card-number-shaped digit runs. *(Stage 4: run over all new files — no matches.)*
4. Check for a stale `.git/*.lock` and a running `git.exe` (Problems §3).
5. Re-run `pytest`, `ruff check .`, `mypy`.
6. Commit, push, verify `origin/main == HEAD`, then record the hash here.

> **When a new local working file appears, ignore it rather than remembering to skip it.**
> An entry in `.gitignore` survives the session; an intention does not.

---

## Next Action

**Stage 12 — Containerisation — is approved, committed and pushed** (approved 2026-09-16; hash in
*Git*). **The next action is Stage 13 — Security and Production Readiness — when the user asks for
it.** Read only its section of `docs/PROJECT_PLAN.md`; `CLAUDE.md` §2 marks it ✅ for sub-agents, but
only if the user asks at kickoff. Carried into Stage 13: add `GET /ready` (12.D) · wire or drop
`BKA_HOST`/`BKA_PORT`, which no app code reads (12.G) · run `ruff format` on the 24 pre-existing
files (12.H) · Stage 11's `off-006`/`off-007` refusal gap and whether to run `--paid`. Host port 8000
is taken by another project; use `BKA_HOST_PORT=8001` for any Docker re-check.

*Superseded:* **Stage 11 — Testing and Evaluation — is approved, committed and pushed** (hash in *Git*). **The
next action is Stage 12 — Containerisation — when the user asks for it.** Read only its section
of `docs/PROJECT_PLAN.md`; `CLAUDE.md` §2 marks it ❌ for sub-agents. Open for
the user: `off-006`/`off-007` refusal gap (Stage 11 unfinished #1) and whether to run `--paid`
(#3). Try it free: `./.venv/Scripts/python.exe -m app.eval`.

*Superseded:* **Stage 10 — Observability — is approved, committed and pushed** (hash in *Git*). **The
next action is Stage 11 — Testing and Evaluation — when the user asks for it.** Read only its
section of `docs/PROJECT_PLAN.md`; `CLAUDE.md` §2 marks it ✅ for sub-agents, but only if the
user asks at kickoff. Still open for the user: *Stage 10 — what remains deliberately
unfinished* #3 (`httpx` logging) and #5 (untraced helpers). Try it free:
`./.venv/Scripts/python.exe -m uvicorn app.main:app` → `http://127.0.0.1:8000/metrics`.

*Superseded:* **Stage 9 — Web interface — is approved, committed and pushed** (hash in *Git*). **The
next action is Stage 10 when the user asks for it.** Read only its section of
`docs/PROJECT_PLAN.md`. Try the page free:
`./.venv/Scripts/python.exe -m uvicorn app.main:app` → open `http://127.0.0.1:8000/`.

*Superseded below.*

**Stage 7 is complete and approved. It is committed (`a3728d9`) and pushed**, verified
`origin/main == HEAD`. 891 tests passing, ruff clean, mypy strict clean over 52 source
files.

**Stage 8 is approved and committed** (readability edits first as `249f04e`, then Stage 8;
hashes in *Git*). **The next action is Stage 9 — Web interface — when the user asks for
it.** Read only its section of `docs/PROJECT_PLAN.md`. Still uncommitted and not Stage 8's:
the user's `/usage` rule in `CLAUDE.md`.

> ✅ **Resolved with the user, same session:** `docs/improve.md` now lives at
> `docs/legacy/improve.md`; `CLAUDE.md` §4 absorbed its readability rule and points to the
> new path (`3fe5ea4`); `docs/legacy/` is git-ignored (`0e04b77`). `ccp.txt` no longer
> exists and is not needed — `CLAUDE.md` is the sole authority. Working tree clean.

*Superseded:* **The next action is to begin Stage 8 — Conversation context — when the user asks for
it.** Do not start it unprompted. Stage 7's approval does not carry over.

> The "Improve.md" session may resume its readability pass over the guide; its further
> edits belong in their own commit. *(Superseded: its §1–§5 edits were committed as
> `249f04e`; the brief is archived at `docs/legacy/improve.md`.)*

> ⚠️ A live LLM call is still a paid call and still needs explicit confirmation at the
> time. Stage 7 added none: every decision is a deterministic rule.

### Stage 7 scope, as it was written before the stage started (`prompt.md` §15)

Agent decision and tool selection: choosing between answering from knowledge, retrieving
more, calling a tool, using both, or refusing. Three things Stage 6 leaves ready:

- **`DecisionReason`** now has three values and is still the literal to extend. Stage 6
  deliberately added **no tool-only branch** — see §6.F and guide §20.15 — and Stage 7 is
  where that becomes a real choice rather than a worse version of the existing one.
- **`app/agent/tool_policy.py`** is the module a model-driven selector replaces. It is
  isolated from `policy.py` for exactly this reason, and guide §20.14 records why the
  deterministic identifier-based rule was right for Stage 6 and what it cannot do.
- **The execution record already exists.** `AgentAnswer` carries `decision`, `retrieval`,
  `tools`, `tool_results` and `used_live_information`, which is the *"expose useful
  execution information"* list from §15 — so Stage 7 adds decisions, not plumbing.

> ⚠️ **A live LLM call is still a paid call** and still needs the user's explicit
> confirmation, given separately at the time. Stage 6 changed nothing here: the provider
> default is still `mock`, `app/mcp/` contains no code path that can reach a network, and
> cloning this repository and running its suite still costs nothing.

### Decision taken before Stage 4 implementation begins — LLM provider

**Decided by the user, 2026-09-09.** Kept as the historical record of Stage 4.

> ✅ **The deferral this record created is now resolved** — see *Stage 5 decision* near
> the top of this file: two adapters, no vendor exclusively chosen, no live key, default
> stays `mock`.

| | |
|---|---|
| **Concrete provider** | **None this stage.** No real provider is picked or wired in |
| **What Stage 4 builds against** | A **mock** `LLMProvider` implementation, only |
| **API key** | Provider-neutral `BKA_LLM_API_KEY`, environment-only, **optional and unset** |
| **Paid calls** | **None.** No live API call this stage, in the suite or by hand |
| **Deferred to** | A separate decision **before Stage 5** — which real provider, and whether a key is ever wired in |

**What this means for the implementation**

- `LLMProvider` (in `app/llm/base.py`) is the vendor-agnostic seam. Stage 4 delivers the
  seam, the prompt layer, the context-injection layer, the error taxonomy and one mock
  implementation behind it. It delivers **no** vendor adapter.
- Because there is no vendor adapter, there is nothing that *can* make a paid call. The
  suite is offline, deterministic and free by construction, not by discipline.
- `BKA_LLM_API_KEY` is defined now and read from the environment only, so the
  configuration seam exists before the provider does. It is unset by default, held as a
  Pydantic `SecretStr`, never hardcoded, never logged, never written to this handover.
- `BKA_LLM_PROVIDER` defaults to `mock`. Requesting any other value fails **loudly** with
  a typed `LLMConfigurationError` saying the concrete adapter arrives in Stage 5 — it
  never silently degrades to the mock, which would let a caller believe a real model
  answered.

> ⚠️ **Correction, same session.** An earlier instruction in this session recorded
> *"Anthropic, key optional, adapter tested against a mock"*, and that version was written
> to this file. The user then revised it to the decision above: **no concrete provider at
> all in Stage 4.** The Anthropic SDK had been installed into `.venv` under the earlier
> instruction; it was **uninstalled**, and it was never added to `requirements.txt`, never
> imported, and no adapter code was written. Recorded because the file must show what was
> decided *and* what was reversed.

**Stage 4 scope, delivered.** Every item of `prompt.md` §12 is implemented and mapped to
its evidence in *Testing → Stage 4 required coverage* above.

---

## Constraints carried forward (all stages)

- Synthetic content only. No proprietary, confidential or copyrighted material.
- Documents and tool results are data, not instructions — untrusted LLM input. Stage 4
  implemented the first concrete defences (fencing, escaping, a stated rule); Stage 6
  extends the same treatment to tool results, and Stage 13 reviews the whole surface.
- No secrets in documents, tests, logs or the handover.
- **Never spend money or call a paid external API without the user's explicit
  confirmation.** Still live and still unresolved: a real LLM call is a paid call. The
  repository currently contains no code path that can make one, and that property should
  not be given up casually when the first adapter lands.
- Do not create a nested `banking-knowledge-agent/` directory.
- Approval cycle: IMPLEMENT → TEST → UPDATE HANDOVER → SHOW → **STOP** → APPROVAL →
  VERIFY → COMMIT → PUSH → VERIFY PUSH → NEXT STAGE. Never commit an unapproved stage.

---

## Moved from HANDOVER.md on 2026-09-16 (Stage 13 close)

Verbatim, as they stood when Stage 13 was approved (`e29bbae`).

### Stage 13 progress

| Step | Status |
|---|---|
| 1. `ruff format` 24 files (13.D) | ✅ done — suite unchanged, 1141 passed / 4 skipped |
| 2. Freeze contract (config fields + production rule, metric names, `security.py` / `rate_limit.py` no-op stubs, `main.py` wiring, `.env.example`, config tests) | ✅ done — 105 targeted tests pass, ruff + mypy clean |
| 3. Six sub-agents U1–U6 dispatched in one batch (split: contract §3) | ✅ all six done. U3–U6 hit the usage limit mid-task and were resumed with context intact. Scratchpad writes were blocked, so findings came back in replies (summarised in guide §16) |
| 4. Integration | ✅ ownership verified (every non-owned change is formatting only) · `metrics.py` docstring fixed · guide §16 review table, §20.54–§20.55, §21.8 · README Security section, `/ready`, config row, counts · contract gap filled (`/ready` 503 → `"status": "not_ready"`) |

**STATUS: APPROVED 2026-09-16 and committed.**

### Stage 12 decisions (12.A–12.H) — full records in guide §20.43–§20.49

| # | Decision |
|---|---|
| 12.A | **Model and index baked into the image** at build time — container runs fully offline, starts fast, index always matches the docs in the image |
| 12.B | **CPU-only PyTorch on `python:3.12-slim`**, same pinned version read from `requirements.txt` — the default Linux wheel drags in GBs of unused CUDA |
| 12.C | **`compose.yaml` = one `app` service**, port 8000, provider `mock`, `./logs` bind-mounted to the host |
| 12.D | **`HEALTHCHECK` on `GET /health` only**, via a Python one-liner (slim has no `curl`). **`GET /ready` moved to Stage 13** |
| 12.E | **"Test through Docker" = both** — full pytest inside the image (`test` target) *and* a smoke test against the running container |
| 12.F | **Runs as non-root user `app`**, owning the model cache, index and log directory |
| 12.G | `BKA_HOST`/`BKA_PORT` are read by **no app code**; uvicorn's flags are what apply. The image sets them and `CMD` passes them through. App code unchanged — wiring them is a Stage 13 candidate |
| 12.H | **The 24 files `ruff format` would rewrite are left unchanged**, carried to Stage 13. All pre-existing; none is a Stage 12 file. `ruff check` (lint) is clean — cosmetics only |

### Deliberately unfinished — Stage 11 (evaluation)

1. **`off-006`, `off-007` answered instead of refused** — banking-adjacent questions clear the 0.25 floor. A real hallucination-resistance gap. Candidates: higher floor for refined searches, hybrid search, or a reranker. **Needs a user decision.**
2. `know-018` evidence lacks `TransactionSwitch` — reported, not gated.
3. **Paid mode never run.** `--paid` implemented and guarded; no real-model answer scored. Needs explicit confirmation at the time.
4. Mentions in free mode are checked against retrieved evidence, not answer wording.
5. Same author wrote corpus, routing rules and dataset — defensible, not independent.
6. API behaviour covered by Stage 9/10 tests, not re-scored by the evaluation.

### Deliberately unfinished — Stage 10 (observability)

1. **`GET /metrics` is unauthenticated** (like `/health`); names and numbers only → **Stage 13**.
2. Metrics are per-process and reset on restart; JSON, not Prometheus → Stage 14.
3. `httpx` full-URL logging — **resolved (10.E)**, raised to `warning`.
4. A 500 from an unhandled exception carries no `X-Request-ID` header (Starlette builds it outside the middleware); the `http.request_failed` log line does carry the id.
5. **Untraced by deliberate exception (10.F):** `Metrics`/`_Histogram` methods, `elapsed_ms`, `get_metrics`, `reset_metrics`, the middleware's inner response wrapper — they run inside the measurements.
6. **Stale "Stage 7 … a model" wording** remains in `app/mcp/models.py` (`ToolSpec`, `input_schema`, `ToolInvocation`) and `app/mcp/base.py` (module docstring, `ToolInputError`) — fix in the next stage that touches `app/mcp/`.
