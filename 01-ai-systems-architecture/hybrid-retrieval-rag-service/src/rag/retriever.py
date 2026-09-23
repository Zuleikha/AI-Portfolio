"""
Hybrid retrieval: dense (ChromaDB) + sparse (BM25) fused with Reciprocal Rank Fusion.

Why hybrid over dense-only?
- Dense retrieval matches semantics well but can miss exact terms — product codes,
  proper nouns, abbreviations, or any token that wasn't well-represented in
  the embedding model's training data.
- BM25 matches exact terms reliably but knows nothing about paraphrase.
- RRF is parameter-free and empirically robust across domains.
  Score formula: sum(1 / (k + rank_i)) where k=60 is the standard default.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi

from src.rag.embedder import CohereEmbedder
from src.store.pinecone_store import PineconeVectorStore


@dataclass
class RetrievedDocument:
    content: str
    metadata: dict
    score: float
    retrieval_method: str  # "dense" | "sparse" | "hybrid"


class HybridRetriever:
    _RRF_K = 60  # standard constant; higher = less aggressive rank promotion

    def __init__(self, store: PineconeVectorStore, embedder: CohereEmbedder) -> None:
        self._store = store
        self._embedder = embedder

    async def retrieve(self, query: str, n_results: int = 10) -> list[RetrievedDocument]:
        query_embedding = await self._embedder.embed_query(query)

        # Both legs can run concurrently — sparse doesn't need the embedding
        dense_task = asyncio.create_task(self._dense(query_embedding, n_results * 2))
        sparse_task = asyncio.create_task(self._sparse(query, n_results * 2))
        dense_results, sparse_results = await asyncio.gather(dense_task, sparse_task)

        return self._rrf(dense_results, sparse_results, n_results)

    # ── Private ───────────────────────────────────────────────────────────────

    async def _dense(self, embedding: list[float], n: int) -> list[RetrievedDocument]:
        results = self._store.query(embedding, n_results=n)
        return [
            RetrievedDocument(
                content=r["content"],
                metadata=r["metadata"],
                score=r["score"],
                retrieval_method="dense",
            )
            for r in results
        ]

    async def _sparse(self, query: str, n: int) -> list[RetrievedDocument]:
        all_docs = self._store.get_all_documents()
        if not all_docs:
            return []

        tokenized = [doc["content"].lower().split() for doc in all_docs]
        bm25 = BM25Okapi(tokenized)
        scores: np.ndarray = bm25.get_scores(query.lower().split())

        top_indices = np.argsort(scores)[::-1][:n]
        return [
            RetrievedDocument(
                content=all_docs[i]["content"],
                metadata=all_docs[i]["metadata"],
                score=float(scores[i]),
                retrieval_method="sparse",
            )
            for i in top_indices
            if scores[i] > 0
        ]

    def _rrf(
        self,
        dense: list[RetrievedDocument],
        sparse: list[RetrievedDocument],
        n: int,
    ) -> list[RetrievedDocument]:
        scores: dict[str, float] = {}
        docs: dict[str, RetrievedDocument] = {}

        for rank, doc in enumerate(dense):
            key = doc.content[:120]
            scores[key] = scores.get(key, 0.0) + 1.0 / (self._RRF_K + rank + 1)
            docs[key] = RetrievedDocument(
                content=doc.content,
                metadata=doc.metadata,
                score=scores[key],
                retrieval_method="hybrid",
            )

        for rank, doc in enumerate(sparse):
            key = doc.content[:120]
            scores[key] = scores.get(key, 0.0) + 1.0 / (self._RRF_K + rank + 1)
            if key not in docs:
                docs[key] = RetrievedDocument(
                    content=doc.content,
                    metadata=doc.metadata,
                    score=scores[key],
                    retrieval_method="hybrid",
                )
            else:
                docs[key].score = scores[key]

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [docs[key] for key, _ in ranked[:n]]
