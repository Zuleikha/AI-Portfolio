"""
Hosted embeddings via the Cohere Embed API (embed-english-v3.0, 1024-dim).

Why a hosted API instead of a local model:
- The previous local sentence-transformers model loaded PyTorch (~400 MB RAM) at
  import time, which exceeds Render's 512 MB free-tier limit and made the live
  deployment unstable (OOM). A hosted call has zero local model / zero PyTorch.
- Reuses the existing COHERE_API_KEY (already used by the reranker) and the same
  httpx-not-SDK pattern: the Cohere SDK pulls in `tokenizers`/`huggingface_hub`,
  which would re-introduce the dependency weight we are trying to avoid.

Cohere v3 embedding models require an `input_type`: documents are embedded with
"search_document" and queries with "search_query". Using the matching type on
each side improves retrieval quality, so embed_batch (ingestion) and embed_query
pass different types.

embed-query/embed-batch are async (httpx.AsyncClient) so they never block the
event loop. Cohere accepts at most 96 texts per call, so batches are chunked.

API: POST https://api.cohere.com/v2/embed (model: embed-english-v3.0)
"""

from __future__ import annotations

import httpx

from config.settings import settings

_EMBED_URL = "https://api.cohere.com/v2/embed"
_MAX_TEXTS_PER_CALL = 96  # Cohere v2 embed limit


class CohereEmbedder:
    def __init__(self) -> None:
        self._api_key = settings.cohere_api_key
        self._model = settings.embedding_model

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string (input_type='search_query')."""
        vectors = await self._embed([text], input_type="search_query")
        return vectors[0]

    async def embed_batch(
        self, texts: list[str], batch_size: int = _MAX_TEXTS_PER_CALL
    ) -> list[list[float]]:
        """Embed a list of documents (input_type='search_document').

        Calls are chunked to Cohere's per-request limit. Returns one vector per
        input text, in order.
        """
        if not texts:
            return []
        size = min(batch_size, _MAX_TEXTS_PER_CALL)
        vectors: list[list[float]] = []
        for i in range(0, len(texts), size):
            vectors.extend(await self._embed(texts[i : i + size], input_type="search_document"))
        return vectors

    # ── Private ───────────────────────────────────────────────────────────────

    async def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        """Call the Cohere Embed API and return float vectors.

        Raises on transport or HTTP errors — embedding has no meaningful
        fallback (without it there is nothing to retrieve), so failures must
        surface rather than be silently swallowed.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                _EMBED_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "texts": texts,
                    "input_type": input_type,
                    "embedding_types": ["float"],
                },
            )
            response.raise_for_status()
            return response.json()["embeddings"]["float"]
