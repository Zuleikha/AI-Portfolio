# Hybrid Retrieval RAG Service

A retrieval-augmented question-answering service. Upload PDF, TXT or Markdown
documents; ask questions; get answers grounded in those documents with inline
citations back to the source chunk.

Retrieval is hybrid — dense vector search and BM25 sparse search run in
parallel, fuse via Reciprocal Rank Fusion, then pass through a cross-encoder
reranker before the LLM sees anything.

## Stack

| Layer | Choice |
|---|---|
| API | FastAPI (async lifespan, Pydantic v2 validation) |
| UI | Streamlit |
| Embeddings | Cohere `embed-english-v3.0`, 1024-dim, hosted |
| Vector store | Pinecone serverless |
| Sparse retrieval | BM25 (`rank-bm25`) |
| Reranking | Cohere `rerank-v3.5` |
| Generation | Anthropic `claude-sonnet-4-6` |
| Config | `pydantic-settings`, env-var bound, validated at import |
| Logging | `structlog` (JSON) |
| Tests | pytest + pytest-asyncio, 130 tests, all providers mocked |

No LangChain. Chunking, fusion and prompt assembly are ~200 lines of direct
code rather than a framework dependency — see [ADR-0005](docs/decisions/ADR-0005-hybrid-retrieval-rrf.md).

## Query path

```
question
   ├─► dense leg   — Cohere embed → Pinecone ANN (top 10)
   └─► sparse leg  — BM25 over the same corpus (top 10)
          └─► RRF fusion (k=60), dedup
                └─► Cohere rerank-v3.5 → top 3
                      └─► Claude, numbered context, citation-enforcing system prompt
                            └─► answer + sources + per-stage latency
```

Full detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); open
[docs/architecture.html](docs/architecture.html) in a browser for the diagram.

## Run it

```bash
cp .env.example .env      # fill in the three required keys
pip install -e ".[dev]"
uvicorn src.api.main:app --reload      # API  → http://localhost:8000
streamlit run src/app.py               # UI   → http://localhost:8501
```

Or with Docker:

```bash
docker compose up
```

Any document dropped into `data/raw/` is ingested automatically at startup.

### Required keys

| Variable | Used for |
|---|---|
| `ANTHROPIC_API_KEY` | Answer generation |
| `COHERE_API_KEY` | Embeddings **and** reranking |
| `PINECONE_API_KEY` | Vector index (created on first run if absent) |

All three are required — the process fails fast at import if any is missing,
rather than at first request.

## API

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness, model names, indexed document count |
| `POST` | `/query` | Question in, grounded answer + sources + timings out |
| `POST` | `/ingest` | Multipart upload of `.pdf` / `.txt` / `.md` |
| `GET` | `/documents` | Indexed sources and their chunk counts |
| `GET` | `/metrics` | Request count, error count, latency, token usage |
| `DELETE` | `/conversations/{id}` | Drop a conversation's history |

Interactive docs at `/docs` once running.

## Tests

```bash
pytest -q
```

130 tests. Every external provider (Anthropic, Cohere, Pinecone) is mocked, so
the suite runs offline with no API keys. `tests/test_e2e.py` drives the real
pipeline end to end with only the transport boundaries stubbed.

## Repository layout

```
config/settings.py     env-bound settings, validated at import
src/rag/               chunker, embedder, retriever, reranker, generator, pipeline
src/store/             Pinecone index lifecycle
src/ingestion/         PDF/TXT/MD loading, per-file error isolation
src/monitoring/        structlog config + in-memory request metrics
src/api/main.py        FastAPI routes
src/app.py             Streamlit UI
docs/decisions/        ADRs
```

## Known limits

The service has no authentication and no rate limiting; it is not safe to
expose publicly as-is. The BM25 leg rebuilds its index per query, which does
not hold beyond a few thousand chunks. Both are tracked in
[docs/ROADMAP.md](docs/ROADMAP.md) with the rest of the backlog.

## Licence

MIT — see [LICENSE](LICENSE).
