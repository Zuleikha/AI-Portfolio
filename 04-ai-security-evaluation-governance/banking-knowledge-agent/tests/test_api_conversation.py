"""Stage 9: the conversation HTTP API and the static web page.

The real agent, the real six tools and the mock provider behind a real FastAPI
app. Offline and free. These tests pin ``docs/HANDOVER.md`` §9.A-§9.E.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.agent import KnowledgeAgent
from app.conversation.models import ConversationAnswer
from app.conversation.service import ConversationService
from app.conversation.store import InMemorySessionStore
from app.core.config import PROJECT_ROOT, Settings
from app.core.logging import reset_logging
from app.llm.base import LLMTimeoutError
from app.llm.mock import MockLLMProvider
from app.llm.service import LLMService
from app.main import create_app
from app.mcp.base import ToolExecutionError
from app.rag.models import RetrievalResult

KNOWLEDGE_QUESTION = "What component handles card authentication?"
TOOL_QUESTION = "Status of TXN-19990101-000001?"
SECRET_DETAIL = "provider said: internal-host-10.0.0.7 token=abc"

# --- Helpers ----------------------------------------------------------------


class EmptyRetriever:
    """A search that never finds anything above the floor."""

    def retrieve(self, query: str, **_kwargs: object) -> RetrievalResult:
        return RetrievalResult(
            query=query, chunks=(), candidates_considered=115, min_score=0.25
        )


class FailingService(ConversationService):
    """A service whose every question fails with a chosen exception."""

    def __init__(self, agent: KnowledgeAgent, error: Exception) -> None:
        super().__init__(agent)
        self._error = error

    def ask(self, session_id: str, question: str) -> ConversationAnswer:
        self.store.turns(session_id)
        raise self._error


def make_client(settings: Settings, service: ConversationService) -> TestClient:
    return TestClient(create_app(settings, conversation_service=service))


@pytest.fixture
def service(tool_agent: KnowledgeAgent, llm_settings: Settings) -> ConversationService:
    return ConversationService(
        tool_agent, InMemorySessionStore.from_settings(llm_settings), llm_settings
    )


@pytest.fixture
def api(llm_settings: Settings, service: ConversationService) -> Iterator[TestClient]:
    reset_logging()
    with make_client(llm_settings, service) as client:
        yield client
    reset_logging()


def start(client: TestClient) -> str:
    response = client.post("/api/sessions")
    assert response.status_code == 201
    session_id: str = response.json()["session_id"]
    return session_id


def ask(client: TestClient, session_id: str, question: str) -> dict[str, object]:
    response = client.post(
        "/api/sessions/ask", json={"session_id": session_id, "question": question}
    )
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


# --- Application wiring (§9.A) -----------------------------------------------


class TestServiceLifetime:
    def test_the_injected_service_is_kept_on_app_state(self, llm_settings, service):
        app = create_app(llm_settings, conversation_service=service)
        assert app.state.conversation is service

    def test_no_service_is_built_until_a_conversation_route_is_used(self, app):
        assert app.state.conversation is None

    def test_the_service_is_built_once_and_shared(
        self, app: FastAPI, service, monkeypatch
    ):
        calls: list[Settings] = []

        def fake_factory(settings: Settings) -> ConversationService:
            calls.append(settings)
            return service

        monkeypatch.setattr(
            "app.api.dependencies.get_conversation_service", fake_factory
        )
        with TestClient(app) as client:
            first = start(client)
            second = start(client)
        assert len(calls) == 1
        assert calls[0] is app.state.settings
        assert first != second

    def test_a_session_survives_across_requests(self, api):
        session_id = start(api)
        ask(api, session_id, TOOL_QUESTION)
        turns = api.post("/api/sessions/turns", json={"session_id": session_id})
        assert turns.status_code == 200
        assert len(turns.json()["turns"]) == 1


# --- Sessions (§9.C) ---------------------------------------------------------


class TestSessions:
    def test_starting_a_session_returns_an_unguessable_id(self, api):
        session_id = start(api)
        assert len(session_id) >= 43

    def test_a_new_session_has_no_turns(self, api):
        session_id = start(api)
        body = api.post("/api/sessions/turns", json={"session_id": session_id}).json()
        assert body == {"turns": []}

    def test_turns_are_listed_oldest_first_with_display_fields(self, api):
        session_id = start(api)
        ask(api, session_id, TOOL_QUESTION)
        ask(api, session_id, KNOWLEDGE_QUESTION)
        turns = api.post("/api/sessions/turns", json={"session_id": session_id}).json()[
            "turns"
        ]
        assert [turn["number"] for turn in turns] == [1, 2]
        assert turns[0]["question"] == TOOL_QUESTION
        assert set(turns[0]) == {
            "number",
            "question",
            "resolved_question",
            "answer_text",
            "decision",
            "refused",
        }

    def test_ending_a_session_makes_its_id_stop_working(self, api):
        session_id = start(api)
        ended = api.post("/api/sessions/end", json={"session_id": session_id})
        assert ended.status_code == 204
        after = api.post(
            "/api/sessions/ask", json={"session_id": session_id, "question": "hi"}
        )
        assert after.status_code == 404

    @pytest.mark.parametrize(
        ("path", "extra"),
        [
            ("/api/sessions/ask", {"question": TOOL_QUESTION}),
            ("/api/sessions/turns", {}),
            ("/api/sessions/end", {}),
        ],
    )
    def test_an_unknown_session_is_404_and_never_a_new_session(self, api, path, extra):
        unknown = "x" * 43
        response = api.post(path, json={"session_id": unknown, **extra})
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert "Start a new session" in detail
        assert unknown not in detail

    def test_the_session_id_is_never_part_of_a_url(self, api):
        schema = api.get("/openapi.json").json()
        for path in schema["paths"]:
            assert "{" not in path, path


# --- Asking (§9.E) -----------------------------------------------------------


class TestAsk:
    def test_a_knowledge_question_reports_that_rag_was_used(self, api):
        body = ask(api, start(api), KNOWLEDGE_QUESTION)
        assert body["rag_used"] is True
        assert body["retrieval"]["performed"] is True  # type: ignore[index]
        assert body["text"]
        assert body["turn"] == 1

    def test_a_tool_question_reports_that_mcp_was_used(self, api):
        body = ask(api, start(api), TOOL_QUESTION)
        assert body["mcp_used"] is True
        tools = body["tools"]
        assert isinstance(tools, list) and tools
        assert {"tool", "ok", "summary", "data", "error_code", "error_message"} <= set(
            tools[0]
        )

    def test_sources_consulted_matches_the_sources_returned(self, api):
        body = ask(api, start(api), KNOWLEDGE_QUESTION)
        assert body["sources_consulted"] is bool(body["sources"])

    def test_the_route_and_each_decision_step_are_returned(self, api):
        body = ask(api, start(api), TOOL_QUESTION)
        decision = body["decision"]
        assert isinstance(decision, dict)
        assert decision["reason"]
        assert decision["explanation"]
        steps = body["steps"]
        assert isinstance(steps, list)
        assert steps[0]["step"] == "plan"

    def test_a_follow_up_reports_how_it_was_resolved(self, api):
        session_id = start(api)
        ask(api, session_id, TOOL_QUESTION)
        body = ask(api, session_id, "what about TXN-19990101-000002?")
        assert body["turn"] == 2
        assert body["resolution"] == "substituted_identifier"
        assert body["is_follow_up"] is True
        assert "TXN-19990101-000002" in str(body["resolved_question"])

    def test_insufficient_evidence_is_reported(self, llm_settings, tool_registry):
        agent = KnowledgeAgent(
            EmptyRetriever(),  # type: ignore[arg-type]
            LLMService(MockLLMProvider(), llm_settings),
            llm_settings,
            tools=tool_registry,
        )
        service = ConversationService(agent, settings=llm_settings)
        with make_client(llm_settings, service) as client:
            body = ask(client, start(client), "How do I rotate the ledger keys?")
        assert body["insufficient"] is True
        assert body["sources_consulted"] is False
        assert body["llm_called"] is False

    def test_a_blank_question_is_rejected_before_the_agent(self, api):
        response = api.post(
            "/api/sessions/ask", json={"session_id": start(api), "question": "   "}
        )
        assert response.status_code == 422

    def test_a_missing_session_id_is_rejected(self, api):
        response = api.post("/api/sessions/ask", json={"question": TOOL_QUESTION})
        assert response.status_code == 422

    def test_extra_fields_are_rejected(self, api):
        response = api.post(
            "/api/sessions/ask",
            json={"session_id": start(api), "question": "hi", "history": ["x"]},
        )
        assert response.status_code == 422


# --- Failures never leak internals (§9.E) ------------------------------------


class TestFailures:
    @pytest.mark.parametrize(
        "error",
        [LLMTimeoutError(SECRET_DETAIL), ToolExecutionError(SECRET_DETAIL)],
        ids=["llm", "tool"],
    )
    def test_a_provider_or_tool_failure_is_502_with_a_fixed_message(
        self, llm_settings, tool_agent, error
    ):
        service = FailingService(tool_agent, error)
        with make_client(llm_settings, service) as client:
            session_id = start(client)
            response = client.post(
                "/api/sessions/ask",
                json={"session_id": session_id, "question": TOOL_QUESTION},
            )
        assert response.status_code == 502
        assert SECRET_DETAIL not in response.text
        assert response.json()["detail"]

    def test_a_failed_question_is_not_recorded(self, llm_settings, tool_agent):
        service = FailingService(tool_agent, LLMTimeoutError(SECRET_DETAIL))
        with make_client(llm_settings, service) as client:
            session_id = start(client)
            client.post(
                "/api/sessions/ask",
                json={"session_id": session_id, "question": TOOL_QUESTION},
            )
            turns = client.post("/api/sessions/turns", json={"session_id": session_id})
        assert turns.json() == {"turns": []}


# --- The web page (§9.D) -----------------------------------------------------

STATIC_DIR = PROJECT_ROOT / "app" / "web" / "static"


class TestWebPage:
    def test_the_page_is_served_at_the_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "Banking Knowledge Agent" in response.text

    @pytest.mark.parametrize("asset", ["app.js", "styles.css"])
    def test_the_page_assets_are_served(self, client, asset):
        assert client.get(f"/{asset}").status_code == 200

    def test_health_and_api_docs_still_win_over_static_files(self, client):
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/openapi.json").status_code == 200

    def test_the_page_shows_every_required_indicator(self):
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        for marker in (
            'id="question"',
            'id="conversation"',
            'id="error"',
        ):
            assert marker in html
        script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        for field in (
            "rag_used",
            "mcp_used",
            "sources_consulted",
            "insufficient",
            "sources",
            "tools",
            "steps",
        ):
            assert field in script

    def test_the_script_never_inserts_text_as_html(self):
        script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
            assert sink not in script

    def test_the_page_loads_nothing_from_the_network(self):
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        assert "http://" not in html
        assert "https://" not in html
