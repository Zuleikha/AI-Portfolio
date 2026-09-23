"""Tests for document chunking.

Two jobs. First, the boundary rules: sections split on headings, the H1 dropped,
oversized sections broken up, tables keeping their headers. Second — and this is
the one that matters in production — the *invariant* that no chunk ever exceeds
the embedder's input window, because the model truncates silently and a
truncated chunk is a passage that quietly stops being findable.

These run against the hashing embedder so they are fast and deterministic.
The same invariant is asserted against the real model in
``test_rag_integration.py``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.knowledge.models import DocumentMetadata, KnowledgeDocument
from app.rag.chunker import (
    ChunkingError,
    _is_table,
    chunk_document,
    chunk_documents,
    split_sections,
)
from app.rag.embeddings import HashingEmbedder


def make_document(content: str, document_id: str = "test-doc") -> KnowledgeDocument:
    """Build a KnowledgeDocument around a body of Markdown."""
    return KnowledgeDocument(
        metadata=DocumentMetadata(
            document_id=document_id,
            title="Test Document",
            domain="atm",
            component="TransactionSwitch",
            version="4.2",
            doc_type="reference",
        ),
        content=content,
        source_path=f"atm/{document_id}.md",
    )


@pytest.fixture
def embedder() -> HashingEmbedder:
    """A deterministic embedder that counts tokens as whitespace words."""
    return HashingEmbedder(dimension=64, max_tokens=64)


# --------------------------------------------------------------------------
# split_sections
# --------------------------------------------------------------------------


def test_splits_on_h2_headings():
    sections = split_sections("# Title\n\n## One\n\nAlpha.\n\n## Two\n\nBeta.")
    assert sections == [("One", "Alpha."), ("Two", "Beta.")]


def test_drops_the_h1_because_metadata_already_carries_the_title():
    sections = split_sections("# ATM Lifecycle\n\n## Stages\n\nBody.")
    assert all("ATM Lifecycle" not in text for _, text in sections)


def test_preamble_before_the_first_heading_becomes_a_headingless_section():
    sections = split_sections("# T\n\nIntro prose.\n\n## One\n\nAlpha.")
    assert sections[0] == (None, "Intro prose.")
    assert sections[1] == ("One", "Alpha.")


def test_document_without_headings_is_one_section():
    assert split_sections("# T\n\nJust prose.") == [(None, "Just prose.")]


def test_empty_sections_are_dropped():
    sections = split_sections("## Empty\n\n## Full\n\nContent.")
    assert sections == [("Full", "Content.")]


def test_h3_headings_do_not_start_a_new_section():
    sections = split_sections("## Main\n\nA.\n\n### Sub\n\nB.")
    assert len(sections) == 1
    assert "### Sub" in sections[0][1]


def test_hash_inside_a_code_fence_is_not_a_heading():
    sections = split_sections("## Config\n\n```\n## not a heading\n```")
    assert len(sections) == 1


def test_body_with_no_content_yields_no_sections():
    assert split_sections("# Title\n\n") == []


# --------------------------------------------------------------------------
# chunk_document — basics and metadata
# --------------------------------------------------------------------------


def test_each_section_becomes_a_chunk(embedder):
    chunks = chunk_document(make_document("## A\n\nAlpha.\n\n## B\n\nBeta."), embedder)
    assert len(chunks) == 2
    assert [chunk.heading for chunk in chunks] == ["A", "B"]


def test_chunk_ids_are_stable_and_ordinal(embedder):
    chunks = chunk_document(make_document("## A\n\nAlpha.\n\n## B\n\nBeta."), embedder)
    assert [chunk.chunk_id for chunk in chunks] == ["test-doc#0", "test-doc#1"]
    assert [chunk.ordinal for chunk in chunks] == [0, 1]


def test_chunking_is_deterministic(embedder):
    document = make_document("## A\n\nAlpha.\n\n## B\n\nBeta.")
    first = chunk_document(document, embedder)
    second = chunk_document(document, embedder)
    assert [chunk.content for chunk in first] == [chunk.content for chunk in second]
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]


def test_every_chunk_carries_the_full_document_metadata(embedder):
    chunks = chunk_document(make_document("## A\n\nAlpha.\n\n## B\n\nBeta."), embedder)
    for chunk in chunks:
        assert chunk.metadata.component == "TransactionSwitch"
        assert chunk.metadata.domain == "atm"
        assert chunk.metadata.version == "4.2"
        assert chunk.source_path == "atm/test-doc.md"
        assert chunk.document_id == "test-doc"


def test_embedding_text_prefixes_title_and_heading_but_content_does_not(embedder):
    chunk = chunk_document(make_document("## Reversals\n\nRetried."), embedder)[0]
    assert chunk.content == "Retried."
    assert chunk.embedding_text == "Test Document — Reversals\n\nRetried."


def test_headingless_chunk_is_prefixed_with_the_title_alone(embedder):
    chunk = chunk_document(make_document("Intro prose."), embedder)[0]
    assert chunk.context_prefix == "Test Document"
    assert chunk.embedding_text.startswith("Test Document\n\n")


def test_token_count_measures_the_embedding_text_not_the_content(embedder):
    chunk = chunk_document(make_document("## Reversals\n\nRetried."), embedder)[0]
    assert chunk.token_count == embedder.count_tokens(chunk.embedding_text)
    assert chunk.token_count > embedder.count_tokens(chunk.content)


def test_citation_names_the_document_section_and_path(embedder):
    chunk = chunk_document(make_document("## Reversals\n\nRetried."), embedder)[0]
    assert chunk.citation == "Test Document — Reversals (atm/test-doc.md)"


def test_chunks_are_immutable(embedder):
    chunk = chunk_document(make_document("## A\n\nAlpha."), embedder)[0]
    with pytest.raises(ValidationError, match="frozen"):
        chunk.content = "changed"


# --------------------------------------------------------------------------
# The invariant: nothing exceeds the model's window
# --------------------------------------------------------------------------


def test_oversized_section_is_split(embedder):
    body = "## Long\n\n" + "\n\n".join(
        f"Paragraph {n} " + "word " * 20 for n in range(8)
    )
    chunks = chunk_document(make_document(body), embedder)
    assert len(chunks) > 1


def test_no_chunk_exceeds_the_budget_however_long_the_section(embedder):
    body = "## Long\n\n" + "\n\n".join(f"Para {n} " + "word " * 30 for n in range(12))
    for chunk in chunk_document(make_document(body), embedder):
        assert chunk.token_count <= embedder.max_tokens


def test_a_single_unbreakable_line_is_split_on_words(embedder):
    body = "## Wall\n\n" + "word " * 400
    for chunk in chunk_document(make_document(body), embedder):
        assert chunk.token_count <= embedder.max_tokens


def test_split_parts_all_keep_the_same_heading(embedder):
    body = "## Long\n\n" + "\n\n".join(f"Para {n} " + "word " * 30 for n in range(10))
    chunks = chunk_document(make_document(body), embedder)
    assert len({chunk.heading for chunk in chunks}) == 1
    assert chunks[0].heading == "Long"


def test_split_parts_are_contiguous_and_lose_no_distinctive_content(embedder):
    body = "## Long\n\n" + "\n\n".join(f"marker{n} " + "word " * 25 for n in range(10))
    joined = " ".join(
        chunk.content for chunk in chunk_document(make_document(body), embedder)
    )
    for n in range(10):
        assert f"marker{n}" in joined


def test_explicit_max_tokens_overrides_the_embedder_limit(embedder):
    body = "## Long\n\n" + "\n\n".join(f"Para {n} " + "word " * 10 for n in range(6))
    wide = chunk_document(make_document(body), embedder, max_tokens=64)
    narrow = chunk_document(make_document(body), embedder, max_tokens=30)
    assert len(narrow) > len(wide)
    assert all(chunk.token_count <= 30 for chunk in narrow)


def test_overlap_repeats_content_between_split_parts(embedder):
    body = "## Long\n\n" + "\n".join(
        f"Line {n} with several words here" for n in range(30)
    )
    with_overlap = chunk_document(make_document(body), embedder, overlap_tokens=20)
    without = chunk_document(make_document(body), embedder, overlap_tokens=0)
    assert sum(len(c.content) for c in with_overlap) > sum(
        len(c.content) for c in without
    )


def test_negative_overlap_is_rejected(embedder):
    with pytest.raises(ValueError, match="overlap_tokens"):
        chunk_document(make_document("## A\n\nAlpha."), embedder, overlap_tokens=-1)


def test_budget_too_small_for_the_prefix_fails_loudly(embedder):
    # The prefix "Test Document — A" is 4 tokens, leaving no room for content.
    with pytest.raises(ChunkingError, match="fills the"):
        chunk_document(make_document("## A\n\nAlpha."), embedder, max_tokens=4)


def test_document_with_no_chunkable_content_fails_loudly(embedder):
    document = make_document("# Title Only")
    with pytest.raises(ChunkingError, match="no chunkable sections"):
        chunk_document(document, embedder)


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------


def _table(rows: int) -> str:
    header = "| Code | Meaning | Action |\n|---|---|---|"
    body = "\n".join(
        f"| LIM-{4000 + n} | Limit breach number {n} | Escalate to operations |"
        for n in range(rows)
    )
    return f"{header}\n{body}"


def test_table_is_recognised():
    assert _is_table(_table(3))
    assert not _is_table("Just a paragraph of prose.")
    assert not _is_table("| header |\n| only two lines |")


def test_oversized_table_is_split_row_wise(embedder):
    chunks = chunk_document(make_document(f"## Codes\n\n{_table(30)}"), embedder)
    assert len(chunks) > 1


def test_every_table_part_repeats_the_header_row(embedder):
    chunks = chunk_document(make_document(f"## Codes\n\n{_table(30)}"), embedder)
    for chunk in chunks:
        assert "| Code | Meaning | Action |" in chunk.content
        assert "|---|---|---|" in chunk.content


def test_no_table_row_is_lost_when_the_table_is_split(embedder):
    chunks = chunk_document(make_document(f"## Codes\n\n{_table(30)}"), embedder)
    joined = "\n".join(chunk.content for chunk in chunks)
    for n in range(30):
        assert f"LIM-{4000 + n}" in joined


def test_table_rows_are_never_broken_mid_row(embedder):
    chunks = chunk_document(make_document(f"## Codes\n\n{_table(30)}"), embedder)
    for chunk in chunks:
        for line in chunk.content.splitlines():
            assert line.startswith("|") and line.endswith("|")


def test_a_table_header_wider_than_the_budget_fails_loudly(embedder):
    header = "| " + " | ".join(f"column{n}" for n in range(80)) + " |"
    separator = "|" + "---|" * 80
    body = f"## Wide\n\n{header}\n{separator}\n" + "\n".join(
        "| " + " | ".join("v" for _ in range(80)) + " |" for _ in range(5)
    )
    with pytest.raises(ChunkingError, match="table header alone"):
        chunk_document(make_document(body), embedder)


# --------------------------------------------------------------------------
# chunk_documents (corpus level)
# --------------------------------------------------------------------------


def test_chunk_documents_covers_every_document(embedder, settings):
    documents = [
        make_document("## A\n\nAlpha.", "doc-a"),
        make_document("## B\n\nBeta.", "doc-b"),
    ]
    chunks = chunk_documents(documents, embedder, settings)
    assert {chunk.document_id for chunk in chunks} == {"doc-a", "doc-b"}


def test_chunk_ids_are_unique_across_the_corpus(embedder, settings):
    documents = [make_document(f"## A\n\nAlpha {n}.", f"doc-{n}") for n in range(5)]
    chunks = chunk_documents(documents, embedder, settings)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


def test_chunking_an_empty_corpus_fails_loudly(embedder, settings):
    with pytest.raises(ChunkingError, match="empty document set"):
        chunk_documents([], embedder, settings)
