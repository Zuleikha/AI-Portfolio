# Security

What this service does and does not protect against. Stated plainly, because a
fraud scorer that overstates its own hardening is worse than one that says it is
a demo.

## Threat model

This is a **portfolio demonstration**, not a deployed product. It is intended to
run locally or behind something that already handles authentication, TLS and
rate limiting. It should not be exposed directly to the internet.

## What is handled

### Input validation

Every request to `/predict` is validated by Pydantic against a model with **30
individually required float fields**. There is no default, no optional field and
no coercion from a string that is not numeric.

- A missing field → `422`, naming the field
- A non-numeric field → `422`
- Extra fields → ignored, not passed to the model

The test suite asserts each of the 30 fields is required individually, so a
schema loosened by accident fails the build.

### No arbitrary deserialisation of user input

The model is loaded with `joblib` from a **repository-local path fixed at
import time**. No request can influence what gets loaded. `joblib.load` on
attacker-controlled bytes is arbitrary code execution; that path does not exist
here.

### Errors do not leak internals

`/predict` wraps scoring in a `try/except`. On failure it logs the full
exception with its trace and returns:

```json
{ "detail": "Internal scoring error" }
```

The exception text never reaches the caller. A test asserts the response body
does not contain it.

### Paths are anchored, not relative

`PROJECT_ROOT = Path(__file__).resolve().parents[1]`. The service starts from
any working directory and always loads the same artefacts. No cwd-dependent
model resolution.

### Fail-fast on a bad artefact

The model loads at import. A missing or corrupt bundle raises and the process
refuses to start, rather than starting and returning wrong answers. For a
service whose only job is scoring, an instance that cannot score has nothing
useful to report.

### No secrets in the repository

There are no API keys, tokens or credentials in the code or config. The only
optional credential is DagsHub experiment tracking, read from the environment
and **opt-in** — training runs fully offline without it. See
[`.env.example`](../.env.example).

### Dependencies are capped

Every runtime dependency in `pyproject.toml` is capped at the next major
version. An unbounded `>=` range means a fresh build can pick up a major release
that breaks model deserialisation with no code change — a real supply-chain and
correctness risk, and the source project's own audit flagged it as HIGH.

## What is NOT handled

| Gap | Consequence |
|---|---|
| **No authentication** | Anyone who can reach the port can score transactions |
| **No rate limiting** | Nothing prevents unbounded request volume |
| **No TLS** | Runs plain HTTP; terminate TLS upstream |
| **No audit log of scoring decisions** | Requests are logged at INFO; there is no tamper-evident record of what was scored and what was decided |
| **No request-size limit beyond the schema** | The schema bounds the shape, not the body size; enforce upstream |
| **No CORS policy** | FastAPI defaults; set explicitly before any browser client |

All of these belong to a deployment layer this repo does not include. They are
tracked in [ROADMAP.md](ROADMAP.md).

## Privacy

### The input carries no direct identifiers

`V1`–`V28` are **PCA components** published with the Kaggle dataset. They are
not merchant, card number, country, or MCC — those fields were transformed away
before publication precisely so the data could be released.

The two derived fields, `log_amount` and `hour_of_day`, carry no identity on
their own.

This means the request body cannot leak a card number, because a card number
cannot be expressed in it. It does **not** mean the components are
non-identifying in combination with other data — PCA is a rotation, not
anonymisation. Do not treat a stored request log as anonymous.

### Nothing is persisted

The service holds no database and writes no transaction data. Each request is
scored and discarded. Application logs record that a request failed, not what it
contained.

### The dataset is not redistributed

`data/raw/` contains only a `.gitkeep`. The Kaggle dataset must be downloaded
under its own licence.

## What a false positive costs

A model that flags a legitimate transaction blocks a real person's payment. The
0.28 threshold was chosen partly for this reason — it flags **0.18%** of traffic
rather than the 0.30% the cost-optimal 0.03 would flag, with precision of 81.6%
against 51.2%. See [DECISIONS.md](DECISIONS.md).

The service returns a probability and a decision. **It does not block anything.**
What happens to a flagged transaction is the caller's decision, and should
involve a human where the cost of being wrong falls on a customer.

## Reporting

This is a portfolio repository with no production deployment. Open an issue for
anything found here.
