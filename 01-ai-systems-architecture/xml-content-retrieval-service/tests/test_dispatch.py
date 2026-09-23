"""
Unit tests for app/dispatch.py — parser selection by root element.

The contract under test is that adding JATS took nothing away: a DITA file must
still route to the DITA parser and produce exactly what it always produced.
"""

import pytest

from app.dispatch import (
    UnknownVocabularyError,
    detect_vocabulary,
    parse_all_files,
    parse_file,
    read_root_tag,
)
from app.parser import parse_all_dita_files, parse_dita_file
from tests.test_jats_parser import write_article

DITA = (
    '<?xml version="1.0"?><topic id="t1"><title>Topic</title><shortdesc>Short.</shortdesc>'
    '<body><section id="s1"><title>Section</title><p>Content.</p></section></body></topic>'
)


def write_dita(path):
    path.write_text(DITA, encoding="utf-8")
    return path


class TestReadRootTag:
    def test_dita_root(self, tmp_path):
        assert read_root_tag(str(write_dita(tmp_path / "a.dita"))) == "topic"

    def test_jats_root(self, tmp_path):
        assert read_root_tag(str(write_article(tmp_path / "a.xml"))) == "article"

    def test_efetch_envelope_root(self, tmp_path):
        assert read_root_tag(str(write_article(tmp_path / "b.xml", wrap=True))) == "pmc-articleset"

    def test_namespaced_root_stripped(self, tmp_path):
        f = tmp_path / "ns.xml"
        f.write_text(
            '<article xmlns="http://jats.nlm.nih.gov"><front/></article>', encoding="utf-8"
        )
        assert read_root_tag(str(f)) == "article"


class TestParseFile:
    def test_dita_routes_to_dita_parser(self, tmp_path):
        f = write_dita(tmp_path / "a.dita")
        assert parse_file(str(f)) == parse_dita_file(str(f))

    def test_jats_routes_to_jats_parser(self, tmp_path):
        chunks = parse_file(str(write_article(tmp_path / "a.xml")))
        assert chunks and all("section_path" in c for c in chunks)

    def test_dita_chunks_have_no_jats_only_fields(self, tmp_path):
        chunk = parse_file(str(write_dita(tmp_path / "a.dita")))[0]
        assert "section_path" not in chunk

    def test_both_vocabularies_share_the_chunk_shape(self, tmp_path):
        dita = parse_file(str(write_dita(tmp_path / "a.dita")))[0]
        jats = parse_file(str(write_article(tmp_path / "b.xml")))[0]
        assert set(dita) <= set(jats)

    def test_unknown_root_raises_rather_than_guessing(self, tmp_path):
        f = tmp_path / "x.xml"
        f.write_text("<catalogue><item>Widget</item></catalogue>", encoding="utf-8")
        with pytest.raises(UnknownVocabularyError, match="catalogue"):
            parse_file(str(f))

    @pytest.mark.parametrize("root", ["concept", "task", "reference"])
    def test_other_dita_topic_types_accepted(self, tmp_path, root):
        f = tmp_path / f"{root}.dita"
        f.write_text(DITA.replace("topic", root), encoding="utf-8")
        assert parse_file(str(f))


class TestDetectVocabulary:
    def test_dita_directory(self, tmp_path):
        write_dita(tmp_path / "a.dita")
        assert detect_vocabulary(str(tmp_path)) == "dita"

    def test_jats_directory(self, tmp_path):
        write_article(tmp_path / "a.xml")
        assert detect_vocabulary(str(tmp_path)) == "jats"

    def test_mixed_directory_reports_none(self, tmp_path):
        write_dita(tmp_path / "a.dita")
        write_article(tmp_path / "b.xml")
        assert detect_vocabulary(str(tmp_path)) is None

    def test_empty_directory_reports_none(self, tmp_path):
        assert detect_vocabulary(str(tmp_path)) is None

    def test_missing_directory_reports_none(self, tmp_path):
        assert detect_vocabulary(str(tmp_path / "nope")) is None


class TestParseAllFiles:
    def test_dita_sweep_is_unchanged(self, tmp_path):
        write_dita(tmp_path / "a.dita")
        write_dita(tmp_path / "b.dita")
        assert parse_all_files(str(tmp_path)) == parse_all_dita_files(str(tmp_path))

    def test_jats_sweep(self, tmp_path):
        write_article(tmp_path / "a.xml")
        write_article(tmp_path / "b.xml")
        assert len(parse_all_files(str(tmp_path))) == 4

    def test_mixed_directory_parses_both(self, tmp_path):
        write_dita(tmp_path / "a.dita")
        write_article(tmp_path / "b.xml", abstract="")
        sources = {c["source_file"] for c in parse_all_files(str(tmp_path))}
        assert sources == {"a", "b"}

    def test_unrecognised_file_skipped_not_fatal(self, tmp_path):
        write_dita(tmp_path / "a.dita")
        (tmp_path / "notes.txt").write_text("not xml at all", encoding="utf-8")
        (tmp_path / "other.xml").write_text("<catalogue/>", encoding="utf-8")
        assert len(parse_all_files(str(tmp_path))) == 1

    def test_real_dita_corpus_still_parses(self):
        from pathlib import Path

        data_dir = Path(__file__).resolve().parents[1] / "data"
        assert parse_all_files(str(data_dir)) == parse_all_dita_files(str(data_dir))
