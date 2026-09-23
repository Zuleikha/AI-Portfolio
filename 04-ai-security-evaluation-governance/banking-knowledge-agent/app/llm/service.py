"""The application-facing LLM service: retrieved context in, grounded answer out.

``LLMService`` is the only thing above this package that callers need. It owns
the sequence that turns evidence into an answer::

    question + RetrievalResult
        -> select_context   (apply the context budget)
        -> build_request    (frozen system prompt + fenced passages + question)
        -> provider.complete
        -> validate         (truncation, refusal, empty body, invented citations)
        -> GroundedAnswer   (text + sources + provenance)

**What it deliberately does not do.** It does not retrieve. It is handed a
:class:`~app.rag.models.RetrievalResult` that someone else produced. Deciding
*whether* to retrieve, reformulating a question, choosing tools and running the
agent loop are Stage 5 and Stage 7; putting any of that here would make this
class the agent under a different name and leave the seam untested.

**Why empty evidence short-circuits.** When there is nothing to answer from, this
service answers with :data:`~app.llm.prompts.INSUFFICIENT_EVIDENCE` and does not
call the provider. A generation request with zero evidence has exactly two
possible outcomes — a refusal, or an answer invented from the model's own
training — and one of those is the failure mode this entire architecture exists
to prevent. Not sending it is cheaper, faster, deterministic, and removes the
only path by which an ungrounded answer could be produced. Stage 5's agent
builds its decision logic on top of this guard; it does not replace it.

**Stage 6 widened what counts as evidence, and nothing else.** A tool result is
evidence, so a question with no matching documents but a successful tool call is
answered rather than refused. The guard itself is unchanged in shape: it still
asks "is there anything to reason from?", it is still the only place that
question is asked, and it still makes zero provider calls when the answer is no.

**A tool result that found nothing still counts.** ``ok=False`` — *no transaction
has that reference* — is a fact about the world, not an absence of evidence, and
the model is instructed to report it. Treating it as emptiness would collapse
"the system says it does not exist" into "we have no information", which are
different answers and lead a support engineer to different next steps.

**Failures are raised, never returned as text.** A truncated or refused
generation is not quietly handed back as an answer. It raises, because a
half-finished sentence about a transaction limit is more dangerous than an
error: it looks complete.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.observability import (
    LLM_CALL_DURATION_MS,
    LLM_CALLS_TOTAL,
    LLM_ERRORS_TOTAL,
    LLM_INPUT_TOKENS_TOTAL,
    LLM_INVALID_CITATIONS_TOTAL,
    LLM_OUTPUT_TOKENS_TOTAL,
    elapsed_ms,
    get_metrics,
)
from app.core.tracing import traced
from app.llm.base import (
    LLMError,
    LLMInvalidCitationError,
    LLMProvider,
    LLMProviderError,
    LLMRefusalError,
    LLMResponseError,
)
from app.llm.citations import invalid_citations
from app.llm.models import CompletionRequest, GroundedAnswer, LLMResponse
from app.llm.prompts import (
    INSUFFICIENT_EVIDENCE,
    SYSTEM_PROMPT_VERSION,
    build_request,
    select_context,
)
from app.mcp.models import ToolResult
from app.rag.models import RetrievalResult

logger = get_logger(__name__)


class LLMService:
    """Generates source-backed answers from retrieved context.

    The provider is injected as a protocol, exactly as the retriever's embedder
    and store are. Swapping a mock for a real adapter is a constructor argument,
    not a change to this class or to anything that calls it.
    """

    def __init__(
        self,
        provider: LLMProvider,
        settings: Settings | None = None,
    ) -> None:
        """Wire the service to a provider.

        Args:
            provider: The model implementation to generate with.
            settings: Application settings. Defaults to the cached singleton.
        """
        self._provider = provider
        self._settings = settings or get_settings()

    @property
    def provider(self) -> LLMProvider:
        """The provider answering requests."""
        return self._provider

    @traced
    def answer(
        self,
        question: str,
        retrieval: RetrievalResult,
        tool_results: tuple[ToolResult, ...] = (),
        history: Sequence[str] = (),
    ) -> GroundedAnswer:
        """Answer ``question`` from the passages and tool results supplied.

        **Stage 8: history is never evidence.** Earlier questions help the model
        read a follow-up, but they do not count toward the refusal guard: a
        follow-up with no passage and no tool result is refused, with no model
        call, exactly as a first question would be.

        Args:
            question: The user's question, in natural language.
            retrieval: Evidence gathered by the RAG layer. An empty result is a
                valid input.
            tool_results: Evidence gathered by the MCP layer. Empty by default,
                which is exactly the Stage 4 and Stage 5 behaviour.
            history: Earlier questions of the conversation, oldest first. Empty
                for a standalone question, which then gets no history block.

        Returns:
            The answer together with its sources and provenance. A refusal is
            returned only when there is neither a passage nor a tool result.

        Raises:
            ValueError: If the question is blank.
            LLMResponseError: If the generation was truncated or empty.
            LLMRefusalError: If the model declined to answer.
            LLMError: For any other provider failure; the concrete subclass says
                whether a retry is worthwhile.
        """
        if not question.strip():
            raise ValueError("Cannot answer an empty question.")

        selected = select_context(retrieval, self._settings)
        if not selected and not tool_results:
            return self._refuse(question, retrieval)

        request = build_request(
            question, selected, self._settings, tool_results, tuple(history)
        )
        # Latency covers the provider call and validation: an unusable generation
        # is a failed LLM call, counted and logged as one.
        metrics = get_metrics()
        metrics.increment(LLM_CALLS_TOTAL)
        started = time.perf_counter()
        try:
            response = self._complete(request)
            self._validate(response)
            self._check_citations(response, len(selected), len(tool_results))
        except LLMError as exc:
            latency = elapsed_ms(started)
            metrics.increment(LLM_ERRORS_TOTAL)
            metrics.observe(LLM_CALL_DURATION_MS, latency)
            logger.warning(
                "llm.failed",
                # Type only: the message may quote the provider's own wording.
                provider=getattr(self._provider, "provider_id", "unknown"),
                error_type=type(exc).__name__,
                retryable=exc.retryable,
                latency_ms=latency,
            )
            raise
        latency = elapsed_ms(started)
        metrics.observe(LLM_CALL_DURATION_MS, latency)
        if response.usage.input_tokens:
            metrics.increment(LLM_INPUT_TOKENS_TOTAL, response.usage.input_tokens)
        if response.usage.output_tokens:
            metrics.increment(LLM_OUTPUT_TOKENS_TOTAL, response.usage.output_tokens)

        # Document citations only. A tool is not a "source" in the sense this
        # field means -- it is not something a reader can open and check -- and
        # merging tool names into the same tuple would undo at the last moment
        # the documentation/live separation the prompt just spent two fences
        # establishing. Tool provenance travels on the agent's own record.
        sources = tuple(scored.chunk.citation for scored in selected)
        answer = GroundedAnswer(
            question=question,
            text=response.text,
            sources=sources,
            chunks_used=len(selected),
            chunks_available=len(retrieval.chunks),
            tools_used=len(tool_results),
            refused=False,
            llm_called=True,
            response=response,
            prompt_version=SYSTEM_PROMPT_VERSION,
        )
        logger.info(
            "llm.answered",
            # Neither the prompt nor the answer text is logged: both embed
            # document content, and Stage 10 decides deliberately what a request
            # record contains. Shape, cost and provenance only. Tool *names* are
            # safe here; their payloads are not, and are not logged.
            provider=response.provider_id,
            model=response.model_id,
            latency_ms=latency,
            prompt_version=SYSTEM_PROMPT_VERSION,
            chunks_used=answer.chunks_used,
            chunks_available=answer.chunks_available,
            tools_used=answer.tools_used,
            tools=[result.tool for result in tool_results],
            history_questions=len(history),
            sources=len(sources),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )
        return answer

    def _refuse(self, question: str, retrieval: RetrievalResult) -> GroundedAnswer:
        """Answer with the fixed insufficient-evidence sentence. No model call."""
        logger.info(
            "llm.refused_no_context",
            candidates=retrieval.candidates_considered,
            min_score=retrieval.min_score,
            top_score=retrieval.top_score,
        )
        return GroundedAnswer(
            question=question,
            text=INSUFFICIENT_EVIDENCE,
            sources=(),
            chunks_used=0,
            chunks_available=len(retrieval.chunks),
            refused=True,
            llm_called=False,
            response=None,
            prompt_version=SYSTEM_PROMPT_VERSION,
        )

    def _complete(self, request: CompletionRequest) -> LLMResponse:
        """Call the provider, guaranteeing only :class:`LLMError` escapes.

        A provider that raises something untyped has a gap in its translation
        table. Wrapping it here keeps a raw SDK exception from reaching the API
        layer -- where it would be reported as a generic 500 with a vendor's
        wording -- while still failing loudly and preserving the cause.

        **Stage 13: the message names the type, never the text.** The original
        exception stays reachable as ``__cause__`` for debugging; its wording
        (which may quote a provider, a host or a payload) is not copied into an
        application error that any caller might print.
        """
        try:
            return self._provider.complete(request)
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - re-raised as a typed error
            raise LLMProviderError(
                f"Provider '{getattr(self._provider, 'provider_id', 'unknown')}' "
                f"raised an untranslated {type(exc).__name__}."
            ) from exc

    @staticmethod
    def _check_citations(response: LLMResponse, chunks: int, tools: int) -> None:
        """Withhold an answer that cites evidence it was never given (14.B).

        The markers themselves are safe to name -- ``[7]`` carries no content --
        and naming them is what makes the failure diagnosable.

        Raises:
            LLMInvalidCitationError: If any ``[n]`` / ``[Tn]`` is outside the
                passages and tool results numbered in the prompt.
        """
        invented = invalid_citations(response.text, chunks, tools)
        if invented:
            get_metrics().increment(LLM_INVALID_CITATIONS_TOTAL)
            raise LLMInvalidCitationError(
                f"Model '{response.model_id}' cited evidence that was not supplied "
                f"({' '.join(invented)}; {chunks} passage(s), {tools} tool "
                "result(s) were sent). The answer is withheld.",
                markers=invented,
            )

    @staticmethod
    def _validate(response: LLMResponse) -> None:
        """Reject a generation that must not be shown as an answer.

        **Stage 13: a generation that ended in an error is withheld too**, even
        when it carries text -- the provider said it did not finish normally
        (for example, the context window filled mid-answer), so the text is no
        safer to show than a truncated one.

        Raises:
            LLMRefusalError: If the model declined.
            LLMResponseError: If the generation was truncated, ended in an
                error, or is empty.
        """
        if response.stop_reason == "refusal":
            raise LLMRefusalError(
                f"Model '{response.model_id}' declined to answer the question."
            )
        if response.stop_reason == "error":
            raise LLMResponseError(
                f"Model '{response.model_id}' reported that the generation ended "
                "in an error. Any partial text is withheld."
            )
        if response.stop_reason == "max_tokens":
            raise LLMResponseError(
                f"Model '{response.model_id}' hit the token ceiling and the "
                "answer is truncated. A truncated answer is withheld rather "
                "than shown, because it reads as complete."
            )
        if not response.text.strip():
            raise LLMResponseError(
                f"Model '{response.model_id}' returned an empty response "
                f"(stop_reason={response.stop_reason})."
            )
