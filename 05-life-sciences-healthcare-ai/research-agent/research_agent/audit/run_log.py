"""Audit record: one JSON file per run, ok or failed (docs/PRD.md, Stage 6, G5 to G8, G12).

The record holds full paper details, claims and quotes so a reader can check the run.
It never holds an error **message** (an httpx error can contain the URL with
``api_key``): only the error class name and the step that failed (G6).
"""

import json
import re
import secrets
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research_agent.observability import traced
from research_agent.state import GraphState
from research_agent.tools.pubmed import Paper

STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
RUN_ID_HEX_BYTES = 4  # 8 hex characters
MAX_CITED_AUTHORS = 3  # Q7
# Record entry when a run is not traced (Stage 7, T3).
TRACE_OFF: dict[str, Any] = {"enabled": False, "backend": None, "project": None}

# Known prompt-injection phrases (G12). Lower case, single spaces. Warn only, never block.
INJECTION_PHRASES: tuple[str, ...] = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore the above instructions",
    "disregard previous instructions",
    "disregard all previous instructions",
    "forget your instructions",
    "new instructions:",
    "you are now",
    "system prompt",
)

_SPACES = re.compile(r"\s+")


@traced
def format_citation(paper: Paper) -> str:
    """Short citation (G8): authors, title, journal, year, url, DOI."""
    parts: list[str] = []
    if paper.authors:
        shown = ", ".join(paper.authors[:MAX_CITED_AUTHORS])
        parts.append(f"{shown}, et al." if len(paper.authors) > MAX_CITED_AUTHORS else f"{shown}.")
    parts.append(paper.title)
    parts.append(f"{paper.journal}.")
    if paper.year is not None:
        parts.append(f"{paper.year}.")
    parts.append(paper.url)
    if paper.doi:
        parts.append(f"doi:{paper.doi}")
    return " ".join(parts)


@traced
def find_injection_warnings(papers: list[Paper]) -> list[dict[str, str]]:
    """``[{pmid, phrase}]`` for each phrase found in a title or abstract (G12).

    Case ignored, whitespace collapsed; once per paper and phrase, in paper order.
    """
    warnings: list[dict[str, str]] = []
    for paper in papers:
        text = _SPACES.sub(" ", f"{paper.title} {paper.abstract or ''}").casefold()
        for phrase in INJECTION_PHRASES:
            if phrase in text:
                warnings.append({"pmid": paper.pmid, "phrase": phrase})
    return warnings


@traced
def new_run_id(now: datetime) -> str:
    """``<YYYYMMDDTHHMMSSZ>_<8 hex>``: UTC time + random, so same-second runs never clash (G5)."""
    return f"{now.astimezone(UTC).strftime(STAMP_FORMAT)}_{secrets.token_hex(RUN_ID_HEX_BYTES)}"


@traced
def build_audit_record(
    *,
    run_id: str,
    created_at: datetime,
    finished_at: datetime,
    state: GraphState,
    error: tuple[str, BaseException] | None,
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The record (G7). Steps that did not run are ``null``. ``trace``: Stage 7, T3."""
    search = state.get("search")
    summary = state.get("summary")
    checked = state.get("checked")

    check: dict[str, Any] | None = None
    if checked is not None:
        check = asdict(checked)
        del check["summary"]  # already under "summary" (G-Q6)

    return {
        "run_id": run_id,
        "created_at": created_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "status": "ok" if error is None else "error",
        "error": None if error is None else {"step": error[0], "type": type(error[1]).__name__},
        "query": state.get("query"),
        "max_results": state.get("max_results"),
        "models": {
            "summarise": summary.model if summary is not None else None,
            "check": checked.check_model if checked is not None else None,
        },
        "search": asdict(search) if search is not None else None,
        "citations": {p.pmid: format_citation(p) for p in search.papers} if search else {},
        "summary": asdict(summary) if summary is not None else None,
        "check": check,
        "counts": {
            "papers": len(search.papers) if search is not None else 0,
            "skipped": len(summary.skipped) if summary is not None else 0,
            "claims": len(summary.claims) if summary is not None else 0,
            "rejected": len(summary.rejected) if summary is not None else 0,
            "verified": len(checked.verified) if checked is not None else 0,
            "failed": len(checked.failed) if checked is not None else 0,
        },
        "injection_warnings": find_injection_warnings(search.papers) if search else [],
        "trace": dict(TRACE_OFF) if trace is None else trace,
    }


@traced
def write_audit_record(record: dict[str, Any], runs_dir: Path) -> Path:
    """Write ``runs_dir/<run_id>.json``; create the folder if missing; never overwrite (G5)."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{record['run_id']}.json"
    with path.open("x", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path
