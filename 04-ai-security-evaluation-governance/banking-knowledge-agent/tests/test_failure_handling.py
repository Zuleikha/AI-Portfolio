"""Stage 13 (U5): what happens when the model, a tool or the code itself fails.

Pinned here:

* an unhandled exception still becomes a 500, but that 500 now carries the
  request's ``X-Request-ID`` and a fixed JSON body, and the exception still
  reaches the server (HANDOVER Stage 10 item 4);
* a generation the provider marked as an error is withheld, like a truncated one;
* a reply the adapter cannot parse is a response error, not an unmapped one;
* no LLM error message repeats the provider's own wording;
* a model or tool failure mid-turn records nothing and is counted.

Offline and free: fake SDK clients, the mock provider, the hashing embedder.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Iterator
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.agent.agent import KnowledgeAgent
from app.api.middleware import RequestContextMiddleware
from app.api.routes.conversation import UPSTREAM_FAILURE
from app.conversation.models import ConversationAnswer
from app.conversation.service import ConversationService
from app.conversation.store import InMemorySessionStore
from app.core.config import Settings
from app.core.observability import REQUEST_ID_HEADER, get_metrics, reset_metrics
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import (
    LLMConnectionError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from app.llm.mock import MockLLMProvider
from app.llm.models import CompletionRequest, LLMMessage, LLMResponse
from app.llm.openai_provider import OpenAIProvider
from app.llm.service import LLMService
from app.main import create_app
from app.mcp.models import ToolResult
from app.mcp.registry import ToolRegistry
from app.rag.retriever import Retriever

KNOWLEDGE_QUESTION = "What component handles card authentication?"
TOOL_QUESTION = "Status of TXN-19990101-000001?"
PROVIDER_DETAIL = "provider-said-internal-host-db7 token=abc"
SERVER_ERROR_BODY = {"detail": "Internal Server Error"}


@pytest.fixture(autouse=True)
def fresh_metrics() -> Iterator[None]:
    reset_metrics()
    yield
    reset_metrics()


def counters() -> dict[str, int]:
    return get_metrics().snapshot()["counters"]


# --- The 500 carries the request id -----------------------------------------


class CrashingService(ConversationService):
    """A service with a bug: every question raises an untyped error."""

    def ask(self, session_id: str, question: str) -> ConversationAnswer:
        raise RuntimeError(PROVIDER_DETAIL)


def crash(client: TestClient, request_id: str = "req-crash"):
    session = client.post("/api/sessions").json()["session_id"]
    return client.post(
        "/api/sessions/ask",
        json={"session_id": session, "question": KNOWLEDGE_QUESTION},
        headers={REQUEST_ID_HEADER: request_id},
    )


class TestUnhandledErrorResponse:
    @pytest.fixture
    def crashing_app(self, tool_agent: KnowledgeAgent, llm_settings: Settings):
        return create_app(
            llm_settings, conversation_service=CrashingService(tool_agent)
        )

    def test_the_500_carries_the_request_id(self, crashing_app):
        with TestClient(crashing_app, raise_server_exceptions=False) as client:
            response = crash(client)
        assert response.status_code == 500
        assert response.headers[REQUEST_ID_HEADER] == "req-crash"

    def test_the_500_body_is_fixed_and_leaks_nothing(self, crashing_app):
        with TestClient(crashing_app, raise_server_exceptions=False) as client:
            response = crash(client)
        assert response.json() == SERVER_ERROR_BODY
        assert PROVIDER_DETAIL not in response.text
        assert "RuntimeError" not in response.text

    def test_the_500_is_counted_once(self, crashing_app):
        with TestClient(crashing_app, raise_server_exceptions=False) as client:
            crash(client)
        assert counters()["http_errors_total"] == 1

    def test_the_exception_still_reaches_the_server(self, crashing_app):
        """Fail loud: the server (and a default TestClient) still sees it."""
        with TestClient(crashing_app) as client, pytest.raises(RuntimeError):
            crash(client)


class RecordingSend:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def __call__(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


async def _receive() -> dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


def http_scope(request_id: str) -> dict[str, Any]:
    return {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "headers": [(REQUEST_ID_HEADER.lower().encode(), request_id.encode())],
    }


class TestMiddlewareDirectly:
    @pytest.mark.anyio
    async def test_a_failure_before_the_response_sends_one_json_500(self):
        async def broken(scope, receive, send):
            raise KeyError("boom")

        send = RecordingSend()
        with pytest.raises(KeyError):
            await RequestContextMiddleware(broken)(http_scope("req-7"), _receive, send)

        starts = [m for m in send.messages if m["type"] == "http.response.start"]
        assert len(starts) == 1
        assert starts[0]["status"] == 500
        headers = {k.decode().lower(): v.decode() for k, v in starts[0]["headers"]}
        assert headers[REQUEST_ID_HEADER.lower()] == "req-7"
        assert headers["content-type"].startswith("application/json")
        body = b"".join(
            m.get("body", b"")
            for m in send.messages
            if m["type"] == "http.response.body"
        )
        assert json.loads(body) == SERVER_ERROR_BODY

    @pytest.mark.anyio
    async def test_a_failure_after_the_response_started_sends_nothing_more(self):
        async def half(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            raise KeyError("boom")

        send = RecordingSend()
        with pytest.raises(KeyError):
            await RequestContextMiddleware(half)(http_scope("req-8"), _receive, send)

        assert [m["type"] for m in send.messages] == ["http.response.start"]
        assert send.messages[0]["status"] == 200
        assert counters().get("http_errors_total", 0) == 0


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --- The service withholds unusable generations -------------------------------


class TestServiceValidation:
    def test_an_error_stop_reason_is_withheld_even_with_text(
        self, llm_settings: Settings, retrieval
    ):
        """Text that ended in an error is not a finished answer."""
        partial = LLMResponse(
            text="The daily limit is set in",
            provider_id="mock",
            model_id="m",
            stop_reason="error",
        )
        service = LLMService(MockLLMProvider(responses=[partial]), llm_settings)
        with pytest.raises(LLMResponseError):
            service.answer(retrieval.query, retrieval)
        assert counters()["llm_errors_total"] == 1

    def test_an_untyped_failure_message_omits_the_raw_text(
        self, llm_settings: Settings, retrieval
    ):
        def handler(_request: object) -> object:
            raise KeyError(PROVIDER_DETAIL)

        service = LLMService(MockLLMProvider(handler=handler), llm_settings)
        with pytest.raises(LLMProviderError) as excinfo:
            service.answer(retrieval.query, retrieval)
        assert "KeyError" in str(excinfo.value)
        assert PROVIDER_DETAIL not in str(excinfo.value)
        assert isinstance(excinfo.value.__cause__, KeyError)


# --- Adapters: malformed replies and provider wording --------------------------


def completion_request() -> CompletionRequest:
    return CompletionRequest(
        system="Frozen system instructions.",
        messages=(LLMMessage(role="user", content="Question: why?"),),
        max_tokens=256,
    )


class FakeAnthropic:
    def __init__(self, reply: Any = None, raises: Exception | None = None) -> None:
        def create(**_kwargs: Any) -> Any:
            if raises is not None:
                raise raises
            return reply

        self.messages = type("Messages", (), {"create": staticmethod(create)})()


class FakeOpenAI:
    def __init__(self, reply: Any = None, raises: Exception | None = None) -> None:
        def create(**_kwargs: Any) -> Any:
            if raises is not None:
                raise raises
            return reply

        completions = type("Completions", (), {"create": staticmethod(create)})()
        self.chat = type("Chat", (), {"completions": completions})()


ADAPTERS = [
    pytest.param(AnthropicProvider, FakeAnthropic, "anthropic", id="anthropic"),
    pytest.param(OpenAIProvider, FakeOpenAI, "openai", id="openai"),
]


def _http_request() -> httpx2.Request:
    return httpx2.Request("POST", "https://example.invalid/v1")


class TestMalformedReplies:
    def test_anthropic_content_that_is_not_a_list(self, llm_settings: Settings):
        reply = type(
            "Message", (), {"content": None, "stop_reason": "end_turn", "model": "m"}
        )()
        provider = AnthropicProvider(llm_settings, client=FakeAnthropic(reply))
        with pytest.raises(LLMResponseError) as excinfo:
            provider.complete(completion_request())
        assert excinfo.value.retryable is False
        assert isinstance(excinfo.value.__cause__, TypeError)

    def test_openai_choice_without_a_message(self, llm_settings: Settings):
        choice = type("Choice", (), {"message": None, "finish_reason": "stop"})()
        reply = type("Completion", (), {"choices": [choice], "model": "m"})()
        provider = OpenAIProvider(llm_settings, client=FakeOpenAI(reply))
        with pytest.raises(LLMResponseError) as excinfo:
            provider.complete(completion_request())
        assert isinstance(excinfo.value.__cause__, AttributeError)

    @pytest.mark.parametrize(("cls", "fake", "sdk"), ADAPTERS)
    def test_a_reply_that_is_not_an_sdk_object(self, llm_settings, cls, fake, sdk):
        provider = cls(llm_settings, client=fake(object()))
        with pytest.raises(LLMResponseError):
            provider.complete(completion_request())


class TestProviderWordingIsNotRepeated:
    @pytest.mark.parametrize(("cls", "fake", "sdk"), ADAPTERS)
    @pytest.mark.parametrize(
        ("error", "code", "expected"),
        [
            ("RateLimitError", 429, LLMRateLimitError),
            ("InternalServerError", 500, LLMConnectionError),
            ("BadRequestError", 400, LLMProviderError),
            ("NotFoundError", 404, Exception),
        ],
    )
    def test_status_errors(self, llm_settings, cls, fake, sdk, error, code, expected):
        module = importlib.import_module(sdk)
        response = httpx2.Response(code, request=_http_request())
        exc = getattr(module, error)(PROVIDER_DETAIL, response=response, body=None)
        with pytest.raises(expected) as excinfo:
            cls(llm_settings, client=fake(raises=exc)).complete(completion_request())
        message = str(excinfo.value)
        assert PROVIDER_DETAIL not in message
        assert str(code) in message or error in message
        assert excinfo.value.__cause__ is exc

    @pytest.mark.parametrize(("cls", "fake", "sdk"), ADAPTERS)
    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            ("APITimeoutError", LLMTimeoutError),
            ("APIConnectionError", LLMConnectionError),
        ],
    )
    def test_transport_errors(self, llm_settings, cls, fake, sdk, error, expected):
        module = importlib.import_module(sdk)
        if error == "APITimeoutError":
            exc = module.APITimeoutError(request=_http_request())
            exc.args = (PROVIDER_DETAIL,)
        else:
            exc = module.APIConnectionError(
                message=PROVIDER_DETAIL, request=_http_request()
            )
        with pytest.raises(expected) as excinfo:
            cls(llm_settings, client=fake(raises=exc)).complete(completion_request())
        assert PROVIDER_DETAIL not in str(excinfo.value)

    @pytest.mark.parametrize(("cls", "fake", "sdk"), ADAPTERS)
    def test_an_unmapped_exception(self, llm_settings, cls, fake, sdk):
        exc = ValueError(PROVIDER_DETAIL)
        with pytest.raises(LLMProviderError) as excinfo:
            cls(llm_settings, client=fake(raises=exc)).complete(completion_request())
        assert "ValueError" in str(excinfo.value)
        assert PROVIDER_DETAIL not in str(excinfo.value)


# --- Mid-turn failures through the API ----------------------------------------


class ExplodingTransactionTool:
    """The real transaction tool's spec, with an implementation bug."""

    def __init__(self, spec: Any) -> None:
        self.spec = spec

    def invoke(self, arguments: object) -> ToolResult:
        raise KeyError(PROVIDER_DETAIL)


