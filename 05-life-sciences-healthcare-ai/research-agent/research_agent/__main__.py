"""Entry point: ``python -m research_agent "<query>" --yes`` (docs/PRD.md, Stage 6).

COSTS MONEY: calls the paid Anthropic API (at most 21 calls, G3). Refuses to run
without ``--yes`` (G1). Errors are not caught: the traceback shows and the exit
code is 1 (fail loud); the audit record is still written (G6).
"""

import argparse
import json
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from langchain_core.runnables import Runnable

from research_agent.graph import DEFAULT_RUNS_DIR, run
from research_agent.observability import traced

EXIT_OK = 0
EXIT_NO_CONSENT = 2


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
    return parser.parse_args(argv)


@traced
def _report(record: dict[str, Any], path: Path) -> str:
    """Verified claims with citations; failed claims as a count only (G-Q2)."""
    counts = record["counts"]
    lines = [
        f"Audit record: {path}",
        " | ".join(f"{name}: {n}" for name, n in counts.items())
        + f" | injection warnings: {len(record['injection_warnings'])}",
    ]
    verified = record["check"]["verified"] if record["check"] else []
    lines.append(f"Verified claims: {len(verified)}")
    for number, claim in enumerate(verified, start=1):
        lines.append(f"{number}. {claim['text']}")
        lines.extend(f"   - {record['citations'][pmid]}" for pmid in claim["pmids"])
    lines.append(f"Failed claims: {counts['failed']} (details in the audit record)")
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
    )
    record = json.loads(outcome.path.read_text(encoding="utf-8"))
    print(_report(record, outcome.path))
    return EXIT_OK


if __name__ == "__main__":
    load_dotenv()  # G2: only when run as a program, never in tests
    raise SystemExit(main())
