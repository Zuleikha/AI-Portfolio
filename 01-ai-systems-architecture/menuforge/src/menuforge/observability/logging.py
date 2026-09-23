"""Structured logging for menuforge.

Emits one JSON object per line. Hides log format, handler wiring, and the
redaction rules behind `configure_logging`, `log_event`, and `operation`.

**Two things must never reach a log sink: raw image bytes and the API key.**
Neither is ever passed to a logging call — `operation` records an image's *size*,
never its content. `SecretRedactingFilter` is a second line of defence that scrubs
the key from any record that somehow carries it.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

# Attribute name used to smuggle structured fields onto a LogRecord.
FIELDS_ATTR = "menuforge_fields"

REDACTED = "***REDACTED***"

# Below this length a "secret" is too short to scrub safely — replacing a 3-char
# string everywhere would mangle unrelated log text.
_MIN_REDACTABLE_LEN = 8


class SecretRedactingFilter(logging.Filter):
    """Scrub the Anthropic API key from any record that carries it.

    Defence in depth. Nothing in menuforge logs the key deliberately; this exists
    so that a future careless call site, or a third-party library logging a
    request header, cannot leak it.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        secret = os.environ.get("ANTHROPIC_API_KEY", "")
        if len(secret) < _MIN_REDACTABLE_LEN:
            return True

        # Render before scanning. The secret is often not a literal in
        # `record.msg` — it arrives inside an exception or some other object
        # passed as a lazy %s argument, and only becomes text at format time.
        # Rendering here collapses that lazy formatting, but only on the rare
        # record that actually carries the secret.
        rendered = record.getMessage()
        if secret in rendered:
            record.msg = rendered.replace(secret, REDACTED)
            record.args = ()

        fields = getattr(record, FIELDS_ATTR, None)
        if isinstance(fields, dict):
            setattr(
                record,
                FIELDS_ATTR,
                {
                    k: (v.replace(secret, REDACTED) if isinstance(v, str) else v)
                    for k, v in fields.items()
                },
            )
        return True


class JsonFormatter(logging.Formatter):
    """Render a record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        fields = getattr(record, FIELDS_ATTR, None)
        if isinstance(fields, dict):
            payload.update(fields)

        if record.exc_info and record.exc_info[0] is not None:
            # The type only — a traceback can carry request data into the sink.
            payload["error_type"] = record.exc_info[0].__name__

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON handler and the redaction filter on the root logger.

    Idempotent: replaces menuforge's own handler rather than stacking a new one
    on every call, so repeated calls (tests, reloads) do not duplicate output.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretRedactingFilter())
    handler.set_name("menuforge")

    root = logging.getLogger()
    for existing in list(root.handlers):
        if existing.get_name() == "menuforge":
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Emit one structured event.

    Only pass values safe to persist — identifiers, sizes, durations, counts.
    Never pass image bytes, credentials, or raw model payloads.
    """
    logger.log(level, event, extra={FIELDS_ATTR: {"event": event, **fields}})


@contextmanager
def operation(logger: logging.Logger, name: str, **fields: Any) -> Iterator[None]:
    """Log an operation's start, its success with duration, or its failure.

    Duration is measured with a monotonic clock, so it is unaffected by system
    clock changes.
    """
    start = time.perf_counter()
    log_event(logger, logging.INFO, f"{name}.start", **fields)
    try:
        yield
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            f"{name}.error",
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
            error_type=type(exc).__name__,
            **fields,
        )
        raise
    log_event(
        logger,
        logging.INFO,
        f"{name}.success",
        duration_ms=round((time.perf_counter() - start) * 1000, 1),
        **fields,
    )
