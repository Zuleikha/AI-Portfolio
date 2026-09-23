"""
dispatch.py
Selects a parser by the document's root element.

The service now understands two XML vocabularies — DITA technical documentation
and JATS research articles. They share one chunk shape, so everything downstream
(indexer, retriever, API, evaluation harness) is unchanged and unaware.

The root element is the natural discriminator: it is the one thing every
well-formed document declares before any content, and it is what the vocabulary
is actually identified by.

    <topic>            -> DITA        (app.parser)
    <article>          -> JATS        (app.jats_parser)
    <pmc-articleset>   -> JATS        (efetch envelope around one or more articles)

An unrecognised root is reported, not guessed at. Silently picking a parser for a
vocabulary the service does not understand would produce chunks that look valid
and are not.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from app.jats_parser import local_name, parse_all_jats_files, parse_jats_file
from app.parser import parse_all_dita_files, parse_dita_file

logger = logging.getLogger(__name__)

DITA_ROOTS = frozenset({"topic", "concept", "task", "reference"})
JATS_ROOTS = frozenset({"article", "pmc-articleset", "article-set"})

# Extensions each vocabulary is conventionally served with. Used only to choose
# which directory-level sweep to run; individual files are still dispatched on
# their root element.
DITA_SUFFIXES = frozenset({".dita", ".ditamap", ".xml"})
JATS_SUFFIXES = frozenset({".xml", ".nxml"})


class UnknownVocabularyError(ValueError):
    """Raised when a document's root element matches no registered parser."""


def read_root_tag(filepath: str) -> str:
    """Local name of the document's root element, without parsing the whole file.

    ``iterparse`` yields the root's ``start`` event before the body is read, so
    this stays cheap on a 100 KB article. The file is opened in binary mode and
    the XML declaration decides the encoding, which is what keeps JATS's
    non-ASCII punctuation intact on a Windows console default of cp1252.
    """
    with open(filepath, "rb") as handle:
        for _event, element in ET.iterparse(handle, events=("start",)):
            return local_name(element.tag)
    raise ET.ParseError(f"no root element in {filepath}")


def parse_file(filepath: str) -> list[dict]:
    """Parse one XML file with whichever parser its root element calls for."""
    root_tag = read_root_tag(filepath)
    if root_tag in DITA_ROOTS:
        return parse_dita_file(filepath)
    if root_tag in JATS_ROOTS:
        return parse_jats_file(filepath)
    raise UnknownVocabularyError(
        f"{Path(filepath).name}: root element <{root_tag}> matches no parser "
        f"(DITA: {sorted(DITA_ROOTS)}; JATS: {sorted(JATS_ROOTS)})"
    )


def detect_vocabulary(data_dir: str) -> str | None:
    """Which vocabulary a directory holds: ``"dita"``, ``"jats"`` or ``None``.

    Every document is sniffed, not just the first: a directory holding both
    vocabularies must report ``None`` so ``parse_all_files`` falls back to
    per-file dispatch rather than parsing one half and dropping the other.
    """
    found: set[str] = set()
    for path in sorted(Path(data_dir).iterdir() if Path(data_dir).is_dir() else []):
        if not path.is_file() or path.suffix.lower() not in (DITA_SUFFIXES | JATS_SUFFIXES):
            continue
        try:
            root_tag = read_root_tag(str(path))
        except (ET.ParseError, OSError):
            continue
        if root_tag in DITA_ROOTS:
            found.add("dita")
        elif root_tag in JATS_ROOTS:
            found.add("jats")
    return found.pop() if len(found) == 1 else None


def parse_all_files(data_dir: str) -> list[dict]:
    """Parse every recognised document in a directory.

    A single-vocabulary directory delegates to that parser's own sweep, which
    keeps the existing DITA behaviour — including its malformed-file handling —
    exactly as it was. A mixed directory falls back to dispatching file by file.
    """
    vocabulary = detect_vocabulary(data_dir)
    if vocabulary == "dita":
        return parse_all_dita_files(data_dir)
    if vocabulary == "jats":
        return parse_all_jats_files(data_dir)

    chunks: list[dict] = []
    for path in sorted(Path(data_dir).glob("*")):
        if not path.is_file():
            continue
        try:
            chunks.extend(parse_file(str(path)))
        except (ET.ParseError, UnknownVocabularyError, OSError):
            logger.warning("Skipping unparseable file: %s", path.name, exc_info=True)
    return chunks