def api_for(agent: KnowledgeAgent, settings: Settings) -> TestClient:
    service = ConversationService(
        agent, InMemorySessionStore.from_settings(settings), settings
    )
    return TestClient(create_app(settings, conversation_service=service))


def ask_and_list(client: TestClient, question: str):
    session = client.post("/api/sessions").json()["session_id"]
    response = client.post(
        "/api/sessions/ask",
        json={"session_id": session, "question": question},
        headers={REQUEST_ID_HEADER: "req-upstream"},
    )
    turns = client.post("/api/sessions/turns", json={"session_id": session}).json()
    return response, turns["turns"]


class TestMidTurnFailures:
    def test_a_model_failure_after_retrieval(
        self, retriever: Retriever, llm_settings: Settings, tool_registry: ToolRegistry
    ):
        def handler(_request: object) -> object:
            raise LLMTimeoutError(PROVIDER_DETAIL)

        llm = LLMService(MockLLMProvider(handler=handler), llm_settings)
        agent = KnowledgeAgent(retriever, llm, llm_settings, tools=tool_registry)
        with api_for(agent, llm_settings) as client:
            response, turns = ask_and_list(client, KNOWLEDGE_QUESTION)

        assert response.status_code == 502
        assert response.json() == {"detail": UPSTREAM_FAILURE}
        assert response.headers[REQUEST_ID_HEADER] == "req-upstream"
        assert PROVIDER_DETAIL not in response.text
        assert turns == []
        assert counters()["llm_errors_total"] == 1

    def test_a_model_failure_after_a_tool_ran(
        self, retriever: Retriever, llm_settings: Settings, tool_registry: ToolRegistry
    ):
        """Tools already ran; they are read-only, and nothing is recorded."""

        def handler(_request: object) -> object:
            raise LLMRateLimitError(PROVIDER_DETAIL, retry_after_seconds=3.0)

        llm = LLMService(MockLLMProvider(handler=handler), llm_settings)
        agent = KnowledgeAgent(retriever, llm, llm_settings, tools=tool_registry)
        with api_for(agent, llm_settings) as client:
            response, turns = ask_and_list(client, TOOL_QUESTION)

        assert response.status_code == 502
        assert turns == []
        assert counters()["tool_calls_total"] >= 1
        assert counters().get("tool_errors_total", 0) == 0
        assert counters()["llm_errors_total"] == 1

    def test_a_tool_bug_aborts_the_turn_before_the_model(
        self,
        retriever: Retriever,
        llm_settings: Settings,
        tool_registry: ToolRegistry,
    ):
        spec = tool_registry.get("check_transaction_status").spec
        registry = ToolRegistry((ExplodingTransactionTool(spec),))
        provider = MockLLMProvider()
        llm = LLMService(provider, llm_settings)
        agent = KnowledgeAgent(retriever, llm, llm_settings, tools=registry)
        with api_for(agent, llm_settings) as client:
            response, turns = ask_and_list(client, TOOL_QUESTION)

        assert response.status_code == 502
        assert response.json() == {"detail": UPSTREAM_FAILURE}
        assert PROVIDER_DETAIL not in response.text
        assert turns == []
        assert provider.call_count == 0
        assert counters()["tool_errors_total"] == 1
        assert counters().get("llm_calls_total", 0) == 0
