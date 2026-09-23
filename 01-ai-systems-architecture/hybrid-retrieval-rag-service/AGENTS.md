# AGENTS.md

Instructions for AI coding agents working in this repository.

## What this is

A retrieval-augmented QA service: FastAPI + Streamlit over Pinecone, with
hybrid dense/BM25 retrieval, Cohere reranking and Anthropic generation.

## Ground rules

- **Config never gets hardcoded.** Every tunable — model names, chunk sizes,
  `top_k` values, timeouts — lives in `config/settings.py` and is overridable by
  environment variable. If you need a new constant, add a field there.
- **No `print()` in `src/`.** Use `logging.getLogger(__name__)`. Structured
  output is configured once in `src/monitoring/metrics.py`.
- **Async stays async.** Query, embed and ingest are I/O-bound paths. Do not
  introduce blocking calls on them; wrap unavoidable sync SDK calls in
  `asyncio.to_thread()`.
- **No LangChain.** It was deliberately left out — the chunking and fusion it
  would provide are implemented directly and are cheaper to reason about. Do
  not add it back.
- **Type hints and docstrings on every public function.**

## Before you commit

```bash
ruff check .
ruff format --check .
mypy src config
pytest -q
```

All four must pass. The suite is fully mocked — a failure is a real failure,
not a missing API key.

## Files that need care

| File | Why |
|---|---|
| `config/settings.py` | Validated at import; a bad change breaks startup everywhere |
| `src/rag/pipeline.py` | Orchestrates every stage — a bug here affects every query |
| `src/store/pinecone_store.py` | All vector reads and writes funnel through it |
| `src/api/main.py` | The entire HTTP contract |

## Decisions

Architectural choices are recorded as ADRs in `docs/decisions/`. If you change
a provider, a retrieval strategy, or anything else with a trade-off worth
remembering, add a numbered ADR rather than burying the reasoning in a commit
message. Superseded ADRs stay in place and are marked as superseded.

## Testing conventions

- One test file per module, mirroring `src/`.
- External providers are mocked at the transport boundary, never bypassed by
  faking the module under test.
- `tests/conftest.py` seeds placeholder API keys so settings validation passes
  in CI.
