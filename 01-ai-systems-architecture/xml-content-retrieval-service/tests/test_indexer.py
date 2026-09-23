"""
Unit tests for app/indexer.py — OpenAI client guard, embedding batching,
and ChromaDB write path. All externals mocked.
"""

from unittest.mock import MagicMock

import pytest

import app.indexer as indexer


@pytest.fixture(autouse=True)
def reset_client():
    indexer._openai_client = None
    yield
    indexer._openai_client = None


class TestGetOpenAIClient:
    def test_raises_clear_error_without_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            indexer.get_openai_client()

    def test_client_is_cached(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        assert indexer.get_openai_client() is indexer.get_openai_client()


class TestEmbedTexts:
    def _mock_client(self, monkeypatch):
        client = MagicMock()

        def create(model, input):
            resp = MagicMock()
            resp.data = [MagicMock(embedding=[0.1, 0.2]) for _ in input]
            return resp

        client.embeddings.create.side_effect = create
        monkeypatch.setattr(indexer, "get_openai_client", lambda: client)
        return client

    def test_one_embedding_per_text(self, monkeypatch):
        self._mock_client(monkeypatch)
        assert len(indexer.embed_texts(["a", "b", "c"])) == 3

    def test_batches_large_inputs(self, monkeypatch):
        client = self._mock_client(monkeypatch)
        indexer.embed_texts(["t"] * 250)
        assert client.embeddings.create.call_count == 3  # 100 + 100 + 50

    def test_empty_input_no_api_call(self, monkeypatch):
        client = self._mock_client(monkeypatch)
        assert indexer.embed_texts([]) == []
        client.embeddings.create.assert_not_called()


class TestIndexChunks:
    def test_clears_then_adds(self, monkeypatch, sample_chunk):
        collection = MagicMock()
        collection.get.return_value = {"ids": ["old_1"]}
        monkeypatch.setattr(indexer, "get_chroma_client", lambda persist_dir=None: MagicMock())
        monkeypatch.setattr(indexer, "get_or_create_collection", lambda c: collection)
        monkeypatch.setattr(indexer, "embed_texts", lambda texts: [[0.0]] * len(texts))

        count = indexer.index_chunks([sample_chunk])

        collection.delete.assert_called_once_with(ids=["old_1"])
        collection.add.assert_called_once()
        assert count == 1

    def test_metadata_keys_match_contract(self, monkeypatch, sample_chunk):
        collection = MagicMock()
        collection.get.return_value = {"ids": []}
        monkeypatch.setattr(indexer, "get_chroma_client", lambda persist_dir=None: MagicMock())
        monkeypatch.setattr(indexer, "get_or_create_collection", lambda c: collection)
        monkeypatch.setattr(indexer, "embed_texts", lambda texts: [[0.0]] * len(texts))

        indexer.index_chunks([sample_chunk])

        metadata = collection.add.call_args.kwargs["metadatas"][0]
        assert set(metadata) == {
            "topic_id",
            "topic_title",
            "section_title",
            "source_file",
            "tags",
            "topic_shortdesc",
        }
