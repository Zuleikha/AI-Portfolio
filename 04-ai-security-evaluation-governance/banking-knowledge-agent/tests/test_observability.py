"""Stage 10: request ids, latency, errors and in-process metrics.

These tests pin ``docs/HANDOVER.md`` §10.A-§10.D:

* 10.A -- the question is logged as a hash and a length, never as text;
* 10.B -- in-process counters and histograms, served at ``GET /metrics``;
* 10.C -- one request id on every log and trace line of a request;
* 10.D -- an incoming ``X-Request-ID`` is used only if it is short and safe.

Offline and free: the mock provider, the hashing embedder, the six synthetic tools.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.agent import KnowledgeAgent
from app.conversation.models import ConversationAnswer
from app.conversation.service import ConversationService, session_fingerprint
from app.conversation.store import InMemorySessionStore
from app.core.config import Settings
from app.core.logging import (
    APP_LOG_FILENAME,
    TRACE_LOG_FILENAME,
    configure_logging,
    get_logger,
    reset_logging,
)
from app.core.observability import (
    FINGERPRINT_LENGTH,
    HISTOGRAM_BUCKETS_MS,
    MAX_REQUEST_ID_LENGTH,
    REQUEST_ID_HEADER,
    Metrics,
    fingerprint,
    get_metrics,
    reset_metrics,
    resolve_request_id,
)
from app.llm.base import LLMTimeoutError
from app.llm.mock import MockLLMProvider
from app.llm.service import LLMService
from app.main import create_app
from app.mcp.base import ToolExecutionError
from app.mcp.models import ToolParameter, ToolResult, ToolSpec
from app.mcp.registry import ToolRegistry
from app.rag.retriever import Retriever

KNOWLEDGE_QUESTION = "What component handles card authentication?"
TOOL_QUESTION = "Status of TXN-19990101-000001?"
SAFE_ID = re.compile(r"^[A-Za-z0-9-]+$")

# --- Helpers ----------------------------------------------------------------


def records(path: Path, event: str | None = None) -> list[dict[str, Any]]:
    """Parse a JSON-lines log file, optionally keeping one event name."""
    if not path.exists():
        return []
    parsed = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    return [r for r in parsed if event is None or r["event"] == event]


class CrashingService(ConversationService):
    """A service with a bug: every question raises an untyped error."""

    def ask(self, session_id: str, question: str) -> ConversationAnswer:
        raise RuntimeError("a bug nobody anticipated")


class ExplodingTool:
    """A tool whose implementation raises something untyped."""

    spec = ToolSpec(
        name="look_up_error_code",
        summary="A stub.",
        description="A stub tool used to test failure logging.",
        parameters=(
            ToolParameter(name="error_code", description="A code.", example="X-1"),
        ),
    )

    def invoke(self, arguments: object) -> ToolResult:
        raise KeyError("boom")


@pytest.fixture(autouse=True)
def fresh_metrics() -> Iterator[None]:
    reset_metrics()
    yield
    reset_metrics()


@pytest.fixture
def log_settings(llm_settings: Settings, tmp_path: Path) -> Iterator[Settings]:
    configured = llm_settings.model_copy(
        update={
            "log_dir": tmp_path / "logs",
            "log_to_file": True,
            "log_format": "json",
        }
    )
    reset_logging()
    configure_logging(configured)
    yield configured
    reset_logging()


@pytest.fixture
def app_log(log_settings: Settings) -> Path:
    return log_settings.log_dir / APP_LOG_FILENAME


@pytest.fixture
def trace_log(log_settings: Settings) -> Path:
    return log_settings.log_dir / TRACE_LOG_FILENAME


@pytest.fixture
def api(tool_agent: KnowledgeAgent, log_settings: Settings) -> Iterator[TestClient]:
    service = ConversationService(
        tool_agent, InMemorySessionStore.from_settings(log_settings), log_settings
    )
    with TestClient(create_app(log_settings, conversation_service=service)) as client:
        yield client


def ask(client: TestClient, question: str) -> tuple[dict[str, Any], str]:
    session = client.post("/api/sessions").json()["session_id"]
    response = client.post(
        "/api/sessions/ask", json={"session_id": session, "question": question}
    )
    assert response.status_code == 200, response.text
    return response.json(), response.headers[REQUEST_ID_HEADER]


# --- 10.D: the request id ----------------------------------------------------


class TestResolveRequestId:
    def test_a_short_safe_incoming_id_is_kept(self):
        assert resolve_request_id("proxy-7f3a-0001") == "proxy-7f3a-0001"

    def test_the_longest_allowed_id_is_kept(self):
        incoming = "a" * MAX_REQUEST_ID_LENGTH
        assert resolve_request_id(incoming) == incoming

    @pytest.mark.parametrize(
        "incoming",
        [
            None,
            "",
            "a" * (MAX_REQUEST_ID_LENGTH + 1),
            "has space",
            "line\nbreak",
            '{"event": "forged"}',
            "semi;colon",
            "unicodé",
        ],
    )
    def test_anything_else_is_replaced_by_a_generated_id(self, incoming):
        generated = resolve_request_id(incoming)
        assert generated != incoming
        assert SAFE_ID.match(generated)
        assert len(generated) <= MAX_REQUEST_ID_LENGTH

    def test_generated_ids_are_unique(self):
        assert len({resolve_request_id(None) for _ in range(200)}) == 200


# --- 10.A: the question fingerprint ------------------------------------------


class TestFingerprint:
    def test_is_deterministic_short_and_hex(self):
        first = fingerprint(KNOWLEDGE_QUESTION)
        assert first == fingerprint(KNOWLEDGE_QUESTION)
        assert len(first) == FINGERPRINT_LENGTH
        assert re.fullmatch(r"[0-9a-f]+", first)

    def test_different_text_gives_a_different_fingerprint(self):
        assert fingerprint("a") != fingerprint("b")

    def test_the_session_fingerprint_is_the_same_function(self):
        assert session_fingerprint("abc") == fingerprint("abc")


# --- 10.B: the metrics registry -----------------------------------------------


class TestMetrics:
    def test_counters_start_at_zero_and_add_up(self):
        metrics = Metrics()
        metrics.increment("things_total")
        metrics.increment("things_total", 4)
        assert metrics.snapshot()["counters"] == {"things_total": 5}

    def test_histograms_record_count_sum_max_and_cumulative_buckets(self):
        metrics = Metrics()
        for value in (3.0, 40.0, 40.0, 999_999.0):
            metrics.observe("latency_ms", value)

        histogram = metrics.snapshot()["histograms"]["latency_ms"]
        assert histogram["count"] == 4
        assert histogram["sum_ms"] == pytest.approx(1_000_082.0)
        assert histogram["max_ms"] == pytest.approx(999_999.0)
        buckets = histogram["buckets"]
        assert list(buckets) == [f"le_{b:g}" for b in HISTOGRAM_BUCKETS_MS] + ["le_inf"]
        assert buckets["le_5"] == 1
        assert buckets["le_50"] == 3
        assert buckets[f"le_{HISTOGRAM_BUCKETS_MS[-1]:g}"] == 3
        assert buckets["le_inf"] == 4

    def test_a_snapshot_is_a_copy(self):
        metrics = Metrics()
        metrics.increment("x_total")
        snapshot = metrics.snapshot()
        metrics.increment("x_total")
        assert snapshot["counters"]["x_total"] == 1

    def test_negative_observations_are_rejected(self):
        with pytest.raises(ValueError):
            Metrics().observe("latency_ms", -1.0)

    def test_concurrent_increments_are_not_lost(self):
        metrics = Metrics()

        def work() -> None:
            for _ in range(2_000):
                metrics.increment("hits_total")

        threads = [threading.Thread(target=work) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert metrics.snapshot()["counters"]["hits_total"] == 16_000

    def test_reset_empties_the_shared_registry(self):
        get_metrics().increment("x_total")
        reset_metrics()
        assert get_metrics().snapshot() == {"counters": {}, "histograms": {}}


# --- 10.C: request middleware -------------------------------------------------


class TestRequestMiddleware:
    def test_a_request_id_is_generated_and_returned(self, api: TestClient):
        response = api.get("/health")
        assert response.status_code == 200
        assert SAFE_ID.match(response.headers[REQUEST_ID_HEADER])

    def test_a_valid_incoming_id_is_echoed(self, api: TestClient):
        response = api.get("/health", headers={REQUEST_ID_HEADER: "upstream-42"})
        assert response.headers[REQUEST_ID_HEADER] == "upstream-42"

    def test_an_unsafe_incoming_id_is_replaced_and_never_logged(
        self, api: TestClient, app_log: Path
    ):
        forged = "x" * 65
        response = api.get("/health", headers={REQUEST_ID_HEADER: forged})
        assert response.headers[REQUEST_ID_HEADER] != forged
        assert forged not in app_log.read_text("utf-8")

    def test_every_request_is_logged_with_its_shape_and_latency(
        self, api: TestClient, app_log: Path
    ):
        response = api.get("/health", headers={REQUEST_ID_HEADER: "req-1"})
        assert response.status_code == 200

        [record] = records(app_log, "http.request")
        assert record["request_id"] == "req-1"
        assert record["method"] == "GET"
        assert record["path"] == "/health"
        assert record["status"] == 200
        assert record["latency_ms"] >= 0

    def test_the_query_string_is_not_logged(self, api: TestClient, app_log: Path):
        api.get("/health?account=12345678")
        # The whole file: the httpx client logger is quietened too (§20.36).
        assert "12345678" not in app_log.read_text("utf-8")

    def test_the_request_id_does_not_leak_past_the_request(
        self, api: TestClient, app_log: Path
    ):
        api.get("/health", headers={REQUEST_ID_HEADER: "req-leak"})
        get_logger("test").info("after.request")
        [record] = records(app_log, "after.request")
        assert "request_id" not in record

    def test_an_unhandled_error_is_logged_counted_and_returns_500(
        self, tool_agent: KnowledgeAgent, log_settings: Settings, app_log: Path
    ):
        service = CrashingService(tool_agent)
        app = create_app(log_settings, conversation_service=service)
        with TestClient(app, raise_server_exceptions=False) as client:
            session = client.post("/api/sessions").json()["session_id"]
            response = client.post(
                "/api/sessions/ask",
                json={"session_id": session, "question": KNOWLEDGE_QUESTION},
                headers={REQUEST_ID_HEADER: "req-crash"},
            )

        assert response.status_code == 500
        [failure] = records(app_log, "http.request_failed")
        assert failure["request_id"] == "req-crash"
        assert failure["error_type"] == "RuntimeError"
        assert "a bug nobody anticipated" not in app_log.read_text("utf-8")
        assert get_metrics().snapshot()["counters"]["http_errors_total"] == 1


# --- One request, end to end -------------------------------------------------


class TestOneRequestEndToEnd:
    def test_every_app_and_trace_line_of_an_answer_carries_its_request_id(
        self, api: TestClient, app_log: Path, trace_log: Path
    ):
        _, request_id = ask(api, KNOWLEDGE_QUESTION)

        for event in ("rag.retrieved", "llm.answered", "agent.answered"):
            found = records(app_log, event)
            assert found, f"{event} was not logged"
            assert {r["request_id"] for r in found} == {request_id}, event

        traced_agent = [
            r
            for r in records(trace_log, "trace")
            if r["function"].endswith("KnowledgeAgent.ask")
        ]
        assert [r["request_id"] for r in traced_agent] == [request_id]

    def test_the_question_is_logged_as_hash_and_length_only(
        self, api: TestClient, app_log: Path, trace_log: Path
    ):
        ask(api, KNOWLEDGE_QUESTION)

        assert KNOWLEDGE_QUESTION not in app_log.read_text("utf-8")
        assert KNOWLEDGE_QUESTION not in trace_log.read_text("utf-8")

        [answered] = records(app_log, "agent.answered")
        assert answered["question_hash"] == fingerprint(KNOWLEDGE_QUESTION)
        assert answered["question_length"] == len(KNOWLEDGE_QUESTION)
        for retrieved in records(app_log, "rag.retrieved"):
            assert "query" not in retrieved
            assert len(retrieved["query_hash"]) == FINGERPRINT_LENGTH
            assert retrieved["query_length"] > 0

    def test_retrieval_llm_and_tool_latency_are_logged(
        self, api: TestClient, app_log: Path
    ):
        ask(api, KNOWLEDGE_QUESTION)
        ask(api, TOOL_QUESTION)

        for event in ("rag.retrieved", "llm.answered", "mcp.tool_called"):
            found = records(app_log, event)
            assert found, f"{event} was not logged"
            assert all(r["latency_ms"] >= 0 for r in found), event

    def test_metrics_endpoint_reports_the_work_done(self, api: TestClient):
        ask(api, KNOWLEDGE_QUESTION)
        ask(api, TOOL_QUESTION)

        response = api.get("/metrics")
        assert response.status_code == 200
        body = response.json()
        counters, histograms = body["counters"], body["histograms"]

        assert counters["http_requests_total"] >= 4
        assert counters["rag_retrievals_total"] >= 1
        assert counters["llm_calls_total"] >= 1
        assert counters["tool_calls_total"] >= 1
        assert counters["llm_input_tokens_total"] > 0
        for name in (
            "http_request_duration_ms",
            "rag_retrieval_duration_ms",
            "llm_call_duration_ms",
            "tool_call_duration_ms",
        ):
            assert histograms[name]["count"] >= 1, name

    def test_metrics_hold_no_content(self, api: TestClient):
        body, _ = ask(api, TOOL_QUESTION)
        text = api.get("/metrics").text
        assert TOOL_QUESTION not in text
        assert "TXN-19990101-000001" not in text
        assert str(body["text"])[:40] not in text


# --- Failures below the API ----------------------------------------------------


class TestFailuresAreLoggedAndCounted:
    def test_a_failed_llm_call(self, retrieval, log_settings: Settings, app_log: Path):
        def timeout(_request: object) -> object:
            raise LLMTimeoutError("provider said: internal-host token=abc")

        service = LLMService(MockLLMProvider(handler=timeout), log_settings)
        with pytest.raises(LLMTimeoutError):
            service.answer(KNOWLEDGE_QUESTION, retrieval)

        [failure] = records(app_log, "llm.failed")
        assert failure["error_type"] == "LLMTimeoutError"
        assert failure["latency_ms"] >= 0
        assert "token=abc" not in app_log.read_text("utf-8")
        counters = get_metrics().snapshot()["counters"]
        assert counters["llm_calls_total"] == 1
        assert counters["llm_errors_total"] == 1

    def test_a_failed_tool_call(self, log_settings: Settings, app_log: Path):
        registry = ToolRegistry((ExplodingTool(),))
        with pytest.raises(ToolExecutionError):
            registry.call("look_up_error_code", {"error_code": "SECRET-VALUE"})

        [failure] = records(app_log, "mcp.tool_failed")
        assert failure["tool"] == "look_up_error_code"
        assert failure["error_type"] == "ToolExecutionError"
        assert failure["latency_ms"] >= 0
        assert "SECRET-VALUE" not in app_log.read_text("utf-8")
        counters = get_metrics().snapshot()["counters"]
        assert counters["tool_calls_total"] == 1
        assert counters["tool_errors_total"] == 1

    def test_a_retrieval_is_counted_and_timed(
        self, retriever: Retriever, log_settings: Settings
    ):
        retriever.retrieve("card authentication")
        snapshot = get_metrics().snapshot()
        assert snapshot["counters"]["rag_retrievals_total"] == 1
        assert snapshot["histograms"]["rag_retrieval_duration_ms"]["count"] == 1
