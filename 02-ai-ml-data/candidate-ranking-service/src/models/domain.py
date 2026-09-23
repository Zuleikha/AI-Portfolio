"""Core domain models shared by the ranking engine and the HTTP layer."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Candidate(BaseModel):
    """One person being ranked."""

    candidate_id: str = Field(..., min_length=1, max_length=128)
    resume_text: str = Field(..., min_length=1)
    skills: list[str] = Field(default_factory=list)
    years_experience: int | None = Field(default=None, ge=0, le=60)


class JobRequirement(BaseModel):
    """The role candidates are ranked against."""

    title: str | None = Field(default=None, max_length=200)
    description: str = Field(default="")
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    min_years_experience: int = Field(default=0, ge=0, le=60)
    max_years_experience: int | None = Field(default=None, ge=0, le=60)

    def as_text(self) -> str:
        """Flatten the requirement into the text a similarity backend sees."""
        parts = [
            self.title or "",
            self.description,
            " ".join(self.required_skills),
            " ".join(self.preferred_skills),
        ]
        return "\n".join(part for part in parts if part).strip()


class ScoreBreakdown(BaseModel):
    """Per-component scores behind an overall score.

    Published in the API response so a score is never an unexplained number.
    """

    skill_match: float = Field(..., ge=0.0, le=1.0)
    experience_match: float = Field(..., ge=0.0, le=1.0)
    text_similarity: float = Field(..., ge=0.0, le=1.0)


class CandidateMatch(BaseModel):
    """A candidate's position in a ranked result set."""

    candidate_id: str
    overall_score: float = Field(..., ge=0.0, le=1.0)
    rank: int = Field(..., ge=1)
    tier: str = Field(..., description="A-D band derived from overall_score.")
    breakdown: ScoreBreakdown
