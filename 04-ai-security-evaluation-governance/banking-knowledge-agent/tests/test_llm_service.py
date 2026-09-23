"""The service: context injection, refusal, error handling, provenance.

Everything here runs against the real corpus with the hashing embedder and the
mock provider -- offline, deterministic, free.
"""

from __future__ import annotations

import re

import pytest

from app.core.config import Settings
from app.core.observability import LLM_INVALID_CITATIONS_TOTAL, get_metrics
from app.llm.base import (
    LLMInvalidCitationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMResponseError,
    LLMTimeoutError,
)
from app.llm.mock import MockLLMProvider
from app.llm.models import GroundedAnswer, LLMResponse
from app.llm.prompts import (
    CONTEXT_CLOSE,
    CONTEXT_OPEN,
    INSUFFICIENT_EVIDENCE,
    SYSTEM_INSTRUCTIONS,
    SYSTEM_PROMPT_VERSION,
)
from app.llm.service import LLMService
from app.rag.models import RetrievalResult


def raising(error: Exception):
    """A mock handler that raises ``error``."""

    def handler(request):
        raise error

    return handler


# --- The happy path ------------------------------------------------------


class TestAnswer:
    def test_returns_a_grounded_answer(self, llm_service, retrieval):
        answer = llm_service.answer(retrieval.query, retrieval)
        assert isinstance(answer, GroundedAnswer)
        assert answer.text

    def test_calls_the_provider_once(self, llm_service, mock_provider, retrieval):
        llm_service.answer(retrieval.query, retrieval)
        assert mock_provider.call_count == 1

    def test_answer_is_marked_grounded(self, llm_service, retrieval):
        answer = llm_service.answer(retrieval.query, retrieval)
        assert answer.is_grounded
        assert answer.llm_called
        assert not answer.refused

    def test_records_the_question(self, llm_service, retrieval):
        answer = llm_service.answer("what handles card authentication?", retrieval)
        assert answer.question == "what handles card authentication?"

    def test_records_the_prompt_version(self, llm_service, retrieval):
        answer = llm_service.answer(retrieval.query, retrieval)
        assert answer.prompt_version == SYSTEM_PROMPT_VERSION

    def test_carries_the_raw_response(self, llm_service, retrieval):
        answer = llm_service.answer(retrieval.query, retrieval)
        assert answer.response is not None
        assert answer.response.provider_id == "mock"

    def test_reports_how_many_passages_were_used(self, llm_service, retrieval):
        answer = llm_service.answer(retrieval.query, retrieval)
        assert 0 < answer.chunks_used <= len(retrieval.chunks)
        assert answer.chunks_available == len(retrieval.chunks)

    def test_returns_one_source_per_passage_used(self, llm_service, retrieval):
        answer = llm_service.answer(retrieval.query, retrieval)
        assert len(answer.sources) == answer.chunks_used

    def test_sources_name_a_real_document(self, llm_service, retrieval):
        answer = llm_service.answer(retrieval.query, retrieval)
        for source in answer.sources:
            assert ".md" in source

    def test_blank_question_is_rejected(self, llm_service, retrieval):
        with pytest.raises(ValueError, match="empty question"):
            llm_service.answer("   ", retrieval)

    def test_blank_question_is_rejected_before_any_provider_call(
        self, llm_service, mock_provider, retrieval
    ):
        with pytest.raises(ValueError):
            llm_service.answer("", retrieval)
        assert mock_provider.call_count == 0


# --- What actually reaches the provider ----------------------------------


