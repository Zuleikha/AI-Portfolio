"""Menu extraction against Claude using forced tool use.

The only module that knows an LLM is involved. Callers get a fully validated
`ExtractedMenu` or an `ExtractionFailedError` — never partial or unvalidated data,
and never a `ValidationError`, which is an internal condition the retry loop handles.

Forced tool use constrains the model's output shape but does not guarantee it, so
Pydantic validation and a retry budget sit on top. See DECISIONS.md D-001.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any, Literal, cast

import anthropic
from anthropic.types import (
    MessageParam,
    OutputConfigParam,
    ToolChoiceToolParam,
    ToolParam,
)
from pydantic import ValidationError

from menuforge.config.settings import get_settings
from menuforge.schemas import ExtractedMenu

logger = logging.getLogger(__name__)

TOOL_NAME = "extract_menu"

TOOL_CHOICE: ToolChoiceToolParam = {"type": "tool", "name": TOOL_NAME}

# Mirrors MenuItemSchema / ExtractedMenu in menuforge.schemas. Change together.
EXTRACT_TOOL: ToolParam = {
    "name": TOOL_NAME,
    "description": "Return the structured list of menu items found in the image.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "price": {"type": "number"},
                        "description": {"type": "string"},
                        "modifiers": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["name", "price"],
                },
            }
        },
        "required": ["items"],
    },
}

EXTRACT_PROMPT = (
    "Extract every menu item, its price, description, and modifiers from this menu image."
)


class ExtractionFailedError(Exception):
    """Extraction did not produce a valid ExtractedMenu. Maps to HTTP 422."""


class ExtractionRefusedError(ExtractionFailedError):
    """The model declined the request.

    A subclass so callers translating to HTTP need only catch
    ``ExtractionFailedError``. Raised without retrying: a refusal on a given image
    is deterministic, so re-sending it would burn the budget to no effect.
    """


class _NoToolUseBlock(Exception):
    """Internal: the response carried no tool_use block. Retryable."""


def model() -> str:
    """The model to call: ``MENUFORGE_MODEL``, else config YAML, else the default.

    Read at call time rather than import time, so it cannot depend on whether
    this module was imported before or after the environment was loaded.
    """
    return get_settings().llm.model


def _media_type_literal(
    media_type: str,
) -> Literal["image/jpeg", "image/png", "image/gif", "image/webp"]:
    """Narrow a validated media type to the literal the SDK expects.

    `menuforge.main` has already rejected anything outside this set before the
    call reaches here, so this is a type-level narrowing, not a runtime check.
    """
    return cast('Literal["image/jpeg", "image/png", "image/gif", "image/webp"]', media_type)


def _client() -> anthropic.Anthropic:
    """Build a client. The key is read from the environment and never logged."""
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _call_model(client: anthropic.Anthropic, image_b64: str, media_type: str) -> dict[str, Any]:
    """Make one forced-tool-use call and return the raw tool arguments."""
    messages: list[MessageParam] = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": _media_type_literal(media_type),
                        "data": image_b64,
                    },
                },
                {"type": "text", "text": EXTRACT_PROMPT},
            ],
        }
    ]

    llm = get_settings().llm
    output_config: OutputConfigParam = {"effort": llm.effort}

    response = client.messages.create(
        model=llm.model,
        max_tokens=llm.max_tokens,
        output_config=output_config,
        tools=[EXTRACT_TOOL],
        tool_choice=TOOL_CHOICE,
        messages=messages,
    )

    if getattr(response, "stop_reason", None) == "refusal":
        raise ExtractionRefusedError("model declined to process this image")

    for block in response.content:
        if block.type == "tool_use":
            # The SDK types tool arguments as `object`; the shape is whatever the
            # model returned, which is exactly what Pydantic validates next.
            return cast("dict[str, Any]", block.input)

    raise _NoToolUseBlock(f"no tool_use block in response (stop_reason={response.stop_reason})")


def extract_menu(image_bytes: bytes, media_type: str) -> ExtractedMenu:
    """Extract structured menu data from an image.

    Retries on schema validation failure and on transient API errors, up to
    ``llm.max_retries`` retries (one more attempt than that in total). Raises
    ``ExtractionFailedError`` when the budget is exhausted.

    Image bytes are base64-encoded for the request and never logged.
    """
    max_retries = get_settings().llm.max_retries
    client = _client()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 2):
        try:
            raw = _call_model(client, image_b64, media_type)
            return ExtractedMenu.model_validate(raw)
        except ExtractionRefusedError:
            logger.error("extraction refused by model, not retrying")
            raise
        except ValidationError as exc:
            last_error = exc
            logger.warning("extraction validation failed, attempt %s: %s", attempt, exc)
        # Deliberately broad: any non-refusal failure of a single attempt is
        # worth retrying, and the SDK does not expose one base class covering
        # network, timeout and API errors. The budget bounds the blast radius,
        # and the last error is re-raised once it is exhausted — nothing is
        # swallowed.
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("extraction call failed, attempt %s: %s", attempt, exc)

    logger.error("extraction exhausted retries after %s attempts", max_retries + 1)
    raise ExtractionFailedError(str(last_error))
