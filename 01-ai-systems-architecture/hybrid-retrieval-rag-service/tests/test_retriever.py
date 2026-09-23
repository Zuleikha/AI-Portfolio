"""Unit tests for HybridRetriever._rrf (pure logic) and retrieve() integration."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.rag.retriever import HybridRetriever, RetrievedDocument


def _doc(content: str, score: float = 0.5, method: str = "dense") -> RetrievedDocument:
    return RetrievedDocument(
        content=content,
        metadata={"source": "test.txt"},
        score=score,
        retrieval_method=method,
    )


@pytest.fixture
def retriever():
    return HybridRetriever(store=MagicMock(), embedder=MagicMock())


# ── _rrf pure-logic tests ─────────────────────────────────────────────────────


class TestRRFFusion:
    def test_both_empty_lists_return_empty(self, retriever):
        assert retriever._rrf([], [], 5) == []

    def test_only_dense_results_are_tagged_hybrid(self, retriever):
        docs = [_doc("a"), _doc("b"), _doc("c")]
        result = retriever._rrf(docs, [], 5)
        assert len(result) == 3
        assert all(d.retrieval_method == "hybrid" for d in result)

    def test_only_sparse_results_are_tagged_hybrid(self, retriever):
        docs = [_doc("x", method="sparse"), _doc("y", method="sparse")]
        result = retriever._rrf([], docs, 5)
        assert len(result) == 2
        assert all(d.retrieval_method == "hybrid" for d in result)

    def test_n_parameter_limits_output_count(self, retriever):
        docs = [_doc(f"doc {i}") for i in range(10)]
        result = retriever._rrf(docs, [], 3)
        assert len(result) == 3

    def test_results_are_sorted_by_descending_score(self, retriever):
        docs = [_doc(f"doc {i}") for i in range(5)]
        result = retriever._rrf(docs, [], 5)
        scores = [d.score for d in result]
        assert scores == sorted(scores, reverse=True)

    def test_doc_in_both_legs_scores_higher_than_single_leg(self, retriever):
        shared = _doc("shared content")
        unique = _doc("unique dense only")
        result = retriever._rrf([shared, unique], [shared], 5)
        shared_score = next(d.score for d in result if d.content == "shared content")
        unique_score = next(d.score for d in result if d.content == "unique dense only")
        assert shared_score > unique_score

    def test_duplicate_content_is_deduplicated(self, retriever):
        doc = _doc("same content")
        result = retriever._rrf([doc], [doc], 10)
        assert len(result) == 1

    def test_rrf_score_uses_k_equals_60(self, retriever):
        doc = _doc("only doc")
        result = retriever._rrf([doc], [], 5)
        # rank=0 → 1 / (60 + 0 + 1) = 1/61
        expected = 1.0 / 61
        assert abs(result[0].score - expected) < 1e-9

    def test_scores_are_additive_across_legs(self, retriever):
        doc = _doc("in both")
        result = retriever._rrf([doc], [doc], 5)
        # rank=0 in dense + rank=0 in sparse = 2/61
        expected = 2.0 / 61
        assert abs(result[0].score - expected) < 1e-9

    def test_higher_rank_in_dense_produces_lower_score(self, retriever):
        first = _doc("rank 0")
        second = _doc("rank 1")
        result = retriever._rrf([first, second], [], 2)
        assert result[0].content == "rank 0"
        assert result[0].score > result[1].score


# ── Integration tests with mocked I/O ─────────────────────────────────────────


class TestHybridRetrieverIntegration:
    @pytest.mark.asyncio
    async def test_empty_store_returns_empty_list(self):
        store = MagicMock()
        store.query.return_value = []
        store.get_all_documents.return_value = []
        embedder = MagicMock()
        embedder.embed_query = AsyncMock(return_value=[0.1] * 384)

        r = HybridRetriever(store, embedder)
        result = await r.retrieve("anything", n_results=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_dense_hit_is_returned_as_retrieved_document(self):
        store = MagicMock()
        store.query.return_value = [
            {
                "content": "Paris is the capital of France.",
                "metadata": {"source": "geo.txt"},
                "score": 0.92,
            }
        ]
        store.get_all_documents.return_value = []
        embedder = MagicMock()
        embedder.embed_query = AsyncMock(return_value=[0.1] * 384)

        r = HybridRetriever(store, embedder)
        result = await r.retrieve("capital of France", n_results=5)

        assert len(result) >= 1
        assert isinstance(result[0], RetrievedDocument)
        assert "Paris" in result[0].content

    @pytest.mark.asyncio
    async def test_output_count_is_bounded_by_n_results(self):
        store = MagicMock()
        store.query.return_value = [
            {"content": f"doc {i}", "metadata": {}, "score": float(i) / 20} for i in range(20)
        ]
        store.get_all_documents.return_value = []
        embedder = MagicMock()
        embedder.embed_query = AsyncMock(return_value=[0.1] * 384)

        r = HybridRetriever(store, embedder)
        result = await r.retrieve("query", n_results=5)
        assert len(result) <= 5

    @pytest.mark.asyncio
    async def test_bm25_only_match_is_returned_when_dense_empty(self):
        # BM25Okapi IDF is negative when a term appears in all documents, so we
        # need multiple docs to ensure the query terms have a positive IDF score.
        store = MagicMock()
        store.query.return_value = []
        store.get_all_documents.return_value = [
            {"content": "The quick brown fox jumped.", "metadata": {"source": "a.txt"}},
            {"content": "The lazy dog slept all day.", "metadata": {"source": "b.txt"}},
            {"content": "The cat sat on the mat.", "metadata": {"source": "c.txt"}},
        ]
        embedder = MagicMock()
        embedder.embed_query = AsyncMock(return_value=[0.1] * 384)

        r = HybridRetriever(store, embedder)
        result = await r.retrieve("quick fox", n_results=5)

        # "quick" and "fox" appear only in the first doc → positive BM25 score
        assert len(result) >= 1
        assert "fox" in result[0].content.lower()
