"""
Cohere Rerank API reranker.

Why rerank after retrieval?
Bi-encoder (embedding) models encode query and document independently, which
means they can't model the interaction between them. A reranker sees both
jointly and produces much more accurate relevance scores — but it's too slow
to run across an entire corpus (O(n) forward passes). The standard solution is
two-stage: retrieve cheaply with bi-encoders, rerank expensively on the small
candidate set.

Why Cohere Rerank API instead of a local CrossEncoder?
sentence-transformers pulls in PyTorch as a hard dependency. Even the CPU-only
build allocates 300–400 MB of RAM at import time; add the cross-encoder model
weights (~84 MB) and the rest of the application and you exceed Render free
tier's 512 MB limit before the first request is served.

Cohere Rerank is a plain HTTP API call — zero local model, zero PyTorch,
zero RAM overhead beyond the request itself. It delivers equivalent
cross-encoder quality (both approaches jointly encode query + document) and the
free tier covers 1,000 requests / month, which is sufficient for a portfolio
workload.

Why httpx instead of the cohere SDK?
The cohere SDK v5 depends on `tokenizers` (a HuggingFace package), which
downloads tokenizer files from the HuggingFace Hub at import time. That brings
back the same OOM problem we were trying to avoid. Using httpx directly keeps
the full dependency tree RAM-free: one POST request, no transitive surprises.

API: POST https://api.cohere.com/v2/rerank (model: rerank-v3.5)
- Requires COHERE_API_KEY env var; falls back to embedding-score ordering if
  absent or on API failure
- Free tier: 1,000 requests / month
"""

from __future__ import annotations

import logging

import httpx

from config.settings import settings
from src.rag.retriever import RetrievedDocument

logger = logging.getLogger(__name__)

_RERANK_URL = "https://api.cohere.com/v2/rerank"
_RERANK_MODEL = "rerank-v3.5"

if settings.cohere_api_key:
    logger.info("Cohere reranker configured (model: %s)", _RERANK_MODEL)
else:
    logger.warning("COHERE_API_KEY not set; reranker will fall back to embedding scores")


class CohereReranker:
    def __init__(self) -> None:
        self._api_key = settings.cohere_api_key

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedDocument],
        top_k: int = 3,
    ) -> list[RetrievedDocument]:
        if not candidates:
            return []

        if not self._api_key:
            return sorted(candidates, key=lambda d: d.score, reverse=True)[:top_k]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    _RERANK_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": _RERANK_MODEL,
                        "query": query,
                        "documents": [doc.content for doc in candidates],
                        "top_n": top_k,
                    },
                )
                response.raise_for_status()
                results = response.json()["results"]
            return [
                RetrievedDocument(
                    content=candidates[r["index"]].content,
                    metadata=candidates[r["index"]].metadata,
                    score=r["relevance_score"],
                    retrieval_method=candidates[r["index"]].retrieval_method,
                )
                for r in results
            ]
        except Exception:
            logger.warning("Cohere rerank call failed; falling back to embedding scores")
            return sorted(candidates, key=lambda d: d.score, reverse=True)[:top_k]
