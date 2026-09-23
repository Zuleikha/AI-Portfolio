"""
Fetch JATS articles from PubMed Central into a local, gitignored corpus.

    python -m scripts.fetch_pmc --query "crispr gene editing" --limit 30
    python -m scripts.fetch_pmc --pmcid PMC7096066

Why a script and not a checked-in corpus
----------------------------------------
PMC Open Access licences **vary per article** — CC-BY, CC-BY-NC, CC0 and others
sit side by side in the same search results. Redistributing third-party articles
from a public portfolio repository would mean honouring each of those licences
individually. Shipping the fetcher instead keeps the evaluation reproducible by
anyone while redistributing nothing: ``data/pmc/`` is gitignored, and every
article's id and stated licence are recorded in ``data/pmc/MANIFEST.json``.

Cost and rate limits
--------------------
NCBI E-utilities is **free and needs no API key**. Unkeyed clients are limited to
3 requests/second, so this script sleeps between calls and batches its fetches.
No paid API is contacted. Set ``NCBI_API_KEY`` to raise the limit to 10/sec.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.jats_parser import article_id, article_licence, article_title, find_article  # noqa: E402

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_QUERY = 'open access[filter] AND "clinical trial"[Publication Type]'
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "pmc"
MANIFEST_NAME = "MANIFEST.json"

# Unkeyed E-utilities allows 3 requests/second. A third of a second plus headroom
# keeps a well-behaved client comfortably inside that without needing a key.
UNKEYED_DELAY_SECONDS = 0.4
KEYED_DELAY_SECONDS = 0.15
FETCH_BATCH_SIZE = 10

# NCBI asks that clients identify themselves so they can contact a badly-behaved
# one rather than simply blocking it.
USER_AGENT = "xml-content-retrieval-service/1.0 (portfolio evaluation corpus builder)"


def _delay() -> float:
    return KEYED_DELAY_SECONDS if os.getenv("NCBI_API_KEY") else UNKEYED_DELAY_SECONDS


def _request(endpoint: str, params: dict[str, str]) -> bytes:
    api_key = os.getenv("NCBI_API_KEY")
    if api_key:
        params = {**params, "api_key": api_key}
    url = f"{EUTILS}/{endpoint}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 — fixed https host
        return response.read()


def search(query: str, limit: int) -> list[str]:
    """Return PMC ids matching a query, newest first."""
    payload = _request(
        "esearch.fcgi",
        {"db": "pmc", "term": query, "retmax": str(limit), "retmode": "xml", "sort": "pub_date"},
    )
    root = ET.fromstring(payload)
    return [element.text.strip() for element in root.iter("Id") if element.text]


def fetch(pmc_ids: list[str]) -> bytes:
    """Fetch full JATS for a batch of PMC ids. Returns a <pmc-articleset>."""
    return _request(
        "efetch.fcgi",
        {"db": "pmc", "id": ",".join(pmc_ids), "retmode": "xml"},
    )


def split_articleset(payload: bytes) -> list[ET.Element]:
    """Split an efetch response into its individual <article> elements.

    efetch returns ``<pmc-articleset>`` even for a single id, and an id whose
    full text is not in the Open Access subset comes back as an empty stub.
    """
    root = ET.fromstring(payload)
    if find_article(root) is None:
        return []
    return [e for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "article"]


def write_article(article: ET.Element, out_dir: Path) -> dict | None:
    """Write one article as UTF-8 JATS. Returns its manifest record.

    Articles with no ``<body>`` are skipped: PMC indexes abstract-only records
    whose full text is not open access, and they would quietly weaken a corpus
    built to test chunking over long documents.
    """
    if not any(e.tag.rsplit("}", 1)[-1] == "body" for e in article):
        return None

    pmc_id = article_id(article)
    filename = f"{pmc_id if pmc_id.startswith('PMC') else 'PMC' + pmc_id}.xml"
    path = out_dir / filename

    # Explicit UTF-8 throughout. JATS carries U+2010 and similar, and the default
    # Windows console encoding (cp1252) cannot represent them.
    ET.ElementTree(article).write(path, encoding="utf-8", xml_declaration=True)

    return {
        "file": filename,
        "pmc_id": pmc_id,
        "title": article_title(article),
        "licence": article_licence(article),
        "source": f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/",
        "bytes": path.stat().st_size,
    }


def build_corpus(query: str, limit: int, out_dir: Path, pmc_ids: list[str] | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    if pmc_ids:
        ids = pmc_ids
        print(f"fetching {len(ids)} explicitly named article(s)")
    else:
        print(f"searching PMC: {query!r} (limit {limit})")
        ids = search(query, limit)
        print(f"  {len(ids)} ids returned")
        time.sleep(_delay())

    records: list[dict] = []
    skipped: list[str] = []
    for start in range(0, len(ids), FETCH_BATCH_SIZE):
        batch = ids[start : start + FETCH_BATCH_SIZE]
        print(f"  fetching {start + 1}-{start + len(batch)} of {len(ids)}")
        articles = split_articleset(fetch(batch))
        for article in articles:
            record = write_article(article, out_dir)
            if record is None:
                skipped.append(article_id(article))
            else:
                records.append(record)
        time.sleep(_delay())

    manifest = {
        "source": "NCBI PubMed Central via E-utilities (free, no API key required)",
        "query": None if pmc_ids else query,
        "requested": len(ids),
        "written": len(records),
        "skipped_no_body": skipped,
        "licence_note": (
            "PMC Open Access licences vary per article. Each article's stated "
            "licence is recorded below. This corpus is gitignored and is not "
            "redistributed; re-create it by running scripts/fetch_pmc.py."
        ),
        "articles": sorted(records, key=lambda r: r["file"]),
    }
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--query", default=DEFAULT_QUERY, help="PMC search term")
    ap.add_argument("--limit", type=int, default=30, help="maximum articles to fetch")
    ap.add_argument("--pmcid", action="append", help="fetch specific ids instead of searching")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    args = ap.parse_args()

    manifest = build_corpus(args.query, args.limit, args.out, args.pmcid)

    total = sum(r["bytes"] for r in manifest["articles"])
    print(f"\nwrote {manifest['written']} articles ({total / 1024:.0f} KB) to {args.out}")
    if manifest["skipped_no_body"]:
        print(f"skipped {len(manifest['skipped_no_body'])} abstract-only record(s)")
    licences = sorted({r["licence"] for r in manifest["articles"]})
    print(f"licences present: {', '.join(licences) or 'none recorded'}")
    print(f"manifest: {args.out / MANIFEST_NAME}")


if __name__ == "__main__":
    main()
