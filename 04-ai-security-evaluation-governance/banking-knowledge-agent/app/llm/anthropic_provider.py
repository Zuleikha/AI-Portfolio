"""Anthropic adapter: the ``LLMProvider`` seam, implemented against a real SDK.

One of exactly two modules in this package allowed to import a vendor. Its whole
job is translation, in both directions::

    CompletionRequest  ──▶  client.messages.create(system=, messages=, max_tokens=)
    anthropic.Message  ──▶  LLMResponse(text, stop_reason, usage, ids)
    anthropic.APIError ──▶  the app's own LLMError taxonomy

Nothing above this module learns that Anthropic exists. The service, the agent,
the CLI and the API all keep talking to :class:`~app.llm.base.LLMProvider`, and
an AST test asserts that the seam modules beside this one stay vendor-free.

**Why the client is injectable.** ``complete()`` is where a paid call would
happen, so the constructor takes an optional ``client``. Tests pass a fake and
exercise every translation path -- request shape, response parsing, all nine
error mappings -- with no network, no key and no spend. Without the seam the
only way to test this file would be to call the API, which is exactly the thing
the project has refused to do since Stage 4.

**No API key means no client is built at all.** Constructing without a key
raises :class:`~app.llm.base.LLMConfigurationError` before an SDK client object
exists, rather than deferring to a 401 at request time. It also means the test
suite cannot accidentally build a live client: the test settings carry no key,
so any test that forgot to inject a fake fails loudly instead of quietly
reaching the internet.

**On thinking and sampling.** No sampling parameters are sent -- current models
reject them, and :class:`~app.llm.models.CompletionRequest` deliberately carries
none (Stage 4, guide 4.9). The ``thinking`` parameter is omitted too, which on
current models means adaptive thinking decides for itself. That is the
recommended default and needs no configuration; the important consequence is
that a response may open with a thinking block, so the text is gathered from the
``text`` blocks specifically rather than from ``content[0]``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import anthropic

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.tracing import traced
from app.llm.base import (
    LLMConfigurationError,
    LLMConnectionError,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
    read_retry_after,
)
from app.llm.models import CompletionRequest, LLMResponse, StopReason, TokenUsage

if TYPE_CHECKING:  # pragma: no cover - typing only
    from anthropic.types import Message

logger = get_logger(__name__)

ANTHROPIC_PROVIDER_ID = "anthropic"

DEFAULT_MODEL = "claude-opus-5"
"""Used when ``BKA_LLM_MODEL`` is unset.

