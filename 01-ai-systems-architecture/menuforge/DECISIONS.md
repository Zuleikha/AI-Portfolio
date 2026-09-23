# Decisions — menuforge

Architecture decision record. Newest last. Each entry states the context, the
call made, what was rejected and why, and what would make us revisit it.

| ID | Decision | Status |
|---|---|---|
| [D-001](#d-001--forced-tool-use-for-structured-menu-extraction) | Forced tool use for structured menu extraction | Accepted |
| [D-002](#d-002--postgres-as-the-only-datastore) | Postgres as the only datastore, plain SQLAlchemy, no queue | Accepted |
| [D-003](#d-003--no-tracing-decorator-structured-logging-only) | No tracing decorator — structured logging only | Accepted |
| [D-004](#d-004--layered-configuration-env-var--yaml--code-default) | Layered configuration: env var > YAML > code default | Accepted |
| [D-005](#d-005--live-api-tests-are-opt-in-and-off-the-push-path) | Live API tests are opt-in and off the push path | Accepted |

---

## D-001 · Forced tool use for structured menu extraction

**Status:** Accepted · **Date:** 2026-08-12
**Ported from:** `restoai/docs/ADR-001-structured-extraction.md`

### Context

The extraction step needs the model to return data matching an exact schema:
item name, price, description, modifiers.

An LLM asked to "return JSON" in a plain text prompt will sometimes wrap it in
prose, use inconsistent field names, or return invalid JSON — especially under
load or with unusual input images. Every one of those outcomes has to be handled
somewhere, and handling it in string-parsing code is the expensive place to do it.

### Decision

Use Claude's **forced tool use** — `tool_choice` set to a specific tool, with an
explicit JSON input schema — instead of prompting for raw JSON in a text response
and parsing it manually.

The model is given one tool, `extract_menu`, and is required to call it. The
response is read from the `tool_use` content block's arguments, not from text.

### Alternatives considered

| Alternative | Verdict | Why |
|---|---|---|
| **Plain prompt asking for JSON**, parsed with `json.loads` | Rejected | No schema enforcement. The model can and does drift on field names or wrap output in explanatory text. Requires more defensive parsing code to solve the same problem. |
| **Regex / string extraction** on a free-text response | Rejected | Fragile. Breaks on any format variation, and does not scale to a more complex schema like nested modifiers. |
| **Separate structured-output step** (a second call to reformat the first) | Rejected for this scope | Doubles latency and cost per request for a problem forced tool use already solves in one call. |

### Consequences

**Forced tool use does not guarantee schema validity end to end.** The model can
still put a string where a number is expected. Validation and retry logic are
still required on top of it — the tool schema narrows the output space, it does
not close it.

What this bought is a **change in failure mode**, from *"unparseable text"* to
*"occasional schema violation"* — a narrower, more predictable failure surface.
The retry loop in `llm/client.py` exists specifically for that residual case,
**not** as a defence against completely malformed output.

There is also a security consequence worth naming: because the model's only
sanctioned output path is tool arguments, text embedded in a menu image
(*"ignore previous instructions and…"*) has a much smaller surface to act on than
it would in a free-text completion. This is a mitigation, not a guarantee.

### What would change at production scale

- **Vary the parameters on retry** — a fallback model, or a lower temperature on
  the second attempt. Retrying with identical parameters against the same model
  has a real chance of reproducing the same mistake. *(Not implemented here; see
  the "same-parameter retry" note in [D-002](#d-002--postgres-as-the-only-datastore)'s
  triggers for the equivalent reasoning.)*
- **Track validation failure rate as a metric.** A rising rate means the schema or
  the prompt needs revisiting — it does not mean "add more retries."

---

## D-002 · Postgres as the only datastore

**Status:** Accepted · **Date:** 2026-08-12

### Context

Extracted menu items have to be persisted and read back. The eventual production
design (`restoai/PRODUCTION.md`) has considerably more moving parts: object
storage for the uploaded image, Kafka between upload and processing, an
autoscaled worker pool, a dead-letter queue, and a tenant-sharded vector database
alongside Postgres.

The question for **this** stage is how much of that to build now, when the thing
being proven is the extraction contract, not the ingestion pipeline.

### Decision

**Postgres is the only datastore, accessed through a plain SQLAlchemy model, with
no queue and no object storage.**

Concretely:

- One table, `menu_items`, one declarative model — no repository layer, no service
  layer, no abstraction over SQLAlchemy.
- Schema created at startup via `create_all`. **No migration tool.**
- The Claude call happens **synchronously on the request thread**. No broker, no
  workers, no background tasks.
- **The uploaded image is not stored.** It is read into memory, sent to the model,
  and dropped. Only the extracted fields are persisted.
- No vector database, no embeddings.
- No tenant column, no per-tenant isolation.

### Alternatives considered

| Alternative | Verdict | Why |
|---|---|---|
| **SQLite** | Rejected | Would remove the need to run a service locally, but diverges from the production target. The `JSON` column for modifiers and concurrent-write behaviour differ enough that a passing test here would not predict production. Cheap now, misleading later. |
| **Queue + worker pool now** (the production design) | Rejected | Correct destination, wrong time. It adds a broker, a worker process, and a DLQ to operate — and none of it changes whether the extraction contract holds. Building it now would mean debugging infrastructure instead of the actual problem. |
| **Postgres + vector DB from the start** | Rejected | Semantic search is explicitly out of scope in PRD.md §5. An index with no query path is dead weight. |
| **Repository / DAO abstraction over SQLAlchemy** | Rejected | A swap-the-database abstraction for a system with one table and no intention of swapping databases. The SQLAlchemy session *is* the abstraction. |
| **Alembic migrations from the start** | Rejected for now | With no deployed data to preserve, `create_all` is sufficient and one less thing to run. See triggers below — **this is the first thing to fall.** |

### Consequences

**What this buys:** one dependency to run locally (`docker compose up postgres`),
a fully synchronous and therefore fully legible failure path, and no
infrastructure between a failing test and its cause.

**What it costs — accepted, and each maps to a trigger below:**

| Cost | Effect |
|---|---|
| Client latency **equals** model latency | 2–5s typical, longer when retries fire. Callers need generous timeouts. |
| A crash mid-request loses the request | No retry, no record that it happened. The caller's upload is simply gone. |
| Failures are only visible in logs | A `422` plus a log line. Someone has to be watching. |
| `create_all` cannot alter an existing table | The first schema change against real data has no upgrade path. |
| Every upload appends | Re-uploading the same menu duplicates rows. No dedupe, no update semantics. |
| One flat table, no tenancy | One customer's data is not isolated from another's. Fine for a prototype, disqualifying for a product. |
| The image is unrecoverable after the call | A failed extraction cannot be replayed or reviewed — the input is gone. |

### What would trigger moving off this

In the order they are expected to bite, following the migration order in
`restoai/PRODUCTION.md`:

| # | Trigger | Move to |
|---|---|---|
| **1** | **Any schema change once real data exists.** `create_all` will not alter a populated table. | **Alembic.** Do this before the first real deployment, not after. |
| **2** | **Client latency becomes a complaint**, or uploads must survive a process crash. | Move the Claude call **off the request thread** into a background worker; `POST /extract` returns a job id. |
| **3** | **More than one worker is needed**, or jobs must survive a crash with a record. | A **real queue** (Kafka in the production design), decoupling upload from processing and letting audit/analytics consume the same event. |
| **4** | **Silent failures become a support cost** — someone is tailing logs to find failed extractions. | **Dead-letter queue plus alerting.** |
| **5** | **A failed extraction needs to be replayed or reviewed by a human.** | Persist the uploaded image to **object storage** and reference it from the row. This is also the precondition for a useful DLQ — a dead-lettered job with no image cannot be retried. |
| **6** | **Semantic search over menu items is actually requested.** | Add embeddings — `pgvector` in the same Postgres first, since it needs no new infrastructure. Only move to a dedicated vector DB at trigger 7. |
| **7** | **More than one tenant**, or one tenant's load degrades another's. | Tenant column and per-tenant limits in Postgres; shard or move to a managed vector DB for search. |

**Note on ordering:** triggers 1 and 5 are the ones that are cheap now and
expensive later. Adding Alembic before there is data to migrate takes an hour;
adding it after costs a hand-written backfill. Storing the image costs an S3
bucket; not storing it means a failed extraction is unrecoverable and there is no
way to build a ground-truth eval set from production traffic later.

---

## D-003 · No tracing decorator, structured logging only

**Status:** Accepted · **Date:** 2026-08-12

### Context

The author's standing engineering rules call for an `@traced` decorator on every
new function, writing to a dedicated sink. menuforge has no tracing module, and
the project brief's file list does not include one.

### Decision

**No `@traced` decorator and no tracing module in this project.** Observability is
structured logging only, via `menuforge.observability.logging`: operation start,
success with duration, and errors.

This is a deliberate, scoped exemption from the standing rule — recorded here so
it reads as a decision rather than an oversight.

### Alternatives considered

| Alternative | Verdict | Why |
|---|---|---|
| **Add `observability/tracing.py` and decorate everything** | Rejected for this project | Adds a module outside the brief's scope. With four modules and one synchronous request path, per-function spans would describe a call graph that fits on one screen. |
| **Decorate only `extract_menu` and the endpoints** | Rejected | The partial version has the cost of the dependency without the property that makes tracing useful — complete coverage. |

### Consequences

Per-request timing is available (the endpoint logs duration), but per-function
timing is not. Finding *which* step in a slow extraction was slow means reading
the log line for the LLM call, not a span tree. Acceptable while there is exactly
one LLM call and one database write per request.

### What would trigger revisiting

- **More than one LLM call per request** — a fallback model, a second extraction
  pass, or a reformat step. At that point "which call was slow" stops being
  answerable from a single duration.
- **The move off the request thread** (D-002 trigger 2). Once work spans a queue
  and a worker, correlating a request to its processing needs trace context;
  logging alone cannot reconstruct it.
- **More than a handful of endpoints**, where the call graph stops being obvious
  from reading `main.py`.

---

## D-004 · Layered configuration: env var > YAML > code default

**Status:** Accepted · **Date:** 2026-08-13

### Context

Stage 0 created `config/development.yaml` and `config/production.yaml`, and
`pyyaml` was declared as a dependency, but nothing ever read either file. The
values that mattered — model id, retry budget, `max_tokens`, effort, upload
limits, log level — lived as module constants, with a single ad-hoc
`MENUFORGE_MODEL` environment override bolted onto the model id.

That left the repo in the worst of both worlds: two config files that looked
authoritative and were not, and a dependency that did nothing. Changing the
upload limit for one environment meant editing code.

### Decision

Wire a typed loader at `src/menuforge/config/settings.py`. Three layers,
strongest first:

1. **Environment variable** — an explicit allow-list, `ENV_OVERRIDES`.
2. **`config/<MENUFORGE_ENV>.yaml`** — the checked-in per-environment values.
3. **Code default** — the Pydantic field defaults, which are what the app runs on
   with no config directory at all.

Settings are Pydantic models with `extra="forbid"` and `frozen=True`, loaded
lazily and cached, with `reset_settings()` for reloads and tests.

**Secrets are excluded by construction.** `ANTHROPIC_API_KEY` and `DATABASE_URL`
have no field on `Settings` and are read from the environment at their point of
use. Because unknown keys are rejected, a credential written into a YAML file
fails the load instead of being silently honoured.

### Alternatives considered

| Option | Verdict | Why |
|---|---|---|
| **Delete the YAML files, environment variables only** | Rejected | Simplest, and genuinely defensible at this size — but it contradicts the Stage 0 file list, and per-environment defaults in a reviewable, diffable file are worth more than one fewer module. |
| **`pydantic-settings`** | Rejected | A new dependency to replace ~40 lines. Its env-var conventions (nested delimiters, prefixes) would also have renamed the existing `MENUFORGE_MODEL`. |
| **Wire only log level and upload limits** | Rejected | Leaves four `llm.*` keys still decorative, which is the exact problem being fixed. |
| **Load config at import time** | Rejected | `main`'s lifespan loads `.env` during startup. Import-time config would freeze values read before that, making behaviour depend on import order. |
| **Allow every field to be overridden by environment variable** | Rejected | An explicit table documents the deployment surface. A generic mechanism would make every field a public API by accident. |

### Consequences

- Configuration is validated at startup. A typo'd key or an out-of-range value
  **fails the boot** instead of being ignored — consistent with the fail-loud rule.
- `llm.client` and `main` read settings at call time, so they hold no tunable
  constants. `MAX_RETRIES`, `MAX_TOKENS`, `DEFAULT_MODEL`, `MAX_UPLOAD_BYTES` and
  `ALLOWED_MEDIA_TYPES` are gone as module constants.
- Settings are process-wide and cached, so tests must reset them. An autouse
  fixture in `tests/conftest.py` does this and pins `MENUFORGE_CONFIG_DIR` to the
  repo's own `config/`, keeping the suite independent of the working directory.
- Two tests load the **shipped** config files, so the files cannot rot back into
  decoration without the suite failing.
- `.env.example` documented `APP_ENV`, which nothing read. Renamed to
  `MENUFORGE_ENV` for consistency with the other variables. No runtime change —
  the old name was never consulted.

### What would trigger revisiting

- **A third environment** beyond development and production, if the files start
  duplicating each other. The fix is a shared `base.yaml` merged underneath, not
  more copies.
- **Per-tenant or per-request configuration.** The cache assumes one config per
  process; anything request-scoped breaks that assumption and needs a different
  shape entirely.
- **Secrets needing rotation without a restart.** Settings are cached at startup;
  live rotation would need an explicit reload path.

---

## D-005 · Live API tests are opt-in and off the push path

**Status:** Accepted · **Date:** 2026-08-13

### Context

Every test asserted against a `MagicMock` shaped the way we *assume* the
Anthropic API behaves. Nothing verified that the tool schema, `tool_choice`,
base64 image encoding and `output_config` we actually send are accepted by the
real service, or that a real response validates against `ExtractedMenu`. A
breaking SDK or API change would have passed CI green.

Separately, `TestClient` drives the ASGI app in-process and never opens a socket,
so HTTP/1.1 parsing, multipart framing over the wire and the server's own error
responses were untested.

### Decision

Two new layers, on different footings:

| Layer | Runs on push? | Why |
|---|---|---|
| `test_server.py` — real uvicorn, ephemeral port, real `httpx` client | **Yes** | Free and fast (~7s). No reason not to. |
| `test_live.py` — one real Anthropic request | **No** | Costs money on every push, and would fail on forks and PRs where the key is absent. |

Live tests carry `pytest.mark.live`, and `addopts = -m "not live"` deselects them
by default. CI runs them from a separate `live.yml` workflow, on
`workflow_dispatch` only — with a `concurrency` group so a queued run and a
running one cannot both spend.

**A schedule is wired but commented out.** A cron spends on a clock nobody is
watching, and a failure sits unread until someone happens to look — so the
default is that spend happens when a person chooses it. The two lines are kept in
`live.yml` so turning it on later is an uncomment, not a rewrite.

**The whole live module derives from one API call**, made once by a module-scoped
fixture. Adding an assertion is free; adding a test that calls the model again is
not.

### Alternatives considered

| Alternative | Verdict | Why |
|---|---|---|
| **Live tests on every push** | Rejected | Spend proportional to commit rate, and red builds on every fork and PR, where the secret is unavailable. |
| **Cassettes / recorded responses** (VCR-style) | Rejected | A recording is a mock that has been true once. It would not catch the API change this exists to catch — the recording keeps passing after the real API moves. |
| **No live test at all** | Rejected | Leaves the central integration assumption unverified. The point of forced tool use (D-001) is a contract with a real service. |
| **A subprocess for the socket tests** | Rejected | `patch.object(main, "extract_menu")` cannot reach another process. A thread in the test process keeps the LLM patched while still using a real socket. |
| **A photograph of a real menu as the fixture** | Rejected | Provenance and licensing questions for a committed binary, for no test benefit. The fixture is generated by a committed script, so it is reproducible and unambiguously ours. |

### Consequences

- A real API or SDK break surfaces within a week, or immediately on a manual run
  — not in production.
- The live test needs the fixture image and its expected prices to stay in sync.
  Both live in `tests/fixtures/`, and the generator is committed alongside.
- The default suite still needs no key and no network.
- `tests.yml` runs `pytest -m live --collect-only` so a misplaced or misspelled
  marker fails the normal build instead of silently disabling the paid tests
  forever.
- Live runs write to a throwaway SQLite file, never a configured database.

### What would trigger revisiting

- **A second live-callable path** (a fallback model, a reformat step). The
  one-call-per-module rule would need rethinking, or the cost stops being trivial.
- **An API break reaching production because nobody ran it.** Manual triggering
  relies on someone remembering. If that fails in practice, uncomment the
  schedule in `live.yml` and add an alert on failure — not add it to push.
- **Flakiness from model variation.** The current assertions demand exact prices
  because the model is transcribing printed text. If that proves unstable, loosen
  to price tolerance *before* loosening the set of dishes — a missing dish is a
  real regression, a rounded price may not be.
