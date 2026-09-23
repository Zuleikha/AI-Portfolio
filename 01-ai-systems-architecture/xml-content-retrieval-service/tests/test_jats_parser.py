"""
Unit tests for app/jats_parser.py — JATS parsing, section nesting, and metadata.

Runs fully offline against synthetic fixtures. No network call is made: the PMC
corpus is fetched by scripts/fetch_pmc.py and is deliberately gitignored, so the
suite must not depend on it being present.

These mirror tests/test_parser.py case for case wherever the two vocabularies
share behaviour, and add cases for what JATS brings that DITA did not — nesting,
missing @id, an abstract outside <body>, and the efetch envelope.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from app.jats_parser import (
    NON_PROSE_TAGS,
    SHORTDESC_MAX_CHARS,
    abstract_text,
    article_id,
    article_licence,
    article_title,
    find_article,
    local_name,
    parse_all_jats_files,
    parse_jats_file,
)

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
    "section_path",
    "section_depth",
}


def article_xml(
    *,
    pmc_id="PMC123456",
    title="A Study of Something",
    abstract="<abstract><p>We measured the thing.</p></abstract>",
    body="<body><sec id='s1'><title>Introduction</title><p>Background text.</p></sec></body>",
    permissions="",
    wrap=False,
) -> str:
    ids = f'<article-id pub-id-type="pmc">{pmc_id}</article-id>' if pmc_id else ""
    doc = (
        "<article>"
        "<front><article-meta>"
        f"{ids}"
        f"<title-group><article-title>{title}</article-title></title-group>"
        f"{permissions}{abstract}"
        "</article-meta></front>"
        f"{body}"
        "</article>"
    ).replace("'", '"')
    if wrap:
        doc = f"<pmc-articleset>{doc}</pmc-articleset>"
    return f'<?xml version="1.0" encoding="UTF-8"?>{doc}'


def write_article(path: Path, **kwargs) -> Path:
    # Explicit UTF-8: JATS carries U+2010 and friends, and the Windows default
    # (cp1252) cannot represent them.
    path.write_text(article_xml(**kwargs), encoding="utf-8")
    return path


@pytest.fixture
def simple(tmp_path):
    return write_article(tmp_path / "PMC123456.xml")


class TestFindArticle:
    def test_article_at_root(self):
        root = ET.fromstring(article_xml())
        assert find_article(root) is not None

    def test_article_inside_efetch_envelope(self):
        root = ET.fromstring(article_xml(wrap=True))
        assert local_name(root.tag) == "pmc-articleset"
        assert find_article(root) is not None

    def test_no_article_returns_none(self):
        assert find_article(ET.fromstring("<pmc-articleset/>")) is None

    def test_namespaced_root_is_matched_on_local_name(self):
        root = ET.fromstring('<article xmlns="http://jats.nlm.nih.gov"><front/></article>')
        assert find_article(root) is not None


class TestParseJatsFile:
    def test_chunk_schema_complete(self, simple):
        for chunk in parse_jats_file(str(simple)):
            assert chunk.keys() >= REQUIRED_CHUNK_KEYS

    def test_chunk_text_not_empty(self, simple):
        assert all(c["text"] for c in parse_jats_file(str(simple)))

    def test_abstract_becomes_its_own_chunk(self, simple):
        chunks = parse_jats_file(str(simple))
        abstract = [c for c in chunks if c["section_id"] == "abstract"]
        assert len(abstract) == 1
        assert "We measured the thing." in abstract[0]["text"]

    def test_efetch_envelope_parses_identically(self, tmp_path):
        flat = parse_jats_file(str(write_article(tmp_path / "a.xml")))
        wrapped = parse_jats_file(str(write_article(tmp_path / "b.xml", wrap=True)))
        assert [c["text"] for c in flat] == [c["text"] for c in wrapped]

    def test_one_chunk_per_section(self, tmp_path):
        body = (
            "<body>"
            + "".join(
                f'<sec id="s{i}"><title>Section {i}</title><p>Content {i}.</p></sec>'
                for i in range(3)
            )
            + "</body>"
        )
        f = write_article(tmp_path / "multi.xml", body=body, abstract="")
        assert len(parse_jats_file(str(f))) == 3

    def test_no_body_still_yields_abstract(self, tmp_path):
        f = write_article(tmp_path / "abs.xml", body="")
        chunks = parse_jats_file(str(f))
        assert len(chunks) == 1 and chunks[0]["section_id"] == "abstract"

    def test_no_body_and_no_abstract_returns_empty(self, tmp_path):
        f = write_article(tmp_path / "empty.xml", body="", abstract="")
        assert parse_jats_file(str(f)) == []

    def test_non_article_document_returns_empty(self, tmp_path):
        f = tmp_path / "other.xml"
        f.write_text('<?xml version="1.0"?><pmc-articleset/>', encoding="utf-8")
        assert parse_jats_file(str(f)) == []

    def test_section_title_not_duplicated_into_text(self, tmp_path):
        chunk = parse_jats_file(str(write_article(tmp_path / "t.xml", abstract="")))[0]
        assert "Introduction" not in chunk["text"]
        assert chunk["section_title"] == "Introduction"

    def test_chunk_ids_unique_when_jats_ids_collide(self, tmp_path):
        body = (
            '<body><sec id="dup"><title>One</title><p>First.</p></sec>'
            '<sec id="dup"><title>Two</title><p>Second.</p></sec></body>'
        )
        chunks = parse_jats_file(str(write_article(tmp_path / "d.xml", body=body, abstract="")))
        ids = [c["chunk_id"] for c in chunks]
        assert len(ids) == len(set(ids)) == 2

    def test_utf8_punctuation_survives(self, tmp_path):
        # U+2010 NON-BREAKING HYPHEN is the character that broke the first
        # reconnaissance run on a cp1252 console.
        body = '<body><sec id="s"><title>T</title><p>dose‐response curve</p></sec></body>'
        chunk = parse_jats_file(str(write_article(tmp_path / "u.xml", body=body, abstract="")))[0]
        assert "dose‐response" in chunk["text"]


class TestNestedSections:
    NESTED = (
        "<body>"
        '<sec id="m"><title>Methods</title><p>Overview prose.</p>'
        '<sec id="m1"><title>Participants</title><p>We recruited 40 adults.</p></sec>'
        '<sec id="m2"><title>Analysis</title><p>We used a t-test.</p>'
        '<sec id="m2a"><title>Software</title><p>R 4.3 was used.</p></sec>'
        "</sec>"
        "</sec>"
        "</body>"
    )

    @pytest.fixture
    def chunks(self, tmp_path):
        return parse_jats_file(
            str(write_article(tmp_path / "n.xml", body=self.NESTED, abstract=""))
        )

    def test_leaf_sections_become_chunks(self, chunks):
        titles = {c["section_title"] for c in chunks}
        assert {"Participants", "Analysis", "Software"} <= titles

    def test_branch_prose_is_not_dropped(self, chunks):
        methods = next(c for c in chunks if c["section_title"] == "Methods")
        assert methods["text"] == "Overview prose."

    def test_branch_chunk_excludes_subsection_text(self, chunks):
        methods = next(c for c in chunks if c["section_title"] == "Methods")
        assert "recruited 40 adults" not in methods["text"]

    def test_ancestor_path_recorded(self, chunks):
        software = next(c for c in chunks if c["section_title"] == "Software")
        assert software["section_path"] == "Methods > Analysis > Software"

    def test_depth_matches_path(self, chunks):
        for chunk in chunks:
            assert chunk["section_depth"] == len(chunk["section_path"].split(" > "))

    def test_empty_branch_section_emits_no_chunk(self, tmp_path):
        body = (
            '<body><sec id="p"><title>Parent</title>'
            '<sec id="c"><title>Child</title><p>Only text.</p></sec></sec></body>'
        )
        chunks = parse_jats_file(str(write_article(tmp_path / "e.xml", body=body, abstract="")))
        assert [c["section_title"] for c in chunks] == ["Child"]


class TestDefensiveIds:
    def test_section_without_id_gets_generated_id(self, tmp_path):
        body = "<body><sec><title>Supporting information</title><p>See file S1.</p></sec></body>"
        chunk = parse_jats_file(str(write_article(tmp_path / "i.xml", body=body, abstract="")))[0]
        assert chunk["section_id"] == "sec1"
        assert chunk["chunk_id"] == "i_sec1"

    def test_generated_ids_are_unique_across_siblings(self, tmp_path):
        body = "<body>" + "<sec><title>T</title><p>Text.</p></sec>" * 3 + "</body>"
        chunks = parse_jats_file(str(write_article(tmp_path / "g.xml", body=body, abstract="")))
        assert len({c["section_id"] for c in chunks}) == 3

    def test_section_without_title_is_labelled_not_dropped(self, tmp_path):
        body = '<body><sec id="s"><p>Orphan text.</p></sec></body>'
        chunk = parse_jats_file(str(write_article(tmp_path / "nt.xml", body=body, abstract="")))[0]
        assert chunk["section_title"] == "Untitled Section"
        assert chunk["text"] == "Orphan text."


class TestNonProseExclusion:
    def test_table_and_figure_text_excluded(self, tmp_path):
        body = (
            '<body><sec id="r"><title>Results</title><p>Effect was large.</p>'
            "<table-wrap><label>Table 1</label><td>99.9</td></table-wrap>"
            "<fig><caption><p>Scatter plot.</p></caption></fig>"
            "</sec></body>"
        )
        chunk = parse_jats_file(str(write_article(tmp_path / "np.xml", body=body, abstract="")))[0]
        assert chunk["text"] == "Effect was large."

    def test_exclusion_list_is_explicit(self):
        assert "table-wrap" in NON_PROSE_TAGS and "fig" in NON_PROSE_TAGS


class TestArticleMetadata:
    def test_pmc_id_preferred_over_other_id_types(self, tmp_path):
        xml = article_xml().replace(
            '<article-id pub-id-type="pmc">PMC123456</article-id>',
            '<article-id pub-id-type="doi">10.1/x</article-id>'
            '<article-id pub-id-type="pmc">PMC123456</article-id>',
        )
        article = find_article(ET.fromstring(xml))
        assert article_id(article) == "PMC123456"

    def test_falls_back_when_no_pmc_id(self):
        xml = article_xml().replace(
            '<article-id pub-id-type="pmc">PMC123456</article-id>',
            '<article-id pub-id-type="doi">10.1/x</article-id>',
        )
        assert article_id(find_article(ET.fromstring(xml))) == "10.1/x"

    def test_missing_id_reported_as_unknown(self):
        assert article_id(find_article(ET.fromstring(article_xml(pmc_id="")))) == "unknown"

    def test_title_extracted(self):
        assert article_title(find_article(ET.fromstring(article_xml()))) == "A Study of Something"

    def test_abstract_outside_body_is_found(self):
        article = find_article(ET.fromstring(article_xml()))
        assert abstract_text(article) == "We measured the thing."

    def test_graphical_abstract_ignored(self):
        xml = article_xml(
            abstract='<abstract abstract-type="graphical"><p>Picture.</p></abstract>'
            "<abstract><p>Real abstract.</p></abstract>"
        )
        assert abstract_text(find_article(ET.fromstring(xml))) == "Real abstract."

    def test_shortdesc_truncated_at_word_boundary(self, tmp_path):
        long_abstract = "<abstract><p>" + ("word " * 200).strip() + "</p></abstract>"
        chunk = parse_jats_file(str(write_article(tmp_path / "long.xml", abstract=long_abstract)))[
            0
        ]
        assert len(chunk["topic_shortdesc"]) <= SHORTDESC_MAX_CHARS + 1
        assert chunk["topic_shortdesc"].endswith("…")

    def test_full_abstract_kept_in_chunk_text(self, tmp_path):
        long_abstract = "<abstract><p>" + ("word " * 200).strip() + "</p></abstract>"
        chunk = parse_jats_file(str(write_article(tmp_path / "long.xml", abstract=long_abstract)))[
            0
        ]
        assert len(chunk["text"]) > SHORTDESC_MAX_CHARS


class TestArticleLicence:
    def test_license_type_attribute_preferred(self):
        xml = article_xml(
            permissions='<permissions><license license-type="open-access"/></permissions>'
        )
        assert article_licence(find_article(ET.fromstring(xml))) == "open-access"

    def test_license_ref_url_read_from_element_text(self):
        xml = article_xml(
            permissions="<permissions><license>"
            '<license_ref content-type="ccbylicense">https://cc.org/by/4.0/</license_ref>'
            "<license-p>Boilerplate that should not be reported.</license-p>"
            "</license></permissions>"
        )
        assert article_licence(find_article(ET.fromstring(xml))) == "https://cc.org/by/4.0/"

    def test_missing_permissions_reported_as_unknown(self):
        assert article_licence(find_article(ET.fromstring(article_xml()))) == "unknown"


class TestParseAllJatsFiles:
    def test_parses_directory(self, tmp_path):
        write_article(tmp_path / "a.xml")
        write_article(tmp_path / "b.xml")
        assert len(parse_all_jats_files(str(tmp_path))) == 4

    def test_nxml_extension_included(self, tmp_path):
        write_article(tmp_path / "a.nxml")
        assert parse_all_jats_files(str(tmp_path))

    def test_malformed_file_is_skipped_not_fatal(self, tmp_path):
        write_article(tmp_path / "good.xml")
        (tmp_path / "bad.xml").write_text("<article><unclosed>", encoding="utf-8")
        assert len(parse_all_jats_files(str(tmp_path))) == 2

    def test_empty_directory_returns_empty_list(self, tmp_path):
        assert parse_all_jats_files(str(tmp_path)) == []

    def test_no_file_counted_twice(self, tmp_path):
        # *.xml and *.nxml are globbed separately; a naive union would duplicate
        # nothing today but will the moment a pattern is added.
        write_article(tmp_path / "a.xml")
        ids = [c["chunk_id"] for c in parse_all_jats_files(str(tmp_path))]
        assert len(ids) == len(set(ids))
