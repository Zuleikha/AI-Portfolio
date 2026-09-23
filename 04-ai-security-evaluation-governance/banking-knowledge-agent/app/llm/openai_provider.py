"""OpenAI adapter: the same seam, a second vendor, no change above it.

The second of exactly two modules in this package allowed to import a vendor.
Its existence is the evidence for the abstraction: swapping providers is
``BKA_LLM_PROVIDER=openai`` and nothing else. Not one line of
:mod:`app.llm.service`, :mod:`app.agent.agent` or the CLI knows which of the two
answered.

Reading this file beside ``anthropic_provider.py`` shows what the seam is
actually absorbing, which is more than "a different function name":

=====================  =============================  =============================
Concern                Anthropic                      OpenAI
=====================  =============================  =============================
System instructions    top-level ``system=``          a ``system`` role message
Output ceiling         ``max_tokens``                 ``max_completion_tokens``
Why it stopped         ``stop_reason`` (7 values)     ``finish_reason`` (5 values)
A refusal              ``stop_reason="refusal"``      ``message.refusal`` is set
The generated text     text blocks in a list          ``message.content``, nullable
Token accounting       ``input``/``output_tokens``    ``prompt``/``completion_``
=====================  =============================  =============================

Every one of those differences would otherwise have leaked upward into the
service, the agent and eventually the web interface.

**Why ``max_completion_tokens`` and not ``max_tokens``.** ``max_tokens`` is
deprecated on this endpoint and is rejected outright by reasoning models, which
bill their reasoning as completion tokens. Sending the parameter the current API
wants keeps the adapter working across the model range rather than only on the
older ones.

The client is injectable and a missing key raises before any client is built,
for the same reasons set out in ``anthropic_provider.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import openai

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
    from openai.types.chat import ChatCompletion

logger = get_logger(__name__)

OPENAI_PROVIDER_ID = "openai"

DEFAULT_MODEL = "gpt-5.5"
"""Used when ``BKA_LLM_MODEL`` is unset. See the note in the sibling adapter on
why a model id lives with its vendor rather than in shared configuration."""

_FINISH_REASONS: dict[str, StopReason] = {
    "stop": "end_turn",
    "length": "max_tokens",
    "content_filter": "refusal",
    "tool_calls": "other",
    "function_call": "other",
}


class OpenAIProvider:
    """An :class:`~app.llm.base.LLMProvider` backed by the OpenAI API."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: Any | None = None,
    ) -> None:
        """Build the adapter, and its SDK client unless one is supplied.

        Args:
            settings: Application settings. Defaults to the cached singleton.
            client: An object exposing ``chat.completions.create``. Injected by
                tests; when ``None`` a real client is built from configuration.

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
                "BKA_LLM_PROVIDER='openai' needs BKA_LLM_API_KEY, which is "
                "unset. Set it in the environment only -- never in a file, and "
                "never in this repository. Note that a real call is a PAID "
                "call: the default provider is 'mock', which is free."
            )
        self._client = openai.OpenAI(
            api_key=key.get_secret_value(),
            timeout=resolved.llm_timeout_seconds,
            max_retries=resolved.llm_max_retries,
        )

    @property
    def provider_id(self) -> str:
        """Identifier recorded on every response this provider produces."""
        return OPENAI_PROVIDER_ID

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

        Raises:
            LLMError: On any failure, translated from the SDK's own hierarchy.
        """
        messages: list[dict[str, str]] = [{"role": "system", "content": request.system}]
        messages.extend(
            {"role": turn.role, "content": turn.content} for turn in request.messages
        )

        try:
            completion = self._client.chat.completions.create(
                model=self._model_id,
                messages=messages,
                max_completion_tokens=request.max_tokens,
            )
        except Exception as exc:
            raise self._translate(exc) from exc

        try:
            response = self._to_response(completion)
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - re-raised as a typed error
            # See the Anthropic adapter: malformed, not unmapped.
            raise LLMResponseError(
                f"OpenAI returned a reply that could not be read "
                f"({type(exc).__name__})."
            ) from exc
        logger.info(
            "llm.openai.completed",
            # Shape and cost only -- never the prompt or the answer.
            model=response.model_id,
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cached_input_tokens=response.usage.cached_input_tokens,
        )
        return response

    def _to_response(self, completion: ChatCompletion) -> LLMResponse:
        """Normalise an SDK completion into :class:`LLMResponse`.

        Raises:
            LLMResponseError: If the reply carries no choices at all. That is
                not a refusal and not an empty answer -- it is a malformed
                response, and it must not be handed on as though the model had
                nothing to say.
        """
        choices = getattr(completion, "choices", None) or []
        if not choices:
            raise LLMResponseError(
                f"OpenAI returned no choices for model '{self._model_id}'."
            )

        choice = choices[0]
        message = choice.message
        usage = getattr(completion, "usage", None)

        # A refusal is reported on the message, not in finish_reason, so it is
        # checked first -- otherwise a refusal arrives labelled "end_turn" and
        # the service shows the empty string as an answer.
        refusal = getattr(message, "refusal", None)
        stop_reason: StopReason = (
            "refusal"
            if refusal
            else _FINISH_REASONS.get(choice.finish_reason or "", "other")
        )

        return LLMResponse(
            text=message.content or "",
            provider_id=OPENAI_PROVIDER_ID,
            model_id=getattr(completion, "model", None) or self._model_id,
            stop_reason=stop_reason,
            usage=TokenUsage(
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                cached_input_tokens=getattr(
                    getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0
                )
                or 0,
            ),
        )

    @staticmethod
    def _translate(exc: Exception) -> Exception:
        """Map an SDK exception onto this application's taxonomy.

        Deliberately the same shape as the Anthropic adapter's, because the two
        vendors' hierarchies happen to agree closely. Where they agree, the
        translation should look identical; where they differ -- refusals, token
        field names, the output-ceiling parameter -- the difference is handled
        above and stops here.

        As in the Anthropic adapter, messages name the SDK type and status,
        never the SDK's own text (Stage 13); the original is ``__cause__``.
        """
        kind = type(exc).__name__
        if isinstance(exc, openai.APITimeoutError):
            return LLMTimeoutError(f"OpenAI request timed out ({kind}).")
        if isinstance(exc, openai.RateLimitError):
            return LLMRateLimitError(
                f"OpenAI rate limit reached ({kind}, {exc.status_code}).",
                retry_after_seconds=read_retry_after(exc),
            )
        if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
            return LLMConfigurationError(
                "OpenAI rejected the credentials in BKA_LLM_API_KEY "
                f"({kind}). The key is wrong, revoked, or lacks "
                "access to the configured model."
            )
        if isinstance(exc, openai.NotFoundError):
            return LLMConfigurationError(
                f"OpenAI does not recognise the configured model ({kind}, "
                f"{exc.status_code}). Check BKA_LLM_MODEL."
            )
        if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
            return LLMConnectionError(
                f"OpenAI returned a server error ({kind}, {exc.status_code})."
            )
        if isinstance(exc, openai.APIConnectionError):
            return LLMConnectionError(f"Could not reach OpenAI ({kind}).")
        if isinstance(exc, openai.APIStatusError):
            return LLMProviderError(
                f"OpenAI rejected the request ({kind}, {exc.status_code})."
            )
        return LLMProviderError(f"OpenAI call failed with an unmapped {kind}.")