class TestWhatIsSent:
    def test_the_system_prompt_is_the_versioned_one(
        self, llm_service, mock_provider, retrieval
    ):
        llm_service.answer(retrieval.query, retrieval)
        assert mock_provider.calls[0].system == SYSTEM_INSTRUCTIONS

    def test_the_question_is_sent(self, llm_service, mock_provider, retrieval):
        llm_service.answer("a very distinctive question", retrieval)
        assert "a very distinctive question" in mock_provider.calls[0].user_text

    def test_retrieved_passages_are_fenced(self, llm_service, mock_provider, retrieval):
        llm_service.answer(retrieval.query, retrieval)
        sent = mock_provider.calls[0].user_text
        assert CONTEXT_OPEN in sent
        assert CONTEXT_CLOSE in sent

    def test_only_the_selected_passages_are_sent(
        self, llm_service, mock_provider, retrieval, llm_settings
    ):
        answer = llm_service.answer(retrieval.query, retrieval)
        sent = mock_provider.calls[0].user_text
        assert sent.count("<passage id=") == answer.chunks_used
        assert answer.chunks_used <= llm_settings.llm_context_max_chunks

    def test_the_knowledge_base_is_not_sent(
        self, llm_service, mock_provider, retrieval, corpus
    ):
        """The claim of this stage, asserted against the real corpus."""
        answer = llm_service.answer(retrieval.query, retrieval)
        sent = mock_provider.calls[0].user_text
        kept = retrieval.chunks[: answer.chunks_used]
        used = {scored.chunk.document_id for scored in kept}
        unused = [d for d in corpus if d.metadata.document_id not in used]
        assert len(unused) >= 10
        for document in unused:
            assert document.content not in sent

    def test_max_tokens_comes_from_configuration(
        self, mock_provider, retrieval, llm_settings
    ):
        settings = llm_settings.model_copy(update={"llm_max_tokens": 777})
        LLMService(mock_provider, settings).answer(retrieval.query, retrieval)
        assert mock_provider.calls[0].max_tokens == 777

    def test_the_context_budget_is_honoured(
        self, mock_provider, retrieval, llm_settings
    ):
        settings = llm_settings.model_copy(update={"llm_context_max_chunks": 1})
        answer = LLMService(mock_provider, settings).answer(retrieval.query, retrieval)
        assert answer.chunks_used == 1
        assert mock_provider.calls[0].user_text.count("<passage id=") == 1


# --- No evidence ---------------------------------------------------------


class TestRefusalWhenThereIsNoEvidence:
    def test_returns_the_exact_insufficient_evidence_sentence(
        self, llm_service, empty_retrieval
    ):
        answer = llm_service.answer("an unanswerable question", empty_retrieval)
        assert answer.text == INSUFFICIENT_EVIDENCE

    def test_is_marked_refused(self, llm_service, empty_retrieval):
        answer = llm_service.answer("an unanswerable question", empty_retrieval)
        assert answer.refused
        assert not answer.is_grounded

    def test_does_not_call_the_provider_at_all(
        self, llm_service, mock_provider, empty_retrieval
    ):
        """A call with no evidence can only refuse or invent. Neither is worth paying
        for."""
        llm_service.answer("an unanswerable question", empty_retrieval)
        assert mock_provider.call_count == 0

    def test_carries_no_sources_and_no_response(self, llm_service, empty_retrieval):
        answer = llm_service.answer("an unanswerable question", empty_retrieval)
        assert answer.sources == ()
        assert answer.response is None
        assert answer.llm_called is False

    def test_still_records_the_question_and_prompt_version(
        self, llm_service, empty_retrieval
    ):
        answer = llm_service.answer("an unanswerable question", empty_retrieval)
        assert answer.question == "an unanswerable question"
        assert answer.prompt_version == SYSTEM_PROMPT_VERSION

    def test_off_topic_question_over_the_real_corpus_is_refused(
        self, llm_service, mock_provider, retriever
    ):
        result = retriever.retrieve("what is the capital of France?")
        answer = llm_service.answer("what is the capital of France?", result)
        if result.is_empty:
            assert answer.refused
            assert mock_provider.call_count == 0


# --- Provider failures ---------------------------------------------------


