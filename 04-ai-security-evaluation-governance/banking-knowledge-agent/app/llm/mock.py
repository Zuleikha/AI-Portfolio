"""A deterministic, offline :class:`~app.llm.base.LLMProvider` implementation.

This is the only provider Stage 4 ships, by decision: no vendor is chosen yet,
so there is nothing here that can reach the network, need a key, or cost money.
The suite is free and offline *by construction* rather than by discipline.

It is not a stub that returns a fixed string. It plays three distinct roles:

``default``
    Synthesises an answer from the passages actually present in the request —
    citing them by the numbers the prompt assigned. That makes it useful for the
    CLI demo and for end-to-end tests, because a bug in context injection shows
    up as a missing or misnumbered citation instead of passing unnoticed.

``scripted``
    Returns caller-supplied responses in order, for asserting how the service
    handles a specific generation (truncated, refused, empty).

``handler``
    Delegates to a callable, which may raise — the way timeout, rate-limit and
    malformed-response handling is exercised without a network.

It also records every :class:`~app.llm.models.CompletionRequest` it receives, so
tests can assert on what was actually sent — that the knowledge base was not
pasted in wholesale, that the system prompt is the versioned one, that the
question is present exactly once.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from app.core.logging import get_logger
from app.core.tracing import traced
from app.llm.base import LLMResponseError
from app.llm.models import CompletionRequest, LLMResponse, StopReason, TokenUsage
from app.llm.prompts import (
    INSUFFICIENT_EVIDENCE,
    TOOL_CITATION_PREFIX,
    TOOL_RESULT_OPEN,
)

logger = get_logger(__name__)

MOCK_PROVIDER_ID = "mock"
MOCK_MODEL_ID = "mock-deterministic-v1"

_PASSAGE_ID_PATTERN = re.compile(r'<passage id="(\d+)"')
_TOOL_RESULT_ID_PATTERN = re.compile(
    re.escape(TOOL_RESULT_OPEN) + r' id="(' + TOOL_CITATION_PREFIX + r'\d+)"'
)
_QUESTION_PATTERN = re.compile(r"^Question: (.+)$", re.MULTILINE | re.DOTALL)

# Roughly four characters per token. Deliberately crude: it exists so usage
# accounting is exercised end to end, and it is named as an estimate rather than
# dressed up as a real tokenizer count.
_CHARS_PER_TOKEN = 4


class MockLLMProvider:
    """An :class:`~app.llm.base.LLMProvider` that never leaves the process.

    Attributes:
        calls: Every request received, in order. Cleared by :meth:`reset`.
    """

    def __init__(
        self,
        responses: Sequence[LLMResponse | str] | None = None,
        handler: Callable[[CompletionRequest], LLMResponse] | None = None,
        model_id: str = MOCK_MODEL_ID,
    ) -> None:
        """Configure the mock's behaviour.

        Args:
            responses: Replies to return in order, as ready-made responses or as
                plain strings. Exhausting the script is an error, not a silent
                wrap-around: a test that sends more requests than it scripted has
                a bug worth surfacing.
            handler: Called for each request instead of the default behaviour.
                May raise, which is how error paths are tested.
            model_id: Reported as the answering model.

        Raises:
            ValueError: If both ``responses`` and ``handler`` are given, since
                the resulting precedence would be invisible at the call site.
        """
        if responses is not None and handler is not None:
            raise ValueError("Pass either 'responses' or 'handler', not both.")
        self._scripted = list(responses) if responses is not None else None
        self._handler = handler
        self._model_id = model_id
        self.calls: list[CompletionRequest] = []

    @property
    def provider_id(self) -> str:
        """Identifier recorded on every response this provider produces."""
        return MOCK_PROVIDER_ID

    @property
    def model_id(self) -> str:
        """Identifier of the pseudo-model answering."""
        return self._model_id

    @property
    def call_count(self) -> int:
        """How many requests have been served since construction or reset."""
        return len(self.calls)

    @property
    def last_request(self) -> CompletionRequest | None:
        """The most recent request, or ``None`` if there has not been one."""
        return self.calls[-1] if self.calls else None

    def reset(self) -> None:
        """Forget recorded calls. Does not restore an exhausted script."""
        self.calls.clear()

    @traced
    def complete(self, request: CompletionRequest) -> LLMResponse:
        """Produce a response for ``request``.

        Args:
            request: The prompt to answer.

        Returns:
            A scripted, handler-produced, or synthesised response.

        Raises:
            LLMResponseError: If a script was provided and is exhausted.
            LLMError: Whatever a configured ``handler`` chooses to raise.
        """
        self.calls.append(request)
        logger.info(
            "llm.mock.complete",
            # The prompt itself is never logged: it embeds retrieved document
            # text, and Stage 10 decides deliberately what request payloads are
            # recorded. Shape only.
            passages=len(_PASSAGE_ID_PATTERN.findall(request.user_text)),
            max_tokens=request.max_tokens,
            call=len(self.calls),
        )

        if self._handler is not None:
            return self._handler(request)
        if self._scripted is not None:
            return self._next_scripted(self._scripted)
        return self._synthesise(request)

    def _next_scripted(self, script: list[LLMResponse | str]) -> LLMResponse:
        """Pop the next scripted reply, normalising a bare string into a response."""
        if not script:
            raise LLMResponseError(
                f"MockLLMProvider script exhausted after {len(self.calls) - 1} "
                "response(s); the code under test sent more requests than the "
                "test scripted."
            )
        nxt = script.pop(0)
        if isinstance(nxt, LLMResponse):
            return nxt
        return self._build(nxt)

    def _synthesise(self, request: CompletionRequest) -> LLMResponse:
        """Answer from the passages in the request, deterministically.

        Reads the passage numbers the prompt assigned and cites them back. This
        makes the mock a genuine check on context injection: if no passage
        reaches the prompt, the mock says so in the same words the real model is
        instructed to use, and the difference is visible in a test.
        """
        text = request.user_text
        passage_ids = _PASSAGE_ID_PATTERN.findall(text)
        tool_ids = _TOOL_RESULT_ID_PATTERN.findall(text)
        question_match = _QUESTION_PATTERN.search(text)
        question = question_match.group(1).strip() if question_match else "(unknown)"

        if tool_ids:
            # Stage 7's tool-only route puts readings and no passages in the
            # prompt. Citing them keeps the mock an honest wiring check for that
            # route instead of answering it with a refusal-shaped sentence.
            citations = "".join(f"[{identifier}]" for identifier in passage_ids)
            citations += "".join(f"[{identifier}]" for identifier in tool_ids)
            return self._build(
                f"Answering from the supplied evidence. "
                f"Question: {question} "
                f"This response was assembled from {len(passage_ids)} retrieved "
                f"passage(s) and {len(tool_ids)} tool result(s) {citations} by the "
                f"deterministic mock provider; it is a wiring check, not a "
                f"generated answer.",
                stop_reason="end_turn",
                prompt_chars=len(request.system) + len(text),
            )

        if not passage_ids:
            return self._build(
                f"{INSUFFICIENT_EVIDENCE} No documentation passages were "
                f"supplied with the question: {question}",
                stop_reason="end_turn",
            )

        citations = "".join(f"[{identifier}]" for identifier in passage_ids)
        return self._build(
            f"Answering from the retrieved documentation. "
            f"Question: {question} "
            f"This response was assembled from {len(passage_ids)} retrieved "
            f"passage(s) {citations} by the deterministic mock provider; it is "
            f"a wiring check, not a generated answer.",
            stop_reason="end_turn",
            prompt_chars=len(request.system) + len(text),
        )

    def _build(
        self,
        text: str,
        stop_reason: StopReason = "end_turn",
        prompt_chars: int = 0,
    ) -> LLMResponse:
        """Wrap generated text in a response with estimated usage."""
        return LLMResponse(
            text=text,
            provider_id=MOCK_PROVIDER_ID,
            model_id=self._model_id,
            stop_reason=stop_reason,
            usage=TokenUsage(
                input_tokens=prompt_chars // _CHARS_PER_TOKEN,
                output_tokens=len(text) // _CHARS_PER_TOKEN,
            ),
        )
