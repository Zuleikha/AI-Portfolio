"""Tests for menuforge.llm.client.

Ported from restoai/tests/test_extraction.py and extended. The Anthropic client
factory is patched, so no network call is made and no real API key is needed.

The retry budget is only observable through the call count, so every retry test
asserts it.
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from menuforge.config.settings import DEFAULTS, get_settings, reset_settings
from menuforge.llm.client import (
    TOOL_NAME,
    ExtractionFailedError,
    ExtractionRefusedError,
    extract_menu,
    model,
)

VALID_INPUT = {
    "items": [
        {
            "name": "Margherita Pizza",
            "price": 12.5,
            "description": "Classic",
            "modifiers": ["extra cheese"],
        }
    ]
}

INVALID_INPUT = {"items": [{"name": "Pizza"}]}  # missing required price

WRONG_TYPE_INPUT = {"items": [{"name": "Pizza", "price": "twelve fifty"}]}


def _tool_block(input_data: dict[str, Any]) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.input = input_data
    return block


def _response(input_data: dict[str, Any], stop_reason: str = "tool_use") -> MagicMock:
    response = MagicMock()
    response.content = [_tool_block(input_data)]
    response.stop_reason = stop_reason
    return response


# --------------------------------------------------------------------------
# The three paths from the reference suite
# --------------------------------------------------------------------------


@patch("menuforge.llm.client._client")
def test_extract_menu_success(mock_client: MagicMock) -> None:
    mock_client.return_value.messages.create.return_value = _response(VALID_INPUT)

    result = extract_menu(b"fake image bytes", "image/png")

    assert len(result.items) == 1
    assert result.items[0].name == "Margherita Pizza"
    assert result.items[0].price == 12.5
    assert mock_client.return_value.messages.create.call_count == 1


@patch("menuforge.llm.client._client")
def test_extract_menu_retries_then_succeeds(mock_client: MagicMock) -> None:
    mock_client.return_value.messages.create.side_effect = [
        _response(INVALID_INPUT),
        _response(VALID_INPUT),
    ]

    result = extract_menu(b"fake image bytes", "image/png")

    assert len(result.items) == 1
    assert mock_client.return_value.messages.create.call_count == 2


@patch("menuforge.llm.client._client")
def test_extract_menu_exhausts_retries_and_raises(mock_client: MagicMock) -> None:
    mock_client.return_value.messages.create.return_value = _response(INVALID_INPUT)

    # The budget is configuration now, so read the expected attempt count from
    # the same place the client reads it rather than hardcoding 3.
    total_attempts = get_settings().llm.max_retries + 1

    with pytest.raises(ExtractionFailedError):
        extract_menu(b"fake image bytes", "image/png")

    assert mock_client.return_value.messages.create.call_count == total_attempts


# --------------------------------------------------------------------------
# Extensions
# --------------------------------------------------------------------------


@patch("menuforge.llm.client._client")
def test_uses_forced_tool_use(mock_client: MagicMock) -> None:
    """The tool call must be forced, not merely offered — this is D-001."""
    mock_client.return_value.messages.create.return_value = _response(VALID_INPUT)

    extract_menu(b"fake image bytes", "image/jpeg")

    kwargs = mock_client.return_value.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    assert [tool["name"] for tool in kwargs["tools"]] == [TOOL_NAME]
    assert kwargs["model"] == model()


@patch("menuforge.llm.client._client")
def test_sends_image_as_base64_with_declared_media_type(mock_client: MagicMock) -> None:
    mock_client.return_value.messages.create.return_value = _response(VALID_INPUT)

    extract_menu(b"fake image bytes", "image/webp")

    content = mock_client.return_value.messages.create.call_args.kwargs["messages"][0]["content"]
    image_block = next(block for block in content if block["type"] == "image")
    assert image_block["source"]["media_type"] == "image/webp"
    assert image_block["source"]["type"] == "base64"
    # Base64 of the raw bytes, never the raw bytes themselves.
    assert image_block["source"]["data"] == "ZmFrZSBpbWFnZSBieXRlcw=="


@patch("menuforge.llm.client._client")
def test_wrong_field_type_is_a_validation_failure(mock_client: MagicMock) -> None:
    """A price the model wrote as prose fails validation and is retried."""
    mock_client.return_value.messages.create.side_effect = [
        _response(WRONG_TYPE_INPUT),
        _response(VALID_INPUT),
    ]

    result = extract_menu(b"fake image bytes", "image/png")

    assert result.items[0].price == 12.5
    assert mock_client.return_value.messages.create.call_count == 2


@patch("menuforge.llm.client._client")
def test_transient_api_error_is_retried(mock_client: MagicMock) -> None:
    """Network and API errors share the retry budget with validation failures."""
    mock_client.return_value.messages.create.side_effect = [
        ConnectionError("connection reset"),
        _response(VALID_INPUT),
    ]

    result = extract_menu(b"fake image bytes", "image/png")

    assert len(result.items) == 1
    assert mock_client.return_value.messages.create.call_count == 2


@patch("menuforge.llm.client._client")
def test_missing_tool_use_block_is_retried(mock_client: MagicMock) -> None:
    """A response with no tool_use block is retryable, not a crash."""
    empty = MagicMock()
    empty.content = []
    empty.stop_reason = "end_turn"
    mock_client.return_value.messages.create.side_effect = [empty, _response(VALID_INPUT)]

    result = extract_menu(b"fake image bytes", "image/png")

    assert len(result.items) == 1
    assert mock_client.return_value.messages.create.call_count == 2


@patch("menuforge.llm.client._client")
def test_refusal_is_not_retried(mock_client: MagicMock) -> None:
    """A refusal is deterministic for a given image, so retrying wastes budget."""
    refusal = MagicMock()
    refusal.content = []
    refusal.stop_reason = "refusal"
    mock_client.return_value.messages.create.return_value = refusal

    with pytest.raises(ExtractionRefusedError):
        extract_menu(b"fake image bytes", "image/png")

    assert mock_client.return_value.messages.create.call_count == 1


def test_refusal_is_an_extraction_failure() -> None:
    """Callers translating to HTTP need only catch the one type."""
    assert issubclass(ExtractionRefusedError, ExtractionFailedError)


@patch("menuforge.llm.client._client")
def test_empty_menu_is_valid(mock_client: MagicMock) -> None:
    """An image with no items is a successful extraction of nothing."""
    mock_client.return_value.messages.create.return_value = _response({"items": []})

    result = extract_menu(b"fake image bytes", "image/png")

    assert result.items == []
    assert mock_client.return_value.messages.create.call_count == 1


@patch("menuforge.llm.client._client")
def test_retry_warnings_do_not_leak_image_bytes(
    mock_client: MagicMock, log_capture: io.StringIO
) -> None:
    """PRD SC-7: the retry path logs, and must not log the image."""
    mock_client.return_value.messages.create.side_effect = [
        _response(INVALID_INPUT),
        _response(VALID_INPUT),
    ]

    extract_menu(b"SENTINELIMAGEBYTES", "image/png")

    assert "SENTINELIMAGEBYTES" not in log_capture.getvalue()
    assert "extraction validation failed" in log_capture.getvalue()


@patch("menuforge.llm.client._client")
def test_api_key_never_reaches_the_log(
    mock_client: MagicMock, log_capture: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even a careless log call cannot leak the key past the redaction filter."""
    secret = "sk-ant-not-a-real-key-0123456789"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)

    mock_client.return_value.messages.create.side_effect = RuntimeError(
        f"upstream rejected key {secret}"
    )

    with pytest.raises(ExtractionFailedError):
        extract_menu(b"fake image bytes", "image/png")

    output = log_capture.getvalue()
    assert secret not in output
    assert "***REDACTED***" in output


