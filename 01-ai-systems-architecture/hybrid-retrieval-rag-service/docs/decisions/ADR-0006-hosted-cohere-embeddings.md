# ADR-0006 — Embeddings: hosted Cohere `embed-english-v3.0`

- Status: Accepted
- Date: 2026-06-27
- Supersedes: [ADR-0002](ADR-0002-local-huggingface-embeddings.md)

## Context

[ADR-0002](ADR-0002-local-huggingface-embeddings.md) used a local
`sentence-transformers` model for embeddings. That pulls in PyTorch (~400 MB RAM)
at startup, which exceeds Render's 512 MB free-tier limit and made the live
deployment unstable (OOM) — re-introducing the exact RAM cost that
[ADR-0004](ADR-0004-cohere-rerank-api.md) deliberately avoided for the reranker.

## Decision

Move embeddings to the **hosted Cohere Embed API**, model
**`embed-english-v3.0`** (**1024-dim**), called directly via `httpx.AsyncClient`
(no Cohere SDK — same rationale as ADR-0004: the SDK pulls in
`tokenizers`/`huggingface_hub`). Implemented in `src/rag/embedder.py`
(`CohereEmbedder`). Endpoint: `POST https://api.cohere.com/v2/embed`.

- Cohere v3 models require an `input_type`: documents are embedded with
  `search_document`, queries with `search_query` — matching types on each side
  improves retrieval quality.
- Requests are chunked to Cohere's 96-texts-per-call limit.
- `COHERE_API_KEY` is now **required** (it already powered reranking; it now also
  powers embeddings). The app fails fast at startup if it is missing.

## Migration impact

- Embedding dimension changed **384 → 1024**, so the existing Pinecone index is
  incompatible. `settings.pinecone_index_name` was changed to
  `rag-assistant-cohere` so a fresh 1024-dim index is created automatically; the
  old `rag-assistant` index is now unused and can be deleted. **Documents must be
  re-ingested.**
- `sentence-transformers` was removed from `requirements.txt`. `transformers` is
  retained — but only for the chunker's local fast tokenizer (token counting),
  which loads no PyTorch. A new `settings.chunk_tokenizer_model` decouples that
  tokenizer from the embedding model.

## Consequences

- ✅ No local PyTorch — the process fits Render's 512 MB free tier again.
- ✅ Reuses the existing Cohere provider/key and the established httpx pattern.
- ✅ Avoids re-introducing OpenAI (deliberately removed in the earlier migration).
- ➖ Embeddings are now a **paid, networked** dependency with no offline fallback;
  if the embed API is down, retrieval cannot run (failure surfaces, not silent).
- ➖ Per-token embedding cost (was $0 when local) — accepted for this task.

## Tests

`tests/test_e2e.py` stubs the Cohere embed HTTP call (no real key, no network);
`tests/test_pipeline.py` mocks `CohereEmbedder`. Full suite: 133 tests, all green,
no API keys required.
