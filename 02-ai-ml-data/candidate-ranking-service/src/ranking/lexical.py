"""TF-IDF ranking backend — the default.

Chosen as the default because it is deterministic, needs no model download and
no network, and runs in milliseconds on CPU. It measures vocabulary overlap,
not meaning: a resume saying "PostgreSQL" scores nothing against a job asking
for "relational databases". The embedding backend exists for that case.

The vectoriser is fitted per request over the job plus the candidates in that
request. Scores are therefore comparable *within* one response and not across
responses — a documented consequence of having no corpus to fit against.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import ClassVar

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.ranking.base import Ranker, RankingWeights
from src.ranking.redaction import strip_contact_details

logger = logging.getLogger(__name__)


class LexicalRanker(Ranker):
    """Rank on TF-IDF cosine similarity between job text and resume text."""

    method: ClassVar[str] = "tfidf"

    def __init__(
        self,
        weights: RankingWeights | None = None,
        max_features: int = 5000,
    ) -> None:
        super().__init__(weights)
        self.max_features = max_features

    def describe(self) -> dict[str, str]:
        return {"method": self.method, "model": "TfidfVectorizer"}

    def text_similarities(self, job_text: str, candidate_texts: Sequence[str]) -> list[float]:
        """Cosine similarity of each candidate's resume against the job text.

        Returns zeros when there is no shared vocabulary to compare — an empty
        job description, or documents made entirely of stop words. That is an
        absence of evidence, and the other score components carry the result.
        """
        if not candidate_texts:
            return []

        redacted = [strip_contact_details(text) for text in candidate_texts]
        documents = [strip_contact_details(job_text), *redacted]

        vectoriser = TfidfVectorizer(
            max_features=self.max_features,
            stop_words="english",
            lowercase=True,
        )
        try:
            matrix = vectoriser.fit_transform(documents)
        except ValueError:
            logger.warning(
                "TF-IDF found no usable vocabulary across %d documents; "
                "text similarity contributes 0 to this ranking",
                len(documents),
            )
            return [0.0] * len(candidate_texts)

        similarities = cosine_similarity(matrix[0:1], matrix[1:])[0]
        return [float(value) for value in similarities]
