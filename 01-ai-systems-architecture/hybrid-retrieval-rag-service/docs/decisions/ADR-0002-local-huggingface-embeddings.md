# ADR-0002 — Embeddings: local HuggingFace `BAAI/bge-small-en-v1.5`

- Status: **Superseded by [ADR-0006](ADR-0006-hosted-cohere-embeddings.md)**
- Date: 2026-06-27 (documenting existing code)

> ⚠️ Superseded. The "open RAM question" below turned out to be a real OOM risk on
> Render's 512 MB free tier, so embeddings were moved to the hosted Cohere Embed
> API. This ADR is kept as the record of why local embeddings were tried.
> See [ADR-0006](ADR-0006-hosted-cohere-embeddings.md).

## Context

Both ingestion and query need text embeddings. Options: a hosted embedding API
(per-token cost, network hop per call) or a local model (one-time load, no
network, no per-call cost).

## Decision

Use a **local** `sentence-transformers` model, **`BAAI/bge-small-en-v1.5`**,
producing **384-dimensional** unit-normalised vectors
(`config/settings.py: embedding_model`, `embedding_dimensions=384`). Implemented
in `src/rag/embedder.py`. `model.encode()` is synchronous and CPU/GPU-bound, so
it runs in a worker thread via `asyncio.to_thread()` to keep the async path free.

384-dim vectors give a smaller Pinecone index and faster similarity search than
larger embedding models.

## Consequences

- ✅ No per-token cost, no network round-trip per embed.
- ✅ Smaller index, faster ANN search (384-dim).
- ➖ **Open question:** `sentence-transformers` pulls in PyTorch (~400 MB RAM at
  import). This re-introduces exactly the memory cost that
  [ADR-0004](ADR-0004-cohere-rerank-api.md) avoided by *not* using a local
  reranker. On Render's 512 MB free tier this is a likely OOM source. Tracked in
  [../AUDIT.md](../AUDIT.md); not yet resolved.

## Supersedes

The earlier iteration used OpenAI `text-embedding-3-small` (1536-dim), still
referenced in historical docs. Replaced by this ADR.