class TestErrorHandling:
    def test_a_timeout_propagates(self, llm_settings, retrieval):
        service = LLMService(
            MockLLMProvider(handler=raising(LLMTimeoutError("timed out"))), llm_settings
        )
        with pytest.raises(LLMTimeoutError):
            service.answer(retrieval.query, retrieval)

    def test_a_rate_limit_propagates_with_its_retry_hint(self, llm_settings, retrieval):
        service = LLMService(
            MockLLMProvider(handler=raising(LLMRateLimitError("slow", 12.0))),
            llm_settings,
        )
        with pytest.raises(LLMRateLimitError) as excinfo:
            service.answer(retrieval.query, retrieval)
        assert excinfo.value.retry_after_seconds == 12.0
        assert excinfo.value.retryable is True

    def test_an_untyped_provider_failure_is_wrapped(self, llm_settings, retrieval):
        """A raw vendor exception must never escape the LLM layer."""
        provider = MockLLMProvider(handler=raising(KeyError("some sdk internal")))
        service = LLMService(provider, llm_settings)
        with pytest.raises(LLMProviderError) as excinfo:
            service.answer(retrieval.query, retrieval)
        assert "KeyError" in str(excinfo.value)

    def test_the_original_cause_is_preserved(self, llm_settings, retrieval):
        original = KeyError("root cause")
        service = LLMService(MockLLMProvider(handler=raising(original)), llm_settings)
        with pytest.raises(LLMProviderError) as excinfo:
            service.answer(retrieval.query, retrieval)
        assert excinfo.value.__cause__ is original

    def test_a_refusal_is_raised_not_returned(self, llm_settings, retrieval):
        refused = LLMResponse(
            text="", provider_id="mock", model_id="m", stop_reason="refusal"
        )
        service = LLMService(MockLLMProvider(responses=[refused]), llm_settings)
        with pytest.raises(LLMRefusalError):
            service.answer(retrieval.query, retrieval)

    def test_a_truncated_answer_is_withheld(self, llm_settings, retrieval):
        """A cut-off answer reads as complete, which makes it worse than an error."""
        truncated = LLMResponse(
            text="The daily withdrawal limit is configured in switch.limits.",
            provider_id="mock",
            model_id="m",
            stop_reason="max_tokens",
        )
        service = LLMService(MockLLMProvider(responses=[truncated]), llm_settings)
        with pytest.raises(LLMResponseError, match="truncated"):
            service.answer(retrieval.query, retrieval)

    def test_an_empty_response_is_rejected(self, llm_settings, retrieval):
        empty = LLMResponse(text="   ", provider_id="mock", model_id="m")
        service = LLMService(MockLLMProvider(responses=[empty]), llm_settings)
        with pytest.raises(LLMResponseError, match="empty"):
            service.answer(retrieval.query, retrieval)

    @pytest.mark.parametrize("marker", ["[99]", "[0]", "[T1]"])
    def test_a_citation_to_evidence_never_sent_is_withheld(
        self, llm_settings, retrieval, marker
    ):
        """14.B: a citation to nothing is the mechanical sign of hallucination."""
        invented = LLMResponse(
            text=f"The limit is 500.00 {marker}.", provider_id="mock", model_id="m"
        )
        service = LLMService(MockLLMProvider(responses=[invented]), llm_settings)
        with pytest.raises(LLMInvalidCitationError, match=re.escape(marker)) as info:
            service.answer(retrieval.query, retrieval)
        assert isinstance(info.value, LLMResponseError), "still a 502 at the API"
        assert info.value.markers == (marker,)
        assert info.value.route is None, "the agent sets the route, not the service"

    def test_citations_to_supplied_passages_are_accepted(self, llm_settings, retrieval):
        cited = LLMResponse(
            text="The limit is 500.00 [1].", provider_id="mock", model_id="m"
        )
        service = LLMService(MockLLMProvider(responses=[cited]), llm_settings)
        assert service.answer(retrieval.query, retrieval).text.endswith("[1].")

    def test_a_withheld_citation_is_counted_as_a_failed_call(
        self, llm_settings, retrieval
    ):
        metrics = get_metrics()
        before = metrics.snapshot()["counters"].get(LLM_INVALID_CITATIONS_TOTAL, 0)
        invented = LLMResponse(text="See [42].", provider_id="mock", model_id="m")
        service = LLMService(MockLLMProvider(responses=[invented]), llm_settings)
        with pytest.raises(LLMResponseError):
            service.answer(retrieval.query, retrieval)
        after = metrics.snapshot()["counters"][LLM_INVALID_CITATIONS_TOTAL]
        assert after == before + 1

    def test_a_failure_produces_no_answer_object(self, llm_settings, retrieval):
        service = LLMService(
            MockLLMProvider(handler=raising(LLMTimeoutError("boom"))), llm_settings
        )
        with pytest.raises(LLMTimeoutError):
            result = service.answer(retrieval.query, retrieval)
            assert result is None  # unreachable: the point is that it raises


