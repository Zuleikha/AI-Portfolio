"""Stage 6 revision: terminal output layout (docs/PRD.md, O1 to O7). Offline, no calls."""

from pathlib import Path
from typing import Any

from research_agent.__main__ import MAX_JOURNAL_CHARS, RULE, WRAP_WIDTH, format_report

PATH = Path("runs/20261112T094819Z_0ee2c803.json")


def paper(
    pmid: str,
    *,
    authors: list[str] | None = None,
    year: int | None = 2021,
    journal: str = "Test Journal",
) -> dict[str, Any]:
    return {
        "pmid": pmid,
        "authors": ["Smith J", "Lee K"] if authors is None else authors,
        "year": year,
        "journal": journal,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


def record(
    verified: list[dict[str, Any]],
    papers: list[dict[str, Any]],
    *,
    failed: int = 0,
) -> dict[str, Any]:
    return {
        "query": "drug x",
        "search": {"papers": papers},
        "check": {"verified": verified, "failed": [{}] * failed},
        "counts": {
            "papers": len(papers),
            "skipped": 0,
            "claims": len(verified) + failed,
            "rejected": 0,
            "verified": len(verified),
            "failed": failed,
        },
        "injection_warnings": [],
    }


def test_report_layout() -> None:  # O1, O2, O3, O4, O5, O7
    rec = record(
        [{"text": "Drug X lowered blood pressure.", "pmids": ["111"]}],
        [paper("111")],
        failed=1,
    )
    assert format_report(rec, PATH) == "\n".join(
        [
            'Research Agent · "drug x"',
            RULE,
            "Papers 1 · Claims 2 · ✔ Verified 1 · ✘ Failed 1",
            "Skipped 0 · Rejected 0 · Injection warnings 0",
            RULE,
            "",
            "✔ 1. Drug X lowered blood pressure.",
            "     Smith J et al. 2021 · Test Journal",
            "     https://pubmed.ncbi.nlm.nih.gov/111/",
            "",
            "✘ Failed: 1 (reasons in the audit record)",
            "",
            f"Audit record: {PATH}",
        ]
    )


def test_long_claim_wraps() -> None:  # O3
    text = " ".join(["Drug X lowered blood pressure in adults"] * 6)
    out = format_report(record([{"text": text, "pmids": ["111"]}], [paper("111")]), PATH)
    lines = out.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("✔ 1. "))
    claim_lines = lines[first : lines.index("     Smith J et al. 2021 · Test Journal")]
    assert len(claim_lines) > 1
    assert all(len(line) <= WRAP_WIDTH for line in claim_lines)
    assert all(line.startswith("     ") for line in claim_lines[1:])
    assert " ".join(line.strip() for line in claim_lines).removeprefix("✔ 1. ") == text


def test_short_citation_variants() -> None:  # O4
    papers = [
        paper("1", authors=["Solo A"]),
        paper("2", year=None),
        paper("3", authors=[]),
    ]
    claims = [{"text": f"Claim {p['pmid']}.", "pmids": [p["pmid"]]} for p in papers]
    out = format_report(record(claims, papers), PATH)
    assert "     Solo A 2021 · Test Journal\n" in out
    assert "     Smith J et al. · Test Journal\n" in out
    assert "     2021 · Test Journal\n" in out


def test_no_verified_claims() -> None:  # O6
    out = format_report(record([], [paper("111")], failed=2), PATH)
    assert "No verified claims." in out
    assert "✔ 1." not in out
    assert out.endswith(f"Audit record: {PATH}")


def test_claim_ten_lines_up() -> None:  # O3
    papers = [paper(str(n)) for n in range(1, 11)]
    text = " ".join(["Drug X lowered blood pressure in adults"] * 4)
    claims = [{"text": text, "pmids": [p["pmid"]]} for p in papers]
    lines = format_report(record(claims, papers), PATH).splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("✔ 10. "))
    block = lines[start + 1 : lines.index("", start)]
    assert block  # wrapped lines + citation + url
    assert all(line.startswith(" " * 6) and line[6] != " " for line in block)


def test_long_journal_cut() -> None:  # O4
    long_name = "J" * 60
    exact = "K" * MAX_JOURNAL_CHARS
    papers = [paper("1", journal=long_name), paper("2", journal=exact)]
    claims = [{"text": f"Claim {p['pmid']}.", "pmids": [p["pmid"]]} for p in papers]
    out = format_report(record(claims, papers), PATH)
    assert f"· {'J' * (MAX_JOURNAL_CHARS - 1)}…\n" in out
    assert long_name not in out
    assert f"· {exact}\n" in out
