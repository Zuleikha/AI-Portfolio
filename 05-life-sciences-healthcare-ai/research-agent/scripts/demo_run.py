"""Demo: real PubMed search + real summary, saved as JSON (docs/PRD.md, "Demo script").

COSTS MONEY: calls the paid Anthropic API. Refuses to run without ``--yes`` (D2).

Usage, from the research-agent folder::

    python -m scripts.demo_run "<query>" --yes

A stop-gap so real claims can be inspected before Stage 5; Stage 6 replaces it.
"""

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from langchain_core.runnables import Runnable

from research_agent.nodes.summarise import Summary, summarise
from research_agent.observability import traced
from research_agent.tools.pubmed import SearchResult, search_pubmed

DEMO_MAX_RESULTS = 5
DEFAULT_RUNS_DIR = Path("runs")
SOURCE = "live demo"
FILE_PREFIX = "demo_"
STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
EXIT_OK = 0
EXIT_NO_CONSENT = 2


@traced
def build_record(result: SearchResult, summary: Summary, created_at: datetime) -> dict[str, Any]:
    """The JSON record, built from the dataclasses (D4)."""
    return {
        "source": SOURCE,
        "created_at": created_at.isoformat(),
        "search": asdict(result),
        "summary": asdict(summary),
    }


@traced
def write_record(record: dict[str, Any], runs_dir: Path, created_at: datetime) -> Path:
    """Write to ``runs_dir/demo_<UTC stamp>.json``; never overwrite (D3)."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{FILE_PREFIX}{created_at.astimezone(UTC).strftime(STAMP_FORMAT)}.json"
    with path.open("x", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


@traced
def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("query", help="PubMed search query")
    parser.add_argument(
        "--yes", action="store_true", help="confirm: this calls the paid Anthropic API"
    )
    return parser.parse_args(argv)


@traced
def main(
    argv: list[str] | None = None,
    *,
    client: httpx.Client | None = None,
    llm: Runnable[Any, Any] | None = None,
    runs_dir: Path = DEFAULT_RUNS_DIR,
) -> int:
    """Run the demo. ``client``, ``llm`` and ``runs_dir`` are test hooks."""
    args = _parse_args(argv)
    if not args.yes:  # D2: spend guard, before any call
        print("This calls the paid Anthropic API. Re-run with --yes to confirm. Nothing was run.")
        return EXIT_NO_CONSENT

    result = search_pubmed(args.query, DEMO_MAX_RESULTS, client=client)
    summary = summarise(result, llm=llm)
    created_at = datetime.now(UTC)
    path = write_record(build_record(result, summary, created_at), runs_dir, created_at)

    # D5: path and counts only, never abstracts or model text.
    print(f"Saved: {path}")
    print(
        f"papers: {len(result.papers)} (of {result.total_found} found) | "
        f"claims: {len(summary.claims)} | skipped: {len(summary.skipped)} | "
        f"rejected: {len(summary.rejected)}"
    )
    return EXIT_OK


if __name__ == "__main__":
    load_dotenv()  # D6: only when run as a script, never in tests
    raise SystemExit(main())
