"""Remove direct contact details from resume text before it is scored.

Email addresses, phone numbers and profile URLs carry no signal about whether
someone can do the job, but they do carry signal about who they are — a
personal domain, a country dialling code. Stripping them before the text
reaches a vectoriser or an embedding model narrows what the score can be
derived from.

This is a mitigation, not anonymisation. Names remain in the text; see
``docs/ROADMAP.md``.
"""

from __future__ import annotations

import re

EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
URL_PATTERN = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)

# Phone formats vary too much between countries to enumerate as patterns
# (+44 20 7946 0958 and (415) 555-0123 share no shape). Instead: find any run
# of digits and separators, then decide by digit count. Horizontal whitespace
# only -- a run must not span lines.
PHONE_CANDIDATE_PATTERN = re.compile(r"(?<!\w)\+?\(?\d[\d.()\-  \t]{5,}\d(?!\w)")

# A phone number carries at least this many digits internationally. A year
# range such as "2019 - 2024" carries eight, so it survives -- employment
# dates are signal and must not be redacted away.
MIN_PHONE_DIGITS = 9

REDACTION_MARKER = " "


def _redact_if_phone(match: re.Match[str]) -> str:
    """Blank a digit run only when it is long enough to be a phone number."""
    text = match.group()
    digit_count = sum(character.isdigit() for character in text)
    return REDACTION_MARKER if digit_count >= MIN_PHONE_DIGITS else text


def strip_contact_details(text: str) -> str:
    """Return ``text`` with emails, URLs and phone numbers removed.

    Order matters: emails and URLs are removed first, because a phone pattern
    can otherwise match digit runs inside them.

    Args:
        text: Raw resume text.

    Returns:
        The text with contact details replaced by whitespace and runs of
        whitespace collapsed. Line structure is preserved.
    """
    without_email = EMAIL_PATTERN.sub(REDACTION_MARKER, text)
    without_urls = URL_PATTERN.sub(REDACTION_MARKER, without_email)
    without_phones = PHONE_CANDIDATE_PATTERN.sub(_redact_if_phone, without_urls)

    lines = [" ".join(line.split()) for line in without_phones.splitlines()]
    return "\n".join(lines).strip()
