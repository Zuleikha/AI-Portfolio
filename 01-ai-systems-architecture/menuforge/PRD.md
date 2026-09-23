# PRD — menuforge

**Status:** Stage 1 · **Owner:** project author · **Type:** prototype service

---

## 1. Goal

Turn a photo of a restaurant menu into structured, validated menu records in a
database, through a single HTTP call.

One endpoint takes an image, makes **one Claude call using forced tool use** to
pull out the items, validates the result against a **Pydantic** contract, and
persists it to **Postgres**. If the model returns a shape that fails validation,
the service retries; if the retries run out, the caller gets a `422`.

**What "done" looks like:** a caller can `POST` a menu image and immediately
`GET` back the items it contained, with prices, as typed JSON — no manual data
entry, no human in the loop.

**Explicit non-goal:** this is a prototype that proves the extraction contract.
It is not a multi-tenant product. See [§5 Out of scope](#5-out-of-scope).

---

## 2. User stories

| # | As a… | I want… | So that… |
|---|---|---|---|
| **US-1** | restaurant operator onboarding to a platform | to upload a photo of my menu and get every item and price back as structured data | I don't have to type in 80 menu items by hand |
| **US-2** | backend developer consuming this service | a stable, typed JSON response shape that never varies | I can write my integration against a contract instead of defensively parsing prose |
| **US-3** | backend developer | a clear, distinct failure response when extraction can't produce valid data | I can retry, queue for human review, or surface an error — instead of storing garbage |
| **US-4** | operator or support engineer | to list the items already extracted and stored | I can verify what actually landed in the database after an upload |
| **US-5** | developer running this locally | to start the service with an API key and a Postgres URL and nothing else | I can evaluate it in minutes without standing up a queue or an auth stack |

---

## 3. Functional requirements

### FR-1 · `POST /extract`
- Accepts a single image file as `multipart/form-data`.
- Validates the upload **before** spending an LLM call (see [FR-5](#fr-5--upload-validation)).
- Base64-encodes the image and sends it to Claude in **one** message.
- Uses **forced tool use** (`tool_choice = {"type": "tool", "name": "extract_menu"}`)
  so the model must return arguments matching a declared JSON schema, rather than
  prose the service has to parse.
- Validates the tool arguments with Pydantic (`ExtractedMenu`).
- Persists every valid item to Postgres.
- Returns the validated menu as JSON.

### FR-2 · Retry on validation failure
- Forced tool use constrains the shape but does **not** guarantee it. The model
  can still return a payload that fails Pydantic validation.
- On validation failure the service **re-calls the model**, up to
  **2 retries** — **3 total attempts** (1 initial + 2).
- Transient API/network errors are retried on the same budget.

### FR-3 · Exhausted retries → `422`
- When all 3 attempts fail, the service raises a single dedicated error type
  and the endpoint returns **HTTP 422** with a message identifying the last failure.
- **Nothing is written to the database** on a failed extraction — a request either
  persists a fully valid menu or persists nothing.

### FR-4 · `GET /items`
- Returns all stored menu items as a JSON array.
- No pagination, no filtering (prototype scope).

### FR-5 · Upload validation
Rejected **before** any LLM call, so a bad upload costs nothing:

| Check | Rule | Response |
|---|---|---|
| Content type | must be an image type (`image/png`, `image/jpeg`, `image/webp`, `image/gif`) | `415` |
| Size | must be under the configured limit | `413` |
| Empty body | zero-byte upload rejected | `400` |

> **Note:** the reference prototype does none of this — it reads any upload and
> defaults an absent content type to `image/png`. This is a deliberate tightening;
> the rationale is recorded in SECURITY.md at Stage 7.

### FR-6 · Startup
- The service creates its database tables on startup so a fresh environment works
  with no migration step.

### FR-7 · Structured logging
- Every extraction logs **start**, **success with duration**, and **errors**.
- Logs never contain raw image bytes or the API key. See [§8](#8-security-considerations).

---

## 4. Technical constraints

| Constraint | Value | Why |
|---|---|---|
| Language | Python ≥ 3.11 | Modern typing (`list[str]`, `X \| None`) used throughout |
| API framework | FastAPI | Async upload handling, automatic OpenAPI |
| LLM | Anthropic Claude, forced tool use | See DECISIONS.md (Stage 2) |
| LLM calls per request | **Exactly one per attempt**, max 3 attempts | Cost and latency ceiling |
| Validation | Pydantic v2 | Single source of truth for the response contract |
| Datastore | Postgres via SQLAlchemy | See DECISIONS.md (Stage 2) |
| Processing model | **Synchronous** — the caller waits for the LLM | No queue in scope; caller must tolerate multi-second latency |
| Credentials | Environment variables only | Never in config files, never in the image |
| Deployment | Single container, stateless | Postgres holds all state |

**Accepted consequence of synchronous processing:** a request can take tens of
seconds when retries fire. Callers need a generous client timeout. Moving to a
job queue is the known fix and is deliberately out of scope.

---

## 5. Out of scope

Not built, and **no stubs or placeholders** for them either:

| Excluded | Reason |
|---|---|
| **Authentication / authorization** | Prototype runs in a trusted context. Adding auth would not change what the extraction contract proves. |
| **Job queue / async processing** | Synchronous keeps the failure path legible. Revisit when p95 latency or upload volume makes waiting untenable. |
| **Vector search / embeddings** | Nothing in the goal requires semantic retrieval. |
| **Frontend / UI** | The deliverable is an API. |
| **Multi-tenant support** | No tenant column, no isolation, no per-tenant limits. All items live in one flat table. |
| **Rate limiting** | Follows from having no auth and no tenancy. |
| **Menu updates / dedupe** | Every upload appends. Re-uploading the same menu duplicates rows. Accepted for a prototype. |
| **Image preprocessing** (deskew, crop, OCR) | The model reads the image directly. |
| **Pagination on `/items`** | Row counts stay small at prototype scale. |

---

## 6. Success criteria

Testable, with the LLM client mocked unless stated otherwise:

| # | Criterion | How it's verified |
|---|---|---|
| **SC-1** | A valid image whose first model call returns a valid payload → `200`, body matches the Pydantic contract, rows in Postgres | Test: success path |
| **SC-2** | First call returns an invalid payload, second returns a valid one → `200`, and the model was called **exactly twice** | Test: retry-then-success, asserting call count |
| **SC-3** | All 3 attempts return invalid payloads → dedicated error raised, endpoint returns **`422`**, and **zero rows written** | Test: exhausted retries |
| **SC-4** | The model is never called more than 3 times for one request | Call-count assertion in SC-3 |
| **SC-5** | `GET /items` returns previously stored items with correct fields and types | Test: `/items` endpoint |
| **SC-6** | A non-image upload → `415`; an oversized upload → `413`; **no LLM call made** in either case | Test: upload validation, asserting the mock was not called |
| **SC-7** | No log line emitted during a full request contains image bytes or the API key value | Test: capture logs, assert absence |
| **SC-8** | The full suite passes in CI on every push | GitHub Actions running pytest |

---

## 7. Failure modes

| Failure | Detection | Behaviour | Caller sees |
|---|---|---|---|
| Model returns a shape that fails Pydantic | `ValidationError` | Retry, up to the 3-attempt budget | `200` if a retry succeeds |
| All attempts fail validation | Retry budget exhausted | Dedicated error raised; **no DB write** | **`422`** |
| Anthropic API error / network failure / timeout | Exception from the SDK | Retried on the same budget | `422` if never recovers |
| No API key in the environment | Missing env var at client construction | Fails loudly at call time | `500` |
| Upload is not an image | Content-type check, pre-LLM | Rejected, **no LLM call** | `415` |
| Upload exceeds the size limit | Size check, pre-LLM | Rejected, **no LLM call** | `413` |
| Upload is empty | Zero-length body | Rejected, **no LLM call** | `400` |
| Image is a valid image but not a menu | **Not detected** — model may return `items: []` or plausible-looking nonsense | Stored as-is | `200` with junk |
| Postgres unreachable | Connection error on session use | Surfaced, not swallowed | `500` |
| Model reads a price wrong (e.g. `9.50` → `950`) | **Not detected** — it is a schema-valid number | Stored as-is | `200` with a wrong price |

> **Known limitation — the honest one:** validation proves the data is the right
> *shape*, not that it is *correct*. A hallucinated item with a plausible price
> passes every check in this system. Detecting that needs either human review or
> an eval set with ground-truth menus; both are out of scope here, and a caller
> must not treat a `200` as a guarantee of accuracy.

---

## 8. Security considerations

Full treatment lands in SECURITY.md at Stage 7. The requirements this PRD imposes:

| Area | Requirement |
|---|---|
| **API key** | Read from the environment only. Never hardcoded, never in config YAML, never in the container image, **never logged** — not in error messages, not in tracebacks. |
| **Image bytes** | Never written to logs, and not persisted after extraction. Only the extracted text fields are stored. |
| **Input validation** | Content type and size checked **before** the LLM call — an unvalidated upload is both a cost risk and an abuse vector. |
| **Untrusted content** | Text in the image is **data, not instructions**. A menu image containing something like *"ignore previous instructions"* must not change service behaviour — forced tool use constrains the model to returning tool arguments, which is a meaningful part of why it was chosen. |
| **Error responses** | Return what failed, not internal detail — no stack traces, connection strings, or key fragments to the caller. |
| **PII** | Menu images are not expected to contain personal data; none is deliberately collected or stored. |
| **Dependencies** | Pinned via `pyproject.toml`; the container runs as a non-root user. |
| **Accepted risk** | With no auth and no rate limiting, **anyone who can reach the endpoint can spend API budget.** This is only acceptable because the service is not internet-exposed. Exposing it publicly requires auth and rate limiting first — that is a hard precondition, not a nice-to-have. |
