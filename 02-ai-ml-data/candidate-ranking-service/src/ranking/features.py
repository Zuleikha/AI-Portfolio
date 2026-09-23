"""Deterministic scoring features shared by every ranking backend.

These functions are pure: same inputs, same outputs, no I/O, no model loading.
Both the lexical and the embedding backend use them for the skill and
experience components, so the two backends differ only in how text similarity
is computed.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Iterable

__all__ = [
    "experience_fit",
    "normalise_skill",
    "parse_skills",
    "skill_coverage",
]


def parse_skills(value: object) -> list[str]:
    """Coerce a skills value into a list of skill strings.

    A CSV round-trip turns the list ``["Python", "SQL"]`` into the *string*
    ``"['Python', 'SQL']"``. This parses that form back with
    :func:`ast.literal_eval`, which evaluates Python literals only. A crafted
    cell such as ``__import__('os').system('...')`` raises ``ValueError``
    instead of executing — which is precisely why ``eval`` must never be used
    on data read from a file.

    Args:
        value: A sequence, a list-repr string, a comma-separated string, or None.

    Returns:
        A list of non-empty skill strings; empty for null-ish input.

    Raises:
        ValueError: If a string value is neither a well-formed list literal nor
            a plain comma-separated list.
    """
    if value is None:
        return []
    if isinstance(value, float) and math.isnan(value):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if not isinstance(value, str):
        raise ValueError(f"Cannot parse skills from {type(value).__name__}")

    text = value.strip()
    if not text:
        return []

    if text[0] in "[(" and text[-1] in "])":
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError) as exc:
            raise ValueError(f"Malformed skills literal: {text[:80]!r}") from exc
        if not isinstance(parsed, (list, tuple, set)):
            raise ValueError(f"Skills literal is not a sequence: {text[:80]!r}")
        return [str(item).strip() for item in parsed if str(item).strip()]

    return [part.strip() for part in text.split(",") if part.strip()]


def normalise_skill(skill: str) -> str:
    """Lowercase a skill and collapse internal whitespace, for comparison."""
    return " ".join(skill.lower().split())


def skill_coverage(candidate_skills: Iterable[str], target_skills: Iterable[str]) -> float:
    """Fraction of ``target_skills`` that the candidate holds.

    Returns 0.0 when the target list is empty: a role that states no skills
    provides no evidence either way, and awarding full marks for absent
    requirements would inflate every candidate identically.
    """
    targets = {normalise_skill(s) for s in target_skills if s and s.strip()}
    if not targets:
        return 0.0
    held = {normalise_skill(s) for s in candidate_skills if s and s.strip()}
    return len(held & targets) / len(targets)


def experience_fit(
    years: int | None,
    min_years: int = 0,
    max_years: int | None = None,
) -> float:
    """Score how a candidate's experience fits a role's stated band.

    - Below the minimum: scales linearly towards it.
    - Inside the band: 1.0.
    - Above the maximum: tapers by 0.1 per excess year, with a 0.7 floor —
      being over-qualified is a weak negative signal, not a disqualification.

    ``years is None`` (not stated on the resume) scores 0.0 rather than
    guessing a value, so an unstated figure can never outrank a stated one.
    """
    if years is None:
        return 0.0
    if min_years > 0 and years < min_years:
        return max(0.0, years / min_years)
    if max_years is None or years <= max_years:
        return 1.0
    excess = years - max_years
    return max(0.7, 1.0 - excess * 0.1)
