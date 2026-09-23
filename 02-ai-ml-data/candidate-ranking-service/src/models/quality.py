"""Schemas for data-quality reporting."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, computed_field


class ValidationFailure(BaseModel):
    """One record that failed schema validation, and why."""

    record_index: int = Field(..., ge=0)
    record_id: str
    errors: list[dict[str, Any]]


class DuplicateSummary(BaseModel):
    """Duplicate detection results."""

    key_duplicate_count: int = Field(default=0, ge=0)
    content_duplicate_count: int = Field(default=0, ge=0)
    duplicate_percentage: float = Field(default=0.0, ge=0.0, le=100.0)


class DataQualityReport(BaseModel):
    """The outcome of running the quality checks over a batch of records.

    ``quality_score`` is derived rather than stored, so it can never drift out
    of step with the counts it is computed from.
    """

    total_records: int = Field(..., ge=0)
    valid_records: int = Field(..., ge=0)
    invalid_records: int = Field(..., ge=0)
    completeness: dict[str, float] = Field(default_factory=dict)
    duplicates: DuplicateSummary = Field(default_factory=DuplicateSummary)
    consistency_issues: list[dict[str, Any]] = Field(default_factory=list)
    failures: list[ValidationFailure] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def quality_score(self) -> float:
        """Percentage of records that passed validation."""
        if self.total_records == 0:
            return 0.0
        return round(self.valid_records / self.total_records * 100, 2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mean_completeness(self) -> float:
        """Mean field completeness across all fields, as a percentage."""
        if not self.completeness:
            return 0.0
        return round(sum(self.completeness.values()) / len(self.completeness), 2)
