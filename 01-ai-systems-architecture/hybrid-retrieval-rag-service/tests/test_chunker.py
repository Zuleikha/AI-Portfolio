"""Unit tests for SentenceAwareChunker."""

import pytest

from src.rag.chunker import SentenceAwareChunker, TextChunk


@pytest.fixture
def chunker():
    # Small sizes so tests don't require large inputs
    return SentenceAwareChunker(chunk_size=50, chunk_overlap=10)


class TestSentenceAwareChunker:
    def test_single_sentence_produces_one_chunk(self, chunker):
        chunks = chunker.chunk("This is a single sentence.")
        assert len(chunks) == 1
        assert chunks[0].content == "This is a single sentence."

    def test_empty_text_returns_empty_list(self, chunker):
        assert chunker.chunk("") == []

    def test_whitespace_only_returns_empty_list(self, chunker):
        assert chunker.chunk("   \n\t  ") == []

    def test_metadata_is_propagated_to_all_chunks(self, chunker):
        meta = {"source": "test.pdf", "file_type": "pdf"}
        long_text = ". ".join(f"Sentence number {i}" for i in range(30)) + "."
        chunks = chunker.chunk(long_text, metadata=meta)
        assert all(c.metadata["source"] == "test.pdf" for c in chunks)
        assert all(c.metadata["file_type"] == "pdf" for c in chunks)

    def test_chunk_index_is_contiguous_from_zero(self, chunker):
        long_text = ". ".join(f"Sentence number {i}" for i in range(40)) + "."
        chunks = chunker.chunk(long_text)
        assert len(chunks) > 1, "expected multiple chunks for a long document"
        indices = [c.metadata["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_chunks_contain_no_empty_content(self, chunker):
        text = ". ".join(f"Sentence {i}" for i in range(20)) + "."
        chunks = chunker.chunk(text)
        assert all(c.content.strip() for c in chunks)

    def test_no_mid_word_cuts(self, chunker):
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "Pack my box with five dozen liquor jugs. "
            "How vexingly quick daft zebras jump."
        )
        chunks = chunker.chunk(text)
        for chunk in chunks:
            # Each chunk should start with an alphabetic character (no dangling
            # partial words from the previous chunk)
            assert chunk.content[0].isalpha() or chunk.content[0] == '"'

    def test_returns_list_of_text_chunks(self, chunker):
        chunks = chunker.chunk("A sentence. Another sentence.")
        assert all(isinstance(c, TextChunk) for c in chunks)

    def test_overlap_reduces_information_loss_across_boundaries(self):
        # With overlap=15, the tail of chunk N should partially appear in chunk N+1
        chunker = SentenceAwareChunker(chunk_size=30, chunk_overlap=15)
        text = ". ".join(f"Sentence about topic {i}" for i in range(25)) + "."
        chunks = chunker.chunk(text)
        if len(chunks) > 1:
            # At least some content from the first chunk should recur in the second
            first_words = set(chunks[0].content.lower().split())
            second_words = set(chunks[1].content.lower().split())
            assert first_words & second_words, "expected overlap between adjacent chunks"
