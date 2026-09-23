"""Tests for the pure scoring features.

The ``parse_skills`` tests exist because the original implementation called
``eval()`` on values read from CSV files. These pin the replacement's
behaviour so that regression cannot return.
"""

from __future__ import annotations

import math

import pytest

from src.ranking.features import (
    experience_fit,
    normalise_skill,
    parse_skills,
    skill_coverage,
)

# --- parse_skills: safety --------------------------------------------------


def test_parse_skills_does_not_execute_code_in_a_list_literal(tmp_path):
    """A payload that ``eval`` would run must raise instead."""
    sentinel = tmp_path / "executed.txt"
    payload = f"[__import__('pathlib').Path({str(sentinel)!r}).touch()]"

    with pytest.raises(ValueError, match="Malformed skills literal"):
        parse_skills(payload)

    assert not sentinel.exists(), "parse_skills executed the payload"


def test_parse_skills_does_not_execute_a_bare_code_string(tmp_path):
    """A non-literal string is treated as text, never as code."""
    sentinel = tmp_path / "executed.txt"
    payload = f"__import__('pathlib').Path({str(sentinel)!r}).touch()"

    result = parse_skills(payload)

    assert not sentinel.exists(), "parse_skills executed the payload"
    assert result == [payload]


def test_parse_skills_rejects_a_non_sequence_literal():
    """Parses as a literal, but yields an int rather than a list of skills."""
    with pytest.raises(ValueError, match="not a sequence"):
        parse_skills("(1)")


def test_parse_skills_rejects_an_expression_that_is_not_a_literal():
    with pytest.raises(ValueError, match="Malformed skills literal"):
        parse_skills("[1, 2][0]")


# --- parse_skills: behaviour ----------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (["Python", "SQL"], ["Python", "SQL"]),
        (("Python", "SQL"), ["Python", "SQL"]),
        ("['Python', 'SQL']", ["Python", "SQL"]),
        ('["Python", "SQL"]', ["Python", "SQL"]),
        ("('Python', 'SQL')", ["Python", "SQL"]),
        ("Python, SQL", ["Python", "SQL"]),
        ("Python,SQL", ["Python", "SQL"]),
        ("Python", ["Python"]),
        ("[]", []),
        ("", []),
        ("   ", []),
        (None, []),
    ],
)
def test_parse_skills_handles_every_shape_the_pipeline_produces(value, expected):
    assert parse_skills(value) == expected


def test_parse_skills_treats_nan_as_missing():
    """Pandas represents an empty CSV cell as NaN, not None."""
    assert parse_skills(float("nan")) == []


def test_parse_skills_strips_whitespace_and_drops_blanks():
    assert parse_skills("['  Python  ', '', '  ', 'SQL']") == ["Python", "SQL"]


def test_parse_skills_rejects_unsupported_types():
    with pytest.raises(ValueError, match="Cannot parse skills from int"):
        parse_skills(42)


def test_parse_skills_roundtrips_a_repr():
    original = ["Python", "Docker", "AWS"]
    assert parse_skills(repr(original)) == original


# --- normalise_skill -------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Python", "python"),
        ("  PYTHON  ", "python"),
        ("Machine   Learning", "machine learning"),
        ("Node.js", "node.js"),
    ],
)
def test_normalise_skill(value, expected):
    assert normalise_skill(value) == expected


# --- skill_coverage --------------------------------------------------------


def test_skill_coverage_is_the_fraction_of_required_skills_held():
    assert skill_coverage(["Python", "SQL", "Go"], ["Python", "SQL", "AWS", "Docker"]) == 0.5


def test_skill_coverage_ignores_case_and_spacing():
    assert skill_coverage(["  pYtHoN "], ["Python"]) == 1.0


def test_skill_coverage_is_zero_when_the_job_states_no_skills():
    """No stated requirement is no evidence, not a free full mark."""
    assert skill_coverage(["Python"], []) == 0.0


def test_skill_coverage_is_zero_for_a_candidate_with_no_skills():
    assert skill_coverage([], ["Python"]) == 0.0


def test_skill_coverage_ignores_blank_entries():
    assert skill_coverage(["Python", "", "  "], ["Python", "SQL"]) == 0.5


def test_skill_coverage_does_not_exceed_one_when_candidate_has_extras():
    assert skill_coverage(["Python", "SQL", "Go", "Rust"], ["Python"]) == 1.0


# --- experience_fit --------------------------------------------------------


@pytest.mark.parametrize(
    ("years", "minimum", "maximum", "expected"),
    [
        (5, 3, 8, 1.0),  # inside the band
        (3, 3, 8, 1.0),  # exactly the minimum
        (8, 3, 8, 1.0),  # exactly the maximum
        (0, 4, 8, 0.0),  # no experience against a 4-year floor
        (2, 4, 8, 0.5),  # halfway to the floor
        (1, 4, 8, 0.25),
        (10, 3, 8, 0.8),  # two years over: 1.0 - 2 * 0.1
        (20, 3, 8, 0.7),  # far over: clamped at the floor
        (5, 0, None, 1.0),  # no stated band
        (0, 0, None, 1.0),  # no experience, no requirement
        (30, 3, None, 1.0),  # open-ended upper bound
    ],
)
def test_experience_fit(years, minimum, maximum, expected):
    assert math.isclose(experience_fit(years, minimum, maximum), expected)


def test_unstated_experience_scores_zero_rather_than_guessing():
    assert experience_fit(None, 3, 8) == 0.0


def test_experience_fit_never_leaves_the_unit_interval():
    for years in range(0, 60):
        value = experience_fit(years, 5, 10)
        assert 0.0 <= value <= 1.0
