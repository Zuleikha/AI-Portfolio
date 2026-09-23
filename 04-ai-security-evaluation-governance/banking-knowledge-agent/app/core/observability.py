"""Request-level observability: request ids, content-free fingerprints, metrics.

Stage 10 builds on the two Stage 1 primitives -- structured logging and
``@traced`` -- rather than replacing them (guide §20.32-§20.35):

* **Request id** (§20.34, §20.35). :func:`resolve_request_id` accepts an
  incoming ``X-Request-ID`` only if it is short and safe, and otherwise makes a
  new one. The request middleware binds it with ``structlog.contextvars``, so
  every log and trace line of that request carries it without any function
  having to pass it along.
* **Fingerprints** (§20.32). :func:`fingerprint` is a short one-way hash. The
  question is logged as a fingerprint and a length, never as text: two log lines
  can be matched as "the same question" without the log holding what was asked.
* **Metrics** (§20.33). :class:`Metrics` keeps counters and latency histograms in
  memory, served at ``GET /metrics``. No new dependency: the ``mcp`` /
  ``fastapi`` pins stay untouched. Metrics hold names and numbers only -- never
  a question, an identifier or an answer.

**What is deliberately not ``@traced`` here.** :meth:`Metrics.increment`,
:meth:`Metrics.observe` and :func:`elapsed_ms` run inside the very measurements
they serve, several times per request. Tracing them would write a trace line per
counter bump and add to the latency being measured.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
import uuid
from bisect import bisect_left
from typing import Any

from app.core.tracing import traced

REQUEST_ID_HEADER = "X-Request-ID"
"""The header a request id is read from and always returned in."""

MAX_REQUEST_ID_LENGTH = 64
"""The longest incoming request id accepted (guide §20.35)."""

_SAFE_REQUEST_ID = re.compile(rf"[A-Za-z0-9-]{{1,{MAX_REQUEST_ID_LENGTH}}}")

FINGERPRINT_LENGTH = 12
"""Hex characters of the SHA-256 fingerprint written to logs."""

HISTOGRAM_BUCKETS_MS: tuple[float, ...] = (
    5.0,
    10.0,
    25.0,
    50.0,
    100.0,
    250.0,
    500.0,
    1000.0,
    2500.0,
    5000.0,
    10000.0,
)
"""Upper bounds of the latency histogram buckets, in milliseconds."""

# Metric names. One place, so an event and its metric cannot drift apart.
HTTP_REQUESTS_TOTAL = "http_requests_total"
HTTP_ERRORS_TOTAL = "http_errors_total"
HTTP_REQUEST_DURATION_MS = "http_request_duration_ms"
RAG_RETRIEVALS_TOTAL = "rag_retrievals_total"
RAG_RETRIEVAL_DURATION_MS = "rag_retrieval_duration_ms"
LLM_CALLS_TOTAL = "llm_calls_total"
LLM_ERRORS_TOTAL = "llm_errors_total"
LLM_CALL_DURATION_MS = "llm_call_duration_ms"
LLM_INPUT_TOKENS_TOTAL = "llm_input_tokens_total"
LLM_OUTPUT_TOKENS_TOTAL = "llm_output_tokens_total"
LLM_INVALID_CITATIONS_TOTAL = "llm_invalid_citations_total"
TOOL_CALLS_TOTAL = "tool_calls_total"
TOOL_ERRORS_TOTAL = "tool_errors_total"
TOOL_CALL_DURATION_MS = "tool_call_duration_ms"
AUTH_FAILURES_TOTAL = "auth_failures_total"
RATE_LIMITED_TOTAL = "rate_limited_total"


@traced
def resolve_request_id(incoming: str | None) -> str:
    """Return the incoming request id if it is safe to log, else a new one.

    Args:
        incoming: The raw ``X-Request-ID`` header value, if any. Untrusted.

    Returns:
        ``incoming`` when it is 1-64 ASCII letters, digits or dashes; otherwise a
        fresh random id in that same format. Anything else -- spaces, line
        breaks, quotes, an overlong value -- could forge or bloat log lines.
    """
    if incoming is not None and _SAFE_REQUEST_ID.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


@traced
def fingerprint(text: str) -> str:
    """A short, one-way identifier for ``text``, safe to write to a log."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:FINGERPRINT_LENGTH]


def elapsed_ms(started: float) -> float:
    """Milliseconds since ``started``, a :func:`time.perf_counter` reading."""
    return round((time.perf_counter() - started) * 1000, 3)


class _Histogram:
    """Count, sum, maximum and per-bucket counts for one latency series."""

    def __init__(self) -> None:
        self.count = 0
        self.total = 0.0
        self.maximum = 0.0
        # One slot per bound, plus one for values above the last bound.
        self.slots = [0] * (len(HISTOGRAM_BUCKETS_MS) + 1)

    def add(self, value: float) -> None:
        self.count += 1
        self.total += value
        self.maximum = max(self.maximum, value)
        self.slots[bisect_left(HISTOGRAM_BUCKETS_MS, value)] += 1

    def as_dict(self) -> dict[str, Any]:
        # Cumulative, as Prometheus does: le_50 counts everything at or below 50.
        buckets: dict[str, int] = {}
        running = 0
        for bound, slot in zip(HISTOGRAM_BUCKETS_MS, self.slots, strict=False):
            running += slot
            buckets[f"le_{bound:g}"] = running
        buckets["le_inf"] = self.count
        return {
            "count": self.count,
            "sum_ms": round(self.total, 3),
            "max_ms": round(self.maximum, 3),
            "buckets": buckets,
        }


class Metrics:
    """Thread-safe in-process counters and latency histograms.

    Route handlers run on worker threads, so every update takes one lock. The
    work under it is a dictionary update; contention is not a concern at this
    scale.
    """

    def __init__(self) -> None:
        """Start with no counters and no histograms."""
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}
        self._histograms: dict[str, _Histogram] = {}

    def increment(self, name: str, amount: int = 1) -> None:
        """Add ``amount`` to the counter ``name``, creating it at zero."""
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def observe(self, name: str, value_ms: float) -> None:
        """Record one latency, in milliseconds, in the histogram ``name``.

        Raises:
            ValueError: If ``value_ms`` is negative -- a clock or caller bug that
                would silently corrupt every average built from it.
        """
        if value_ms < 0:
            raise ValueError(f"Latency cannot be negative: {value_ms} ms.")
        with self._lock:
            self._histograms.setdefault(name, _Histogram()).add(value_ms)

    def snapshot(self) -> dict[str, Any]:
        """A copy of every counter and histogram, safe to serialise."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "histograms": {
                    name: histogram.as_dict()
                    for name, histogram in self._histograms.items()
                },
            }

    def clear(self) -> None:
        """Forget every counter and histogram."""
        with self._lock:
            self._counters.clear()
            self._histograms.clear()


_metrics = Metrics()


def get_metrics() -> Metrics:
    """The process-wide metrics registry."""
    return _metrics


def reset_metrics() -> None:
    """Empty the process-wide registry in place. Intended for tests."""
    _metrics.clear()
