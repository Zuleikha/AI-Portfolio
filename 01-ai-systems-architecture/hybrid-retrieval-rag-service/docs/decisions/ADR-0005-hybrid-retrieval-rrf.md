# ADR-0005 — Retrieval: hybrid dense + BM25 + RRF

- Status: Accepted
- Date: 2026-06-27 (documenting existing code)

## Context

Dense (embedding) retrieval finds semantic matches but can miss exact tokens —
names, model numbers, rare technical terms. BM25 keyword retrieval nails exact
terms but is blind to paraphrase. Each covers the other's failure mode.

## Decision

Run **both legs** and fuse with **Reciprocal Rank Fusion (RRF)**. Implemented in
`src/rag/retriever.py` (`HybridRetriever.retrieve`).

- Dense leg: Pinecone ANN over hosted Cohere `embed-english-v3.0` embeddings.
- Sparse leg: BM25 via `rank-bm25`.
- Fusion: `score = Σ 1/(k + rank_i)` with **k=60**; deduplicated by document id.
- Default `retrieval_top_k = 10` candidates passed on to the reranker.

RRF uses only rank positions, so the different score scales of cosine similarity
and BM25 don't need normalising or weight tuning — it's parameter-free.

## Consequences

- ✅ Recovers exact-term matches dense search misses.
- ✅ No weights to tune; robust across document domains.
- ➖ BM25 is rebuilt per query (no cache) — slow for very large corpora (10k+ chunks).

The RRF formula (k=60, additivity, deduplication) is pinned by
`tests/test_retriever.py`.
