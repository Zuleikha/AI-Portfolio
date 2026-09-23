"""Integration tests for FastAPI routes using a mocked pipeline and ingestor."""

import io
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import src.api.main as main_module
from src.ingestion.ingest import IngestionResult
from src.rag.pipeline import RAGResponse

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_pipeline():
    p = MagicMock()
    p.document_count = 5
    p.store.get_all_documents.return_value = [
        {"content": "text about Paris", "metadata": {"source": "geo.txt"}},
        {"content": "more content", "metadata": {"source": "bio.pdf"}},
    ]
    p.query = AsyncMock(
        return_value=RAGResponse(
            answer="The answer is 42 [1].",
            sources=[{"content": "context", "metadata": {"source": "geo.txt"}, "score": 0.9}],
            tokens_used=80,
            latency_ms=350.0,
            retrieval_latency_ms=100.0,
            rerank_latency_ms=50.0,
            chunks_retrieved=5,
            chunks_after_rerank=3,
        )
    )
    p.clear_conversation = MagicMock()
    return p


@pytest.fixture
def mock_ingestor():
    i = MagicMock()
    i._ingest = AsyncMock(
        return_value=IngestionResult(
            source="test.txt",
            chunks_created=4,
            characters_processed=800,
        )
    )
    i.ingest_pdf_bytes = AsyncMock(
        return_value=IngestionResult(
            source="doc.pdf",
            chunks_created=6,
            characters_processed=1500,
        )
    )
    return i


@pytest.fixture
def client(mock_pipeline, mock_ingestor):
    """TestClient backed by a mock pipeline — no real API keys are used."""

    @asynccontextmanager
    async def _lifespan(app):
        main_module.pipeline = mock_pipeline
        main_module.ingestor = mock_ingestor
        yield
        main_module.pipeline = None
        main_module.ingestor = None

    saved = main_module.app.router.lifespan_context
    main_module.app.router.lifespan_context = _lifespan

    with TestClient(main_module.app) as c:
        yield c

    main_module.app.router.lifespan_context = saved


# ── GET / ─────────────────────────────────────────────────────────────────────


class TestRootRoute:
    def test_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_body_contains_message_and_docs(self, client):
        data = client.get("/").json()
        assert "message" in data
        assert "docs" in data

    def test_docs_link_points_to_docs_path(self, client):
        data = client.get("/").json()
        assert data["docs"] == "/docs"


# ── GET /health ───────────────────────────────────────────────────────────────


class TestHealthRoute:
    def test_returns_200(self, client):
        assert client.get("/health").status_code == 200

    def test_status_is_ok(self, client):
        assert client.get("/health").json()["status"] == "ok"

    def test_contains_model_and_document_fields(self, client):
        data = client.get("/health").json()
        assert "embedding_model" in data
        assert "llm_model" in data
        assert "documents_indexed" in data

    def test_document_count_reflects_pipeline(self, client, mock_pipeline):
        mock_pipeline.document_count = 42
        assert client.get("/health").json()["documents_indexed"] == 42


# ── POST /query ───────────────────────────────────────────────────────────────


class TestQueryRoute:
    def test_valid_question_returns_200(self, client):
        r = client.post("/query", json={"question": "What is the meaning of life?"})
        assert r.status_code == 200

    def test_response_contains_required_fields(self, client):
        r = client.post("/query", json={"question": "Tell me something."})
        data = r.json()
        for field in (
            "answer",
            "sources",
            "tokens_used",
            "latency_ms",
            "retrieval_latency_ms",
            "rerank_latency_ms",
            "chunks_retrieved",
            "chunks_after_rerank",
        ):
            assert field in data, f"missing field: {field}"

    def test_pipeline_is_called_with_correct_conversation_id(self, client, mock_pipeline):
        client.post("/query", json={"question": "Hello?", "conversation_id": "sess-xyz"})
        mock_pipeline.query.assert_awaited_once()
        assert mock_pipeline.query.call_args.kwargs["conversation_id"] == "sess-xyz"

    def test_empty_question_returns_422(self, client):
        assert client.post("/query", json={"question": ""}).status_code == 422

    def test_question_exceeding_max_length_returns_422(self, client):
        assert client.post("/query", json={"question": "x" * 2001}).status_code == 422

    def test_retrieval_k_zero_returns_422(self, client):
        assert client.post("/query", json={"question": "q", "retrieval_k": 0}).status_code == 422

    def test_retrieval_k_above_50_returns_422(self, client):
        assert client.post("/query", json={"question": "q", "retrieval_k": 51}).status_code == 422

    def test_rerank_k_above_20_returns_422(self, client):
        assert client.post("/query", json={"question": "q", "rerank_k": 21}).status_code == 422

    def test_rerank_k_zero_returns_422(self, client):
        assert client.post("/query", json={"question": "q", "rerank_k": 0}).status_code == 422

    def test_valid_boundary_retrieval_k_50_is_accepted(self, client):
        r = client.post("/query", json={"question": "q", "retrieval_k": 50})
        assert r.status_code == 200

    def test_valid_boundary_rerank_k_20_is_accepted(self, client):
        r = client.post("/query", json={"question": "q", "rerank_k": 20})
        assert r.status_code == 200


