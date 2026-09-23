"""Structured logging configuration.

Uses ``structlog`` so every log line is a structured event rather than a
formatted string. This matters later: request IDs, retrieval latency, tool
calls and LLM latency (Stage 10) all become queryable fields instead of prose.

Logs are written to stdout and, when enabled, to a file on disk. Trace events
emitted by :mod:`app.core.tracing` go to a dedicated ``traces.log`` sink so
they never pollute the application log stream.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import structlog
from pydantic import SecretBytes, SecretStr

from app.core.config import Settings, get_settings

APP_LOG_FILENAME = "app.log"
TRACE_LOG_FILENAME = "traces.log"
TRACE_LOGGER_NAME = "bka.trace"

QUIETENED_LOGGERS = ("httpx",)
"""Third-party loggers held at WARNING (guide §20.36).

``httpx`` -- used by the test client and the LLM vendor SDKs -- logs every
outgoing request with its full URL at INFO. A URL can carry a query string.
"""

_MAX_LOG_BYTES = 5 * 1024 * 1024
_LOG_BACKUP_COUNT = 3

_configured = False

REDACTED = "[REDACTED]"
SENSITIVE_FIELD_NAMES = frozenset(
    {
        "api_key",
        "llm_api_key",
        "authorization",
        "proxy_authorization",
        "x_api_key",
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "cookie",
        "set_cookie",
        "session_id",
    }
)
"""Event field names always replaced by :data:`REDACTED` (Stage 13, guide §16).

Matched case-insensitively, with ``-`` read as ``_`` so a header name
(``X-API-Key``) and a keyword argument (``x_api_key``) are the same field.
Defence in depth: application code already never logs these.
"""


def _is_sensitive(name: object) -> bool:
    """Return True when ``name`` is a sensitive field name.

    Not ``@traced``: called from the log processor below (see its note).
    """
    return (
        isinstance(name, str)
        and name.lower().replace("-", "_") in SENSITIVE_FIELD_NAMES
    )


def _redact_leaf(value: Any) -> Any:
    """Replace a pydantic secret with :data:`REDACTED`; return anything else as is.

    Not ``@traced``: called from the log processor below (see its note).
    """
    if isinstance(value, SecretStr | SecretBytes):
        return REDACTED
    if isinstance(value, list | tuple):
        return type(value)(
            REDACTED if isinstance(v, SecretStr | SecretBytes) else v for v in value
        )
    return value


def redact_sensitive_fields(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Redact sensitive-named fields and pydantic secrets (a structlog processor).

    Top-level fields and keys of a dict nested one level down are checked. A
    nested dict is copied, never mutated, because it may belong to the caller.

    Deliberately NOT ``@traced`` (same exemption as 10.F): it runs inside
    logging itself, on every log line, and a traced log processor would emit
    a trace event from within the log call that records it -- recursion.
    """
    for key, value in list(event_dict.items()):
        if _is_sensitive(key):
            event_dict[key] = REDACTED
        elif isinstance(value, dict):
            event_dict[key] = {
                inner_key: REDACTED if _is_sensitive(inner_key) else _redact_leaf(inner)
                for inner_key, inner in value.items()
            }
        else:
            event_dict[key] = _redact_leaf(value)
    return event_dict


def _shared_processors() -> list[structlog.types.Processor]:
    """Return the structlog processors shared by every renderer."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        # Last, so fields merged from context variables are covered too.
        redact_sensitive_fields,
    ]


def _build_file_handler(path: Path) -> logging.Handler:
    """Create a size-rotating file handler writing JSON lines to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        path,
        maxBytes=_MAX_LOG_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=_shared_processors(),
        )
    )
    return handler


def configure_logging(settings: Settings | None = None) -> None:
    """Configure structlog and the stdlib logging bridge.

    Safe to call more than once; only the first call takes effect.
    """
    global _configured
    if _configured:
        return

    settings = settings or get_settings()
    level = getattr(logging, settings.log_level)

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[
            *_shared_processors(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=renderer,
            foreign_pre_chain=_shared_processors(),
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(stream_handler)
    root.setLevel(level)
    for name in QUIETENED_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    trace_logger = logging.getLogger(TRACE_LOGGER_NAME)
    trace_logger.handlers.clear()
    trace_logger.setLevel(level)
    # Trace events are a dedicated sink, never mixed into the app stream.
    trace_logger.propagate = False

    if settings.log_to_file:
        root.addHandler(_build_file_handler(settings.log_dir / APP_LOG_FILENAME))
        trace_logger.addHandler(
            _build_file_handler(settings.log_dir / TRACE_LOG_FILENAME)
        )
    else:
        trace_logger.addHandler(logging.NullHandler())

    _configured = True


def reset_logging() -> None:
    """Tear down logging configuration. Intended for tests."""
    global _configured
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()
    logging.getLogger(TRACE_LOGGER_NAME).handlers.clear()
    for name in QUIETENED_LOGGERS:
        logging.getLogger(name).setLevel(logging.NOTSET)
    _configured = False


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for ``name``."""
    logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(name)
    return logger
