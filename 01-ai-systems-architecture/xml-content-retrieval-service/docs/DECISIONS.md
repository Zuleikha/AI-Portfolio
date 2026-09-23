# DECISIONS — 07-dita-rag-pipeline

Technical decisions and their rationale. Add new entries at the bottom.

## 1. DITA XML over plain text input
Structured XML with well-defined `<topic>`, `<body>`, `<section>` elements enables
deterministic chunking — no heuristic text splitting needed.

## 2. Section-level chunking
Each `<section>` becomes exactly one chunk. Chunks stay semantically coherent and
carry natural metadata (topic title, section title) instead of arbitrary token windows.

## 3. ChromaDB as the vector store
Local persistence, zero external infrastructure, cosine similarity (`hnsw:space: cosine`).
Right size for a single-node documentation assistant.

## 4. OpenAI `text-embedding-3-small` + `gpt-4o-mini`
Cost-efficient embedding and generation. Trade-off: no offline fallback — the whole
pipeline depends on the OpenAI API. Switching embedding models requires a full re-index
(fixed dimensionality per collection).

## 5. Temperature 0.2 for generation
Documentation answers should be consistent and grounded, not creative.

## 6. Single Docker image for API and UI
Both services build from one `Dockerfile`; `docker-compose.yml` overrides the command
for the UI. Simpler builds at the cost of a slightly larger UI image.

## 7. Startup auto-index only when the store is empty (2026-06-12)
Previously every container restart re-embedded the full corpus — paying OpenAI for
unchanged documents and briefly wiping the collection. Startup now skips indexing when
the collection already has documents; `POST /index` remains the explicit full-rebuild path.

## 8. Package-absolute imports (`from app.parser import …`) (2026-06-12)
Bare imports (`from parser import …`) broke `uvicorn app.api:app` in Docker
(`ModuleNotFoundError`) and shadowed a historical stdlib module name. All intra-package
imports now go through the `app` package; `app/__init__.py` makes it explicit.

## 9. Lazy OpenAI client (2026-06-12)
The client is created on first use, not at import. The API can start, serve `/health`,
and run its test suite without `OPENAI_API_KEY`; a missing key fails loudly with a clear
message only when an embedding or generation call is attempted.
