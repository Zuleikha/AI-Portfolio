# ADR-0003 — Vector store: Pinecone serverless

- Status: Accepted
- Date: 2026-06-27 (documenting existing code)

## Context

The system needs a vector store for dense retrieval that survives redeploys on a
host without persistent disk (Render free tier), and that doesn't load a large
index into the app process's memory.

## Decision

Use **Pinecone serverless** (`config/settings.py: pinecone_index_name`,
default `"rag-assistant"`). Implemented in `src/store/pinecone_store.py`
(`add_documents`, `query`, `get_all_documents`, `count`). The index is created
automatically on first run if absent, using a cosine metric to match the
embeddings from [ADR-0006](ADR-0006-hosted-cohere-embeddings.md). The index
dimension is `settings.embedding_dimensions` (1024 for `embed-english-v3.0`); the
old 384-dim index is incompatible, so the index name was changed to force a fresh
one.

## Consequences

- ✅ Managed hosting; the index persists across redeploys.
- ✅ Zero in-process RAM cost for the index (vs ChromaDB's in-process HNSW).
- ➖ One network round-trip per query (~50–100 ms).
- ➖ Requires `PINECONE_API_KEY`; app fails fast at startup if missing.

## Supersedes

v1 used ChromaDB (in-process, local disk). The legacy wrapper
`src/store/chroma_store.py` and `data/chroma/` are kept for reference only and
are not used in the current system.
