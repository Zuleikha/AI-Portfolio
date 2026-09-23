"""Tests for contact-detail redaction."""

from __future__ import annotations

import pytest

from src.ranking.redaction import strip_contact_details

RESUME = """Jane Smith
jane.smith@example.com | (415) 555-0123
https://github.com/janesmith

SKILLS
Python, PostgreSQL, Docker
"""


def test_email_is_removed():
    assert "jane.smith@example.com" not in strip_contact_details(RESUME)
    assert "@" not in strip_contact_details(RESUME)


def test_phone_number_is_removed():
    cleaned = strip_contact_details(RESUME)
    assert "555-0123" not in cleaned
    assert "415" not in cleaned


def test_url_is_removed():
    cleaned = strip_contact_details(RESUME)
    assert "github.com/janesmith" not in cleaned
    assert "https" not in cleaned


def test_skills_and_name_survive_redaction():
    """Redaction must not damage the content the ranking depends on."""
    cleaned = strip_contact_details(RESUME)
    for token in ("Jane Smith", "Python", "PostgreSQL", "Docker", "SKILLS"):
        assert token in cleaned


def test_line_structure_is_preserved():
    cleaned = strip_contact_details("line one\n\nline two")
    assert "line one" in cleaned
    assert "line two" in cleaned


@pytest.mark.parametrize(
    "phone",
    [
        "+1 415 555 0123",
        "(415) 555-0123",
        "415-555-0123",
        "415.555.0123",
        "+44 20 7946 0958",
    ],
)
def test_common_phone_formats_are_caught(phone: str):
    cleaned = strip_contact_details(f"Contact: {phone}")
    assert not any(char.isdigit() for char in cleaned)


def test_years_in_work_history_are_not_mistaken_for_phone_numbers():
    """A four-digit year must survive; losing dates would gut the experience signal."""
    cleaned = strip_contact_details("Senior Engineer at TechCorp (2019 - 2024)")
    assert "2019" in cleaned
    assert "2024" in cleaned


def test_empty_input_is_handled():
    assert strip_contact_details("") == ""
    assert strip_contact_details("   \n  ") == ""
