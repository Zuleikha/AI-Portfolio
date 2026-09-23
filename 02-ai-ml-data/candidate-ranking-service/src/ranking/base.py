"""The ranking contract shared by every backend.

A backend supplies one thing: text similarity between a job and a set of
candidates. Everything else — skill coverage, experience fit, weighting,
ordering, tiering — lives here, so swapping TF-IDF for embeddings changes one
component of the score and nothing about how the result is assembled.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from src.models.domain import Candidate, CandidateMatch, JobRequirement, ScoreBreakdown
from src.ranking.features import experience_fit, skill_coverage

# Score bands published with each result. Deliberately coarse: the difference
# between 0.61 and 0.63 is not meaningful, and presenting it as a fine-grained
# ordering invites more confidence than the score supports.
TIER_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (0.75, "A"),
    (0.50, "B"),
    (0.25, "C"),
)
LOWEST_TIER = "D"


def tier_for(score: float) -> str:
    """Map an overall score onto its band."""
    for threshold, tier in TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return LOWEST_TIER


@dataclass(frozen=True)
class RankingWeights:
    """How the three score components are combined.

    Attributes:
        skill: Weight of skill coverage.
        experience: Weight of experience fit.
        similarity: Weight of free-text similarity.
        required_share: Within the skill component, the share attributed to
            required (versus preferred) skills.
    """

    skill: float = 0.5
    experience: float = 0.3
    similarity: float = 0.2
    required_share: float = 0.8

    def __post_init__(self) -> None:
        total = self.skill + self.experience + self.similarity
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Component weights must sum to 1.0, got {total:.4f}")
        if not 0.0 <= self.required_share <= 1.0:
            raise ValueError(f"required_share must be in [0, 1], got {self.required_share}")


class Ranker(ABC):
    """Base class for ranking backends."""

    method: ClassVar[str]

    def __init__(self, weights: RankingWeights | None = None) -> None:
        self.weights = weights or RankingWeights()

    @abstractmethod
    def text_similarities(self, job_text: str, candidate_texts: Sequence[str]) -> list[float]:
        """Return a similarity in [0, 1] for each candidate text.

        Implementations must return one value per candidate text, in order.
        """

    def describe(self) -> dict[str, str]:
        """Identify the backend for the API's health and rank responses."""
        return {"method": self.method}

    def skill_component(self, candidate: Candidate, job: JobRequirement) -> float:
        """Blend required- and preferred-skill coverage into one score.

        When a job states only one of the two lists, that list carries the
        whole component — otherwise a job with no preferred skills would cap
        every candidate at ``required_share``.
        """
        has_required = bool(job.required_skills)
        has_preferred = bool(job.preferred_skills)

        if not has_required and not has_preferred:
            return 0.0
        if has_required and not has_preferred:
            return skill_coverage(candidate.skills, job.required_skills)
        if has_preferred and not has_required:
            return skill_coverage(candidate.skills, job.preferred_skills)

        required = skill_coverage(candidate.skills, job.required_skills)
        preferred = skill_coverage(candidate.skills, job.preferred_skills)
        return (
            self.weights.required_share * required + (1 - self.weights.required_share) * preferred
        )

    def rank(self, job: JobRequirement, candidates: Sequence[Candidate]) -> list[CandidateMatch]:
        """Score and order candidates against a job.

        Ties break on ``candidate_id`` so the ordering is total and stable —
        never on insertion order, which would make results depend on upload
        sequence.

        Args:
            job: The role to rank against.
            candidates: Candidates to score. May be empty.

        Returns:
            Matches sorted best-first, each with its rank and component
            breakdown.
        """
        if not candidates:
            return []

        job_text = job.as_text()
        similarities = self.text_similarities(
            job_text, [candidate.resume_text for candidate in candidates]
        )
        if len(similarities) != len(candidates):
            raise ValueError(
                f"{type(self).__name__} returned {len(similarities)} similarities "
                f"for {len(candidates)} candidates"
            )

        scored: list[tuple[float, Candidate, ScoreBreakdown]] = []
        for candidate, similarity in zip(candidates, similarities, strict=True):
            breakdown = ScoreBreakdown(
                skill_match=_clamp(self.skill_component(candidate, job)),
                experience_match=_clamp(
                    experience_fit(
                        candidate.years_experience,
                        job.min_years_experience,
                        job.max_years_experience,
                    )
                ),
                text_similarity=_clamp(similarity),
            )
            overall = _clamp(
                breakdown.skill_match * self.weights.skill
                + breakdown.experience_match * self.weights.experience
                + breakdown.text_similarity * self.weights.similarity
            )
            scored.append((overall, candidate, breakdown))

        scored.sort(key=lambda row: (-row[0], row[1].candidate_id))

        return [
            CandidateMatch(
                candidate_id=candidate.candidate_id,
                overall_score=round(overall, 4),
                rank=position,
                tier=tier_for(overall),
                breakdown=breakdown,
            )
            for position, (overall, candidate, breakdown) in enumerate(scored, start=1)
        ]


def _clamp(value: float) -> float:
    """Constrain a score to [0, 1].

    Cosine similarity over embeddings can be negative; a negative component
    would otherwise pull an overall score below the range the API publishes.
    """
    return min(1.0, max(0.0, float(value)))
