"""Ranking backends and the factory that selects one from configuration."""

from __future__ import annotations

from src.ranking.base import Ranker, RankingWeights, tier_for
from src.ranking.embedding import EmbeddingRanker
from src.ranking.lexical import LexicalRanker
from src.utils.config import Settings

__all__ = [
    "EmbeddingRanker",
    "LexicalRanker",
    "Ranker",
    "RankingWeights",
    "build_ranker",
    "tier_for",
]


def build_ranker(settings: Settings) -> Ranker:
    """Construct the ranking backend named by ``settings.ranking_method``.

    Args:
        settings: Loaded configuration.

    Returns:
        A ready-to-use ranker.

    Raises:
        ImportError: If the embedding backend is selected without its optional
            dependency installed.
    """
    weights = RankingWeights(
        skill=settings.skill_weight,
        experience=settings.experience_weight,
        similarity=settings.similarity_weight,
        required_share=settings.required_skill_share,
    )
    if settings.ranking_method == "embedding":
        return EmbeddingRanker(weights=weights, model_name=settings.embedding_model)
    return LexicalRanker(weights=weights)
