"""Tests for the knowledge document loader and the shipped corpus.

Two things are under test here:

1. The loader itself -- that it parses valid documents correctly and fails loud
   on every kind of malformed input.
2. The real knowledge base -- that every shipped document is valid, that the
   corpus covers the domains the agent will be asked about, and that it contains
   nothing resembling a secret or a real card number.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.knowledge import (
    DocumentMetadata,
    EmptyDocumentError,
    FrontMatterError,
    KnowledgeBaseNotFoundError,
    KnowledgeDocument,
    MetadataError,
    load_document,
    load_knowledge_base,
)
from app.knowledge.loader import DuplicateDocumentIdError, split_front_matter
from app.knowledge.models import DocType, Domain

EXPECTED_DOMAINS = {
    "atm",
    "cards",
    "payments",
    "digital-banking",
    "api",
    "configuration",
    "operations",
    "platform",
}

VALID_FRONT_MATTER = """\
document_id: {document_id}
title: Sample Document
domain: atm
component: TransactionSwitch
version: "4.2"
doc_type: reference
"""


def write_document(
    root: Path,
    document_id: str,
    *,
    front_matter: str | None = None,
    body: str = "# Sample\n\nSome body text.",
    subdirectory: str = "",
) -> Path:
    """Write a document into ``root`` and return its path."""
    directory = root / subdirectory if subdirectory else root
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{document_id}.md"
    header = (
        front_matter
        if front_matter is not None
        else VALID_FRONT_MATTER.format(document_id=document_id)
    )
    path.write_text(f"---\n{header}---\n\n{body}\n", encoding="utf-8")
    return path


@pytest.fixture
def corpus(knowledge_root: Path) -> tuple[KnowledgeDocument, ...]:
    """The real knowledge base, loaded once per test."""
    return load_knowledge_base(knowledge_root)


# --------------------------------------------------------------------------
# Loading a single valid document
# --------------------------------------------------------------------------


def test_loads_a_valid_document(tmp_path: Path):
    path = write_document(tmp_path, "sample-document")

    document = load_document(path, tmp_path)

    assert document.metadata.document_id == "sample-document"
    assert document.metadata.title == "Sample Document"
    assert document.metadata.domain == "atm"
    assert document.metadata.component == "TransactionSwitch"
    assert document.metadata.version == "4.2"
    assert document.metadata.doc_type == "reference"


def test_front_matter_is_stripped_from_content(tmp_path: Path):
    path = write_document(tmp_path, "sample-document")

    document = load_document(path, tmp_path)

    assert document.content.startswith("# Sample")
    assert "document_id:" not in document.content
    assert "---" not in document.content


def test_source_path_is_relative_and_posix(tmp_path: Path):
    path = write_document(tmp_path, "sample-document", subdirectory="atm")

    document = load_document(path, tmp_path)

    assert document.source_path == "atm/sample-document.md"
    assert "\\" not in document.source_path


def test_optional_tags_default_to_empty(tmp_path: Path):
    path = write_document(tmp_path, "sample-document")

    assert load_document(path, tmp_path).metadata.tags == ()


def test_tags_are_parsed_when_present(tmp_path: Path):
    front_matter = VALID_FRONT_MATTER.format(document_id="tagged-document")
    front_matter += "tags:\n  - atm\n  - reversal\n"
    path = write_document(tmp_path, "tagged-document", front_matter=front_matter)

    assert load_document(path, tmp_path).metadata.tags == ("atm", "reversal")


def test_leading_byte_order_mark_is_tolerated(tmp_path: Path):
    path = write_document(tmp_path, "sample-document")
    path.write_text("﻿" + path.read_text(encoding="utf-8"), encoding="utf-8")

    assert load_document(path, tmp_path).metadata.document_id == "sample-document"


def test_citation_names_the_document_and_its_path(tmp_path: Path):
    path = write_document(tmp_path, "sample-document", subdirectory="atm")

    citation = load_document(path, tmp_path).citation

    assert "Sample Document" in citation
    assert "atm/sample-document.md" in citation


def test_documents_are_immutable(tmp_path: Path):
    document = load_document(write_document(tmp_path, "sample-document"), tmp_path)

    with pytest.raises(ValidationError):
        document.metadata.domain = "cards"  # type: ignore[misc]


# --------------------------------------------------------------------------
# Front matter failures
# --------------------------------------------------------------------------


def test_missing_front_matter_raises(tmp_path: Path):
    path = tmp_path / "no-front-matter.md"
    path.write_text("# Just a heading\n\nNo metadata at all.\n", encoding="utf-8")

    with pytest.raises(FrontMatterError, match="front-matter block"):
        load_document(path, tmp_path)


def test_unterminated_front_matter_raises(tmp_path: Path):
    path = tmp_path / "unterminated.md"
    path.write_text("---\ndocument_id: unterminated\n\n# Body\n", encoding="utf-8")

    with pytest.raises(FrontMatterError, match="never closed"):
        load_document(path, tmp_path)


def test_invalid_yaml_front_matter_raises(tmp_path: Path):
    path = write_document(
        tmp_path,
        "broken-yaml",
        front_matter='document_id: "broken-yaml\ntitle: [unclosed\n',
    )

    with pytest.raises(FrontMatterError, match="not valid YAML"):
        load_document(path, tmp_path)


def test_scalar_front_matter_raises(tmp_path: Path):
    path = write_document(tmp_path, "scalar", front_matter="just a string\n")

    with pytest.raises(FrontMatterError, match="must be a mapping"):
        load_document(path, tmp_path)


def test_empty_file_raises(tmp_path: Path):
    path = tmp_path / "empty.md"
    path.write_text("", encoding="utf-8")

    with pytest.raises(FrontMatterError):
        load_document(path, tmp_path)


def test_split_front_matter_returns_both_parts():
    front_matter, body = split_front_matter(
        "---\nkey: value\n---\n\nbody text\n", "sample.md"
    )

    assert front_matter == "key: value"
    assert body.strip() == "body text"


# --------------------------------------------------------------------------
# Metadata failures
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "omitted",
    ["title", "domain", "component", "version", "doc_type"],
)
def test_missing_required_metadata_field_raises(tmp_path: Path, omitted: str):
    front_matter = "".join(
        line + "\n"
        for line in VALID_FRONT_MATTER.format(document_id="incomplete").splitlines()
        if not line.startswith(f"{omitted}:")
    )
    path = write_document(tmp_path, "incomplete", front_matter=front_matter)

    with pytest.raises(MetadataError, match="invalid document metadata"):
        load_document(path, tmp_path)


def test_unknown_domain_raises(tmp_path: Path):
    front_matter = VALID_FRONT_MATTER.format(document_id="bad-domain").replace(
        "domain: atm", "domain: cryptocurrency"
    )
    path = write_document(tmp_path, "bad-domain", front_matter=front_matter)

    with pytest.raises(MetadataError):
        load_document(path, tmp_path)


def test_unknown_doc_type_raises(tmp_path: Path):
    front_matter = VALID_FRONT_MATTER.format(document_id="bad-type").replace(
        "doc_type: reference", "doc_type: blogpost"
    )
    path = write_document(tmp_path, "bad-type", front_matter=front_matter)

    with pytest.raises(MetadataError):
        load_document(path, tmp_path)


def test_unrecognised_metadata_field_raises(tmp_path: Path):
    front_matter = VALID_FRONT_MATTER.format(document_id="typo") + "compnent: Switch\n"
    path = write_document(tmp_path, "typo", front_matter=front_matter)

    with pytest.raises(MetadataError):
        load_document(path, tmp_path)


def test_document_id_must_match_filename(tmp_path: Path):
    front_matter = VALID_FRONT_MATTER.format(document_id="a-different-id")
    path = write_document(tmp_path, "on-disk-name", front_matter=front_matter)

    with pytest.raises(MetadataError, match="does not match the filename"):
        load_document(path, tmp_path)


def test_non_slug_document_id_raises(tmp_path: Path):
    front_matter = VALID_FRONT_MATTER.format(document_id="Not A Slug")
    path = write_document(tmp_path, "Not A Slug", front_matter=front_matter)

    with pytest.raises(MetadataError):
        load_document(path, tmp_path)


def test_document_without_body_raises(tmp_path: Path):
    path = write_document(tmp_path, "bodyless", body="   \n\n")

    with pytest.raises(EmptyDocumentError, match="no body content"):
        load_document(path, tmp_path)


# --------------------------------------------------------------------------
# Loading a knowledge base directory
# --------------------------------------------------------------------------


def test_loads_documents_from_nested_directories(tmp_path: Path):
    write_document(tmp_path, "first-document", subdirectory="atm")
    write_document(tmp_path, "second-document", subdirectory="cards/deep")

    documents = load_knowledge_base(tmp_path)

    assert {doc.metadata.document_id for doc in documents} == {
        "first-document",
        "second-document",
    }


def test_documents_are_returned_in_deterministic_order(tmp_path: Path):
    for name in ("charlie-doc", "alpha-doc", "bravo-doc"):
        write_document(tmp_path, name)

    paths = [doc.source_path for doc in load_knowledge_base(tmp_path)]

    assert paths == sorted(paths)


def test_missing_knowledge_directory_raises(tmp_path: Path):
    with pytest.raises(KnowledgeBaseNotFoundError, match="does not exist"):
        load_knowledge_base(tmp_path / "absent")


def test_empty_knowledge_directory_raises(tmp_path: Path):
    with pytest.raises(KnowledgeBaseNotFoundError, match="No '.md' documents"):
        load_knowledge_base(tmp_path)


def test_duplicate_document_ids_raise(tmp_path: Path):
    front_matter = VALID_FRONT_MATTER.format(document_id="shared-id")
    write_document(tmp_path, "shared-id", subdirectory="atm")
    write_document(
        tmp_path, "shared-id", front_matter=front_matter, subdirectory="cards"
    )

    with pytest.raises(DuplicateDocumentIdError, match="Duplicate document_id"):
        load_knowledge_base(tmp_path)


def test_one_broken_document_fails_the_whole_load(tmp_path: Path):
    write_document(tmp_path, "good-document")
    (tmp_path / "broken-document.md").write_text("no front matter", encoding="utf-8")

    with pytest.raises(FrontMatterError):
        load_knowledge_base(tmp_path)


def test_defaults_to_the_configured_knowledge_directory():
    assert load_knowledge_base() == load_knowledge_base(Settings().knowledge_dir)


# --------------------------------------------------------------------------
# The shipped knowledge base
# --------------------------------------------------------------------------


def test_knowledge_base_has_enough_documents_for_retrieval(corpus):
    assert len(corpus) >= 12


def test_every_expected_domain_is_covered(corpus):
    assert {doc.metadata.domain for doc in corpus} == EXPECTED_DOMAINS


def test_every_document_has_complete_metadata(corpus):
    for document in corpus:
        metadata = document.metadata
        assert metadata.document_id
        assert metadata.title
        assert metadata.domain in EXPECTED_DOMAINS
        assert metadata.component
        assert metadata.version
        assert metadata.doc_type


def test_document_ids_are_unique(corpus):
    ids = [doc.metadata.document_id for doc in corpus]

    assert len(ids) == len(set(ids))


def test_every_document_has_substantial_content(corpus):
    for document in corpus:
        assert len(document.content.split()) >= 150, document.source_path


def test_corpus_uses_several_document_types(corpus):
    doc_types = {doc.metadata.doc_type for doc in corpus}

    assert {"reference", "api", "configuration"} <= doc_types
    assert {"runbook", "troubleshooting"} & doc_types


def test_corpus_names_multiple_components(corpus):
    components = {doc.metadata.component for doc in corpus}

    assert len(components) >= 6


@pytest.mark.parametrize(
    "phrase",
    [
        "card authentication",
        "AuthorizationService",
        "CardSecurityModule",
        "/v1/payments/authorise",
        "limits.atm.daily_withdrawal_amount",
        "reversal",
        "LIM-4001",
        "COR-5008",
    ],
)
def test_corpus_covers_the_agents_seed_questions(corpus, phrase: str):
    """Stage 5 asks these questions; the evidence must exist in the corpus."""
    haystack = "\n".join(doc.content for doc in corpus)

    assert phrase in haystack


# --------------------------------------------------------------------------
# Security of the corpus
# --------------------------------------------------------------------------

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"(?i)\b(password|passwd|api[_-]?key|secret[_-]?key|access[_-]?token)"
        r"\s*[:=]\s*[\"']?[A-Za-z0-9/+=_-]{8,}"
    ),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]

PAN_PATTERN = re.compile(r"(?<!\d)\d{13,19}(?!\d)")


def test_corpus_contains_no_secret_like_values(corpus):
    for document in corpus:
        for pattern in SECRET_PATTERNS:
            assert not pattern.search(
                document.content
            ), f"{document.source_path} matched {pattern.pattern}"


def test_corpus_contains_no_card_number_like_digits(corpus):
    for document in corpus:
        assert not PAN_PATTERN.search(document.content), document.source_path


def test_corpus_documents_are_synthetic(corpus):
    """The brief forbids reproducing any real vendor's documentation."""
    haystack = "\n".join(doc.content for doc in corpus).lower()

    assert "cr2" not in haystack
    assert "bankworld" not in haystack


# --------------------------------------------------------------------------
# Type contracts
# --------------------------------------------------------------------------


def test_domain_and_doc_type_are_closed_sets():
    assert set(Domain.__args__) == EXPECTED_DOMAINS
    assert set(DocType.__args__) == {
        "reference",
        "api",
        "configuration",
        "runbook",
        "troubleshooting",
    }


def test_metadata_rejects_blank_component():
    with pytest.raises(ValidationError):
        DocumentMetadata(
            document_id="sample",
            title="Sample",
            domain="atm",
            component="",
            version="4.2",
            doc_type="reference",
        )
