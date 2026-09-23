"""
jats_parser.py
Parses JATS XML articles (PubMed Central) into structured chunks with metadata.

This is an **additional** parser alongside ``parser.py``, not a replacement. The
thesis is the same one the DITA parser tests: an authored section boundary is a
better chunk boundary than a character budget. JATS is the harder case, and the
interesting one, because a real research article carries structure DITA did not:

* ``<sec>`` **nests** — ``Materials and Methods`` routinely has sub-sections.
  A leaf section becomes a chunk, and the ancestor titles survive as
  ``section_path``. A branch section's own prose (the text before its first
  sub-section) becomes a chunk too, so no authored text is silently dropped.
* ``<abstract>`` sits **outside** ``<body>`` and is usually the highest-value
  text in the article, so it is emitted as a chunk in its own right.
* Sections are **not guaranteed an ``@id``**, so chunk ids are generated
  defensively from position.
* JATS uses characters such as U+2010 NON-BREAKING HYPHEN, so all file I/O is
  explicit UTF-8.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from app.parser import extract_text, generate_tags

logger = logging.getLogger(__name__)

# Non-prose containers. Their text is real, but it is tabular or caption
# material that would dominate a chunk without answering a question about the
# article's argument. Excluded deliberately, and listed here so the choice is
# reviewable rather than buried in a condition.
NON_PROSE_TAGS = frozenset(
    {"table-wrap", "fig", "graphic", "media", "supplementary-material", "table-wrap-group"}
)

# An article abstract is the JATS analogue of DITA's <shortdesc>, but it can run
# to several thousand characters. Metadata travels with every chunk into the
# vector store, so it is truncated at a word boundary for that use only. The
# untruncated abstract is still emitted as its own chunk.
SHORTDESC_MAX_CHARS = 300

PATH_SEPARATOR = " > "


def local_name(tag: str) -> str:
    """Tag name without its XML namespace.

    PMC usually serves JATS without a default namespace, but ``mml:`` and
    ``xlink:`` do appear, and some mirrors namespace the whole document. Matching
    on the local name costs nothing and removes a whole class of silent failure.
    """
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def find_article(root: ET.Element) -> ET.Element | None:
    """Locate the ``<article>`` element.

    E-utilities ``efetch`` wraps results in ``<pmc-articleset>``, so the article
    is a child, not the root. A file saved from a single article has ``<article>``
    at the root. Both are accepted.
    """
    if local_name(root.tag) == "article":
        return root
    for element in root.iter():
        if local_name(element.tag) == "article":
            return element
    return None


def _child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if local_name(child.tag) == name:
            return child
    return None


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in element if local_name(c.tag) == name]


def _descend(element: ET.Element | None, *names: str) -> ET.Element | None:
    """Follow a chain of direct children by local name."""
    current = element
    for name in names:
        if current is None:
            return None
        current = _child(current, name)
    return current


def _prose_text(element: ET.Element, *, skip_sections: bool) -> str:
    """Text of an element, minus its title, sub-sections and non-prose blocks.

    ``skip_sections`` distinguishes the two cases: a leaf section contributes all
    of its prose, while a branch section contributes only the prose it owns
    directly — its sub-sections become chunks of their own.
    """
    parts: list[str] = []
    if element.text and element.text.strip():
        parts.append(element.text.strip())
    for child in element:
        name = local_name(child.tag)
        skip = name in NON_PROSE_TAGS or name == "title" or (skip_sections and name == "sec")
        if not skip:
            text = extract_text(child)
            if text:
                parts.append(text)
        if child.tail and child.tail.strip():
            parts.append(child.tail.strip())
    return " ".join(parts)


def _truncate_words(text: str, limit: int) -> str:
    """Trim to ``limit`` characters without cutting a word in half."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    cut = collapsed[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{cut}…"


def article_id(article: ET.Element) -> str:
    """The article's PMC identifier, falling back through the other id types."""
    meta = _descend(article, "front", "article-meta")
    if meta is None:
        return "unknown"
    ids = {
        (element.get("pub-id-type") or "unknown"): (element.text or "").strip()
        for element in _children(meta, "article-id")
    }
    for id_type in ("pmc", "pmid", "doi", "publisher-id"):
        if ids.get(id_type):
            return ids[id_type]
    return next((value for value in ids.values() if value), "unknown")


def article_title(article: ET.Element) -> str:
    title = _descend(article, "front", "article-meta", "title-group", "article-title")
    text = extract_text(title) if title is not None else ""
    return text or "Untitled"


