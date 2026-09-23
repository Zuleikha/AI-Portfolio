"""Unit tests for CohereReranker — fallback and API-success paths."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.rag.reranker import CohereReranker
from src.rag.retriever import RetrievedDocument


def _doc(content: str, score: float = 0.5) -> RetrievedDocument:
    return RetrievedDocument(
        content=content,
        metadata={"source": "test.txt"},
        score=score,
        retrieval_method="hybrid",
    )


@pytest.fixture
def reranker():
    return CohereReranker()


@pytest.fixture
def reranker_no_key(reranker):
    reranker._api_key = None
    return reranker


# ── Fallback behaviour (no API key or call failure) ───────────────────────────


class TestFallbackBehaviour:
    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty_list(self, reranker_no_key):
        result = await reranker_no_key.rerank("query", [], top_k=3)
        assert result == []

    @pytest.mark.asyncio
    async def test_no_api_key_sorts_by_score_descending(self, reranker_no_key):
        docs = [_doc("low", 0.2), _doc("high", 0.9), _doc("mid", 0.5)]
        result = await reranker_no_key.rerank("query", docs, top_k=3)
        scores = [d.score for d in result]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_no_api_key_respects_top_k(self, reranker_no_key):
        docs = [_doc(f"doc {i}", float(i) / 10) for i in range(10)]
        result = await reranker_no_key.rerank("query", docs, top_k=3)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_no_api_key_top_k_one_returns_best_doc(self, reranker_no_key):
        docs = [_doc("best", 0.99), _doc("worst", 0.01)]
        result = await reranker_no_key.rerank("query", docs, top_k=1)
        assert len(result) == 1
        assert result[0].content == "best"

    @pytest.mark.asyncio
    async def test_api_failure_falls_back_to_score_sort(self, reranker):
        docs = [_doc("low", 0.3), _doc("high", 0.9)]

        with patch("src.rag.reranker.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(side_effect=Exception("connection refused"))
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await reranker.rerank("query", docs, top_k=2)

        assert len(result) == 2
        assert result[0].score >= result[1].score

    @pytest.mark.asyncio
    async def test_http_error_falls_back_to_score_sort(self, reranker):
        docs = [_doc("a", 0.8), _doc("b", 0.4)]

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 429")

        with patch("src.rag.reranker.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await reranker.rerank("query", docs, top_k=2)

        assert result[0].content == "a"


# ── Successful API response path ───────────────────────────────────────────────


class TestAPISuccessPath:
    @pytest.mark.asyncio
    async def test_api_reorders_candidates_by_relevance_score(self, reranker):
        docs = [_doc("first", 0.5), _doc("second", 0.8), _doc("third", 0.3)]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"index": 2, "relevance_score": 0.97},
                {"index": 0, "relevance_score": 0.72},
            ]
        }

        with patch("src.rag.reranker.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await reranker.rerank("query", docs, top_k=2)

        assert len(result) == 2
        assert result[0].content == "third"
        assert result[0].score == pytest.approx(0.97)
        assert result[1].content == "first"
        assert result[1].score == pytest.approx(0.72)

    @pytest.mark.asyncio
    async def test_api_preserves_original_metadata(self, reranker):
        docs = [
            RetrievedDocument(
                content="doc",
                metadata={"source": "report.pdf", "chunk_index": 3},
                score=0.6,
                retrieval_method="hybrid",
            )
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"results": [{"index": 0, "relevance_score": 0.88}]}

        with patch("src.rag.reranker.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await reranker.rerank("query", docs, top_k=1)

        assert result[0].metadata == {"source": "report.pdf", "chunk_index": 3}

    @pytest.mark.asyncio
    async def test_api_top_k_limits_results(self, reranker):
        docs = [_doc(f"doc {i}", float(i) / 10) for i in range(5)]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": [{"index": i, "relevance_score": float(5 - i) / 5} for i in range(2)]
        }

        with patch("src.rag.reranker.httpx.AsyncClient") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await reranker.rerank("query", docs, top_k=2)

        assert len(result) == 2
