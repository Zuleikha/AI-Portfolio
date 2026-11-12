"""Entry point: ``python -m research_agent "<query>" --yes [--trace]`` (docs/PRD.md, Stages 6, 7).

COSTS MONEY: calls the paid Anthropic API (at most 21 calls, G3). Refuses to run
without ``--yes`` (G1). Errors are not caught: the traceback shows and the exit
code is 1 (fail loud); the audit record is still written (G6).
"""

import argparse
import json
import textwrap
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from langchain_core.runnables import Runnable

from research_agent.graph import DEFAULT_RUNS_DIR, run
from research_agent.observability import traced

EXIT_OK = 0
EXIT_NO_CONSENT = 2
WRAP_WIDTH = 88  # O3
RULE = "─" * 40  # O1, O2
MAX_JOURNAL_CHARS = 50  # O4


@traced
def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m research_agent",
        description="Search PubMed, summarise, check every claim, write an audit record.",
    )
    parser.add_argument("query", help="PubMed search query")
    parser.add_argument(
        "--yes", action="store_true", help="confirm: this calls the paid Anthropic API"
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="send a trace of this run to LangSmith (needs LANGSMITH_API_KEY; only with --yes)",
    )
    return parser.parse_args(argv)


@traced
def _short_citation(paper: dict[str, Any]) -> str:
    """``<first author>[ et al.] <year> · <journal>`` (O4). Full citation stays in the record."""
    authors: list[str] = paper["authors"]
    parts: list[str] = []
    if authors:
        parts.append(f"{authors[0]} et al." if len(authors) > 1 else authors[0])
    if paper["year"] is not None:
        parts.append(str(paper["year"]))
    journal: str = paper["journal"]
    if len(journal) > MAX_JOURNAL_CHARS:
        journal = journal[: MAX_JOURNAL_CHARS - 1] + "…"
    return f"{' '.join(parts)} · {journal}"


@traced
def format_report(record: dict[str, Any], path: Path) -> str:
    """Terminal output (O1 to O7): header, counts, verified claims with short citations."""
    counts = record["counts"]
    lines = [
        f'Research Agent · "{record["query"]}"',
        RULE,
        f"Papers {counts['papers']} · Claims {counts['claims']} · "
        f"✔ Verified {counts['verified']} · ✘ Failed {counts['failed']}",
        f"Skipped {counts['skipped']} · Rejected {counts['rejected']} · "
        f"Injection warnings {len(record['injection_warnings'])}",
        RULE,
    ]
    papers = {p["pmid"]: p for p in (record["search"] or {}).get("papers", [])}
    verified = record["check"]["verified"] if record["check"] else []
    if not verified:
        lines += ["", "No verified claims."]
    for number, claim in enumerate(verified, start=1):
        marker = f"✔ {number}. "
        indent = " " * len(marker)  # O3: line up under the claim text
        lines.append("")
        lines += textwrap.wrap(
            claim["text"], width=WRAP_WIDTH, initial_indent=marker, subsequent_indent=indent
        )
        for pmid in claim["pmids"]:
            lines.append(indent + _short_citation(papers[pmid]))
            lines.append(indent + papers[pmid]["url"])
    lines += ["", f"✘ Failed: {counts['failed']} (reasons in the audit record)"]
    lines += ["", f"Audit record: {path}"]
    return "\n".join(lines)


@traced
def main(
    argv: list[str] | None = None,
    *,
    client: httpx.Client | None = None,
    summarise_llm: Runnable[Any, Any] | None = None,
    check_llm: Runnable[Any, Any] | None = None,
    runs_dir: Path = DEFAULT_RUNS_DIR,
) -> int:
    """Run once and print the result. ``client``, ``*_llm`` and ``runs_dir`` are test hooks."""
    args = _parse_args(argv)
    if not args.yes:  # G1: spend guard, before any call
        print("This calls the paid Anthropic API. Re-run with --yes to confirm. Nothing was run.")
        return EXIT_NO_CONSENT

    outcome = run(
        args.query,
        runs_dir=runs_dir,
        client=client,
        summarise_llm=summarise_llm,
        check_llm=check_llm,
        trace=args.trace,
    )
    record = json.loads(outcome.path.read_text(encoding="utf-8"))
    print(format_report(record, outcome.path))
    return EXIT_OK


if __name__ == "__main__":
    load_dotenv()  # G2: only when run as a program, never in tests
    raise SystemExit(main())
