"""Tests for the chunking strategies under comparison."""

import pytest

from eval.chunkers import naive_chunks, strategies, structure_aware_chunks

DATA = "data"


def test_structure_aware_gives_one_chunk_per_authored_section():
    chunks = structure_aware_chunks(DATA)
    assert len(chunks) == 12
    assert all(c["section_id"] != "unknown" for c in chunks)


def test_naive_chunks_do_not_claim_a_section():
    """A structure-blind splitter has no section to name; it must not invent one."""
    for c in naive_chunks(DATA, size=300):
        assert c["section_id"] == "unknown"
        assert c["section_title"] == "unknown"


def test_naive_window_size_is_respected():
    for c in naive_chunks(DATA, size=200):
        assert len(c["text"]) <= 200


def test_smaller_windows_produce_more_chunks():
    assert len(naive_chunks(DATA, 150)) > len(naive_chunks(DATA, 600))


def test_overlap_increases_total_text_but_not_chunk_width():
    plain = naive_chunks(DATA, 300, overlap=0)
    lapped = naive_chunks(DATA, 300, overlap=100)
    assert sum(len(c["text"]) for c in lapped) > sum(len(c["text"]) for c in plain)
    assert all(len(c["text"]) <= 300 for c in lapped)


def test_both_strategies_emit_the_same_chunk_shape():
    """Scoring must not be able to tell which strategy produced a chunk."""
    a = structure_aware_chunks(DATA)[0]
    b = naive_chunks(DATA, 300)[0]
    assert set(a) == set(b)


@pytest.mark.parametrize(
    "size,overlap",
    [(0, 0), (-1, 0), (100, -1), (100, 100), (100, 150)],
)
def test_invalid_window_settings_are_rejected(size, overlap):
    with pytest.raises(ValueError):
        naive_chunks(DATA, size, overlap)


def test_strategy_set_contains_structure_aware_and_a_naive_sweep():
    s = strategies(DATA)
    assert "structure-aware" in s
    assert sum(1 for k in s if k.startswith("naive-")) >= 4
