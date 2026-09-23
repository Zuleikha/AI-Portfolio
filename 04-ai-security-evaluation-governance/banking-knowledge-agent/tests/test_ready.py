"""Stage 13 (carried 12.D): the readiness probe, ``GET /ready``.

``/health`` answers "is the process alive?"; ``/ready`` answers "can it serve
a question?" -- the vector index on disk matches the configured embedding
model, and the configured LLM provider is usable. Every check is offline: no
network, no paid call, no embedding model load.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.logging import reset_logging
from app.knowledge.models import DocumentMetadata
from app.main import create_app
from app.rag.embeddings import HashingEmbedder
from app.rag.models import Chunk, EmbeddedChunk
from app.rag.vectorstore import (
    CHUNKS_FILENAME,
    MANIFEST_FILENAME,
    VECTORS_FILENAME,
    InMemoryVectorStore,
)

SECRET_TEXT = "internal-host-10.0.0.7 token=abc"


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "embedding_model": "hashing",
        "vectorstore_dir": tmp_path / "vectorstore",
        "llm_provider": "mock",
        "log_dir": tmp_path / "logs",
        "log_to_file": False,
    }
    values.update(overrides)
    return Settings(**values)


def write_index(directory: Path) -> None:
    """Persist a one-chunk index built for the hashing embedder."""
    embedder = HashingEmbedder()
    chunk = Chunk(
        chunk_id="doc-a#0",
        document_id="doc-a",
        ordinal=0,
        heading="Section",
        content="Card authentication.",
        metadata=DocumentMetadata(
            document_id="doc-a",
            title="Title",
            domain="cards",
            component="CardAuth",
            version="1.0",
            doc_type="reference",
        ),
        source_path="cards/doc-a.md",
        token_count=2,
    )
    vector = embedder.embed_query("Card authentication.")
    store = InMemoryVectorStore(embedder.model_id, embedder.dimension)
    store.add([EmbeddedChunk(chunk=chunk, embedding=tuple(float(v) for v in vector))])
    store.save(directory, corpus_fingerprint="test")


def edit_manifest(directory: Path, **changes: Any) -> None:
    path = directory / MANIFEST_FILENAME
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update(changes)
    path.write_text(json.dumps(manifest), encoding="utf-8")


@pytest.fixture
def index_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "vectorstore"
    write_index(directory)
    return directory


def client_for(settings: Settings) -> Iterator[TestClient]:
    reset_logging()
    app = create_app(settings)
    with TestClient(app) as client:
        yield client
    # The probe must never build the conversation service (model + index).
    assert app.state.conversation is None
    reset_logging()


@pytest.fixture
def ready_client(tmp_path: Path, index_dir: Path) -> Iterator[TestClient]:
    yield from client_for(make_settings(tmp_path))


def get_ready(settings: Settings) -> Any:
    reset_logging()
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/ready")
    assert app.state.conversation is None
    reset_logging()
    return response


class TestReady:
    def test_all_checks_pass(self, ready_client):
        response = ready_client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ready",
            "checks": {"vectorstore": "ok", "llm": "ok"},
        }

    def test_ready_is_in_the_openapi_schema(self, ready_client):
        assert "/ready" in ready_client.get("/openapi.json").json()["paths"]

    def test_ready_is_open_when_an_api_key_is_configured(self, tmp_path, index_dir):
        settings = make_settings(tmp_path, api_key=SecretStr("s3cret-key"))
        response = get_ready(settings)
        assert response.status_code == 200

    def test_health_is_unchanged(self, ready_client):
        assert ready_client.get("/health").json()["status"] == "ok"


class TestVectorstoreCheck:
    def failed(self, response: Any) -> None:
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["checks"] == {"vectorstore": "failed", "llm": "ok"}

    def test_missing_index(self, tmp_path):
        self.failed(get_ready(make_settings(tmp_path)))

    def test_index_built_by_another_model(self, tmp_path, index_dir):
        edit_manifest(index_dir, model_id="some-other-model")
        self.failed(get_ready(make_settings(tmp_path)))

    def test_index_for_a_different_configured_model(self, tmp_path, index_dir):
        settings = make_settings(tmp_path, embedding_model="org/other-model")
        self.failed(get_ready(settings))

    def test_old_format_version(self, tmp_path, index_dir):
        edit_manifest(index_dir, format_version=0)
        self.failed(get_ready(make_settings(tmp_path)))

    def test_manifest_is_not_json(self, tmp_path, index_dir):
        (index_dir / MANIFEST_FILENAME).write_text("{not json", encoding="utf-8")
        self.failed(get_ready(make_settings(tmp_path)))

    def test_manifest_is_not_an_object(self, tmp_path, index_dir):
        (index_dir / MANIFEST_FILENAME).write_text("[1, 2]", encoding="utf-8")
        self.failed(get_ready(make_settings(tmp_path)))

    @pytest.mark.parametrize("name", [VECTORS_FILENAME, CHUNKS_FILENAME])
    def test_missing_data_file(self, tmp_path, index_dir, name):
        (index_dir / name).unlink()
        self.failed(get_ready(make_settings(tmp_path)))

    def test_vector_count_disagrees_with_manifest(self, tmp_path, index_dir):
        edit_manifest(index_dir, chunk_count=7)
        self.failed(get_ready(make_settings(tmp_path)))

    def test_vector_width_disagrees_with_manifest(self, tmp_path, index_dir):
        edit_manifest(index_dir, dimension=12)
        self.failed(get_ready(make_settings(tmp_path)))

    def test_empty_index(self, tmp_path):
        directory = tmp_path / "vectorstore"
        embedder = HashingEmbedder()
        InMemoryVectorStore(embedder.model_id, embedder.dimension).save(
            directory, corpus_fingerprint="empty"
        )
        self.failed(get_ready(make_settings(tmp_path)))

    def test_corrupt_vectors_file(self, tmp_path, index_dir):
        (index_dir / VECTORS_FILENAME).write_bytes(b"not a numpy file")
        self.failed(get_ready(make_settings(tmp_path)))

    def test_real_model_id_is_compared_without_loading_it(
        self, tmp_path, index_dir, monkeypatch
    ):
        def boom(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("the embedding model must not be loaded")

        monkeypatch.setattr(
            "app.rag.embeddings.SentenceTransformerEmbedder._loaded", boom
        )
        edit_manifest(index_dir, model_id="org/real-model")
        settings = make_settings(tmp_path, embedding_model="org/real-model")
        response = get_ready(settings)
        assert response.status_code == 200


class TestLlmCheck:
    @pytest.mark.parametrize("provider", ["anthropic", "openai"])
    def test_paid_provider_without_key_is_not_ready(
        self, tmp_path, index_dir, provider
    ):
        response = get_ready(make_settings(tmp_path, llm_provider=provider))
        assert response.status_code == 503
        assert response.json()["checks"] == {"vectorstore": "ok", "llm": "failed"}

    @pytest.mark.parametrize("provider", ["anthropic", "openai"])
    def test_paid_provider_with_blank_key_is_not_ready(
        self, tmp_path, index_dir, provider
    ):
        settings = make_settings(
            tmp_path, llm_provider=provider, llm_api_key=SecretStr("   ")
        )
        assert get_ready(settings).status_code == 503

    @pytest.mark.parametrize("provider", ["anthropic", "openai"])
    def test_paid_provider_with_key_is_ready_without_any_call(
        self, tmp_path, index_dir, provider, monkeypatch
    ):
        def no_build(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("the probe must not build a provider")

        monkeypatch.setattr("app.llm.factory.get_provider", no_build)
        monkeypatch.setattr("app.llm.factory._build_paid_provider", no_build)
        settings = make_settings(
            tmp_path, llm_provider=provider, llm_api_key=SecretStr("sk-test")
        )
        response = get_ready(settings)
        assert response.status_code == 200
        assert "sk-test" not in response.text

    def test_paid_provider_whose_sdk_is_missing_is_not_ready(
        self, tmp_path, index_dir, monkeypatch
    ):
        monkeypatch.setattr("importlib.util.find_spec", lambda _name: None)
        settings = make_settings(
            tmp_path, llm_provider="openai", llm_api_key=SecretStr("sk-test")
        )
        assert get_ready(settings).status_code == 503

    def test_unknown_provider_is_not_ready(self, tmp_path, index_dir):
        response = get_ready(make_settings(tmp_path, llm_provider="nope"))
        assert response.status_code == 503
        assert response.json()["checks"]["llm"] == "failed"


class TestNoLeaks:
    def test_body_and_log_carry_no_exception_text(
        self, tmp_path, index_dir, monkeypatch
    ):
        def explode(_settings: Settings) -> None:
            raise RuntimeError(SECRET_TEXT)

        monkeypatch.setattr("app.api.routes.health.check_vectorstore", explode)
        settings = make_settings(
            tmp_path, log_to_file=True, log_format="json", log_level="DEBUG"
        )
        response = get_ready(settings)
        assert response.status_code == 503
        assert response.json() == {
            "status": "not_ready",
            "checks": {"vectorstore": "failed", "llm": "ok"},
        }
        assert SECRET_TEXT not in response.text

        log_text = "".join(
            path.read_text(encoding="utf-8")
            for path in (tmp_path / "logs").glob("*")
            if path.is_file()
        )
        assert "api.ready_check_failed" in log_text
        assert "RuntimeError" in log_text
        assert SECRET_TEXT not in log_text

    def test_failure_body_never_names_the_index_path(self, tmp_path):
        response = get_ready(make_settings(tmp_path))
        assert str(tmp_path) not in response.text
        assert "vectorstore\\" not in response.text
