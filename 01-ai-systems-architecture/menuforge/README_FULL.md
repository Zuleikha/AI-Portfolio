# menuforge

Turns a photo of a restaurant menu into structured, validated records in a
database, through one HTTP call.

`POST` a menu image and the service makes a **single Claude call using forced tool
use** to pull out the items, validates the result against a **Pydantic** contract,
and stores it in **Postgres**. If the model returns a shape that fails validation
it retries; if the retries run out you get a `422`. `GET /items` reads back what
was stored.

```
image ──▶ POST /extract ──▶ Claude (forced tool use) ──▶ Pydantic ──▶ Postgres ──▶ JSON
                                      ▲                      │
                                      └──── retry, max 2 ────┘
```

**Status:** working prototype. One endpoint, synchronous, no queue.
**Not production-ready:** no authentication and no rate limiting — see
[SECURITY.md](SECURITY.md) before exposing it to anything.

---

## Setup

**Requirements:** Python 3.11+, Postgres, an Anthropic API key.

**1. Start Postgres**

```bash
docker run -d --name menuforge-db \
  -e POSTGRES_USER=menuforge \
  -e POSTGRES_PASSWORD=menuforge \
  -e POSTGRES_DB=menuforge \
  -p 5432:5432 postgres:16
```

**2. Create and activate a virtual environment**

Keeps the project's dependencies out of your global Python install. `.venv/` is
gitignored.

```bash
python -m venv .venv

source .venv/bin/activate          # macOS / Linux
source .venv/Scripts/activate      # Windows, Git Bash
.\.venv\Scripts\Activate.ps1       # Windows, PowerShell
```

> **If `python -m venv` fails with `No module named venv`**, your Python
> installation is incomplete — reinstall it from
> [python.org](https://www.python.org/downloads/) with the standard library
> included. `pip install virtualenv` is not a reliable workaround: a virtualenv
> built on an incomplete base can segfault when importing packages with native
> extensions.

**3. Install**

```bash
pip install -e ".[dev]"
```

**4. Set the environment**

Copy the example and fill in your key. The service loads `.env` on startup.

```bash
cp .env.example .env
# then edit .env and set ANTHROPIC_API_KEY
```

Real environment variables take precedence over `.env`, so exporting a value
overrides the file — useful in CI and containers, where `.env` is usually absent:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

`.env` is gitignored; `.env.example` is the committed reference.

**Secrets** — environment only, never in a config file:

| Variable | Required | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | **yes** | — (fails at call time if unset) |
| `DATABASE_URL` | no | `postgresql+psycopg://menuforge:menuforge@localhost:5432/menuforge` |

**Everything else** comes from `config/<MENUFORGE_ENV>.yaml`, which each variable
below overrides:

| Variable | Overrides | Default |
|---|---|---|
| `MENUFORGE_ENV` | which file is loaded | `development` |
| `MENUFORGE_CONFIG_DIR` | where the files live | `config` |
| `MENUFORGE_LOG_LEVEL` | `logging.level` | `INFO` |
| `MENUFORGE_MODEL` | `llm.model` | `claude-sonnet-5` |
| `MENUFORGE_MAX_RETRIES` | `llm.max_retries` | `2` |
| `MENUFORGE_MAX_TOKENS` | `llm.max_tokens` | `8000` |
| `MENUFORGE_EFFORT` | `llm.effort` | `low` |
| `MENUFORGE_MAX_UPLOAD_BYTES` | `upload.max_bytes` | `10485760` |

Precedence is **environment variable → YAML → code default**. Config is validated
on load: an unknown or malformed key fails startup rather than being ignored. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the module contract.

**5. Run**

```bash
uvicorn menuforge.main:app --reload
```

Tables are created on startup, so there is no migration step.

---

## Use it

```bash
curl -X POST http://localhost:8000/extract -F "file=@/path/to/menu.jpg"
curl http://localhost:8000/items
```

Full request and response examples, error codes, and behavioural notes:
**[docs/API.md](docs/API.md)**. Interactive docs are served at
`http://localhost:8000/docs`.

---

## Tests

```bash
pytest
```

77 tests, no infrastructure and no API key needed — the Anthropic client is
mocked and the suite falls back to a temporary SQLite database when
`DATABASE_URL` is unset. CI runs the same suite against a real Postgres, plus
`ruff`, `ruff format --check`, and `mypy`.

| Layer | File | What it uses |
|---|---|---|
| Unit | `test_schemas.py` | Nothing — pure validation |
| Unit | `test_settings.py` | Temp YAML files |
| Unit | `test_extraction.py` | Patched Anthropic client |
| API | `test_api.py` | In-process ASGI via `TestClient` |
| **Socket** | `test_server.py` | **Real uvicorn on an ephemeral port, real HTTP** |
| **Live** | `test_live.py` | **The real Anthropic API — costs money** |

### Live tests

`test_live.py` sends a synthetic menu image to the real API and asserts the
dishes and prices come back exactly. It is the only thing that proves our tool
schema and image encoding are accepted by the actual service rather than by a
mock shaped the way we assume it behaves.

**It is deselected by default** (`addopts = -m "not live"` in `pyproject.toml`)
and makes **one** request per run. To run it you need a real key:

```bash
pytest -m live
```

In CI it runs only via [`live.yml`](.github/workflows/live.yml), triggered by
hand (`gh workflow run live.yml`) — never on push. A weekly schedule is present
but commented out. See
[DECISIONS.md D-005](DECISIONS.md#d-005--live-api-tests-are-opt-in-and-off-the-push-path).

The fixture image is generated, not photographed:

```bash
python tests/fixtures/generate_menu_image.py
```

---

## Docker

```bash
docker build -t menuforge .
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY -e DATABASE_URL menuforge
```

Runs as a non-root user; the API key comes from the environment and is never
baked into the image.

---

## Where to read next

| Question | Document |
|---|---|
| What does it do, and what is deliberately excluded? | [PRD.md](PRD.md) |
| Why is it built this way? | [DECISIONS.md](DECISIONS.md) |
| How are the modules split, and how is each tested alone? | [ARCHITECTURE.md](ARCHITECTURE.md) |
| What is validated, what is not, and what must be added before exposure? | [SECURITY.md](SECURITY.md) |
| What are the endpoints? | [docs/API.md](docs/API.md) |
| What was actually built, and what was left out on purpose? | [docs/build-record.html](docs/build-record.html) |

**The two worth reading before changing anything:** DECISIONS.md explains why
forced tool use rather than prompted JSON parsing, and why Postgres alone with no
queue — including what would trigger moving off each. ARCHITECTURE.md gives the
module boundaries, notably that persistence deliberately does not import the
extraction schemas.

---

## Known limitations

- **A `200` means the right shape, not the right data.** A hallucinated item with
  a plausible price passes every check here.
- **Every upload appends** — re-uploading a menu duplicates its rows.
- **The image is not stored**, so a failed extraction cannot be replayed or
  reviewed.
- **Retries reuse the same model and prompt**, so a systematic failure will not
  self-correct.
- **Client latency equals model latency**, since the call is on the request thread.
