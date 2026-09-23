"""Stage 13: request validation on the conversation API.

A question longer than ``question_max_chars`` and an oversized or malformed
session id are refused with 422 before the agent runs, and the refusal never
repeats what was sent. Offline and free: hashing embedder, mock provider.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent.agent import KnowledgeAgent
from app.api.routes.conversation import (
    QUESTION_TOO_LONG,
    SESSION_ID_MAX_LENGTH,
    UPSTREAM_FAILURE,
)
from app.conversation.models import ConversationAnswer
from app.conversation.service import ConversationService
from app.conversation.store import SESSION_ID_BYTES, InMemorySessionStore
from app.core.config import Settings
from app.core.logging import reset_logging
from app.main import create_app
from app.rag.embeddings import EmbeddingError

LIMIT = 40
BASE_QUESTION = "Status of TXN-19990101-000001?"
SECRET_DETAIL = "model cache at C:/internal/path token=abc"


class RecordingService(ConversationService):
    """The real service, remembering every question that reached it."""

    def __init__(self, agent: KnowledgeAgent, settings: Settings) -> None:
        super().__init__(agent, InMemorySessionStore.from_settings(settings), settings)
        self.asked: list[str] = []

    def ask(self, session_id: str, question: str) -> ConversationAnswer:
        self.asked.append(question)
        return super().ask(session_id, question)


@pytest.fixture
def limited_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        embedding_model="hashing",
        vectorstore_dir=tmp_path / "vectorstore",
        llm_provider="mock",
        log_dir=tmp_path / "logs",
        log_to_file=False,
        question_max_chars=LIMIT,
        rate_limit_per_minute=0,
    )


@pytest.fixture
def service(tool_agent: KnowledgeAgent, limited_settings: Settings) -> RecordingService:
    return RecordingService(tool_agent, limited_settings)


@pytest.fixture
def api(limited_settings: Settings, service: RecordingService) -> Iterator[TestClient]:
    reset_logging()
    with TestClient(create_app(limited_settings, conversation_service=service)) as c:
        yield c
    reset_logging()


def start(client: TestClient) -> str:
    response = client.post("/api/sessions")
    assert response.status_code == 201
    session_id: str = response.json()["session_id"]
    return session_id


def padded(length: int) -> str:
    question = BASE_QUESTION + " " * (length - len(BASE_QUESTION) - 1) + "?"
    assert len(question) == length
    return question


class TestQuestionLength:
    def test_a_question_at_the_limit_is_answered(self, api, service):
        question = padded(LIMIT)
        response = api.post(
            "/api/sessions/ask", json={"session_id": start(api), "question": question}
        )
        assert response.status_code == 200, response.text
        assert service.asked == [question]

    def test_one_character_over_is_rejected_before_the_agent(self, api, service):
        response = api.post(
            "/api/sessions/ask",
            json={"session_id": start(api), "question": padded(LIMIT + 1)},
        )
        assert response.status_code == 422
        assert response.json() == {"detail": QUESTION_TOO_LONG.format(limit=LIMIT)}
        assert service.asked == []

    def test_the_refusal_does_not_echo_the_question(self, api):
        marker = "ZEBRA-" + "q" * 200
        response = api.post(
            "/api/sessions/ask", json={"session_id": start(api), "question": marker}
        )
        assert response.status_code == 422
        assert "ZEBRA" not in response.text

    def test_a_rejected_question_records_no_turn(self, api):
        session_id = start(api)
        api.post(
            "/api/sessions/ask",
            json={"session_id": session_id, "question": padded(LIMIT + 5)},
        )
        turns = api.post("/api/sessions/turns", json={"session_id": session_id})
        assert turns.json() == {"turns": []}

    def test_the_default_limit_applies_without_configuration(self):
        assert Settings(environment="test").question_max_chars == 2000


class TestSessionId:
    def test_real_ids_fit_the_bound_with_headroom(self):
        real = secrets.token_urlsafe(SESSION_ID_BYTES)
        assert len(real) < SESSION_ID_MAX_LENGTH

    def test_a_real_id_is_accepted(self, api):
        response = api.post("/api/sessions/turns", json={"session_id": start(api)})
        assert response.status_code == 200

    @pytest.mark.parametrize("path", ["/api/sessions/turns", "/api/sessions/end"])
    def test_an_oversized_id_is_rejected_at_validation(self, api, path):
        huge = "a" * (SESSION_ID_MAX_LENGTH + 1)
        response = api.post(path, json={"session_id": huge})
        assert response.status_code == 422

    def test_an_oversized_id_is_rejected_on_ask(self, api, service):
        response = api.post(
            "/api/sessions/ask",
            json={"session_id": "a" * 10_000, "question": BASE_QUESTION},
        )
        assert response.status_code == 422
        assert service.asked == []

    @pytest.mark.parametrize(
        "bad", ["has space", "semi;colon", "line\nbreak", "slash/id", "dot.id"]
    )
    def test_a_non_url_safe_id_is_rejected(self, api, bad):
        response = api.post("/api/sessions/turns", json={"session_id": bad})
        assert response.status_code == 422

    def test_an_unknown_well_formed_id_is_still_404(self, api):
        response = api.post("/api/sessions/turns", json={"session_id": "x" * 43})
        assert response.status_code == 404


class TestValidationErrorBody:
    """Stage 14 (carried from 13): a 422 names the field, never the value sent."""

    MARKER = "ZEBRA-marker"

    def test_a_bad_session_id_is_not_echoed(self, api):
        response = api.post(
            "/api/sessions/turns", json={"session_id": f"has space {self.MARKER}"}
        )
        assert response.status_code == 422
        assert self.MARKER not in response.text

    def test_a_wrong_type_is_not_echoed(self, api):
        response = api.post(
            "/api/sessions/ask",
            json={"session_id": start(api), "question": {"x": self.MARKER}},
        )
        assert response.status_code == 422
        assert self.MARKER not in response.text

    def test_each_error_keeps_location_message_and_type_only(self, api):
        response = api.post("/api/sessions/turns", json={"session_id": "has space"})
        detail = response.json()["detail"]
        assert detail, "a 422 must still say what was wrong"
        for error in detail:
            assert "input" not in error
            assert "ctx" not in error
            assert {"loc", "msg", "type"} <= error.keys()
            assert error["loc"] == ["body", "session_id"]

    def test_malformed_json_is_not_echoed(self, api):
        response = api.post(
            "/api/sessions/turns",
            content=f'{{"session_id": "{self.MARKER}"',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        assert self.MARKER not in response.text


class FailingEmbedService(RecordingService):
    """A service whose question cannot be embedded mid-turn."""

    def ask(self, session_id: str, question: str) -> ConversationAnswer:
        self.store.turns(session_id)
        raise EmbeddingError(SECRET_DETAIL)


class TestEmbeddingFailure:
    def test_is_502_with_the_fixed_message_and_no_detail(
        self, tool_agent, limited_settings, tmp_path
    ):
        service = FailingEmbedService(tool_agent, limited_settings)
        reset_logging()
        with TestClient(
            create_app(limited_settings, conversation_service=service)
        ) as client:
            session_id = start(client)
            response = client.post(
                "/api/sessions/ask",
                json={"session_id": session_id, "question": BASE_QUESTION},
            )
            turns = client.post("/api/sessions/turns", json={"session_id": session_id})
        reset_logging()
        assert response.status_code == 502
        assert response.json() == {"detail": UPSTREAM_FAILURE}
        assert SECRET_DETAIL not in response.text
        assert turns.json() == {"turns": []}
