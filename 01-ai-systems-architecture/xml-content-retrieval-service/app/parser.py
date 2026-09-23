"""
parser.py
Parses DITA XML files into structured chunks with metadata.
Each section within a topic becomes one chunk.
"""

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_text(element) -> str:
    """Recursively extract all text content from an XML element."""
    parts = []
    if element.text:
        parts.append(element.text.strip())
    for child in element:
        parts.append(extract_text(child))
        if child.tail:
            parts.append(child.tail.strip())
    return " ".join(p for p in parts if p)


def parse_dita_file(filepath: str) -> list[dict]:
    """
    Parse a DITA file and return a list of chunks.
    Each chunk is one section with metadata.
    """
    tree = ET.parse(filepath)
    root = tree.getroot()

    topic_id = root.get("id", "unknown")
    topic_title = root.findtext("title", default="Untitled")
    topic_shortdesc = root.findtext("shortdesc", default="")

    filename = Path(filepath).stem
    chunks = []

    body = root.find("body")
    if body is None:
        return chunks

    for section in body.findall("section"):
        section_id = section.get("id", "unknown")
        section_title = section.findtext("title", default="Untitled Section")
        section_text = extract_text(section)

        # Remove the leading title text from the body to avoid duplication —
        # only when the text starts with it, so mid-sentence matches survive
        if section_text.startswith(section_title):
            section_text = section_text[len(section_title) :].strip()

        chunks.append(
            {
                "chunk_id": f"{filename}_{section_id}",
                "topic_id": topic_id,
                "topic_title": topic_title,
                "topic_shortdesc": topic_shortdesc,
                "section_id": section_id,
                "section_title": section_title,
                "text": section_text,
                "source_file": filename,
                "tags": generate_tags(topic_title, section_title),
            }
        )

    return chunks


def generate_tags(topic_title: str, section_title: str) -> str:
    """Generate simple keyword tags from titles for metadata enrichment."""
    combined = f"{topic_title} {section_title}".lower()
    keywords = []
    tag_map = {
        "install": "installation",
        "config": "configuration",
        "troubleshoot": "troubleshooting",
        "license": "licensing",
        "performance": "performance",
        "workspace": "workspace",
        "unit": "units",
        "crash": "crashes",
        "error": "errors",
        "download": "download",
        "system": "system-requirements",
        "user": "user-preferences",
    }
    for keyword, tag in tag_map.items():
        if keyword in combined:
            keywords.append(tag)
    return ", ".join(keywords) if keywords else "general"


def parse_all_dita_files(data_dir: str) -> list[dict]:
    """Parse all .dita files in a directory."""
    data_path = Path(data_dir)
    all_chunks = []
    for dita_file in sorted(data_path.glob("*.dita")):
        try:
            chunks = parse_dita_file(str(dita_file))
        except ET.ParseError:
            logger.warning("Skipping malformed DITA file: %s", dita_file.name, exc_info=True)
            continue
        all_chunks.extend(chunks)
        logger.info("Parsed %s: %d chunks", dita_file.name, len(chunks))
    return all_chunks
