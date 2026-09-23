"""
Unit tests for app/parser.py — DITA parsing, chunking, and tag generation.
Runs fully offline against the real sample files in data/.
"""

from pathlib import Path

from app.parser import extract_text, generate_tags, parse_all_dita_files, parse_dita_file

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

REQUIRED_CHUNK_KEYS = {
    "chunk_id",
    "topic_id",
    "topic_title",
    "topic_shortdesc",
    "section_id",
    "section_title",
    "text",
    "source_file",
    "tags",
}


def write_dita(path, topic_id="t1", title="Topic", sections=1):
    body = "".join(
        f'<section id="s{i}"><title>Section {i}</title><p>Content {i}.</p></section>'
        for i in range(sections)
    )
    path.write_text(
        f'<?xml version="1.0"?><topic id="{topic_id}">'
        f"<title>{title}</title><shortdesc>Short.</shortdesc>"
        f"<body>{body}</body></topic>"
    )


class TestParseDitaFile:
    def test_parses_all_sample_files(self):
        for f in DATA_DIR.glob("*.dita"):
            chunks = parse_dita_file(str(f))
            assert chunks, f"No chunks parsed from {f.name}"

    def test_chunk_schema_complete(self):
        chunks = parse_dita_file(str(DATA_DIR / "installation.dita"))
        for chunk in chunks:
            assert chunk.keys() >= REQUIRED_CHUNK_KEYS

    def test_chunk_text_not_empty(self):
        chunks = parse_dita_file(str(DATA_DIR / "installation.dita"))
        assert all(c["text"] for c in chunks)

    def test_chunk_ids_unique_within_file(self):
        chunks = parse_dita_file(str(DATA_DIR / "troubleshooting.dita"))
        ids = [c["chunk_id"] for c in chunks]
        assert len(ids) == len(set(ids))

    def test_one_chunk_per_section(self, tmp_path):
        f = tmp_path / "multi.dita"
        write_dita(f, sections=3)
        assert len(parse_dita_file(str(f))) == 3

    def test_no_body_returns_empty(self, tmp_path):
        f = tmp_path / "nobody.dita"
        f.write_text('<topic id="t"><title>T</title></topic>')
        assert parse_dita_file(str(f)) == []

    def test_section_title_stripped_from_text_start(self, tmp_path):
        f = tmp_path / "t.dita"
        write_dita(f, sections=1)
        chunk = parse_dita_file(str(f))[0]
        assert not chunk["text"].startswith("Section 0")

    def test_title_inside_body_text_survives(self, tmp_path):
        f = tmp_path / "t.dita"
        f.write_text(
            '<topic id="t"><title>T</title><body>'
            '<section id="s"><title>Units</title>'
            "<p>Change the Units setting in preferences.</p></section>"
            "</body></topic>"
        )
        chunk = parse_dita_file(str(f))[0]
        assert "Units setting" in chunk["text"]


class TestParseAllDitaFiles:
    def test_parses_sample_directory(self):
        chunks = parse_all_dita_files(str(DATA_DIR))
        assert len(chunks) >= 3

    def test_malformed_file_is_skipped_not_fatal(self, tmp_path):
        write_dita(tmp_path / "good.dita")
        (tmp_path / "bad.dita").write_text("<topic><unclosed>")
        chunks = parse_all_dita_files(str(tmp_path))
        assert len(chunks) == 1

    def test_empty_directory_returns_empty_list(self, tmp_path):
        assert parse_all_dita_files(str(tmp_path)) == []


class TestGenerateTags:
    def test_known_keyword_maps_to_tag(self):
        assert "installation" in generate_tags("Installing the product", "Steps")

    def test_multiple_keywords_combined(self):
        tags = generate_tags("Troubleshooting", "License errors")
        assert "troubleshooting" in tags and "licensing" in tags and "errors" in tags

    def test_no_match_returns_general(self):
        assert generate_tags("Foo", "Bar") == "general"

    def test_case_insensitive(self):
        assert "configuration" in generate_tags("CONFIG", "")


class TestExtractText:
    def test_nested_elements_flattened(self, tmp_path):
        import xml.etree.ElementTree as ET

        el = ET.fromstring("<p>Run <b>setup.exe</b> now.</p>")
        assert extract_text(el) == "Run setup.exe now."
