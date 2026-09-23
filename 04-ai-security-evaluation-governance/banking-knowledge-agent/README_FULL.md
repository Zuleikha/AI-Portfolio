# Banking Knowledge Agent

A source-backed AI support agent for a banking technology platform — ATM and self-service,
digital banking, cards, payments, APIs, configuration and incident troubleshooting. It answers
from its own documentation and from live support tools, cites every claim, and says plainly when
it does not know. The goal is not "a chatbot" but production-oriented AI engineering: retrieval,
an agent loop, MCP tools, conversation context, testing and clean, swappable boundaries.

> **All banking data in this repository is synthetic** — documents, error codes, component
> names and tool responses are invented for this project. No proprietary, confidential or
> copyrighted material is used.

---

## Status

| | |
|---|---|
| **Current stage** | **Stage 15 — Final Engineering Review** complete · the final stage |
| **Implemented** | Config, logging, tracing · knowledge base · RAG pipeline · LLM abstraction + Anthropic/OpenAI adapters · knowledge agent with rule-based decisions · six MCP tools + MCP server · conversation sessions · conversation API + web page · request ids, latency logging and in-process metrics · evaluation dataset, scored metrics and CLI scorecard · Docker image and Compose (offline, non-root, health-checked) · API key, rate limit, readiness probe, input limits, log redaction · production architecture documented; runtime citation check, safe 422 bodies, `python -m app` · full engineering review: dead code removed, money guard and `Retry-After` reader deduplicated, JSON container logs |
| **Next** | Nothing outstanding — the 15 planned stages are complete |

Stages 6 and 13 were built with parallel sub-agents against a shared contract frozen first — see the architecture guide §21.

Detailed progress, decisions and the exact next action: [`docs/HANDOVER.md`](docs/HANDOVER.md). What changed in each stage: [`CHANGELOG.md`](CHANGELOG.md).

---

## Architecture

```
Browser ──▶ Web page (static) ──▶ FastAPI  /api/sessions/*
                                     │
                                     ▼
                           ConversationService      session store · follow-up rules
                                     │
                                     ▼
                             KnowledgeAgent         decide: docs? tools? both? refuse?
                          ┌──────────┴──────────┐
                          ▼                     ▼
                  Retriever (RAG)         ToolRegistry (MCP)
                  documentation           live readings
                          └──────────┬──────────┘
                                     ▼
                              LLMService ──▶ LLMProvider   mock · anthropic · openai
                                     │
                                     ▼
                     Answer + sources + tool activity + route taken
```

Every layer sits behind a small interface (a Python `Protocol`), so embedders, vector stores,
LLM vendors, tools and session stores can be swapped without touching the layers around them.
Full reference, diagrams and decision records: [`docs/architecture-guide.html`](docs/architecture-guide.html).

---

## Technology Stack

| Technology | Purpose |
|---|---|
| **Python 3.12** | Language with the most mature LLM, embedding and vector-search ecosystem |
| **FastAPI + uvicorn** | HTTP API and static web page; typed models and generated OpenAPI docs |
| **Pydantic / pydantic-settings** | Validation at the boundary; typed `BKA_*` environment configuration |
| **structlog** | Structured log events with fields, written to `logs/` |
| **sentence-transformers** (`all-MiniLM-L6-v2`) | Local embeddings — semantic search, no API key, no per-query cost |
| **NumPy** | The vector index is one matrix; search is one matrix multiplication |
| **`anthropic` + `openai`** | Two vendor adapters behind one provider interface — neither is the default |
| **`mcp`** (pinned `1.12.4`) | Official Model Context Protocol SDK, used only by the MCP server |
| **PyYAML** | Document front matter, `safe_load` only |
| **pytest · ruff · mypy (strict)** | Tests, lint and format, static type checking |

---

## Requirements

