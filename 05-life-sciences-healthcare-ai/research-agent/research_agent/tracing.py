"""Opt-in tracing with LangSmith (docs/PRD.md, Stage 7, rules T1 to T13).

Off unless a run asks for it (``--trace``). Two parts (option A):

- ``tracing_config``: the trace details for one run (tracer, run name, ``run_id``, tags).
- ``tracing_scope``: wraps the whole run; switches tracing on or off for it (even against
  ``LANGSMITH_TRACING=true``, T1) and flushes pending traces on exit (T8).

``redact`` strips secrets from everything the tracer sends (T5, T13). Tracing failures
are logged as a warning with the error class name only and never change the run (T8).
"""

import logging
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tracers.langchain import LangChainTracer, wait_for_all_tracers
from langsmith import Client, tracing_context

from research_agent.observability import traced

logger = logging.getLogger(__name__)

BACKEND = "langsmith"
RUN_NAME = "research-agent"
TAGS = ("research-agent", "stage-7")
DEFAULT_PROJECT = "research-agent"  # T12
KEY_ENV = "LANGSMITH_API_KEY"
PROJECT_ENV = "LANGSMITH_PROJECT"
# Values of these settings are removed from anything traced (T5).
SECRET_ENVS = ("ANTHROPIC_API_KEY", "NCBI_API_KEY", "NCBI_EMAIL", KEY_ENV)
REDACTED = "[REDACTED]"

_API_KEY_PARAM = re.compile(r"(api_key=)[^&\s\"']+", re.IGNORECASE)


class TracingConfigError(RuntimeError):
    """``--trace`` was asked for but tracing is not set up (T2)."""


@traced
def project_name() -> str:
    """``LANGSMITH_PROJECT``, or ``research-agent`` when unset or blank (T12)."""
    return os.environ.get(PROJECT_ENV, "").strip() or DEFAULT_PROJECT


@traced
def trace_info(*, enabled: bool) -> dict[str, Any]:
    """The audit record's ``trace`` entry (T3)."""
    if not enabled:
        return {"enabled": False, "backend": None, "project": None}
    return {"enabled": True, "backend": BACKEND, "project": project_name()}


@traced
def tracing_config(run_id: str, *, enabled: bool) -> RunnableConfig:
    """Trace details for one run (T3). Off → empty config. On → needs the key (T2)."""
    if not enabled:
        return {}
    if not os.environ.get(KEY_ENV, "").strip():
        raise TracingConfigError(f"--trace needs {KEY_ENV} (see .env.example)")
    client = Client(hide_inputs=redact, hide_outputs=redact)  # T13
    tracer = LangChainTracer(project_name=project_name(), client=client)
    return {
        "callbacks": [tracer],
        "run_name": RUN_NAME,
        "metadata": {"run_id": run_id},
        "tags": list(TAGS),
    }


@traced
def _flush() -> None:
    """Send pending traces. A failure is a warning, class name only (T8)."""
    try:
        wait_for_all_tracers()
    except Exception as exc:  # T8: tracing never changes the run's result
        logger.warning("trace flush failed (%s)", type(exc).__name__)


@contextmanager
@traced
def tracing_scope(*, enabled: bool) -> Iterator[None]:
    """Run the block with tracing on or off (T1); flush on exit when on (T8)."""
    with tracing_context(enabled=enabled):
        try:
            yield
        finally:
            if enabled:
                _flush()


@traced
def redact(data: Any) -> Any:
    """A copy of ``data`` with ``api_key=...`` values and secret env values replaced (T5)."""
    secrets = sorted(
        {value for name in SECRET_ENVS if (value := os.environ.get(name, "").strip())},
        key=len,
        reverse=True,
    )
    return _redact(data, secrets)


@traced
def _redact(value: Any, secrets: list[str]) -> Any:
    """Recursive helper for ``redact``."""
    if isinstance(value, str):
        text = _API_KEY_PARAM.sub(rf"\g<1>{REDACTED}", value)
        for secret in secrets:
            text = text.replace(secret, REDACTED)
        return text
    if isinstance(value, dict):
        return {key: _redact(item, secrets) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(_redact(item, secrets) for item in value)
    return value
