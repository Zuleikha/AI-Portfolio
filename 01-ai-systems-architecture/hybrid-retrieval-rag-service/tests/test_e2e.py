"""
End-to-end pipeline test (embed → retrieve → generate).

Exercises the real flow with only the external service boundaries stubbed:
- CohereEmbedder's HTTP call to the Cohere Embed API is stubbed (no real key,
  no network) — the real embedder code path runs, only the transport is faked
- A small in-memory store stands in for Pinecone
- The real HybridRetriever (dense + BM25 + RRF) and the rerank fallback run
- The Anthropic Messages API is stubbed to return a fixed answer

The chunker still loads a local fast tokenizer at construction; if that can't be
fetched offline the test skips rather than fails.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.rag.chunker import TextChunk
from src.rag.pipeline import RAGPipeline, RAGResponse


class _InMemoryStore:
    """Minimal, network-free stand-in for PineconeVectorStore."""

    def __init__(self) -> None:
        self._docs: list[dict] = []

    def add_documents(self, ids, embeddings, documents, metadatas) -> None:
        for doc, meta in zip(documents, metadatas, strict=True):
            self._docs.append({"content": doc, "metadata": meta})

    def query(self, query_embedding, n_results: int = 10, where=None) -> list[dict]:
        return [
            {"content": d["content"], "metadata": d["metadata"], "score": 1.0}
            for d in self._docs[:n_results]
        ]

    def get_all_documents(self) -> list[dict]:
        return [{"content": d["content"], "metadata": d["metadata"]} for d in self._docs]

    @property
    def count(self) -> int:
        return len(self._docs)


def _mock_async_client(post_mock):
    """Wrap a mocked .post in an async-context-manager AsyncClient stub."""
    client = MagicMock()
    client.post = post_mock
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _embed_response(n_texts: int, dim: int = 1024):
    """Stub Cohere /v2/embed response: {"embeddings": {"float": [[...], ...]}}."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(
        return_value={"embeddings": {"float": [[0.1] * dim for _ in range(n_texts)]}}
    )
    return resp


def _anthropic_response(text: str, input_tokens: int = 40, output_tokens: int = 12):
    """Stub Anthropic Messages response (content blocks + split usage)."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    resp = MagicMock()
    resp.content = [block]
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    return resp


@pytest.mark.asyncio
async def test_end_to_end_embed_retrieve_generate():
    # The embedder reaches Cohere over httpx; the generator uses the Anthropic
    # SDK. Both boundaries are stubbed, so the test needs no keys and no network.
    embed_calls: list[str] = []

    async def _dispatch(url, *args, **kwargs):
        embed_calls.append(url)
        if "embed" in url:
            n = len(kwargs.get("json", {}).get("texts", [""]))
            return _embed_response(n)
        raise AssertionError(f"unexpected URL in test: {url}")

    post = AsyncMock(side_effect=_dispatch)
    messages_create = AsyncMock(
        return_value=_anthropic_response("Paris is the capital of France [1].")
    )

    with (
        patch("src.rag.pipeline.PineconeVectorStore", return_value=_InMemoryStore()),
        patch("src.rag.embedder.httpx.AsyncClient", return_value=_mock_async_client(post)),
        patch("src.rag.generator.AsyncAnthropic") as MockAnthropic,
    ):
        MockAnthropic.return_value.messages.create = messages_create

        try:
            pipeline = RAGPipeline()
        except Exception as exc:  # noqa: BLE001 - offline tokenizer-download failure
            pytest.skip(f"Chunker tokenizer unavailable offline: {exc}")

        # Network-free rerank fallback (no Cohere rerank call).
        pipeline.reranker._api_key = None

        # 1. Embed a short document (via stubbed Cohere) and store it.
        chunk = TextChunk(
            content="Paris is the capital of France.",
            metadata={"source": "geography.txt", "chunk_index": 0},
        )
        ingested = await pipeline.ingest_chunks([chunk])
        assert ingested == 1
        assert pipeline.document_count == 1

        # 2 + 3. Retrieve relevant chunks, then generate through stubbed Anthropic.
        response = await pipeline.query("What is the capital of France?")

    # 4. A non-empty, grounded answer comes back.
    assert isinstance(response, RAGResponse)
    assert response.answer.strip(), "expected a non-empty answer"
    assert "Paris" in response.answer
    assert response.chunks_retrieved >= 1
    assert any("embed" in u for u in embed_calls), "embeddings should go via the stubbed Cohere API"
    messages_create.assert_awaited_once()
