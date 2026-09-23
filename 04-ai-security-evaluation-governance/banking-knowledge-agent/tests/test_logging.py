"""Structured logging and tracing tests."""

from __future__ import annotations

import json
import logging

import pytest

from app.core.logging import (
    APP_LOG_FILENAME,
    TRACE_LOG_FILENAME,
    configure_logging,
    get_logger,
    reset_logging,
)
from app.core.tracing import traced


@pytest.fixture
def configured(settings):
    reset_logging()
    configure_logging(settings)
    yield settings
    reset_logging()


def test_application_log_is_written_to_disk(configured):
    get_logger("test").info("stage_one.event", detail="value")

    log_file = configured.log_dir / APP_LOG_FILENAME
    assert log_file.exists()

    record = json.loads(log_file.read_text(encoding="utf-8").splitlines()[-1])
    assert record["event"] == "stage_one.event"
    assert record["detail"] == "value"
    assert record["level"] == "info"
    assert "timestamp" in record


def test_traced_writes_to_the_dedicated_trace_sink(configured):
    @traced
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5

    trace_file = configured.log_dir / TRACE_LOG_FILENAME
    record = json.loads(trace_file.read_text(encoding="utf-8").splitlines()[-1])
    assert record["event"] == "trace"
    assert record["function"].endswith("add")
    assert record["outcome"] == "ok"
    assert record["duration_ms"] >= 0


def test_traced_records_errors_and_reraises(configured):
    @traced
    def boom() -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError):
        boom()

    trace_file = configured.log_dir / TRACE_LOG_FILENAME
    record = json.loads(trace_file.read_text(encoding="utf-8").splitlines()[-1])
    assert record["outcome"] == "error"
    assert record["error_type"] == "ValueError"


def test_traces_are_not_mixed_into_the_application_log(configured):
    @traced
    def noop() -> None:
        return None

    noop()

    app_log = (configured.log_dir / APP_LOG_FILENAME).read_text(encoding="utf-8")
    assert '"event": "trace"' not in app_log


def test_traced_arguments_are_never_logged(configured):
    @traced
    def login(password: str) -> str:
        return "ok"

    login("super-secret-value")

    trace_file = configured.log_dir / TRACE_LOG_FILENAME
    assert "super-secret-value" not in trace_file.read_text(encoding="utf-8")


def test_traced_preserves_function_metadata():
    @traced
    def documented() -> None:
        """Docstring survives."""

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "Docstring survives."


def test_httpx_is_quietened_to_warning(configured):
    """Its info lines carry full request URLs; warnings still get through."""
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.info("HTTP Request: GET http://testserver/health?account=12345678")
    httpx_logger.warning("httpx.warning.kept")

    app_log = (configured.log_dir / APP_LOG_FILENAME).read_text(encoding="utf-8")
    assert "12345678" not in app_log
    assert "httpx.warning.kept" in app_log


def test_reset_logging_restores_the_httpx_level(configured):
    reset_logging()
    assert logging.getLogger("httpx").level == logging.NOTSET


def test_configure_logging_is_idempotent(configured):
    configure_logging(configured)
    configure_logging(configured)
    get_logger("test").info("still.working")

    log_file = configured.log_dir / APP_LOG_FILENAME
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert sum(1 for line in lines if json.loads(line)["event"] == "still.working") == 1


async def test_traced_async_records_coroutine_calls(configured):
    from app.core.tracing import traced_async

    @traced_async
    async def fetch() -> str:
        return "value"

    assert await fetch() == "value"

    trace_file = configured.log_dir / TRACE_LOG_FILENAME
    record = json.loads(trace_file.read_text(encoding="utf-8").splitlines()[-1])
    assert record["function"].endswith("fetch")
    assert record["outcome"] == "ok"


async def test_traced_async_records_errors_and_reraises(configured):
    from app.core.tracing import traced_async

    @traced_async
    async def boom() -> None:
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        await boom()

    trace_file = configured.log_dir / TRACE_LOG_FILENAME
    record = json.loads(trace_file.read_text(encoding="utf-8").splitlines()[-1])
    assert record["outcome"] == "error"
    assert record["error_type"] == "RuntimeError"
