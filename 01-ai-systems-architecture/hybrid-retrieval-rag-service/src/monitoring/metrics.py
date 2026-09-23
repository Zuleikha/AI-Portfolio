"""
Structured logging setup and in-process request metrics.

Logging:
  Uses structlog for machine-readable JSON logs in production and a
  human-friendly console renderer in debug mode.  This replaces the
  scattered print() calls in v1.

Metrics:
  A lightweight in-memory accumulator exposed at GET /metrics.
  For production, replace with Prometheus counters + a /metrics scrape
  endpoint, or push to Datadog / CloudWatch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import structlog


def configure_logging(level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=log_level)


@dataclass
class RequestMetrics:
    query_count: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    errors: int = 0
    _latency_window: list[float] = field(default_factory=list, repr=False)
    _token_window: list[int] = field(default_factory=list, repr=False)

    def record(self, tokens: int, latency_ms: float) -> None:
        self.query_count += 1
        self.total_tokens += tokens
        self.total_latency_ms += latency_ms
        self._latency_window.append(latency_ms)
        self._token_window.append(tokens)
        # Rolling window of last 100 requests
        if len(self._latency_window) > 100:
            self._latency_window = self._latency_window[-100:]
            self._token_window = self._token_window[-100:]

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(1, self.query_count)

    @property
    def avg_tokens_per_query(self) -> float:
        return self.total_tokens / max(1, self.query_count)

    def to_dict(self) -> dict:
        return {
            "query_count": self.query_count,
            "total_tokens": self.total_tokens,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "avg_tokens_per_query": round(self.avg_tokens_per_query, 1),
            "errors": self.errors,
            "recent_latencies_ms": [round(x, 1) for x in self._latency_window[-10:]],
        }


# Module-level singleton — imported by the API layer
_metrics = RequestMetrics()


def get_metrics() -> RequestMetrics:
    return _metrics
