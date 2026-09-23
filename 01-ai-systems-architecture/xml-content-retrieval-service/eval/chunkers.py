"""
Chunking strategies under comparison.

Two families:

* **structure-aware** — the production parser. One authored section becomes one
  chunk, and the document hierarchy survives as metadata.
* **naive** — a fixed-size character window over the same document text, with
  optional overlap. This is what a text splitter does when it is handed markup it
  does not understand: it throws the structure away and re-derives boundaries
  from a budget.

Both produce the same chunk shape, so the retrieval and scoring code cannot tell
which strategy it is serving.

The comparison runs over **either** corpus — DITA technical documentation or JATS
research articles — because the chunking question is the same one in both, and a
result that only holds on a 3.7 KB toy corpus is not a result. Which vocabulary a
directory holds is decided by ``app.dispatch``, not by this module.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from app.dispatch import DITA_ROOTS, JATS_ROOTS, detect_vocabulary, parse_all_files, read_root_tag
from app.jats_parser import (
    NON_PROSE_TAGS,
    abstract_text,
    article_id,
    article_title,
    find_article,
    local_name,
)
from app.parser import extract_text

# Window widths swept for the naive family. The DITA corpus is small enough that
# 600 characters is half a document; a research article needs the sweep to run
# out to sizes that are genuinely a fraction of the text, or the "baseline"
# quietly becomes "retrieve the whole document".
DITA_WINDOW_SIZES = (150, 300, 600)
JATS_WINDOW_SIZES = (300, 600, 1200, 2400)
OVERLAPS = (0, 50)

CORPUS_SUFFIXES = {"dita": ("*.dita",), "jats": ("*.xml", "*.nxml")}


def structure_aware_chunks(data_dir: str) -> list[dict]:
    """The production strategy: one authored section per chunk."""
    return parse_all_files(data_dir)


def _dita_document_text(root: ET.Element, filepath: str) -> tuple[str, dict]:
    topic_title = root.findtext("title", default="Untitled")
    topic_shortdesc = root.findtext("shortdesc", default="")
    body = root.find("body")
    body_text = extract_text(body) if body is not None else ""
    full = " ".join(p for p in (topic_title, topic_shortdesc, body_text) if p)
    meta = {
        "topic_id": root.get("id", "unknown"),
        "topic_title": topic_title,
        "topic_shortdesc": topic_shortdesc,
        "source_file": Path(filepath).stem,
    }
    return full, meta


def _jats_section_text(element: ET.Element) -> list[str]:
    """Flatten a JATS ``<sec>`` tree in reading order, titles included.

    Titles are kept deliberately. The structure-aware strategy lifts a section
    title out of the body text and into metadata; leaving the titles in the
    flattened stream means the naive strategy loses no *words*, only the
    boundaries. That is the only difference the comparison is entitled to
    measure.
    """
    parts: list[str] = []
    for child in element:
        name = local_name(child.tag)
        if name in NON_PROSE_TAGS:
            continue
        if name == "sec":
            parts.extend(_jats_section_text(child))
            continue
        text = extract_text(child)
        if text:
            parts.append(text)
    return parts


def _jats_document_text(root: ET.Element, filepath: str) -> tuple[str, dict]:
    article = find_article(root)
    if article is None:
        return "", {}
    title = article_title(article)
    abstract = abstract_text(article)
    body = next((e for e in article if local_name(e.tag) == "body"), None)
    body_parts = _jats_section_text(body) if body is not None else []
    full = " ".join(p for p in (title, abstract, *body_parts) if p)
    meta = {
        "topic_id": article_id(article),
        "topic_title": title,
        "topic_shortdesc": "",
        "source_file": Path(filepath).stem,
    }
    return " ".join(full.split()), meta


def document_text(filepath: str) -> tuple[str, dict]:
    """Flatten one document to plain text, as a structure-blind splitter sees it.

    Returns the text plus the document-level metadata that *any* strategy could
    know without understanding the markup (the file it came from).
    """
    root_tag = read_root_tag(filepath)
    root = ET.parse(filepath).getroot()
    if root_tag in DITA_ROOTS:
        return _dita_document_text(root, filepath)
    if root_tag in JATS_ROOTS:
        return _jats_document_text(root, filepath)
    return "", {}


def _corpus_files(data_dir: str) -> list[Path]:
    vocabulary = detect_vocabulary(data_dir) or "dita"
    path = Path(data_dir)
    files = {p for pattern in CORPUS_SUFFIXES[vocabulary] for p in path.glob(pattern)}
    return sorted(files, key=lambda p: p.name)


def naive_chunks(data_dir: str, size: int, overlap: int = 0) -> list[dict]:
    """Fixed-size character windows over the flattened document text.

    ``size`` is the window width in characters and ``overlap`` how much each
    window repeats of the previous one. Section titles are *not* treated as
    boundaries — that is the whole point of the comparison.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0:
        raise ValueError("overlap must not be negative")
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")

    stride = size - overlap
    chunks: list[dict] = []

    for source in _corpus_files(data_dir):
        try:
            text, meta = document_text(str(source))
        except ET.ParseError:
            continue
        if not text:
            continue
        for i, start in enumerate(range(0, len(text), stride)):
            window = text[start : start + size].strip()
            if not window:
                continue
            chunks.append(
                {
                    "chunk_id": f"{meta['source_file']}_w{i}",
                    "topic_id": meta["topic_id"],
                    "topic_title": meta["topic_title"],
                    "topic_shortdesc": meta["topic_shortdesc"],
                    # A naive splitter has no section to name. Saying "unknown"
                    # rather than inventing one keeps the comparison honest.
                    "section_id": "unknown",
                    "section_title": "unknown",
                    "text": window,
                    "source_file": meta["source_file"],
                    "tags": "general",
                }
            )
            if start + size >= len(text):
                break

    return chunks


def window_sizes(data_dir: str) -> tuple[int, ...]:
    """Window widths to sweep, scaled to the corpus the run is against."""
    return JATS_WINDOW_SIZES if detect_vocabulary(data_dir) == "jats" else DITA_WINDOW_SIZES


def strategies(data_dir: str) -> dict[str, list[dict]]:
    """Every strategy in the comparison, built from the same corpus.

    The naive family is swept across several window sizes deliberately: comparing
    against a single badly-chosen baseline would prove nothing. The report quotes
    the *best* naive configuration, not the most convenient one.
    """
    out: dict[str, list[dict]] = {"structure-aware": structure_aware_chunks(data_dir)}
    for size in window_sizes(data_dir):
        for overlap in OVERLAPS:
            out[f"naive-{size}c-o{overlap}"] = naive_chunks(data_dir, size, overlap)
    return out