- Python 3.12
- Git
- ~90 MB free for the embedding model (downloaded once from Hugging Face on first use)
- *Optional:* Docker with Compose v2, to run it as a container instead (see [Docker](#docker))

No API key is needed. The default LLM provider is a free, deterministic, in-process mock.

---

## Setup

```bash
git clone https://github.com/Zuleikha/banking-knowledge-agent.git
cd banking-knowledge-agent

uv venv .venv --python 3.12                       # or: python -m venv .venv
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt

cp .env.example .env                               # optional — every setting has a safe default
.venv/Scripts/python.exe -m app.rag build          # build the search index (git-ignored)
```

---

## Run

Step-by-step, with what you should see at each point and how to verify the system end to end:
[`docs/HOW_TO_RUN.md`](docs/HOW_TO_RUN.md).

```bash
.venv/Scripts/python.exe -m app --reload                 # web app on BKA_HOST:BKA_PORT (default 127.0.0.1:8000)

.venv/Scripts/python.exe -m app.agent demo               # decision paths, end to end
.venv/Scripts/python.exe -m app.agent conversation-demo  # follow-up rules, end to end
.venv/Scripts/python.exe -m app.mcp demo                 # one call of each tool
.venv/Scripts/python.exe -m app.eval                     # evaluation scorecard (free)
```

| URL | What it is |
|---|---|
| <http://127.0.0.1:8000/> | Web page — ask questions, see sources, tool activity and the route taken |
| <http://127.0.0.1:8000/health> | Liveness check |
| <http://127.0.0.1:8000/ready> | Readiness check — index and LLM configuration (200 / 503) |
| <http://127.0.0.1:8000/metrics> | In-process counters and latency histograms (JSON); needs `X-API-Key` when `BKA_API_KEY` is set |
| <http://127.0.0.1:8000/docs> | Interactive API documentation |
| <http://127.0.0.1:8000/openapi.json> | OpenAPI schema |

---

## Test

```bash
.venv/Scripts/python.exe -m pytest                        # full suite
.venv/Scripts/python.exe -m pytest -m "not integration"   # skip the real embedding model
.venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m mypy
```

**1416 tests**, none of which call a paid API; 77 are marked `integration` and load the real embedding model; 4 are the Docker smoke test, skipped unless `BKA_SMOKE_BASE_URL` is set.

---

## RAG Pipeline

```
Markdown docs ──▶ load + validate ──▶ chunk (## headings) ──▶ embed ──▶ NumPy index
question ──▶ embed ──▶ filter ──▶ cosine score ──▶ top-k ──▶ score floor ──▶ passages + sources
```

- 15 synthetic documents → 115 chunks, each within the model's 256-token window.
- Chunk size is measured in the embedding model's own tokens; tables keep their header row.
- Exact cosine search over one matrix — no approximate index needed at this size.
- A **score floor (0.25)** returns nothing when nothing is relevant, so the agent can refuse.
- The index manifest pins the model and a corpus fingerprint; a stale or foreign index is refused.

## LLM Abstraction

```
passages + tool results ──▶ budget ──▶ fenced prompt (v1.2.0) ──▶ LLMProvider ──▶ validate ──▶ GroundedAnswer
```

- One `LLMProvider` protocol; only the two adapter modules may import a vendor SDK (enforced by a test).
- Switching vendor is one setting: `BKA_LLM_PROVIDER=mock | anthropic | openai`.
- Spending needs two deliberate acts — a paid provider **and** `BKA_LLM_API_KEY`; `demo` refuses without `--paid`.
- Retrieved text, tool results and questions are fenced or escaped as untrusted data (prompt-injection defence).
- No evidence → refusal with **no model call**; truncated, refused or empty generations raise, and so does an answer citing `[n]`/`[Tn]` that was never sent.
- Eight typed errors, each with a `retryable` flag.

## Knowledge Agent

```
question ──▶ plan ──▶ call tools ──▶ search (once more if weak) ──▶ answer ──▶ record the route
```

- Five paths: answer from docs · retrieve more · call a tool · use both · refuse.
- Every choice is a **deterministic rule** — no model decides routing.
- A weak search (top score < 0.50) gets one refined retry; the score floor is never lowered.
- Tools are chosen from the registry's own specs (error codes, transaction refs, config keys, components).
- The answer carries **decisions, not reasoning**: route, each choice point, search and tool summaries.

## Conversation Context

```
session id + question ──▶ resolve follow-up (rules) ──▶ agent(question, earlier QUESTIONS) ──▶ store turn
```

- "Is it healthy?" becomes a standalone question using the previous question's identifiers or topic.
- The model sees earlier **questions** only, fenced as *not evidence*; earlier answers are never sent.
- Bounded: 3 earlier questions / 1000 characters sent · 50 turns · 1000 sessions · 30-minute idle expiry.
- In-memory store behind a `SessionStore` protocol; an unknown session id is an error, never a new session.

## Web Interface

```
index.html + app.js ──▶ POST /api/sessions · /ask · /turns · /end ──▶ ConversationService
```

- No build step: plain HTML, JavaScript and CSS served by FastAPI; all text inserted as text.
- Badges for RAG used, MCP tools used, sources consulted and insufficient information.
- The session id travels only in the JSON body — never in a URL or access log.
- Errors: missing/wrong API key → 401 · unknown session → 404 · blank or too-long question → 422 · rate limit → 429 · tool, model or embedding failure → 502, no internal detail.
- An **API key** box appears on the page; the key is kept for this browser tab only and sent as `X-API-Key`.
- One question at a time per session (per-session lock).

## MCP Tools

```
KnowledgeAgent ──▶ ToolRegistry (in-process) ◀── MCP server (stdio JSON-RPC) ◀── any MCP client
                        │
                        ▼
      six synthetic tools, one module each
```

- `get_system_configuration` · `check_transaction_status` · `get_component_status` · `look_up_error_code` · `retrieve_system_version` · `check_service_health`.
- The tools exist once; the MCP server is a thin wrapper over the same registry.
- Pure and offline: no clock, network or file access — same arguments, same result.
- "Not found" is a normal result (`ok=False`); a malformed call raises.
- Tool results are untrusted input and get the same fencing as documents.

## Documentation vs Live Information

```
<retrieved_documentation>  [1] [2]  how the platform SHOULD behave
<tool_results>             [T1]     how it IS behaving now
```

- Kept apart end to end: separate prompt fences, citation forms and answer fields.
- They can disagree — e.g. a documented limit of 500.00 vs a live account override of 250.00 — and the answer must report both.
- `AgentAnswer.used_live_information` says whether any part of an answer came from a tool.

## Observability

```
request ──▶ middleware: X-Request-ID ──▶ rag · tools · llm (latency_ms each) ──▶ http.request (latency_ms)
                              │                                                        │
                              └──── request_id on every app + trace log line ──────────┴──▶ GET /metrics
```

- One `request_id` per HTTP request, on every log and trace line; returned in `X-Request-ID`.
- An incoming `X-Request-ID` is used only if it is 1–64 letters, digits or dashes; otherwise one is generated.
- `latency_ms` on retrieval, each LLM call, each tool call and the whole request; failures logged by error type only.
- The question is logged as a 12-character hash and a length — never the text; the query string is never logged.
- `GET /metrics`: in-memory counters and latency histograms as JSON; no new dependency; resets on restart.

## Evaluation

```
data/eval/questions.yaml ──▶ app/eval runner ──▶ retrieval ranks + agent answer + rule checks
     49 questions                                        │
                                   pytest gates ◀── EvalReport ──▶ python -m app.eval scorecard
```

- 49 reviewed questions across knowledge, paraphrase, tool, hybrid, failure, off-topic and injection; each names its expected route, documents, tools and facts.
- Retrieval: recall@5 and MRR. Answers: route, tools, documents, refusal, honest refusal, citation validity, required facts.
- Measured (real embedding model, mock provider): recall@5 **1.000** · MRR **0.927** · path accuracy **0.959**.
- Soft floors in the dataset file (0.90 · 0.85 · 0.90) gate the `integration` tests; invented citations and dishonest refusals gate at 100%. A withheld answer is scored as a failed citation check; the run continues.
- Free by default, whatever `BKA_LLM_PROVIDER` says; `--paid` runs the real model only with a paid provider **and** a key set.

## Docker

```
docker build ─▶ python:3.12-slim + CPU-only torch ─▶ model downloaded + index built ─▶ image
                                                                                      │
docker compose up ─▶ app (user: app, offline) ─▶ :8000 ◀── HEALTHCHECK GET /health ───┘
                        └─ ./logs mounted from the host
```

- **Offline at runtime:** the embedding model and search index are baked in at build time; `HF_HUB_OFFLINE=1`.
- **Small where it counts:** CPU-only PyTorch at the pinned version — no CUDA libraries.
- **Non-root:** runs as `app`; owns only the model cache, index and `logs/`.
- **Free by default:** Compose sets `BKA_LLM_PROVIDER=mock`; no API key appears in any container file.
- **Probes:** `HEALTHCHECK` uses `/health` (liveness); `/ready` is there for orchestrators. The image runs `python -m app --no-access-log`.
- **Logs:** the image sets `BKA_LOG_FORMAT=json` — one object per line for a log collector to parse into fields. Override with `-e BKA_LOG_FORMAT=console` to read them yourself.
- **Two build targets:** `runtime` (what Compose runs) and `test` (runtime + dev tools + the full suite).

```bash
docker compose up --build -d                       # http://localhost:8000 · docker compose ps → (healthy)
docker build --target test -t bka-test . && docker run --rm bka-test          # full suite in the image
BKA_SMOKE_BASE_URL=http://localhost:8000 .venv/Scripts/python.exe -m pytest tests/test_docker_smoke.py
docker compose down
```

## Security

```
request ──▶ rate limit (429) ──▶ API key (401) ──▶ input limits (422) ──▶ agent ──▶ fenced prompt
                                                                            │
                     logs ◀── redaction processor ◀── fingerprints only ◀───┘
```

- **API key (optional):** `BKA_API_KEY` protects `/api/*` and `/metrics`; constant-time compare; **production refuses to start without it**. `/health`, `/ready` and the page stay open.
- **Rate limit:** `BKA_RATE_LIMIT_PER_MINUTE` per client, in process; `429` + `Retry-After`; runs before the key check.
- **Input limits:** questions ≤ `BKA_QUESTION_MAX_CHARS`, session ids ≤ 64 URL-safe characters, tool arguments ≤ 256 characters. A `422` names the field, never the value sent.
- **Prompt injection:** documents, tool results, earlier questions **and the current question** are escaped against fence forgery in any case or spacing.
- **Logs:** fields named like secrets and any `SecretStr` value are written as `[REDACTED]`; application logs hold no questions, answers, keys or client addresses in clear (uvicorn's own access log, which prints client IP and path, is off in the container via `--no-access-log`).
- **Failures:** provider and tool errors reach callers as fixed text; every 500 carries `X-Request-ID`.
- **Not built (design only, see Production Architecture):** per-user identity, TLS, shared rate-limit store, secrets manager, hashed lock file, vulnerability scanning. Full review: architecture guide §16.

## Production Architecture

```
            LOCAL (built)                              PRODUCTION (design only)
Client ─▶ one uvicorn process              Client ─▶ load balancer + TLS + sign-in
           API → Agent                                API × N replicas → Agent
             ├─ RAG  NumPy index (in image)             ├─ RAG  managed vector DB ◀─ ingestion job
             ├─ MCP  6 synthetic tools                  ├─ MCP  same contracts → real systems
             └─ LLM  mock (paid adapters exist)         └─ LLM  gateway: deadline, breaker, fallback
           sessions + limits in memory                sessions + limits in Redis
```

- **Only the local column exists.** The production column is a documented design; no infrastructure was built for it.
- **First change for scale:** move sessions and rate-limit counters to a shared store — every other step depends on it.
- **Each production box is one new class** behind an existing protocol (`VectorStore`, `SessionStore`, `LLMProvider`, `Tool`).
- Covered: scaling, vector DB, LLM abstraction, MCP, service boundaries, deployment, observability, failure modes, data privacy, high availability — architecture guide §17.

---

## Configuration

All settings are optional `BKA_*` environment variables with safe defaults. Full descriptions and
defaults: [`.env.example`](.env.example). Secrets come from the environment only and are never logged.
`python -m app` applies `BKA_HOST`/`BKA_PORT` (locally and in the image); `BKA_HOST_PORT` (Compose
only, default `8000`) picks the port on your machine.

| Area | Variables |
|---|---|
| App / server | `BKA_APP_NAME` `BKA_APP_VERSION` `BKA_ENVIRONMENT` `BKA_DEBUG` `BKA_HOST` `BKA_PORT` |
| Knowledge / RAG | `BKA_KNOWLEDGE_DIR` `BKA_VECTORSTORE_DIR` `BKA_EMBEDDING_MODEL` `BKA_EMBEDDING_DEVICE` `BKA_EMBEDDING_BATCH_SIZE` `BKA_CHUNK_MAX_TOKENS` `BKA_CHUNK_OVERLAP_TOKENS` `BKA_RETRIEVAL_TOP_K` `BKA_RETRIEVAL_MIN_SCORE` |
| Agent | `BKA_AGENT_CONFIDENT_SCORE` |
| Conversation | `BKA_CONVERSATION_MAX_HISTORY_TURNS` `BKA_CONVERSATION_MAX_HISTORY_CHARS` `BKA_CONVERSATION_MAX_TURNS` `BKA_CONVERSATION_MAX_SESSIONS` `BKA_CONVERSATION_TTL_SECONDS` |
| LLM | `BKA_LLM_PROVIDER` `BKA_LLM_MODEL` `BKA_LLM_MAX_TOKENS` `BKA_LLM_TIMEOUT_SECONDS` `BKA_LLM_MAX_RETRIES` `BKA_LLM_CONTEXT_MAX_CHUNKS` `BKA_LLM_CONTEXT_MAX_CHARS` `BKA_LLM_API_KEY` |
| Security | `BKA_API_KEY` `BKA_RATE_LIMIT_PER_MINUTE` `BKA_QUESTION_MAX_CHARS` |
| Evaluation | `BKA_EVAL_DATASET_PATH` |
| Logging | `BKA_LOG_LEVEL` `BKA_LOG_FORMAT` `BKA_LOG_DIR` `BKA_LOG_TO_FILE` |

---

## Repository Structure

```
banking-knowledge-agent/
├── app/
│   ├── agent/           Knowledge agent: decisions, tool selection, answering
│   ├── __main__.py      `python -m app` — starts the web app from the settings
│   ├── conversation/    Sessions, follow-up rules, conversation service
│   ├── core/            Settings, logging, tracing, observability (request ids, metrics), CLI constants
│   ├── eval/            Evaluation: dataset, metrics, runner, scorecard CLI
│   ├── knowledge/       Document models and the strict loader
│   ├── llm/             Provider protocol, prompts, citation check, mock and vendor adapters
│   ├── mcp/             Tool contract, registry, MCP server, six tools
│   ├── rag/             Chunking, embeddings, vector store, retrieval
│   └── web/static/      The no-build web page
├── data/
│   ├── eval/            Evaluation questions, expectations and score floors
│   ├── knowledge/       15 synthetic banking documents, by domain
│   └── vectorstore/     Built search index (git-ignored)
├── docs/
│   ├── HOW_TO_RUN.md            Step-by-step run and end-to-end verification guide
│   ├── HANDOVER.md              Progress, decisions, next action
│   ├── PROJECT_PLAN.md          Stage requirements
│   ├── stage13-contract.md      Shared contract the Stage 13 sub-agents built against
│   └── architecture-guide.html  Architecture reference and decision records
├── tests/               Unit, integration, API and container tests
├── CHANGELOG.md         What changed in each of the 15 stages
├── CLAUDE.md            Working rules for AI-assisted development
├── Dockerfile           Image build: runtime and test targets
├── compose.yaml         One-command local run (single app service)
├── .dockerignore        Keeps secrets and local state out of the image
├── .env.example         Documented configuration
├── pyproject.toml       pytest, ruff and mypy configuration
└── requirements*.txt    Pinned runtime and dev dependencies
```

---

## Engineering Focus

- **Grounded answers** — every claim cited; no evidence means an explicit refusal with no model call.
- **Deterministic, testable decisions** — routing, tool choice and follow-ups are rules, not model calls.
- **Swappable boundaries** — protocols for embedders, vector stores, LLM providers, tools and session stores.
- **Vendor neutrality, proven** — two real adapters behind one interface; switching is one setting.
- **Security by default** — prompt-injection fencing, optional API key (mandatory in production), rate limiting, input limits, log redaction, secrets only from the environment.
- **Observable** — a request id on every log line, per-step latency, and in-process metrics.
- **Cost safety** — free mock by default; paid calls need two deliberate settings.
- **Real protocols** — a genuine MCP server alongside the in-process registry.
- **Quality gates** — 1416 tests with no paid call, strict mypy, ruff; retrieval and routing scored on a reviewed evaluation set with the real model.
- **Documented reasoning** — every design decision recorded with what was chosen, why and what was rejected.

---

## Licence

**No licence is granted.** Copyright © 2026 Zuleikha, all rights reserved.

This is a demonstration and portfolio project, published so it can be read and assessed. It is
not offered for reuse: no permission is given to copy, modify or redistribute it. Ask first.

All data is synthetic — no real banking system, customer or transaction is represented.
