"""Shared types passed between graph nodes (docs/ARCHITECTURE.md).

Nodes import these from here, never from each other. Data only: no logic, no
functions. ``nodes.summarise`` and ``nodes.citation_check`` re-export their own
types so existing import paths keep working. Stage 6 adds the graph state here.
"""

from dataclasses import dataclass

# ---------------------------------------------------------------- summarise (Stage 4)


@dataclass(frozen=True)
class Claim:
    text: str
    pmids: list[str]


@dataclass(frozen=True)
class SkippedPaper:
    pmid: str
    reason: str


@dataclass(frozen=True)
class RejectedClaim:
    text: str
    pmids: list[str]
    reason: str


@dataclass(frozen=True)
class Summary:
    query: str
    claims: list[Claim]
    used_pmids: list[str]
    skipped: list[SkippedPaper]
    rejected: list[RejectedClaim]
    model: str


# ---------------------------------------------------------------- citation check (Stage 5)


@dataclass(frozen=True)
class Quote:
    pmid: str
    text: str


@dataclass(frozen=True)
class VerifiedClaim:
    text: str
    pmids: list[str]
    quotes: list[Quote]


@dataclass(frozen=True)
class FailedClaim:
    text: str
    pmids: list[str]
    quotes: list[Quote]
    reasons: list[str]
    explanation: str


@dataclass(frozen=True)
class CheckedSummary:
    query: str
    verified: list[VerifiedClaim]
    failed: list[FailedClaim]
    summary: Summary
    check_model: str
