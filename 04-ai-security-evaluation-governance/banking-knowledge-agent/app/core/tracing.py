"""The ``@traced`` decorator.

Every application function is wrapped so that its invocation, duration and
outcome are recorded as a structured trace event. Traces go to a dedicated
on-disk sink (``logs/traces.log``) via the ``bka.trace`` logger -- they are
never routed through the application log stream or an external proxy.

Stage 10 builds request-level observability on top of these primitives.

Do NOT apply these decorators to FastAPI route handlers. FastAPI resolves a
handler's (postponed) annotations against that function's ``__globals__``;
a wrapper defined here resolves them against this module instead, so
dependency annotations silently degrade into query parameters. Route
handlers are traced by request middleware instead.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

import structlog

from app.core.logging import TRACE_LOGGER_NAME

P = ParamSpec("P")
R = TypeVar("R")

_trace_logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(
    TRACE_LOGGER_NAME
)


def traced(func: Callable[P, R]) -> Callable[P, R]:
    """Record a structured trace event for each call to ``func``.

    Arguments are deliberately NOT logged: they may carry customer data,
    credentials or tokens. Only the qualified name, duration and outcome are
    recorded.
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        started = time.perf_counter()
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            _emit(func, started, "error", error_type=type(exc).__name__)
            raise
        _emit(func, started, "ok")
        return result

    return wrapper


def traced_async(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Async counterpart of :func:`traced` for coroutine functions."""

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        started = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
        except Exception as exc:
            _emit(func, started, "error", error_type=type(exc).__name__)
            raise
        _emit(func, started, "ok")
        return result

    return wrapper


def _emit(func: Callable[..., Any], started: float, outcome: str, **extra: Any) -> None:
    """Write a single trace event to the dedicated trace sink."""
    _trace_logger.info(
        "trace",
        function=f"{func.__module__}.{func.__qualname__}",
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        outcome=outcome,
        **extra,
    )
