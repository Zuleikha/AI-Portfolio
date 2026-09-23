"""Keep `docs/build-record.html` honest, and derive its publishable copy.

`docs/build-record.html` is the source of truth: it is versioned alongside the
code it describes, renders from disk, and links to the other docs. Two jobs live
here.

**1. Live counts.** The record quotes file, test and line counts, which drift
every time the repo moves. Each one is marked up as
``<span data-stat="NAME">…</span>``; this script recomputes them from the repo
and writes them back, so the numbers are derived rather than remembered.

    python scripts/derive_artifact.py --refresh   # rewrite with fresh counts
    python scripts/derive_artifact.py --check     # fail if any count is stale

`--check` runs in CI, so a commit that changes the counts without refreshing the
record fails the build instead of quietly leaving a wrong number in a document
whose whole purpose is to be accurate.

**2. The published fragment.** The artifact on claude.ai is a derived copy,
because two things about a standalone document are wrong in that context:

- **The document skeleton.** claude.ai wraps the uploaded file in its own
  ``<!doctype html>…<head>…</head><body>``. Publishing a complete document would
  nest one inside another.
- **Repo-relative links.** ``../DECISIONS.md`` resolves on GitHub and on disk,
  and 404s on claude.ai.

    python scripts/derive_artifact.py --out fragment.html

Publish the result to the existing page, so the link stays stable:
https://claude.ai/code/artifact/099ecde6-78cd-4025-876f-e8c1e9d0bc38
(private to the repository owner; publishing without that URL creates a
second, unrelated artifact rather than updating this one.)

Deriving always applies fresh counts in memory, so the published page is correct
even if someone forgot to run ``--refresh``.

Every transform is asserted: a change to the source that breaks an assumption
here fails loudly rather than publishing something malformed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "docs" / "build-record.html"

# Emitted by the host at publish time; duplicating them nests two documents.
SKELETON_TAGS = (
    "<!doctype html>",
    '<html lang="en">',
    "<head>",
    "</head>",
    "<body>",
    "</body>",
    "</html>",
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
)

# <a href="../ANYTHING.md">text</a>  ->  text
REPO_LINK = re.compile(r'<a href="\.\./[^"]+\.md">(.*?)</a>', re.DOTALL)

# <span ... data-stat="name" ...>value</span>
STAT_SPAN = re.compile(
    r'(<span[^>]*\bdata-stat="(?P<name>[a-z_]+)"[^>]*>)(?P<value>[^<]*)(</span>)'
)

COLLECTED = re.compile(r"(\d+)(?:/\d+)? tests? collected")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout


def _collected(marker: str) -> int:
    """Count tests pytest collects for a marker expression.

    Collection is used rather than counting `def test_` in the source, because
    parametrised tests expand to several cases each and a source count would be
    quietly wrong.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", marker],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    match = COLLECTED.search(result.stdout)
    if match is None:
        raise ValueError(f"could not read a test count from pytest (marker {marker!r})")
    return int(match.group(1))


def collect_stats() -> dict[str, int]:
    """Recompute every live figure the record quotes.

    Deliberately excludes a commit count: it changes on the very commit that
    records it, so it could never be both live and checked.
    """
    tracked = [line for line in _git("ls-files").splitlines() if line]
    src_files = [f for f in tracked if f.startswith("src/") and f.endswith(".py")]
    src_lines = sum(
        len((REPO_ROOT / f).read_text(encoding="utf-8").splitlines()) for f in src_files
    )

    total = _collected("")
    live = _collected("live")

    return {
        "files": len(tracked),
        "src_lines": src_lines,
        "tests_total": total,
        "tests_live": live,
        "tests_default": total - live,
    }


def apply_stats(html: str, stats: dict[str, int]) -> str:
    """Write each live figure into every element that carries its marker."""
    seen: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        if name not in stats:
            raise ValueError(f'unknown data-stat="{name}" in the record')
        seen.add(name)
        return f"{match.group(1)}{stats[name]}{match.group(4)}"

    updated = STAT_SPAN.sub(replace, html)

    unused = sorted(set(stats) - seen)
    if unused:
        raise ValueError(f"computed stats that the record never uses: {', '.join(unused)}")
    return updated


def stale_stats(html: str, stats: dict[str, int]) -> dict[str, tuple[str, int]]:
    """Return every marked figure whose written value is out of date."""
    stale = {}
    for match in STAT_SPAN.finditer(html):
        name = match.group("name")
        written = match.group("value").strip()
        if name in stats and written != str(stats[name]):
            stale[name] = (written, stats[name])
    return stale


def derive(html: str) -> str:
    """Turn a standalone build-record document into a publishable fragment."""
    for tag in SKELETON_TAGS:
        html = html.replace(tag + "\n", "").replace(tag, "")

    html = REPO_LINK.sub(r"\1", html)
    html = re.sub(r"\n{3,}", "\n\n", html).strip() + "\n"

    _assert_publishable(html)
    return html


def _assert_publishable(html: str) -> None:
    """Fail loudly rather than publish something malformed."""
    lowered = html.lower()
    for tag in ("<!doctype", "<html", "<head>", "<body>"):
        if tag in lowered:
            raise ValueError(f"document skeleton survived the strip: {tag}")

    if 'href="../' in html:
        raise ValueError("a repo-relative link survived; it would 404 once published")

    for required in ("<title>", 'class="page"', "<style>"):
        if required not in html:
            raise ValueError(f"expected {required} in the fragment; the source may have moved")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh and derive the build record.")
    parser.add_argument(
        "--source",
        type=Path,
        default=SOURCE,
        help="standalone HTML to work on (default: docs/build-record.html)",
    )
    parser.add_argument("--out", type=Path, help="write the fragment here (default: stdout)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--refresh", action="store_true", help="rewrite the source with fresh counts, then stop"
    )
    mode.add_argument(
        "--check", action="store_true", help="exit 1 if any count in the source is stale"
    )
    args = parser.parse_args(argv)

    if not args.source.is_file():
        parser.error(f"no such file: {args.source}")

    html = args.source.read_text(encoding="utf-8")

    try:
        stats = collect_stats()

        if args.check:
            stale = stale_stats(html, stats)
            if stale:
                for name, (written, actual) in sorted(stale.items()):
                    print(f"stale: {name} says {written}, repo says {actual}", file=sys.stderr)
                print(
                    "\nrun: python scripts/derive_artifact.py --refresh",
                    file=sys.stderr,
                )
                return 1
            print(f"all {len(stats)} counts current")
            return 0

        refreshed = apply_stats(html, stats)

        if args.refresh:
            if refreshed == html:
                print("counts already current; nothing to write")
            else:
                args.source.write_text(refreshed, encoding="utf-8")
                print(f"refreshed {args.source}")
            return 0

        fragment = derive(refreshed)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.out is None:
        # Write bytes, not text: the record contains characters (→, ·, —) that
        # a cp1252 console cannot encode, and stdout is frequently piped anyway.
        sys.stdout.buffer.write(fragment.encode("utf-8"))
    else:
        args.out.write_text(fragment, encoding="utf-8")
        print(f"wrote {args.out} ({len(fragment.encode('utf-8'))} bytes)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