Named here rather than in :mod:`app.core.config` on purpose: a model id is a
vendor's string, and the shared configuration is vendor-neutral. Each adapter
owns its own default, so switching provider does not require also knowing to
change the model name.
"""

_STOP_REASONS: dict[str, StopReason] = {
    "end_turn": "end_turn",
    "max_tokens": "max_tokens",
    "refusal": "refusal",
    "stop_sequence": "other",
    "tool_use": "other",
    "pause_turn": "other",
    # The *input* exceeded the window. Not a truncated answer -- there is no
    # answer -- so it must not be reported as one.
    "model_context_window_exceeded": "error",
}


class AnthropicProvider:
    """An :class:`~app.llm.base.LLMProvider` backed by the Anthropic API."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: Any | None = None,
    ) -> None:
        """Build the adapter, and its SDK client unless one is supplied.

        Args:
            settings: Application settings. Defaults to the cached singleton.
            client: An object exposing ``messages.create``. Injected by tests;
                when ``None`` a real client is constructed from configuration.

        Raises:
            LLMConfigurationError: If no client is supplied and
                ``BKA_LLM_API_KEY`` is unset.
        """
        resolved = settings or get_settings()
        self._model_id = resolved.llm_model or DEFAULT_MODEL

        if client is not None:
            self._client = client
            return

        key = resolved.llm_api_key
        if key is None:
            raise LLMConfigurationError(
                "BKA_LLM_PROVIDER='anthropic' needs BKA_LLM_API_KEY, which is "
                "unset. Set it in the environment only -- never in a file, and "
                "never in this repository. Note that a real call is a PAID "
                "call: the default provider is 'mock', which is free."
            )
        self._client = anthropic.Anthropic(
            api_key=key.get_secret_value(),
            timeout=resolved.llm_timeout_seconds,
            max_retries=resolved.llm_max_retries,
        )

    @property
    def provider_id(self) -> str:
        """Identifier recorded on every response this provider produces."""
        return ANTHROPIC_PROVIDER_ID

    @property
    def model_id(self) -> str:
        """The configured model, or this adapter's default."""
        return self._model_id

    @traced
    def complete(self, request: CompletionRequest) -> LLMResponse:
        """Generate one response.

        **This is a paid API call.**

        Args:
            request: The provider-agnostic request to translate and send.

        Returns:
            The generation, normalised into this application's vocabulary.
            Truncated, refused and empty generations are returned faithfully
            here and rejected by :class:`~app.llm.service.LLMService` -- an
            adapter reports what happened; it does not decide what is usable.

        Raises:
            LLMError: On any failure, translated from the SDK's own hierarchy.
        """
        try:
            message = self._client.messages.create(
                model=self._model_id,
                max_tokens=request.max_tokens,
                system=request.system,
                messages=[
                    {"role": turn.role, "content": turn.content}
                    for turn in request.messages
                ],
            )
        except Exception as exc:
            raise self._translate(exc) from exc

        try:
            response = self._to_response(message)
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - re-raised as a typed error
            # The call succeeded but the reply is not the shape the SDK
            # promises. Malformed, not unmapped: retrying will not fix it.
            raise LLMResponseError(
                f"Anthropic returned a reply that could not be read "
                f"({type(exc).__name__})."
            ) from exc
        logger.info(
            "llm.anthropic.completed",
            # Shape and cost only -- never the prompt or the answer, both of
            # which embed retrieved document text (Stage 4 decision, unchanged).
            model=response.model_id,
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cached_input_tokens=response.usage.cached_input_tokens,
        )
        return response

    def _to_response(self, message: Message) -> LLMResponse:
        """Normalise an SDK message into :class:`LLMResponse`.

        Text is gathered from the ``text`` blocks rather than from
        ``content[0]``: with thinking enabled the first block is a thinking
        block, and reading it positionally would put reasoning where the answer
        belongs.
        """
        text = "".join(block.text for block in message.content if block.type == "text")
        usage = getattr(message, "usage", None)
        return LLMResponse(
            text=text,
            provider_id=ANTHROPIC_PROVIDER_ID,
            # The model the API says answered, not the one that was asked for.
            # They differ when a request is served by a fallback, and a stored
            # answer should record what actually produced it.
            model_id=getattr(message, "model", None) or self._model_id,
            stop_reason=_STOP_REASONS.get(message.stop_reason or "", "other"),
            usage=TokenUsage(
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cached_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            ),
        )

    @staticmethod
    def _translate(exc: Exception) -> Exception:
        """Map an SDK exception onto this application's taxonomy.

        Ordered most specific first, because the SDK's own hierarchy nests:
        ``APITimeoutError`` is an ``APIConnectionError``, and every status error
        is an ``APIError``. Reversing two of these lines would silently coarsen
        the mapping rather than break a test.

        **Stage 13: messages name the SDK type and status, never the SDK's own
        text**, which can quote the provider's response body. The original
        stays reachable as ``__cause__`` (``raise ... from exc``).
        """
        kind = type(exc).__name__
        if isinstance(exc, anthropic.APITimeoutError):
            return LLMTimeoutError(f"Anthropic request timed out ({kind}).")
        if isinstance(exc, anthropic.RateLimitError):
            return LLMRateLimitError(
                f"Anthropic rate limit reached ({kind}, {exc.status_code}).",
                retry_after_seconds=read_retry_after(exc),
            )
        if isinstance(
            exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError
        ):
            # The key, not the request. Never retryable, and the message must
            # not echo the key or any part of it.
            return LLMConfigurationError(
                "Anthropic rejected the credentials in BKA_LLM_API_KEY "
                f"({kind}). The key is wrong, revoked, or lacks "
                "access to the configured model."
            )
        if isinstance(exc, anthropic.NotFoundError):
            return LLMConfigurationError(
                f"Anthropic does not recognise the configured model ({kind}, "
                f"{exc.status_code}). Check BKA_LLM_MODEL."
            )
        if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
            return LLMConnectionError(
                f"Anthropic returned a server error ({kind}, {exc.status_code})."
            )
        if isinstance(exc, anthropic.APIConnectionError):
            return LLMConnectionError(f"Could not reach Anthropic ({kind}).")
        if isinstance(exc, anthropic.APIStatusError):
            return LLMProviderError(
                f"Anthropic rejected the request ({kind}, {exc.status_code})."
            )
        return LLMProviderError(f"Anthropic call failed with an unmapped {kind}.")
