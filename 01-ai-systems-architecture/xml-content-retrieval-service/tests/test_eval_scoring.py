"""Tests for retrieval scoring and the comparison metrics."""

import pytest

from eval.chunkers import structure_aware_chunks
from eval.run_comparison import load_questions
from eval.scoring import BM25, evaluate, is_relevant, searchable_text, tokenize


def test_tokenize_lowercases_and_drops_punctuation():
    assert tokenize("Ports 443 and 80!") == ["ports", "443", "and", "80"]


def test_bm25_ranks_the_matching_document_first():
    bm = BM25(["gpu drivers cause crashes", "licence seats are exhausted"])
    assert bm.scores("gpu drivers")[0] > bm.scores("gpu drivers")[1]


def test_bm25_idf_stays_positive_for_a_term_in_every_document():
    """Unsmoothed idf goes negative here, which would invert the ranking."""
    bm = BM25(["alpha beta", "alpha gamma"])
    assert bm.idf["alpha"] > 0


def test_relevance_ignores_case_and_whitespace_differences():
    chunk = {"text": "RAM: 16 GB minimum,\n  32  GB recommended"}
    assert is_relevant(chunk, "32 GB recommended")


def test_relevance_is_false_when_the_span_was_split_away():
    """The failure mode the whole comparison exists to detect."""
    assert not is_relevant({"text": "RAM: 16 GB minimum, 32 GB"}, "32 GB recommended")


def test_metadata_mode_indexes_the_authored_hierarchy():
    chunk = {
        "text": "body",
        "topic_title": "Installing",
        "section_title": "Requirements",
        "tags": "t",
    }
    assert "Requirements" in searchable_text(chunk, use_metadata=True)
    assert "Requirements" not in searchable_text(chunk, use_metadata=False)


def test_every_labelled_span_really_occurs_in_its_labelled_section():
    """Guards the ground truth itself — a wrong label would silently skew results."""
    chunks = {(c["source_file"], c["section_id"]): c for c in structure_aware_chunks("data")}
    for q in load_questions():
        chunk = chunks.get((q["source_file"], q["section_id"]))
        assert chunk is not None, f"{q['id']} names a section that does not exist"
        assert is_relevant(chunk, q["answer_span"]), f"{q['id']} span missing from its section"


def test_evaluate_reports_every_metric_in_range():
    r = evaluate(structure_aware_chunks("data"), load_questions(), use_metadata=False)
    for key in ("recall@1", "recall@3", "recall@5", "mrr"):
        assert 0.0 <= r[key] <= 1.0
    assert r["recall@1"] <= r["recall@3"] <= r["recall@5"]
    assert r["chunks"] == 12


def test_evaluate_rejects_an_empty_corpus():
    with pytest.raises(ValueError):
        evaluate([], load_questions(), use_metadata=False)


def test_comparison_is_deterministic():
    """Two identical runs must agree, or the published numbers mean nothing."""
    qs = load_questions()
    chunks = structure_aware_chunks("data")
    assert evaluate(chunks, qs, use_metadata=True) == evaluate(chunks, qs, use_metadata=True)
