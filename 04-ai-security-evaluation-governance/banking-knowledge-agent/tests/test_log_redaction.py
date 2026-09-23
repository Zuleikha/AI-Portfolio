"""Log redaction tests (Stage 13, unit U6).

The application already never logs keys, headers or session ids. The redaction
processor is defence in depth: if a future log call passes a sensitive-named
field or a ``SecretStr`` by mistake, every sink still shows ``[REDACTED]``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.logging import (
    APP_LOG_FILENAME,
    REDACTED,
    SENSITIVE_FIELD_NAMES,
    TRACE_LOG_FILENAME,
    TRACE_LOGGER_NAME,
    _shared_processors,
    configure_logging,
    get_logger,
    redact_sensitive_fields,
    reset_logging,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEAK = "leak-value-must-not-appear"


@pytest.fixture
def configured(settings: Settings):
    reset_logging()
    configure_logging(settings)
    yield settings
    reset_logging()


def _last_app_record(settings: Settings) -> dict[str, object]:
    lines = (settings.log_dir / APP_LOG_FILENAME).read_text("utf-8").splitlines()
    record: dict[str, object] = json.loads(lines[-1])
    return record


# --- The processor itself ------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "api_key",
        "llm_api_key",
        "authorization",
        "x-api-key",
        "x_api_key",
        "password",
        "secret",
        "token",
        "cookie",
        "session_id",
    ],
)
def test_each_sensitive_field_is_redacted(field):
    event = redact_sensitive_fields(None, "info", {"event": "e", field: LEAK})
    assert event[field] == REDACTED
    assert event["event"] == "e"


@pytest.mark.parametrize("field", ["API_KEY", "Authorization", "X-Api-Key", "Token"])
def test_field_names_match_case_insensitively(field):
    event = redact_sensitive_fields(None, "info", {field: LEAK})
    assert event[field] == REDACTED


def test_non_sensitive_fields_are_untouched():
    original = {
        "event": "http.request",
        "path": "/api/sessions",
        "status": 200,
        "latency_ms": 1.5,
        "session": "fp-1234",
        "tokens_in": 10,
    }
    assert redact_sensitive_fields(None, "info", dict(original)) == original


def test_sensitive_keys_nested_one_level_are_redacted():
    event = redact_sensitive_fields(
        None,
        "info",
        {"headers": {"Authorization": LEAK, "X-API-Key": LEAK, "accept": "json"}},
    )
    assert event["headers"] == {
        "Authorization": REDACTED,
        "X-API-Key": REDACTED,
        "accept": "json",
    }


def test_nested_input_dict_is_not_mutated():
    headers = {"authorization": LEAK}
    redact_sensitive_fields(None, "info", {"headers": headers})
    assert headers == {"authorization": LEAK}


def test_secretstr_is_redacted_under_any_field_name():
    event = redact_sensitive_fields(
        None,
        "info",
        {
            "harmless_name": SecretStr(LEAK),
            "nested": {"inner": SecretStr(LEAK)},
            "items": [SecretStr(LEAK), "kept"],
        },
    )
    assert event["harmless_name"] == REDACTED
    assert event["nested"] == {"inner": REDACTED}
    assert event["items"] == [REDACTED, "kept"]


def test_sensitive_set_covers_the_stage_13_names():
    assert {"api_key", "llm_api_key", "x_api_key", "session_id"} <= set(
        SENSITIVE_FIELD_NAMES
    )


def test_processor_is_in_the_shared_chain():
    """Shared chain = structlog loggers AND the stdlib ``foreign_pre_chain``."""
    assert redact_sensitive_fields in _shared_processors()


# --- Every sink ----------------------------------------------------------------


def test_json_file_output_is_redacted(configured):
    get_logger("test").info(
        "redaction.check",
        api_key=LEAK,
        headers={"x-api-key": LEAK},
        secret_value=SecretStr(LEAK),
        detail="visible",
    )

    text = (configured.log_dir / APP_LOG_FILENAME).read_text("utf-8")
    assert LEAK not in text
    record = _last_app_record(configured)
    assert record["api_key"] == REDACTED
    assert record["headers"] == {"x-api-key": REDACTED}
    assert record["secret_value"] == REDACTED
    assert record["detail"] == "visible"


def test_context_bound_fields_are_redacted(configured):
    import structlog

    with structlog.contextvars.bound_contextvars(session_id=LEAK):
        get_logger("test").info("redaction.context")

    assert LEAK not in (configured.log_dir / APP_LOG_FILENAME).read_text("utf-8")
    assert _last_app_record(configured)["session_id"] == REDACTED


def test_trace_sink_is_redacted(configured):
    import structlog

    structlog.stdlib.get_logger(TRACE_LOGGER_NAME).info("trace", token=LEAK)

    text = (configured.log_dir / TRACE_LOG_FILENAME).read_text("utf-8")
    assert LEAK not in text
    assert REDACTED in text


def test_console_output_is_redacted(tmp_path, capsys):
    settings = Settings(
        environment="test",
        log_format="console",
        log_dir=tmp_path / "logs",
        log_to_file=False,
    )
    reset_logging()
    configure_logging(settings)
    try:
        get_logger("test").info("redaction.console", password=LEAK, detail="shown")
    finally:
        reset_logging()

    out = capsys.readouterr().out
    assert "redaction.console" in out
    assert LEAK not in out
    assert REDACTED in out
    assert "shown" in out


def test_stdlib_records_still_render_through_the_chain(configured):
    logging.getLogger("thirdparty").warning("thirdparty.warning")
    assert _last_app_record(configured)["event"] == "thirdparty.warning"


# --- Build and repository ignore files -------------------------------------------


def _entries(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text("utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


@pytest.mark.parametrize("pattern", ["**/.env", "**/.env.*", "**/*.pem", "**/*.key"])
def test_dockerignore_excludes_secret_files_at_any_depth(pattern):
    """``COPY app`` / ``COPY data`` must not carry a nested ``.env`` or key file."""
    assert pattern in _entries(PROJECT_ROOT / ".dockerignore")


@pytest.mark.parametrize(
    "pattern", [".env", ".env.*", "!.env.example", "*.pem", "*.key"]
)
@pytest.mark.skipif(
    not (PROJECT_ROOT / ".gitignore").exists(),
    # 15.C: .dockerignore keeps git metadata out of the image by design.
    reason="no .gitignore: not a git checkout (e.g. inside the image)",
)
def test_gitignore_excludes_env_files_but_keeps_the_example(pattern):
    assert pattern in _entries(PROJECT_ROOT / ".gitignore")
