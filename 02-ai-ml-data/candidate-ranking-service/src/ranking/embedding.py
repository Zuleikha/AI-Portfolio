"""Sentence-embedding ranking backend.

Opt-in. It captures meaning that TF-IDF cannot — "PostgreSQL" against
"relational databases" — at the cost of a multi-hundred-megabyte dependency
tree and a model download on first use. Install with::

    pip install -e ".[embeddings]"

and set ``RANKING_METHOD=embedding``.

``sentence_transformers`` is imported inside the constructor, not at module
scope, so the module remains importable — and the rest of the service
testable — when the extra is not installed.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import ClassVar, Protocol, runtime_checkable

import numpy as np

from src.ranking.base import Ranker, RankingWeights
from src.ranking.redaction import strip_contact_details

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@runtime_checkable
class Encoder(Protocol):
    """The slice of the sentence-transformers API this backend depends on.

    Depending on the protocol rather than the concrete class lets tests inject
    a deterministic stub encoder, so the ranking logic is verified without a
    model download or a network call.
    """

    def encode(self, sentences: Sequence[str], **kwargs: object) -> np.ndarray:
        """Return one embedding row per input sentence."""
        ...


class EmbeddingRanker(Ranker):
    """Rank on cosine similarity between sentence embeddings."""

    method: ClassVar[str] = "embedding"

    def __init__(
        self,
        weights: RankingWeights | None = None,
        model_name: str = DEFAULT_MODEL,
        encoder: Encoder | None = None,
    ) -> None:
        """Build the backend.

        Args:
            weights: Component weights.
            model_name: Sentence-transformers checkpoint to load.
            encoder: A pre-built encoder. When given, no model is loaded —
                the injection point used by tests.

        Raises:
            ImportError: If no encoder is supplied and the optional
                ``embeddings`` extra is not installed.
        """
        super().__init__(weights)
        self.model_name = model_name

        if encoder is not None:
            self._encoder = encoder
            return

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on install extras
            raise ImportError(
                "RANKING_METHOD='embedding' requires the optional dependency. "
                'Install it with: pip install -e ".[embeddings]"'
            ) from exc

        logger.info("Loading embedding model %s", model_name)
        self._encoder = SentenceTransformer(model_name)

    def describe(self) -> dict[str, str]:
        return {"method": self.method, "model": self.model_name}

    def text_similarities(self, job_text: str, candidate_texts: Sequence[str]) -> list[float]:
        """Cosine similarity between the job embedding and each resume embedding.

        Zero-norm rows (an empty document, or a degenerate encoder output)
        score 0.0 rather than producing a divide-by-zero NaN that would
        propagate silently into the ranking.
        """
        if not candidate_texts:
            return []

        documents = [
            strip_contact_details(job_text),
            *(strip_contact_details(text) for text in candidate_texts),
        ]
        embeddings = np.asarray(self._encoder.encode(documents), dtype=np.float64)
        if embeddings.ndim != 2 or embeddings.shape[0] != len(documents):
            raise ValueError(
                f"Encoder returned shape {embeddings.shape} for {len(documents)} documents"
            )

        job_vector, candidate_vectors = embeddings[0], embeddings[1:]
        job_norm = float(np.linalg.norm(job_vector))
        candidate_norms = np.linalg.norm(candidate_vectors, axis=1)

        if job_norm == 0.0:
            return [0.0] * len(candidate_texts)

        dot_products = candidate_vectors @ job_vector
        with np.errstate(invalid="ignore", divide="ignore"):
            similarities = dot_products / (candidate_norms * job_norm)

        return [0.0 if not np.isfinite(value) else float(value) for value in similarities]