# ── POST /ingest ──────────────────────────────────────────────────────────────


class TestIngestRoute:
    def test_txt_upload_returns_200(self, client):
        r = client.post(
            "/ingest",
            files=[("files", ("hello.txt", io.BytesIO(b"Hello world."), "text/plain"))],
        )
        assert r.status_code == 200

    def test_txt_response_shape(self, client):
        r = client.post(
            "/ingest",
            files=[("files", ("note.txt", io.BytesIO(b"Some content."), "text/plain"))],
        )
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert "filename" in data[0]
        assert "chunks_created" in data[0]
        assert "characters_processed" in data[0]

    def test_md_upload_succeeds(self, client):
        r = client.post(
            "/ingest",
            files=[("files", ("readme.md", io.BytesIO(b"# Title\nContent."), "text/markdown"))],
        )
        assert r.status_code == 200

    def test_pdf_upload_calls_ingest_pdf_bytes(self, client, mock_ingestor):
        client.post(
            "/ingest",
            files=[("files", ("report.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))],
        )
        mock_ingestor.ingest_pdf_bytes.assert_awaited_once()

    def test_unsupported_extension_returns_400(self, client):
        r = client.post(
            "/ingest",
            files=[("files", ("data.csv", io.BytesIO(b"a,b,c"), "text/csv"))],
        )
        assert r.status_code == 400

    def test_400_error_message_mentions_supported_types(self, client):
        r = client.post(
            "/ingest",
            files=[("files", ("x.docx", io.BytesIO(b"content"), "application/octet-stream"))],
        )
        assert r.status_code == 400
        assert "Supported" in r.json()["detail"] or "supported" in r.json()["detail"]


# ── GET /documents ────────────────────────────────────────────────────────────


class TestDocumentsRoute:
    def test_returns_200(self, client):
        assert client.get("/documents").status_code == 200

    def test_returns_list(self, client):
        assert isinstance(client.get("/documents").json(), list)

    def test_each_entry_has_name_and_chunks(self, client):
        data = client.get("/documents").json()
        for item in data:
            assert "name" in item
            assert "chunks" in item

    def test_document_sources_are_grouped(self, client):
        names = [item["name"] for item in client.get("/documents").json()]
        assert "geo.txt" in names
        assert "bio.pdf" in names


# ── GET /metrics ──────────────────────────────────────────────────────────────


class TestMetricsRoute:
    def test_returns_200(self, client):
        assert client.get("/metrics").status_code == 200

    def test_contains_expected_keys(self, client):
        data = client.get("/metrics").json()
        for key in (
            "query_count",
            "total_tokens",
            "avg_latency_ms",
            "avg_tokens_per_query",
            "errors",
            "recent_latencies_ms",
        ):
            assert key in data


# ── DELETE /conversation/{id} ─────────────────────────────────────────────────


class TestConversationRoute:
    def test_delete_existing_conversation_returns_204(self, client):
        assert client.delete("/conversation/sess-abc").status_code == 204

    def test_delete_nonexistent_conversation_returns_204(self, client):
        assert client.delete("/conversation/no-such-session").status_code == 204

    def test_delete_calls_pipeline_clear_conversation(self, client, mock_pipeline):
        client.delete("/conversation/my-session")
        mock_pipeline.clear_conversation.assert_called_once_with("my-session")
