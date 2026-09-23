# Security — menuforge

What this prototype defends against, what it deliberately does not, and the one
precondition that must be met before it is exposed to anything untrusted.

> **Read this first:** menuforge has **no authentication and no rate limiting**.
> It is safe only on a trusted network. See [§5](#5-explicitly-out-of-scope).

---

## 1. Input validation on upload

Every upload is checked **before any model call**, so a bad or hostile upload
costs no API spend. This matters as much for cost as for correctness: without it,
anyone who can reach the endpoint can burn API budget with arbitrary files.

| Check | Rule | Rejected with |
|---|---|---|
| **Content type** | Must be `image/png`, `image/jpeg`, `image/webp`, or `image/gif` | `415` |
| **Size** | Must not exceed **10,485,760 bytes (10 MiB)** | `413` |
| **Non-empty** | Must be larger than 0 bytes | `400` |

**Oversized uploads are refused before being read into memory** where the client
declares a size — the declared length is checked first, then the actual length
after reading. This prevents a large upload from consuming memory just to be
rejected afterwards.

Each rejection is logged as an `extract.rejected` event with its reason, so
refusals are visible rather than silent.

### What is *not* validated

The content type is taken from the client's `Content-Type` header — **it is not
verified against the file's actual bytes.** A caller can label anything
`image/png`. This is acceptable only because the model, not an image decoder, is
what reads the file: there is no local parser to attack with a malformed image.
The realistic outcome of a mislabelled file is a `422`, not a compromise.

Sniffing magic bytes would be the fix if this were ever exposed publicly.

---

## 2. What happens on a malformed or oversized image

| Input | Outcome |
|---|---|
| **Oversized** (> 10 MiB) | `413`. No model call, no memory spent reading the body where the size is declared. |
| **Empty** (0 bytes) | `400`. No model call. |
| **Wrong content type** (PDF, executable, anything non-image) | `415`. No model call. |
| **Correct type, corrupt bytes** | Passes validation and reaches the model. The model cannot read it, so the attempt fails, is retried up to the 3-attempt budget, and the caller gets a `422`. Nothing is written. |
| **A valid image that is not a menu** | **Not detected.** The model may return `items: []` or plausible-looking nonsense, which is stored and returned as a `200`. |

**The honest limitation:** validation proves the data is the right *shape*, not
that it is *correct*. Detecting a hallucinated item or a misread price needs human
review or a ground-truth eval set — both out of scope. A caller must not treat a
`200` as a guarantee of accuracy.

---

## 3. Credentials

**The Anthropic API key is never logged.** Three mechanisms, in order:

1. **It is only ever read from the environment** (`ANTHROPIC_API_KEY`). It is
   never hardcoded, never written into `config/*.yaml`, and never baked into the
   container image. This is **enforced, not merely documented**: the settings
   models forbid unknown keys and declare no credential fields, so a key written
   into a config file fails the load at startup rather than being accepted. The
   same applies to `DATABASE_URL`. See `tests/test_settings.py`.
2. **Nothing logs it deliberately.** No log call in menuforge takes the key or the
   client object as an argument.
3. **`SecretRedactingFilter` scrubs it anyway.** Every log record is rendered and
   scanned before it reaches a sink; any occurrence of the key is replaced with
   `***REDACTED***`. This covers the message, lazy `%s` arguments — including a key
   embedded in an exception raised by a third-party library — and structured
   fields.

That third layer is not theoretical. It was added as defence in depth, and the
test suite caught a case where an upstream error carrying the key would otherwise
have reached the log in full.

**The test suite needs no real key.** The default run patches the Anthropic client
and uses an obvious placeholder. Only the opt-in `live` tests use a real key, read
from the environment or `.env` — never committed, and never written to a fixture.
In CI it exists solely as a repository secret consumed by `live.yml`.

Tracebacks are deliberately **not** written to the log sink; error events record
the exception *type* only, so request data cannot ride into logs inside a stack
trace.

**Error responses** return what failed, not internal detail — no connection
strings and no key fragments.

---

## 4. Data handling

| Item | Treatment |
|---|---|
| **Image bytes** | Never logged. Only `size_bytes` is recorded. **Not persisted** — the image is read into memory, sent to the model, and dropped. |
| **Extracted text** | Persisted to Postgres. Menu items are not expected to contain personal data, and none is deliberately collected. |
| **Prompt injection** | Text inside a menu image is **data, not instructions**. An image containing *"ignore previous instructions…"* has a small surface to act on: forced tool use constrains the model to returning arguments for one declared tool, and anything that fails the Pydantic contract is rejected rather than acted upon. This is a **mitigation, not a guarantee** — see [DECISIONS.md D-001](DECISIONS.md#d-001--forced-tool-use-for-structured-menu-extraction). |
| **Transport** | The service speaks plain HTTP. TLS is the deployment's responsibility (a reverse proxy or load balancer). |

**Dependencies and runtime:** dependencies are declared in `pyproject.toml`, and
the container runs as a **non-root user**.

---

## 5. Explicitly out of scope

Not built, and no partial versions of them either.

| Excluded | Consequence you are accepting |
|---|---|
| **Authentication** | Anyone who can reach the endpoint can use it. There is no notion of a caller, so nothing can be attributed, revoked, or audited per user. |
| **Rate limiting** | Follows from having no auth. There is no per-caller quota and no ceiling on request volume. |
| **Multi-tenancy** | One flat table, no tenant column. One customer's data is not isolated from another's. |
| **Audit logging** | Operations are logged, but there is no tamper-evident record of who did what — there is no "who". |
| **Secrets management** | Credentials come from environment variables. No vault, no rotation. |

### The precondition

**Together, no auth and no rate limiting mean anyone who can reach `/extract` can
spend your Anthropic budget without limit.** Upload validation caps the cost of a
single request; nothing caps the number of requests.

This is acceptable **only** while the service is not reachable from an untrusted
network. Exposing it publicly requires authentication and rate limiting **first** —
that is a hard precondition, not a nice-to-have, and it is the thing most likely
to be forgotten when a prototype gets a demo URL.

---

## 6. Reporting

This is a prototype and not a deployed service. Raise anything you find as an
issue in this repository.
