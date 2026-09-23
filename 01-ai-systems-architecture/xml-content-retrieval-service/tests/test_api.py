"""
Endpoint tests for app/api.py via FastAPI TestClient.
Search / generation / indexing layers are mocked — fully offline.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.api as api


@pytest.fixture
def client(monkeypatch):
    # Keep the startup lifespan offline
    monkeypatch.setattr(api, "collection_count", lambda persist_dir=None: 5)
    with TestClient(api.app) as c:
        yield c


class TestHealth:
    def test_returns_200_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestSearchEndpoint:
    def test_happy_path(self, client, monkeypatch, retrieved_chunk):
        monkeypatch.setattr(api, "search", lambda q, n_results, persist_dir: [retrieved_chunk])
        resp = client.post("/search", json={"query": "install"})
        assert resp.status_code == 200
        assert resp.json()[0]["chunk_id"] == retrieved_chunk["chunk_id"]

    def test_empty_query_rejected(self, client):
        assert client.post("/search", json={"query": ""}).status_code == 422

    @pytest.mark.parametrize("n", [0, -1, 21])
    def test_n_results_out_of_bounds_rejected(self, client, n):
        resp = client.post("/search", json={"query": "x", "n_results": n})
        assert resp.status_code == 422

    def test_internal_error_not_leaked(self, client, monkeypatch):
        def boom(q, n_results, persist_dir):
            raise ValueError("secret internal path C:/keys.txt")

        monkeypatch.setattr(api, "search", boom)
        resp = client.post("/search", json={"query": "x"})
        assert resp.status_code == 500
        assert "secret" not in resp.text


class TestAskEndpoint:
    def test_happy_path(self, client, monkeypatch, retrieved_chunk):
        monkeypatch.setattr(api, "search", lambda q, n_results, persist_dir: [retrieved_chunk])
        monkeypatch.setattr(api, "generate_answer", lambda q, chunks: "Use the installer.")
        resp = client.post("/ask", json={"query": "how to install?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "Use the installer."
        assert data["sources"][0]["topic"] == retrieved_chunk["metadata"]["topic_title"]

    def test_internal_error_not_leaked(self, client, monkeypatch):
        def boom(q, n_results, persist_dir):
            raise RuntimeError("OPENAI_API_KEY is not set")

        monkeypatch.setattr(api, "search", boom)
        resp = client.post("/ask", json={"query": "x"})
        assert resp.status_code == 500
        assert "OPENAI_API_KEY" not in resp.text


class TestIndexEndpoint:
    def test_missing_data_dir_returns_404(self, client, monkeypatch):
        monkeypatch.setattr(api, "DATA_DIR", "./does-not-exist")
        assert client.post("/index").status_code == 404

    def test_no_dita_files_returns_404(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(api, "DATA_DIR", str(tmp_path))
        assert client.post("/index").status_code == 404

    def test_happy_path(self, client, monkeypatch, sample_chunk):
        monkeypatch.setattr(api, "parse_all_files", lambda d: [sample_chunk])
        monkeypatch.setattr(api, "index_chunks", lambda chunks, persist_dir: len(chunks))
        resp = client.post("/index")
        assert resp.status_code == 200
        assert resp.json() == {"indexed": 1, "status": "ok"}


class TestStartupIndexing:
    def test_skips_when_collection_populated(self, monkeypatch):
        monkeypatch.setattr(api, "collection_count", lambda persist_dir=None: 12)
        parse = MagicMock()
        monkeypatch.setattr(api, "parse_all_files", parse)
        with TestClient(api.app):
            pass
        parse.assert_not_called()

    def test_indexing_failure_does_not_block_startup(self, monkeypatch):
        def boom(persist_dir=None):
            raise RuntimeError("OPENAI_API_KEY is not set")

        monkeypatch.setattr(api, "collection_count", boom)
        with TestClient(api.app) as c:
            assert c.get("/health").status_code == 200

    def test_indexes_when_collection_empty(self, monkeypatch, sample_chunk):
        monkeypatch.setattr(api, "collection_count", lambda persist_dir=None: 0)
        monkeypatch.setattr(api, "parse_all_files", lambda d: [sample_chunk])
        index = MagicMock(return_value=1)
        monkeypatch.setattr(api, "index_chunks", index)
        with TestClient(api.app):
            pass
        index.assert_called_once()