def article_licence(article: ET.Element) -> str:
    """Licence as stated by the article, for provenance recording.

    PMC Open Access licences vary per article, so this is read from the document
    rather than assumed. ``unknown`` is reported honestly when absent.
    """
    permissions = _descend(article, "front", "article-meta", "permissions")
    if permissions is None:
        return "unknown"
    licence = _child(permissions, "license")
    if licence is None:
        return "unknown"

    declared = licence.get("license-type")
    if declared:
        return declared

    # NCBI serves the machine-readable licence as <ali:license_ref>, which
    # carries the URL as element *text*, not as an attribute. Checking that
    # before the prose fallback is the difference between "CC-BY 4.0" and 120
    # characters of boilerplate.
    for child in licence:
        if local_name(child.tag) == "license_ref":
            url = (child.text or "").strip() or _href(child)
            if url:
                return url

    for element in (licence, *licence.iter()):
        href = _href(element)
        if href:
            return href

    text = extract_text(licence)
    return _truncate_words(text, 120) if text else "unknown"


def _href(element: ET.Element) -> str:
    """An element's link target, namespaced or not."""
    return element.get("{http://www.w3.org/1999/xlink}href") or element.get("href") or ""


def abstract_text(article: ET.Element) -> str:
    """The article abstract, flattened. Sits outside ``<body>`` in JATS."""
    meta = _descend(article, "front", "article-meta")
    if meta is None:
        return ""
    for abstract in _children(meta, "abstract"):
        # Skip translated or graphical abstracts; the unqualified one is the
        # article's own.
        if abstract.get("abstract-type") in (None, "", "summary"):
            return _prose_text(abstract, skip_sections=False)
    return ""


def _walk_sections(
    parent: ET.Element,
    ancestors: tuple[str, ...],
    counter: list[int],
) -> list[tuple[str, str, tuple[str, ...], str]]:
    """Depth-first walk yielding ``(section_id, title, path, text)`` per chunk.

    ``counter`` is a single-element list used as a mutable ordinal so that a
    section with no ``@id`` still gets a stable, document-unique identifier.
    """
    emitted: list[tuple[str, str, tuple[str, ...], str]] = []

    for section in _children(parent, "sec"):
        counter[0] += 1
        ordinal = counter[0]
        section_id = section.get("id") or f"sec{ordinal}"
        title_element = _child(section, "title")
        title = extract_text(title_element) if title_element is not None else ""
        title = title or "Untitled Section"
        path = (*ancestors, title)

        subsections = _children(section, "sec")
        text = _prose_text(section, skip_sections=bool(subsections))
        if text:
            emitted.append((section_id, title, path, text))

        if subsections:
            emitted.extend(_walk_sections(section, path, counter))

    return emitted


def parse_jats_file(filepath: str) -> list[dict]:
    """Parse a JATS article and return a list of chunks.

    One authored section becomes one chunk, plus one chunk for the abstract.
    The chunk shape matches the DITA parser's exactly, so the indexer, retriever
    and evaluation harness cannot tell which parser produced a chunk.
    """
    root = ET.parse(filepath).getroot()
    article = find_article(root)
    if article is None:
        logger.warning("No <article> element found in %s", Path(filepath).name)
        return []

    filename = Path(filepath).stem
    topic_id = article_id(article)
    topic_title = article_title(article)
    abstract = abstract_text(article)
    shortdesc = _truncate_words(abstract, SHORTDESC_MAX_CHARS) if abstract else ""

    entries: list[tuple[str, str, tuple[str, ...], str]] = []
    if abstract:
        entries.append(("abstract", "Abstract", ("Abstract",), abstract))

    body = _child(article, "body")
    if body is not None:
        entries.extend(_walk_sections(body, (), [0]))

    chunks: list[dict] = []
    seen: dict[str, int] = {}
    for section_id, section_title, path, text in entries:
        chunk_id = f"{filename}_{section_id}"
        # JATS @id values are only conventionally unique. Suffix a repeat rather
        # than let one chunk overwrite another in the vector store.
        if chunk_id in seen:
            seen[chunk_id] += 1
            chunk_id = f"{chunk_id}_{seen[chunk_id]}"
        else:
            seen[chunk_id] = 0

        chunks.append(
            {
                "chunk_id": chunk_id,
                "topic_id": topic_id,
                "topic_title": topic_title,
                "topic_shortdesc": shortdesc,
                "section_id": section_id,
                "section_title": section_title,
                "text": " ".join(text.split()),
                "source_file": filename,
                "tags": generate_tags(topic_title, section_title),
                # JATS-only enrichment. The DITA corpus is flat, so these carry
                # no information there and are not added to its chunks.
                "section_path": PATH_SEPARATOR.join(path),
                "section_depth": len(path),
            }
        )

    return chunks


def parse_all_jats_files(data_dir: str) -> list[dict]:
    """Parse every JATS file in a directory. ``.xml`` and PMC's ``.nxml``."""
    data_path = Path(data_dir)
    files = sorted(
        {p for pattern in ("*.xml", "*.nxml") for p in data_path.glob(pattern)},
        key=lambda p: p.name,
    )
    all_chunks: list[dict] = []
    for jats_file in files:
        try:
            chunks = parse_jats_file(str(jats_file))
        except ET.ParseError:
            logger.warning("Skipping malformed JATS file: %s", jats_file.name, exc_info=True)
            continue
        all_chunks.extend(chunks)
        logger.info("Parsed %s: %d chunks", jats_file.name, len(chunks))
    return all_chunks
