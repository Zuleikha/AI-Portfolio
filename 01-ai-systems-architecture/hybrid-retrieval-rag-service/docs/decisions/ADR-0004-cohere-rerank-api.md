# ADR-0004 — Reranker: Cohere Rerank API (no local CrossEncoder)

- Status: Accepted
- Date: 2026-06-27 (documenting existing code)

## Context

Two-stage retrieval needs a reranker: bi-encoder retrieval is cheap but can't
model query–document interaction; a cross-encoder scores the pair jointly and is
far more accurate, but too slow to run over a whole corpus. The standard pattern
is retrieve cheaply, rerank a small candidate set.

A **local** cross-encoder (`sentence-transformers` CrossEncoder) requires PyTorch
(~300–400 MB RAM at import) plus model weights — which blows past Render's 512 MB
free tier before the first request.

## Decision

Use the **Cohere Rerank API**, model **`rerank-v3.5`**, called directly via
`httpx.AsyncClient` (no Cohere SDK — the SDK pulls in `tokenizers`/HuggingFace
Hub, re-introducing the same dependency weight). Implemented in
`src/rag/reranker.py`. Endpoint: `POST https://api.cohere.com/v2/rerank`.

**There is no local CrossEncoder in this system** — this was a deliberate
avoidance, not an omission.

## Fallback (graceful degradation)

- If `COHERE_API_KEY` is **absent**, rerank falls back to embedding-score ordering.
- If the API call **fails** (any exception), same fallback, logged as a warning.
- Either way the service stays up; quality degrades but `/query` still answers.

Both fallback paths are covered by `tests/test_reranker.py`.

## Consequences

- ✅ Cross-encoder quality with zero local PyTorch / zero RAM overhead.
- ✅ Free tier covers ~1,000 requests/month.
- ➖ External dependency for best-quality reranking (mitigated by fallback).