def test_model_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no override, the shipped config agrees with the code default."""
    monkeypatch.delenv("MENUFORGE_MODEL", raising=False)
    reset_settings()

    assert model() == DEFAULTS.llm.model


def test_model_is_overridable_at_call_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read per call, so it cannot depend on import order vs. loading .env."""
    monkeypatch.setenv("MENUFORGE_MODEL", "claude-opus-5")
    reset_settings()

    assert model() == "claude-opus-5"


@patch("menuforge.llm.client._client")
def test_request_uses_the_configured_budget(
    mock_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Config reaches the actual API call, not just the settings object."""
    monkeypatch.setenv("MENUFORGE_MAX_TOKENS", "1234")
    monkeypatch.setenv("MENUFORGE_EFFORT", "high")
    reset_settings()
    mock_client.return_value.messages.create.return_value = _response(VALID_INPUT)

    extract_menu(b"fake image bytes", "image/png")

    kwargs = mock_client.return_value.messages.create.call_args.kwargs
    assert kwargs["max_tokens"] == 1234
    assert kwargs["output_config"] == {"effort": "high"}


@patch("menuforge.llm.client._client")
def test_retry_budget_is_configurable(
    mock_client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MENUFORGE_MAX_RETRIES", "0")
    reset_settings()
    mock_client.return_value.messages.create.return_value = _response(INVALID_INPUT)

    with pytest.raises(ExtractionFailedError):
        extract_menu(b"fake image bytes", "image/png")

    assert mock_client.return_value.messages.create.call_count == 1
