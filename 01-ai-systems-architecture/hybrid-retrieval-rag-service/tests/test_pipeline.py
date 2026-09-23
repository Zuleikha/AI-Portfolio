"""Integration-style tests for RAGPipeline using mocked dependencies."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.rag.chunker import TextChunk
from src.rag.generator import GenerationResult
from src.rag.pipeline import RAGPipeline, RAGResponse
from src.rag.retriever import RetrievedDocument

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_pipeline():
    """
    RAGPipeline with all external I/O replaced by mocks.
    Lets us test orchestration logic without hitting external APIs or the filesystem.
    """
    dummy_doc = RetrievedDocument(
        content="The capital of France is Paris.",
        metadata={"source": "geography.txt", "chunk_index": 0},
        score=0.95,
        retrieval_method="hybrid",
    )
    dummy_generation = GenerationResult(
        answer="The capital of France is Paris [1].",
        sources=[{"content": "The capital of France is Paris.", "metadata": {}, "score": 0.95}],
        tokens_used=42,
        latency_ms=180.0,
        model="claude-sonnet-4-6",
    )

    with (
        patch("src.rag.pipeline.CohereEmbedder") as MockEmbedder,
        patch("src.rag.pipeline.PineconeVectorStore") as MockStore,
        patch("src.rag.pipeline.HybridRetriever") as MockRetriever,
        patch("src.rag.pipeline.CohereReranker") as MockReranker,
        patch("src.rag.pipeline.RAGGenerator") as MockGenerator,
    ):
        mock_store = MockStore.return_value
        mock_store.count = 5
        mock_store.add_documents = MagicMock()

        mock_embedder = MockEmbedder.return_value
        mock_embedder.embed_batch = AsyncMock(return_value=[[0.1] * 1024])
        mock_embedder.embed_query = AsyncMock(return_value=[0.1] * 1024)

        mock_retriever = MockRetriever.return_value
        mock_retriever.retrieve = AsyncMock(return_value=[dummy_doc])

        mock_reranker = MockReranker.return_value
        mock_reranker.rerank = AsyncMock(return_value=[dummy_doc])

        mock_generator = MockGenerator.return_value
        mock_generator.generate = AsyncMock(return_value=dummy_generation)

        yield RAGPipeline()


# ── Ingestion tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_returns_chunk_count(mock_pipeline):
    chunks = [
        TextChunk(content="First chunk.", metadata={"source": "a.txt", "chunk_index": 0}),
        TextChunk(content="Second chunk.", metadata={"source": "a.txt", "chunk_index": 1}),
    ]
    count = await mock_pipeline.ingest_chunks(chunks)
    assert count == 2


@pytest.mark.asyncio
async def test_ingest_empty_list_returns_zero(mock_pipeline):
    count = await mock_pipeline.ingest_chunks([])
    assert count == 0


# ── Query tests ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_returns_rag_response(mock_pipeline):
    response = await mock_pipeline.query("What is the capital of France?")
    assert isinstance(response, RAGResponse)
    assert "Paris" in response.answer
    assert response.tokens_used == 42
    assert response.chunks_retrieved == 1
    assert response.chunks_after_rerank == 1


@pytest.mark.asyncio
async def test_query_with_empty_store_returns_guidance(mock_pipeline):
    mock_pipeline.store.count = 0
    response = await mock_pipeline.query("Any question")
    assert "ingest" in response.answer.lower() or "no documents" in response.answer.lower()
    assert response.tokens_used == 0


# ── Conversation history tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_conversation_history_grows_after_query(mock_pipeline):
    await mock_pipeline.query("First question", conversation_id="sess-1")
    history = mock_pipeline.get_conversation_history("sess-1")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_conversation_history_is_capped_at_six_messages(mock_pipeline):
    for i in range(5):
        await mock_pipeline.query(f"Question {i}", conversation_id="sess-cap")
    history = mock_pipeline.get_conversation_history("sess-cap")
    assert len(history) <= 6


@pytest.mark.asyncio
async def test_clear_conversation_empties_history(mock_pipeline):
    await mock_pipeline.query("Something", conversation_id="sess-clear")
    mock_pipeline.clear_conversation("sess-clear")
    assert mock_pipeline.get_conversation_history("sess-clear") == []


@pytest.mark.asyncio
async def test_clear_nonexistent_conversation_is_safe(mock_pipeline):
    mock_pipeline.clear_conversation("does-not-exist")  # should not raise


# ── Document count ────────────────────────────────────────────────────────────


def test_document_count_delegates_to_store(mock_pipeline):
    mock_pipeline.store.count = 42
    assert mock_pipeline.document_count == 42