# --- End to end, offline -------------------------------------------------


class TestEndToEnd:
    @pytest.mark.parametrize(
        "question",
        [
            "Why would an ATM transaction fail after card authentication?",
            "What component handles card authentication?",
            "Which API is used for payment authorisation?",
            "How would I troubleshoot a failed cash withdrawal?",
            "What configuration controls transaction limits?",
        ],
    )
    def test_the_seed_questions_produce_an_answer_or_an_honest_refusal(
        self, llm_service, retriever, question
    ):
        answer = llm_service.answer(question, retriever.retrieve(question))
        assert answer.text
        if answer.refused:
            assert answer.text == INSUFFICIENT_EVIDENCE
            assert not answer.sources
        else:
            assert answer.sources
            assert answer.chunks_used > 0

    def test_an_answer_is_always_one_of_grounded_or_refused(
        self, llm_service, retriever
    ):
        for question in ("card authentication", "bake sourdough bread"):
            answer = llm_service.answer(question, retriever.retrieve(question))
            assert answer.is_grounded != answer.refused

    def test_the_service_is_reusable_across_questions(
        self, llm_service, mock_provider, retriever
    ):
        for question in ("card authentication", "payment authorisation", "atm states"):
            llm_service.answer(question, retriever.retrieve(question))
        assert mock_provider.call_count >= 1

    def test_a_default_constructed_service_uses_the_cached_settings(
        self, mock_provider, retrieval
    ):
        answer = LLMService(mock_provider).answer(retrieval.query, retrieval)
        assert answer.text

    def test_no_answer_text_leaks_into_the_sources(self, llm_service, retrieval):
        answer = llm_service.answer(retrieval.query, retrieval)
        for source in answer.sources:
            assert answer.text not in source


# --- Guarding the Stage 4 / Stage 5 boundary ------------------------------


class TestScopeBoundary:
    def test_the_service_does_not_retrieve(self, llm_service):
        """Retrieval belongs to the caller. The agent that decides is Stage 5."""
        assert not hasattr(llm_service, "retrieve")
        assert not hasattr(llm_service, "retriever")

    def test_an_empty_result_object_is_a_valid_input(self, llm_service):
        empty = RetrievalResult(
            query="q", chunks=(), candidates_considered=0, min_score=0.25
        )
        answer = llm_service.answer("a question", empty)
        assert answer.refused

    def test_settings_default_to_the_singleton(self, mock_provider):
        service = LLMService(mock_provider)
        assert isinstance(service.provider, MockLLMProvider)

    def test_the_provider_is_exposed_for_inspection(self, llm_service, mock_provider):
        assert llm_service.provider is mock_provider

    def test_settings_are_not_the_test_settings_by_accident(
        self, llm_settings: Settings
    ):
        assert llm_settings.environment == "test"
        assert llm_settings.llm_provider == "mock"
