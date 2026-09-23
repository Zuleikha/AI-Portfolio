"""Question -> embedding -> vector search -> relevant documents -> sources.

This is the layer the agent will call in Stage 5. It is deliberately free of
any LLM dependency so that retrieval quality can be measured on its own: if an
answer is wrong, the first question is always *"did retrieval find the right
passage?"*, and that must be answerable without a model in the loop.

**On the minimum-score threshold.** Cosine similarity from a sentence
embedder is a *ranking* signal, not a calibrated probability -- 0.6 does not
mean "60% relevant", and the useful range differs per model. Without a floor,
the store will happily return its five least-bad chunks for *"what is the
capital of France?"*, and a downstream LLM handed five confident-looking
banking passages tends to write a confident answer from them. The floor is what
turns "nothing here is relevant" into an empty result the agent can honestly
refuse on. The default was chosen by measuring this corpus with this model --
see ``python -m app.rag calibrate`` -- not taken from a blog post, and it must
be re-measured if either the corpus or the model changes.
"""

from __future__ import annotations

import time

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.observability import (
    RAG_RETRIEVAL_DURATION_MS,
    RAG_RETRIEVALS_TOTAL,
    elapsed_ms,
    fingerprint,
    get_metrics,
)
from app.core.tracing import traced
from app.rag.embeddings import Embedder
from app.rag.models import RetrievalResult, ScoredChunk
from app.rag.vectorstore import Filters, VectorStore

logger = get_logger(__name__)


class Retriever:
    """Finds the knowledge-base passages relevant to a question.

    Composes an :class:`~app.rag.embeddings.Embedder` and a
    :class:`~app.rag.vectorstore.VectorStore`, both injected as protocols. The
    tests exercise it with a hashing embedder and an in-memory store; production
    passes a sentence-transformers embedder and a persisted store. Neither this
    class nor its callers change.
    """

    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        settings: Settings | None = None,
    ) -> None:
        """Wire a retriever from its two collaborators.

        Args:
            embedder: Must be the same model the store was indexed with.
            store: The searchable index.
            settings: Application settings. Defaults to the cached singleton.
        """
        resolved = settings or get_settings()
        self._embedder = embedder
        self._store = store
        self._default_k = resolved.retrieval_top_k
        self._default_min_score = resolved.retrieval_min_score

    @property
    def embedder(self) -> Embedder:
        """The embedder used for queries."""
        return self._embedder

    @property
    def store(self) -> VectorStore:
        """The index being searched."""
        return self._store

    @traced
    def retrieve(
        self,
        query: str,
        k: int | None = None,
        filters: Filters | None = None,
        min_score: float | None = None,
    ) -> RetrievalResult:
        """Retrieve the passages most relevant to ``query``.

        Args:
            query: The user's question, in natural language.
            k: Maximum passages to return. Defaults to ``retrieval_top_k``.
            filters: Optional metadata restriction, e.g. ``{"domain": "atm"}``.
            min_score: Cosine floor a passage must clear. Defaults to
                ``retrieval_min_score``. Pass ``-1.0`` to disable the floor,
                which is useful when evaluating ranking in isolation.

        Returns:
            The matches and the context needed to interpret them -- including
            an empty ``chunks`` tuple when nothing cleared the floor, which is a
            valid outcome rather than an error.

        Raises:
            ValueError: If the query is blank.
            EmbeddingError: If the query cannot be embedded.
        """
        if not query.strip():
            raise ValueError("Cannot retrieve for an empty query.")

        top_k = k if k is not None else self._default_k
        floor = min_score if min_score is not None else self._default_min_score

        started = time.perf_counter()
        query_vector = self._embedder.embed_query(query)
        matches = self._store.search(query_vector, k=top_k, filters=filters)
        kept: tuple[ScoredChunk, ...] = tuple(
            match for match in matches if match.score >= floor
        )

        result = RetrievalResult(
            query=query,
            chunks=kept,
            candidates_considered=self._store.count(filters),
            min_score=floor,
        )
        latency = elapsed_ms(started)
        metrics = get_metrics()
        metrics.increment(RAG_RETRIEVALS_TOTAL)
        metrics.observe(RAG_RETRIEVAL_DURATION_MS, latency)

        logger.info(
            "rag.retrieved",
            # The query is logged as a fingerprint and a length, never as text
            # (guide §20.32): a support question can hold customer data. The
            # fingerprint still lets two lines be matched as the same query.
            query_hash=fingerprint(query),
            query_length=len(query),
            latency_ms=latency,
            returned=len(kept),
            scored=len(matches),
            candidates=result.candidates_considered,
            top_score=result.top_score,
            documents=[match.chunk.document_id for match in kept],
        )
        return result

    @traced
    def retrieve_many(
        self,
        queries: list[str],
        k: int | None = None,
        filters: Filters | None = None,
        min_score: float | None = None,
    ) -> tuple[RetrievalResult, ...]:
        """Retrieve for several questions. Used by the evaluation harness."""
        return tuple(
            self.retrieve(query, k=k, filters=filters, min_score=min_score)
            for query in queries
        )
