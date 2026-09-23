"""Request and response bodies for the HTTP API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.domain import Candidate, CandidateMatch, JobRequirement
from src.monitoring.fairness import FairnessReport


class HealthResponse(BaseModel):
    """Liveness plus the facts needed to interpret a ranking."""

    status: str
    timestamp: datetime
    ranking: dict[str, str] = Field(
        ..., description="Active backend, e.g. {'method': 'tfidf', 'model': '...'}"
    )
    candidates_stored: int = Field(..., ge=0)
    capacity: int = Field(..., ge=1)


class UploadResponse(BaseModel):
    """Result of storing one candidate."""

    candidate_id: str
    created: bool = Field(..., description="False when an existing record was replaced.")
    candidates_stored: int = Field(..., ge=0)


class CandidateListResponse(BaseModel):
    """The ids currently held in the store."""

    count: int = Field(..., ge=0)
    candidate_ids: list[str]


class RankRequest(BaseModel):
    """Rank the stored candidates against a job."""

    job: JobRequirement
    top_k: int | None = Field(
        default=None,
        ge=1,
        description="Return only the top K matches. All matches when omitted.",
    )


class RankResponse(BaseModel):
    """A ranked shortlist, labelled with how it was produced.

    ``scoring_method`` is not decoration: a score means something different
    under TF-IDF than under embeddings, and a consumer that cannot tell which
    produced a number cannot interpret it.
    """

    scoring_method: str
    model: str | None = None
    candidates_considered: int = Field(..., ge=0)
    results: list[CandidateMatch]


class InlineRankRequest(BaseModel):
    """Rank a set of candidates supplied in the request itself.

    The stateless path: nothing is stored, so it leaves no candidate data
    behind in the process.
    """

    job: JobRequirement
    candidates: list[Candidate] = Field(..., min_length=1)
    top_k: int | None = Field(default=None, ge=1)


class FairnessRequest(BaseModel):
    """Outcomes to measure selection fairness over.

    Group labels are supplied by the caller. The service does not infer
    protected attributes from candidate data.
    """

    groups: list[str] = Field(..., min_length=1)
    selected: list[bool] = Field(..., min_length=1)
    qualified: list[bool] | None = Field(
        default=None,
        description="Optional ground-truth labels enabling the equal-opportunity metric.",
    )


class FairnessResponse(BaseModel):
    """The measured fairness report."""

    report: FairnessReport
