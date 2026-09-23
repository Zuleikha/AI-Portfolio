"""
RAG pipeline — orchestrates every stage from ingestion to answer generation.

Stage order:
  ingest:  chunk → embed (batch) → upsert into Pinecone
  query:   embed query → hybrid retrieve → Cohere rerank → generate

All query paths are async. The reranker makes a synchronous HTTP call to the
Cohere API; it falls back to embedding-score ordering if the key is absent or
the call fails.
"""

from __future__ import annotations

import logging
import time

from config.settings import settings
from src.rag.chunker import SentenceAwareChunker, TextChunk
from src.rag.embedder import CohereEmbedder
from src.rag.generator import GenerationResult, RAGGenerator
from src.rag.reranker import CohereReranker
from src.rag.retriever import HybridRetriever
from src.store.pinecone_store import PineconeVectorStore

logger = logging.getLogger(__name__)


class RAGResponse:
    __slots__ = (
        "answer",
        "sources",
        "tokens_used",
        "latency_ms",
        "retrieval_latency_ms",
        "rerank_latency_ms",
        "chunks_retrieved",
        "chunks_after_rerank",
    )

    def __init__(
        self,
        answer: str,
        sources: list[dict],
        tokens_used: int,
        latency_ms: float,
        retrieval_latency_ms: float,
        rerank_latency_ms: float,
        chunks_retrieved: int,
        chunks_after_rerank: int,
    ) -> None:
        self.answer = answer
        self.sources = sources
        self.tokens_used = tokens_used
        self.latency_ms = latency_ms
        self.retrieval_latency_ms = retrieval_latency_ms
        self.rerank_latency_ms = rerank_latency_ms
        self.chunks_retrieved = chunks_retrieved
        self.chunks_after_rerank = chunks_after_rerank

    def __iter__(self):
        for attr in self.__slots__:
            yield attr, getattr(self, attr)


_NO_DOCS_ANSWER = (
    "No documents have been indexed yet. "
    "Upload a PDF or text file using the /ingest endpoint first."
)


class RAGPipeline:
    def __init__(self) -> None:
        self.embedder = CohereEmbedder()
        self.store = PineconeVectorStore()
        self.retriever = HybridRetriever(self.store, self.embedder)
        self.reranker = CohereReranker()
        self.generator = RAGGenerator()
        self.chunker = SentenceAwareChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        self._history: dict[str, list[dict]] = {}

    # ── Ingestion ─────────────────────────────────────────────────────────────

    async def ingest_chunks(self, chunks: list[TextChunk]) -> int:
        if not chunks:
            return 0

        texts = [c.content for c in chunks]
        embeddings = await self.embedder.embed_batch(texts)

        ids = [
            f"{c.metadata.get('source', 'doc')}::{c.metadata.get('chunk_index', i)}"
            for i, c in enumerate(chunks)
        ]

        self.store.add_documents(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=[c.metadata for c in chunks],
        )
        logger.info("Ingested %d chunks into Pinecone", len(chunks))
        return len(chunks)

    # ── Query ─────────────────────────────────────────────────────────────────

    async def query(
        self,
        question: str,
        conversation_id: str = "default",
        retrieval_k: int | None = None,
        rerank_k: int | None = None,
    ) -> RAGResponse:
        if self.store.count == 0:
            return RAGResponse(
                answer=_NO_DOCS_ANSWER,
                sources=[],
                tokens_used=0,
                latency_ms=0.0,
                retrieval_latency_ms=0.0,
                rerank_latency_ms=0.0,
                chunks_retrieved=0,
                chunks_after_rerank=0,
            )

        r_k = retrieval_k or settings.retrieval_top_k
        rr_k = rerank_k or settings.rerank_top_k

        t0 = time.perf_counter()

        t_r = time.perf_counter()
        candidates = await self.retriever.retrieve(question, n_results=r_k)
        retrieve_ms = (time.perf_counter() - t_r) * 1000

        t_rr = time.perf_counter()
        reranked = await self.reranker.rerank(question, candidates, top_k=rr_k)
        rerank_ms = (time.perf_counter() - t_rr) * 1000

        history = self._history.get(conversation_id, [])
        gen: GenerationResult = await self.generator.generate(question, reranked, history)

        self._update_history(conversation_id, question, gen.answer)

        total_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "query finished | retrieved=%d reranked=%d tokens=%d total_ms=%.0f",
            len(candidates),
            len(reranked),
            gen.tokens_used,
            total_ms,
        )

        return RAGResponse(
            answer=gen.answer,
            sources=gen.sources,
            tokens_used=gen.tokens_used,
            latency_ms=total_ms,
            retrieval_latency_ms=retrieve_ms,
            rerank_latency_ms=rerank_ms,
            chunks_retrieved=len(candidates),
            chunks_after_rerank=len(reranked),
        )

    # ── Conversation management ───────────────────────────────────────────────

    def get_conversation_history(self, conversation_id: str) -> list[dict]:
        return self._history.get(conversation_id, [])

    def clear_conversation(self, conversation_id: str) -> None:
        self._history.pop(conversation_id, None)

    def _update_history(self, conversation_id: str, question: str, answer: str) -> None:
        history = self._history.setdefault(conversation_id, [])
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        # Keep last 3 turns (6 messages) to bound prompt size
        if len(history) > 6:
            self._history[conversation_id] = history[-6:]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @property
    def document_count(self) -> int:
        return self.store.count
