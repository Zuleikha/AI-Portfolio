# Stage 13 — Shared Contract (FROZEN 2026-09-16)

Written by the main session **before** any sub-agent starts. Sub-agents implement
against it and **do not change it**. If a unit needs a contract change, it stops and
reports that instead of making the change.

Decisions behind it: `docs/HANDOVER.md` 13.A–13.D · guide §20.50–§20.53.

---

## 1. Already written by the main session (do not edit)

| File | What is frozen |
|---|---|
| `app/core/config.py` | `api_key: SecretStr \| None = None` · `rate_limit_per_minute: int = 60` (≥0, 0 = off) · `question_max_chars: int = 2000` (≥1) · production without a non-blank key → `ValidationError` mentioning `BKA_API_KEY` |
| `app/core/observability.py` | new metric names `AUTH_FAILURES_TOTAL = "auth_failures_total"`, `RATE_LIMITED_TOTAL = "rate_limited_total"` |
| `app/api/security.py` | `API_KEY_HEADER = "X-API-Key"` · `AUTH_REQUIRED` message · `require_api_key(request: Request) -> None` (stub) |
| `app/api/rate_limit.py` | `RATE_LIMITED` message · `WINDOW_SECONDS = 60.0` · `FixedWindowRateLimiter(limit, window_seconds=60.0, clock=time.monotonic)` with `.check(client: str) -> float \| None` · `enforce_rate_limit(request: Request) -> None` (stubs) |
| `app/main.py` | `app.state.rate_limiter` = limiter or `None` when limit is 0 · `/metrics` gets `require_api_key` · `/api/sessions/*` gets `[enforce_rate_limit, require_api_key]` in that order · `/health` open |
| `.env.example`, `tests/test_config.py` | the three new settings documented / tested |

## 2. Behaviour everyone relies on

| Case | Response |
|---|---|
| Key configured, header missing or wrong | `401`, body `{"detail": AUTH_REQUIRED}`, header `WWW-Authenticate: ApiKey` — identical for missing and wrong |
| Key not configured | no check at all |
| Over the rate limit | `429`, body `{"detail": RATE_LIMITED}`, header `Retry-After: <int seconds, ≥1, rounded up>` |
| Question longer than `question_max_chars` | `422` (FastAPI validation shape or `HTTPException(422)` — unit U3 chooses, documents it) |
| `GET /ready`, all checks pass | `200` `{"status": "ready", "checks": {"<name>": "ok", ...}}` |
| `GET /ready`, any check fails | `503` same shape with `"status": "not_ready"` (gap filled at integration — U3's choice), failing check value `"failed"` — **never** exception text |

Rules for every unit:

- **Never log** a key, a header value, a question, an answer, a session id, or a client
  address in clear. A client address may be logged only via `fingerprint()`.
- Log event names: `api.auth_rejected` (field `reason`: `missing`\|`invalid`),
  `api.rate_limited`, `api.ready_check_failed` (fields `check`, `error_type`).
- Metrics: increment `AUTH_FAILURES_TOTAL` on each 401, `RATE_LIMITED_TOTAL` on each 429.
- Key comparison uses `hmac.compare_digest`.
- Rate-limit client key: `request.client.host`, or `"unknown"` when absent. No
  `X-Forwarded-For` trust (documented as a Stage 14 proxy concern).
- `@traced` on every new function **except** FastAPI route handlers and dependencies
  (existing rule, `app/api/dependencies.py`) and hot-path helpers already exempted (10.F).
- `/ready` makes **no network call and no paid call**, and never loads the embedding model.

## 3. Units — one sub-agent each

| Unit | Areas (plan list) | Owns (may edit) | Tests it adds |
|---|---|---|---|
| **U1 Auth** | Authentication · Authorisation | `app/api/security.py` body · `app/web/static/app.js`, `index.html`, `styles.css` (key box; stored in `sessionStorage`, wrapped in try/catch; sent as `X-API-Key` on every `/api` call) | `tests/test_api_auth.py` |
| **U2 Rate limit** | Rate limiting | `app/api/rate_limit.py` bodies (thread-safe; expired windows pruned so memory stays bounded) | `tests/test_rate_limit.py` |
| **U3 Readiness + input** | Input validation · `/ready` (12.D) | `app/api/routes/health.py` · `app/api/routes/conversation.py` (length limit; `session_id` length bound) | `tests/test_ready.py`, `tests/test_api_validation.py` |
| **U4 Injection + MCP** | Prompt injection risks · MCP security | `app/llm/prompts.py`, `app/mcp/**` (incl. stale "Stage 7 … a model" wording, Stage 10 item 6) | `tests/test_security_injection.py` |
| **U5 Failure handling** | LLM failure · Tool failure | `app/llm/service.py`, `app/llm/*_provider.py`, `app/agent/agent.py`, `app/api/middleware.py` (500 carries `X-Request-ID`, Stage 10 item 4) | `tests/test_failure_handling.py` |
| **U6 Secrets · logging · privacy · deps** | Secrets management · Logging risks · Data privacy · Dependency security | `app/core/logging.py` (redaction processor for sensitive-named fields), `.gitignore`, `.dockerignore` | `tests/test_log_redaction.py` |

**Nobody else edits:** `app/core/config.py`, `app/core/observability.py`, `app/main.py`,
`tests/conftest.py`, existing test files, `requirements*.txt`, `Dockerfile`,
`compose.yaml`, `README.md`, `docs/**`. Needed there? → report it, main session integrates.

**Every unit:** no git write commands · no network · no paid API · no package installs ·
run checks only via `./.venv/Scripts/python.exe -m …` · pytest without `-q` · run its own
test files plus `ruff check`, `ruff format --check` and `mypy` · fixes are *lightweight*.

## 4. Findings file — one per unit, fixed shape

Written to the session scratchpad as `findings-U<n>.md`; the main session merges them into
guide §16 and §20.

```
# U<n> — <unit name>
## <Plan area>
| Risk | Status | Evidence (file:line) | Protection / note |
(Status is one of: FIXED · ALREADY OK · DOCUMENTED · STAGE 14)
## Changes
- file — one line
## Tests
- command → result
## Needs main session
- contract change / shared-file edit requests, or "None"
```
