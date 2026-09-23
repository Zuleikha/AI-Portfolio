"""
Pinecone-backed vector store — drop-in replacement for ChromaVectorStore.

Interface is identical so pipeline.py and retriever.py need only an import swap.

Key differences from Chroma:
- Index must exist in Pinecone before use; created here on first run if absent.
- Vector text content is stored as metadata field "_content" (Pinecone stores
  vectors and metadata but not raw text natively).
- get_all_documents() paginates via index.list() (serverless) + batch fetch.
- Upsert is batched at 100 vectors to stay within Pinecone's recommended limit.
"""

from __future__ import annotations

import logging
import time

from pinecone import Pinecone, ServerlessSpec

from config.settings import settings

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100
_CONTENT_KEY = "_content"


class PineconeVectorStore:
    def __init__(self) -> None:
        pc = Pinecone(api_key=settings.pinecone_api_key)

        existing = {idx.name for idx in pc.list_indexes()}
        if settings.pinecone_index_name not in existing:
            logger.info("Creating Pinecone index '%s'", settings.pinecone_index_name)
            pc.create_index(
                name=settings.pinecone_index_name,
                dimension=settings.embedding_dimensions,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            # Wait for index to become ready (usually <60 s for serverless)
            for _ in range(60):
                status = pc.describe_index(settings.pinecone_index_name).status
                if status.ready:
                    break
                time.sleep(2)
            else:
                raise RuntimeError("Pinecone index did not become ready in time")

        self._index = pc.Index(settings.pinecone_index_name)
        logger.info("Pinecone index '%s' ready", settings.pinecone_index_name)

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_documents(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        vectors = [
            {"id": id_, "values": emb, "metadata": {**meta, _CONTENT_KEY: doc}}
            for id_, emb, doc, meta in zip(ids, embeddings, documents, metadatas, strict=True)
        ]
        for i in range(0, len(vectors), _BATCH_SIZE):
            self._index.upsert(vectors=vectors[i : i + _BATCH_SIZE])

    # ── Read ──────────────────────────────────────────────────────────────────

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        where: dict | None = None,
    ) -> list[dict]:
        kwargs: dict = {
            "vector": query_embedding,
            "top_k": max(1, n_results),
            "include_metadata": True,
        }
        if where:
            kwargs["filter"] = where

        result = self._index.query(**kwargs)
        docs = []
        for match in result.matches:
            meta = dict(match.metadata)
            content = meta.pop(_CONTENT_KEY, "")
            docs.append({"content": content, "metadata": meta, "score": match.score})
        return docs

    def get_all_documents(self) -> list[dict]:
        """Return every stored document (used to build the BM25 index).

        Uses index.list() (serverless pagination) + batch fetch.
        For very large indexes this will be slow — same caveat as Chroma.
        """
        all_ids: list[str] = []
        for id_batch in self._index.list():
            all_ids.extend(id_batch)

        if not all_ids:
            return []

        docs: list[dict] = []
        for i in range(0, len(all_ids), _BATCH_SIZE):
            batch = all_ids[i : i + _BATCH_SIZE]
            result = self._index.fetch(ids=batch)
            for vector in result.vectors.values():
                meta = dict(vector.metadata)
                content = meta.pop(_CONTENT_KEY, "")
                docs.append({"content": content, "metadata": meta})
        return docs

    # ── Admin ─────────────────────────────────────────────────────────────────

    @property
    def count(self) -> int:
        return self._index.describe_index_stats().total_vector_count

    def reset(self) -> None:
        """Delete all vectors from the index (useful in tests)."""
        self._index.delete(delete_all=True)
