"""The ``LLMProvider`` seam, and the error taxonomy every provider maps onto.

This module is the reason the application is not tied to a vendor. Everything
above it — the service, the agent in Stage 5, the API in Stage 9 — depends on the
:class:`LLMProvider` protocol and on the exceptions defined here. Nothing above
it imports an SDK, names a vendor, or handles a vendor's exception type.

**Why a protocol rather than an abstract base class.** A protocol is satisfied
structurally, so a test double, a future adapter, or a caching decorator is a
provider by virtue of having the right methods — no inheritance, no registration,
no import of this module at all. The same choice was made for
:class:`~app.rag.embeddings.Embedder` and :class:`~app.rag.vectorstore.VectorStore`
in Stage 3, and it is what let the RAG pipeline be tested with a hashing embedder
without a single ``if testing:`` branch.

**Why the errors live here and not in each adapter.** Callers need to answer one
question about a failure: *can this be retried, or is it broken?* Vendor SDKs
each answer that with their own class hierarchy. If those leaked upward, every
call site would grow a vendor-specific ``except`` chain, and swapping providers
would mean rewriting error handling everywhere. Each adapter translates its
vendor's failures into these types **once**, at the boundary, and
:attr:`LLMError.retryable` carries the only distinction most callers need.

Errors are never swallowed here. A failed generation raises; it does not return
an empty answer that a caller might mistake for the model having nothing to say.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.llm.models import CompletionRequest, LLMResponse


class LLMError(RuntimeError):
    """Base class for every failure originating in the LLM layer.

    Attributes:
        retryable: Whether the same request could plausibly succeed if sent
            again. Subclasses set this; callers should branch on it rather than
            on the concrete type, so a new error class does not silently become
            non-retryable at every existing call site.
    """

    retryable: bool = False


class LLMConfigurationError(LLMError):
    """The LLM layer is misconfigured: no provider, unknown provider, no key.

    Never retryable — the request is fine, the environment is not. Raised at the
    point of use rather than at import or construction time, so that an
    application with no LLM configured still starts, still serves ``/health``,
    and still runs every non-LLM code path. A missing key must not be a startup
    crash; it must be an explicit failure of the one operation that needs it.
    """


class LLMTimeoutError(LLMError):
    """The provider did not respond within the configured timeout."""

    retryable = True


class LLMConnectionError(LLMError):
    """The request never completed: the transport failed, or the service did.

    Covers a connection reset, a DNS or TLS failure, and any 5xx the provider
    returns. Retryable, because nothing about the request is wrong.

    **Added in Stage 5, and the reason is worth keeping.** Stage 4 defined this
    taxonomy with no adapter to test it against, and it had a gap: the only
    retryable types were a timeout and a rate limit. Writing the first two real
    adapters immediately produced failures that are neither -- ``APIConnectionError``
    and ``InternalServerError`` exist in both vendors' SDKs -- and the choices
    were to mislabel them as timeouts or to mark them non-retryable through
    :class:`LLMProviderError`. Both are wrong in the one field callers branch on.
    That a concrete adapter found this within an hour is the argument for
    building one at all.
    """

    retryable = True


class LLMRateLimitError(LLMError):
    """The provider rejected the request for rate or quota reasons."""

    retryable = True

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        """Record how long the provider asked the caller to wait, when it said.

        Args:
            message: Human-readable description of the failure.
            retry_after_seconds: The provider's advertised cool-off, if any.
                ``None`` means the provider did not say — which is not the same
                as "retry immediately", so it is kept distinguishable.
        """
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class LLMResponseError(LLMError):
    """The provider replied, but the reply cannot be used as an answer.

    Covers a truncated generation, an empty body, and anything that fails to
    parse. Deliberately distinct from a transport failure: the call succeeded, so
    retrying the identical request will usually produce the identical problem.
    A truncated answer is the dangerous case — it reads as complete and ends
    mid-sentence — which is why it is an error here rather than a warning.
    """


class LLMInvalidCitationError(LLMResponseError):
    """The answer cites a passage or tool result that was never sent (14.B).

    A :class:`LLMResponseError`, so every caller that withholds an unusable
    answer -- the API's 502 included -- handles it unchanged. Its own type exists
    for the one caller that must tell it apart: the evaluation scores it as a
    failed citation check instead of stopping the run (14.E).

    Attributes:
        markers: The invalid markers, e.g. ``("[9]",)``. Safe to log: a marker
            carries no content.
        route: The agent's route for the question, set by the agent before it
            re-raises. ``None`` when raised outside an agent. A plain string
            because this layer does not know the agent's types.
    """

    def __init__(self, message: str, markers: tuple[str, ...]) -> None:
        """Record the markers alongside the message."""
        super().__init__(message)
        self.markers = markers
        self.route: str | None = None


class LLMRefusalError(LLMError):
    """The model declined to answer.

    Separate from :class:`LLMResponseError` because the correct handling differs:
    a refusal is a decision about the content of the request, so it should be
    surfaced to the user rather than retried or silently replaced.
    """


class LLMProviderError(LLMError):
    """A provider failed in a way its adapter did not anticipate.

    The catch-all that keeps an unmapped vendor exception from escaping the LLM
    layer as a raw SDK type. Its presence in logs is a signal that an adapter's
    translation table has a gap.
    """


@runtime_checkable
class LLMProvider(Protocol):
    """Generates a response for a prompt. The application's only model interface.

    Implementations must guarantee:

    * ``complete`` either returns a valid :class:`~app.llm.models.LLMResponse` or
      raises an :class:`LLMError`. No other exception type escapes, and no
      sentinel "empty" response stands in for a failure.
    * ``provider_id`` and ``model_id`` identify what actually answered, so a
      logged or displayed answer can always be traced back to its source.
    * The call is synchronous. Stage 9 introduces the async path; adding it now
      would mean an untested interface with no caller.
    """

    @property
    def provider_id(self) -> str:
        """Short identifier for this implementation, e.g. ``"mock"``."""

    @property
    def model_id(self) -> str:
        """Identifier of the model that answers, recorded on every response."""

    def complete(self, request: CompletionRequest) -> LLMResponse:
        """Generate a single response.

        Args:
            request: The system instructions, conversation turns and token
                ceiling to generate against.

        Returns:
            The generation, normalised into this application's own vocabulary.

        Raises:
            LLMError: On any failure. The concrete subclass tells the caller
                whether a retry is worthwhile.
        """


def read_retry_after(exc: Exception) -> float | None:
    """Read the provider's advertised cool-off from an SDK exception.

    Reading a ``Retry-After`` header is HTTP, not vendor behaviour: both
    adapters held a byte-identical copy of this until Stage 15, which is two
    places for one rule to be corrected in. It lives beside
    :class:`LLMRateLimitError` because that is the only error that carries the
    value.

    Args:
        exc: The SDK exception, which may or may not carry an HTTP response.

    Returns:
        The advertised wait in seconds, or ``None`` when the provider did not
        say -- deliberately kept distinguishable from "retry immediately".
    """
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        # Retry-After may legitimately be an HTTP date. Not parsing it here is
        # a deliberate omission: the caller treats None as "no advice given",
        # which is the safe reading.
        return None
