"""Validation schemas for structured resume records (Pydantic v2).

These are the contract for data entering the pipeline. Validation is strict on
purpose: a record that fails here is reported as a quality error rather than
silently ranked on partial data.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

MAX_SKILLS = 50


class SkillLevel(StrEnum):
    """Self-reported proficiency.

    ``StrEnum`` rather than a ``str, Enum`` mixin so that ``str(level)`` yields
    ``"expert"`` and not ``"SkillLevel.EXPERT"`` — the value is what gets
    serialised and compared, and the two forms differ there.
    """

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class ContactInfo(BaseModel):
    """Contact details. Held for completeness checks, never used for ranking."""

    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = Field(default=None, pattern=r"^\+?[\d\s\-()]{10,20}$")
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None


class Skill(BaseModel):
    """A named skill with optional depth."""

    name: str = Field(..., min_length=1, max_length=50)
    level: SkillLevel | None = None
    years_experience: int | None = Field(default=None, ge=0, le=50)


class Education(BaseModel):
    """One qualification."""

    degree: str = Field(..., min_length=1)
    institution: str = Field(..., min_length=1)
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)
    gpa: float | None = Field(default=None, ge=0.0, le=4.0)
    major: str | None = None
    minor: str | None = None


class Experience(BaseModel):
    """One role in an employment history."""

    title: str = Field(..., min_length=1)
    company: str = Field(..., min_length=1)
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$|^present$")
    description: str = Field(..., min_length=20, max_length=2000)
    skills_used: list[str] = Field(default_factory=list)
    location: str | None = None

    @field_validator("end_date")
    @classmethod
    def end_must_follow_start(cls, value: str | None, info) -> str | None:
        """Reject a role that ends before it starts.

        Validated on the entry itself rather than on the parent list, so the
        error points at the offending role instead of the whole resume. ISO
        dates compare correctly as strings, so no parsing is needed.
        """
        start = info.data.get("start_date")
        if value and value != "present" and start and start > value:
            raise ValueError(f"start_date {start} is after end_date {value}")
        return value


class ResumeSchema(BaseModel):
    """A complete, validated resume record."""

    id: str | None = None
    name: str = Field(..., min_length=1, max_length=100)
    contact: ContactInfo
    skills: list[str | Skill] = Field(..., min_length=1, max_length=MAX_SKILLS)
    education: list[Education] = Field(..., min_length=1)
    experience: list[Experience] = Field(default_factory=list)
    summary: str | None = Field(default=None, min_length=50, max_length=1000)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

    def skill_names(self) -> list[str]:
        """Flatten mixed string/object skills into plain names."""
        return [skill if isinstance(skill, str) else skill.name for skill in self.skills]
