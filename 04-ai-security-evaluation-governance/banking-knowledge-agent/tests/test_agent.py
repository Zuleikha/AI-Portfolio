"""The knowledge agent: routing, wiring, refusals, provenance, error handling.

Offline and deterministic throughout. The retriever uses the hashing embedder
and the provider is ``MockLLMProvider``, so nothing here embeds with a real
model, reaches a network, or costs anything. What is asserted is *agent*
behaviour -- which collaborator was called, in what order, with what, and what
the caller can tell about the result afterwards. Retrieval quality with the real
model is ``test_agent_integration.py``.
"""

from __future__ import annotations

import pytest

from app.agent.agent import KnowledgeAgent
from app.agent.factory import get_agent
from app.agent.models import AgentAnswer, RetrievalDecision, RetrievalSummary
from app.agent.policy import decide_retrieval
from app.core.config import Settings
from app.llm.base import (
    LLMConfigurationError,
    LLMInvalidCitationError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from app.llm.mock import MOCK_PROVIDER_ID, MockLLMProvider
from app.llm.models import LLMResponse
from app.llm.prompts import INSUFFICIENT_EVIDENCE
from app.llm.service import LLMService
from app.rag.models import RetrievalResult
from app.rag.retriever import Retriever

SEED_QUESTIONS = (
    "Why would an ATM transaction fail after card authentication?",
    "What component handles card authentication?",
    "Which API is used for payment authorisation?",
    "How would I troubleshoot a failed cash withdrawal?",
    "What configuration controls transaction limits?",
)

NOTHING_TO_SEARCH = ("!!! ???", "---", "***", "?", "   .   ", "&&&")


class RecordingRetriever:
    """A retriever stand-in that records every call and returns a fixed result."""

    def __init__(self, result: RetrievalResult) -> None:
        self._result = result
        self.queries: list[str] = []

    def retrieve(self, query: str, **_kwargs: object) -> RetrievalResult:
        self.queries.append(query)
        return self._result

    @property
    def call_count(self) -> int:
        return len(self.queries)


# --- The routing policy ---------------------------------------------------


class TestRetrievalPolicy:
    @pytest.mark.parametrize("question", SEED_QUESTIONS)
    def test_a_real_question_requires_retrieval(self, question):
        decision = decide_retrieval(question)
        assert decision.retrieve is True
        assert decision.reason == "knowledge_required"

    @pytest.mark.parametrize("question", NOTHING_TO_SEARCH)
    def test_a_question_with_no_searchable_content_skips_retrieval(self, question):
        decision = decide_retrieval(question)
        assert decision.retrieve is False
        assert decision.reason == "no_searchable_content"

    def test_a_single_alphanumeric_character_is_enough_to_search(self):
        """The gate is 'nothing to search for', not 'too short to be serious'.

        Judging a question's substance is the score floor's job, and it has
        measured evidence behind it. This rule only skips input that could not
        match anything by construction.
        """
        assert decide_retrieval("PIN?").retrieve is True
        assert decide_retrieval("4").retrieve is True

    def test_a_blank_question_is_an_error_not_a_decision(self):
        with pytest.raises(ValueError, match="empty question"):
            decide_retrieval("   ")

    def test_the_policy_does_not_route_on_banking_keywords(self):
        """A question with no domain vocabulary still retrieves.

        Guards the decision recorded in guide 20.5: a keyword classifier would
        skip retrieval here, and retrieval would have succeeded.
        """
        assert decide_retrieval("Why did the withdrawal reverse?").retrieve is True
        assert decide_retrieval("What caused that failure?").retrieve is True

    def test_the_explanation_is_human_readable_and_carries_no_document_text(self):
        for question in ("What component handles card authentication?", "!!!"):
            explanation = decide_retrieval(question).explanation
            assert explanation.endswith(".")
            assert len(explanation.split()) >= 5

    def test_the_decision_is_frozen(self):
        decision = decide_retrieval("What component handles card authentication?")
        with pytest.raises(ValueError, match="frozen"):
            decision.retrieve = False  # type: ignore[misc]

    def test_the_decision_is_deterministic(self):
        first = decide_retrieval("Which API is used for payment authorisation?")
        second = decide_retrieval("Which API is used for payment authorisation?")
        assert first == second


# --- The happy path: question in, grounded answer out ---------------------


class TestGroundedAnswers:
    @pytest.mark.parametrize("question", SEED_QUESTIONS)
    def test_each_seed_question_produces_a_grounded_answer(
        self, agent: KnowledgeAgent, question
    ):
        answer = agent.ask(question)
        assert isinstance(answer, AgentAnswer)
        assert answer.is_grounded
        assert answer.refused is False
        assert answer.text.strip()

    @pytest.mark.parametrize("question", SEED_QUESTIONS)
    def test_each_seed_question_cites_at_least_one_source(
        self, agent: KnowledgeAgent, question
    ):
        answer = agent.ask(question)
        assert answer.sources
        assert all(source.strip() for source in answer.sources)

    def test_the_question_is_echoed_back_unchanged(self, agent: KnowledgeAgent):
        question = "  What component handles card authentication?  "
        assert agent.ask(question).question == question

    def test_the_answer_records_the_prompt_version(self, agent: KnowledgeAgent):
        answer = agent.ask(SEED_QUESTIONS[1])
        assert answer.prompt_version == answer.answer.prompt_version
        assert answer.prompt_version

    def test_ask_many_answers_every_question_in_order(self, agent: KnowledgeAgent):
        answers = agent.ask_many(list(SEED_QUESTIONS))
        assert len(answers) == len(SEED_QUESTIONS)
        assert [answer.question for answer in answers] == list(SEED_QUESTIONS)

    def test_a_blank_question_is_rejected_before_anything_is_called(
        self, retrieval: RetrievalResult, llm_settings: Settings
    ):
        provider = MockLLMProvider()
        retriever = RecordingRetriever(retrieval)
        agent = KnowledgeAgent(
            retriever,  # type: ignore[arg-type]
            LLMService(provider, llm_settings),
            llm_settings,
        )
        with pytest.raises(ValueError, match="empty question"):
            agent.ask("   ")
        assert retriever.call_count == 0
        assert provider.call_count == 0


# --- The wiring: retrieval feeds generation, exactly once -----------------


class TestWiring:
    def test_the_question_is_passed_to_the_retriever_verbatim(
        self, retrieval: RetrievalResult, llm_settings: Settings
    ):
        # A confident first pass: Stage 7 repeats a *weak* search, and the hashing
        # embedder scores below the designed 0.50 threshold (HANDOVER 7.D). The
        # second pass is tested in test_agent_decisions.py.
        settings = llm_settings.model_copy(update={"agent_confident_score": 0.0})
        retriever = RecordingRetriever(retrieval)
        agent = KnowledgeAgent(
            retriever,  # type: ignore[arg-type]
            LLMService(MockLLMProvider(), settings),
            settings,
        )
        agent.ask("Which API is used for payment authorisation?")
        assert retriever.queries == ["Which API is used for payment authorisation?"]

    def test_one_question_triggers_exactly_one_retrieval_and_one_generation(
        self, retrieval: RetrievalResult, llm_settings: Settings
    ):
        """A confident first pass is one retrieval (see HANDOVER 7.D)."""
        settings = llm_settings.model_copy(update={"agent_confident_score": 0.0})
        provider = MockLLMProvider()
        retriever = RecordingRetriever(retrieval)
        agent = KnowledgeAgent(
            retriever,  # type: ignore[arg-type]
            LLMService(provider, settings),
            settings,
        )
        agent.ask("What component handles card authentication?")
        assert retriever.call_count == 1
        assert provider.call_count == 1

    def test_the_retrieved_passages_reach_the_prompt(
        self, agent: KnowledgeAgent, mock_provider: MockLLMProvider
    ):
        answer = agent.ask("What component handles card authentication?")
        request = mock_provider.last_request
        assert request is not None
        assert request.user_text.count("<passage id=") == answer.chunks_used

    def test_the_question_reaches_the_prompt(
        self, agent: KnowledgeAgent, mock_provider: MockLLMProvider
    ):
        question = "How would I troubleshoot a failed cash withdrawal?"
        agent.ask(question)
        assert mock_provider.last_request is not None
        assert question in mock_provider.last_request.user_text

    def test_the_agent_does_not_send_the_whole_knowledge_base(
        self, agent: KnowledgeAgent, mock_provider: MockLLMProvider, llm_settings
    ):
        agent.ask("What configuration controls transaction limits?")
        request = mock_provider.last_request
        assert request is not None
        passages = request.user_text.count("<passage id=")
        assert 0 < passages <= llm_settings.llm_context_max_chunks

    def test_the_agent_adds_no_prompt_of_its_own(
        self, agent: KnowledgeAgent, mock_provider: MockLLMProvider
    ):
        """Prompt construction stays in one module. The agent routes, it does
        not write instructions."""
        from app.llm.prompts import SYSTEM_INSTRUCTIONS

        agent.ask("What component handles card authentication?")
        assert mock_provider.last_request is not None
        assert mock_provider.last_request.system == SYSTEM_INSTRUCTIONS

    def test_the_agent_exposes_its_collaborators(
        self, agent: KnowledgeAgent, mock_provider: MockLLMProvider
    ):
        assert isinstance(agent.retriever, Retriever)
        assert agent.llm_service.provider is mock_provider


# --- Refusals: two routes to the same sentence ----------------------------


class TestRefusalAfterSearching:
    def test_a_question_the_corpus_cannot_answer_is_refused(
        self, empty_retrieval: RetrievalResult, llm_settings: Settings
    ):
        provider = MockLLMProvider()
        agent = KnowledgeAgent(
            RecordingRetriever(empty_retrieval),  # type: ignore[arg-type]
            LLMService(provider, llm_settings),
            llm_settings,
        )
        answer = agent.ask("What is the capital of France?")
        assert answer.refused is True
        assert answer.text == INSUFFICIENT_EVIDENCE

    def test_a_refusal_makes_no_model_call(
        self, empty_retrieval: RetrievalResult, llm_settings: Settings
    ):
        """Stage 4's guard, reached through the agent and still intact."""
        provider = MockLLMProvider()
        agent = KnowledgeAgent(
            RecordingRetriever(empty_retrieval),  # type: ignore[arg-type]
            LLMService(provider, llm_settings),
            llm_settings,
        )
        agent.ask("What is the capital of France?")
        assert provider.call_count == 0

    def test_a_refusal_cites_nothing(
        self, empty_retrieval: RetrievalResult, llm_settings: Settings
    ):
        agent = KnowledgeAgent(
            RecordingRetriever(empty_retrieval),  # type: ignore[arg-type]
            LLMService(MockLLMProvider(), llm_settings),
            llm_settings,
        )
        answer = agent.ask("What is the capital of France?")
        assert answer.sources == ()
        assert answer.chunks_used == 0
        assert answer.is_grounded is False

    def test_a_refusal_after_searching_still_reports_the_search(
        self, empty_retrieval: RetrievalResult, llm_settings: Settings
    ):
        """The diagnosis 'searched and found nothing' must stay distinguishable
        from 'did not search'."""
        agent = KnowledgeAgent(
            RecordingRetriever(empty_retrieval),  # type: ignore[arg-type]
            LLMService(MockLLMProvider(), llm_settings),
            llm_settings,
        )
        answer = agent.ask("What is the capital of France?")
        assert answer.decision.retrieve is True
        assert answer.retrieval.performed is True
        assert answer.retrieval.chunks_returned == 0


class TestRefusalWithoutSearching:
    @pytest.mark.parametrize("question", NOTHING_TO_SEARCH)
    def test_an_unsearchable_question_is_refused(self, agent: KnowledgeAgent, question):
        answer = agent.ask(question)
        assert answer.refused is True
        assert answer.text == INSUFFICIENT_EVIDENCE

    def test_no_retrieval_happens(
        self, retrieval: RetrievalResult, llm_settings: Settings
    ):
        retriever = RecordingRetriever(retrieval)
        agent = KnowledgeAgent(
            retriever,  # type: ignore[arg-type]
            LLMService(MockLLMProvider(), llm_settings),
            llm_settings,
        )
        agent.ask("!!! ???")
        assert retriever.call_count == 0

    def test_no_model_call_happens(
        self, agent: KnowledgeAgent, mock_provider: MockLLMProvider
    ):
        agent.ask("!!! ???")
        assert mock_provider.call_count == 0

    def test_the_record_says_no_search_was_run(self, agent: KnowledgeAgent):
        answer = agent.ask("!!! ???")
        assert answer.decision.retrieve is False
        assert answer.decision.reason == "no_searchable_content"
        assert answer.retrieval.performed is False
        assert answer.retrieval.candidates_considered == 0
        assert answer.retrieval.min_score is None

    def test_both_refusal_routes_produce_the_identical_sentence(
        self, empty_retrieval: RetrievalResult, llm_settings: Settings
    ):
        """One definition of 'insufficient', not two.

        The API, the web interface and Stage 11's evaluation harness all detect
        a refusal by matching this exact string.
        """
        searched = KnowledgeAgent(
            RecordingRetriever(empty_retrieval),  # type: ignore[arg-type]
            LLMService(MockLLMProvider(), llm_settings),
            llm_settings,
        ).ask("What is the capital of France?")
        unsearched = KnowledgeAgent(
            RecordingRetriever(empty_retrieval),  # type: ignore[arg-type]
            LLMService(MockLLMProvider(), llm_settings),
            llm_settings,
        ).ask("!!! ???")
        assert searched.text == unsearched.text == INSUFFICIENT_EVIDENCE


# --- The execution record -------------------------------------------------


class TestExecutionRecord:
    def test_a_grounded_answer_reports_what_retrieval_considered(
        self, agent: KnowledgeAgent
    ):
        answer = agent.ask("What component handles card authentication?")
        assert answer.retrieval.performed is True
        assert answer.retrieval.candidates_considered > 0
        assert answer.retrieval.chunks_returned > 0
        assert answer.retrieval.top_score is not None

    def test_chunks_used_never_exceeds_chunks_returned(self, agent: KnowledgeAgent):
        for question in SEED_QUESTIONS:
            answer = agent.ask(question)
            assert answer.chunks_used <= answer.retrieval.chunks_returned

    def test_documents_are_deduplicated(self, agent: KnowledgeAgent):
        answer = agent.ask("How would I troubleshoot a failed cash withdrawal?")
        documents = answer.retrieval.documents
        assert len(documents) == len(set(documents))

    def test_the_summary_carries_no_document_text(self, agent: KnowledgeAgent):
        """The summary is the part that is safe to log and to render.

        Passage text is document content; it stays in the answer's own
        provenance, not in the shape report.
        """
        answer = agent.ask("What component handles card authentication?")
        dumped = str(answer.retrieval.model_dump())
        for scored in agent.retriever.retrieve(answer.question).chunks:
            assert scored.chunk.content not in dumped

    def test_the_llm_layers_own_result_is_preserved_unmodified(
        self, agent: KnowledgeAgent
    ):
        answer = agent.ask("Which API is used for payment authorisation?")
        assert answer.text == answer.answer.text
        assert answer.sources == answer.answer.sources
        assert answer.answer.response is not None
        assert answer.answer.response.provider_id == MOCK_PROVIDER_ID

    def test_the_answer_is_frozen(self, agent: KnowledgeAgent):
        answer = agent.ask("What component handles card authentication?")
        with pytest.raises(ValueError, match="frozen"):
            answer.text = "rewritten"  # type: ignore[misc]

    def test_usage_is_reported_for_a_grounded_answer(self, agent: KnowledgeAgent):
        answer = agent.ask("What component handles card authentication?")
        assert answer.answer.response is not None
        assert answer.answer.response.usage.total_tokens > 0

    def test_a_summary_of_a_performed_search_round_trips(
        self, retrieval: RetrievalResult
    ):
        summary = RetrievalSummary.from_result(retrieval)
        assert summary.performed is True
        assert summary.chunks_returned == len(retrieval.chunks)
        assert summary.top_score == retrieval.top_score
        assert summary.min_score == retrieval.min_score

    def test_a_not_performed_summary_is_empty_rather_than_zeroed_by_accident(self):
        summary = RetrievalSummary.not_performed()
        assert summary.performed is False
        assert summary.min_score is None
        assert summary.documents == ()


# --- Failures are propagated, never disguised as refusals -----------------


class TestErrorHandling:
    @pytest.mark.parametrize(
        "error",
        [
            LLMTimeoutError("provider timed out"),
            LLMRateLimitError("rate limited", retry_after_seconds=1.0),
            LLMResponseError("malformed response"),
        ],
    )
    def test_a_provider_failure_propagates(
        self, retrieval: RetrievalResult, llm_settings: Settings, error
    ):
        """A broken model is not an undocumented answer.

        Turning a timeout into 'the knowledge base does not contain enough
        information' would send whoever is reading to fix the wrong thing.
        """

        def fail(_request):
            raise error

        agent = KnowledgeAgent(
            RecordingRetriever(retrieval),  # type: ignore[arg-type]
            LLMService(MockLLMProvider(handler=fail), llm_settings),
            llm_settings,
        )
        with pytest.raises(type(error)):
            agent.ask("What component handles card authentication?")

    def test_a_truncated_generation_is_not_returned_as_an_answer(
        self, retrieval: RetrievalResult, llm_settings: Settings
    ):
        truncated = LLMResponse(
            text="The daily withdrawal limit is configured by switch.limits.",
            provider_id="mock",
            model_id="mock-deterministic-v1",
            stop_reason="max_tokens",
        )
        agent = KnowledgeAgent(
            RecordingRetriever(retrieval),  # type: ignore[arg-type]
            LLMService(MockLLMProvider(responses=[truncated]), llm_settings),
            llm_settings,
        )
        with pytest.raises(LLMResponseError, match="truncated"):
            agent.ask("What configuration controls transaction limits?")

    def test_a_withheld_answer_carries_the_route_taken(
        self, retrieval: RetrievalResult, llm_settings: Settings
    ):
        # 14.E: the evaluation scores the withheld answer on the real route.
        question = "What configuration controls transaction limits?"
        agent = KnowledgeAgent(
            RecordingRetriever(retrieval),  # type: ignore[arg-type]
            LLMService(
                MockLLMProvider(responses=["See [1].", "See [9]."]), llm_settings
            ),
            llm_settings,
        )
        answered = agent.ask(question)
        with pytest.raises(LLMInvalidCitationError) as info:
            agent.ask(question)
        assert info.value.route == answered.decision.reason
        assert info.value.markers == ("[9]",)

    def test_a_retrieval_failure_propagates(self, llm_settings: Settings):
        class BrokenRetriever:
            def retrieve(self, query: str, **_kwargs: object) -> RetrievalResult:
                raise RuntimeError("index unavailable")

        agent = KnowledgeAgent(
            BrokenRetriever(),  # type: ignore[arg-type]
            LLMService(MockLLMProvider(), llm_settings),
            llm_settings,
        )
        with pytest.raises(RuntimeError, match="index unavailable"):
            agent.ask("What component handles card authentication?")


# --- Construction ---------------------------------------------------------


class TestAgentFactory:
    def test_an_unavailable_provider_fails_loudly(self, llm_settings: Settings):
        """No silent substitution, reached through the agent's own factory."""
        settings = llm_settings.model_copy(update={"llm_provider": "not-a-provider"})
        with pytest.raises(LLMConfigurationError):
            get_agent(settings)

    def test_the_agent_can_be_constructed_with_explicit_collaborators(
        self, retriever: Retriever, llm_settings: Settings
    ):
        agent = KnowledgeAgent(
            retriever, LLMService(MockLLMProvider(), llm_settings), llm_settings
        )
        assert agent.retriever is retriever

    def test_no_api_key_is_needed(self, retriever: Retriever, llm_settings: Settings):
        settings = llm_settings.model_copy(update={"llm_api_key": None})
        assert settings.llm_api_key is None
        agent = KnowledgeAgent(
            retriever, LLMService(MockLLMProvider(), settings), settings
        )
        assert agent.ask("What component handles card authentication?").text


# --- The stage boundary ---------------------------------------------------


class TestStageBoundary:
    """Guards that pin what the agent may and may not do at the current stage.

    Two of these were written in Stage 5 to fail the moment MCP arrived, and in
    Stage 6 they did exactly that. They are moved forward rather than deleted:
    their value is not the specific values they assert but that changing them is
    a deliberate act which forces a decision record to be written first (see
    ``docs/HANDOVER.md`` §6.F, and §7.C for the Stage 7 move).
    """

    def test_an_agent_built_without_a_registry_still_has_no_tools(
        self, agent: KnowledgeAgent
    ):
        """The Stage 5 composition must remain valid and tool-free.

        The ``agent`` fixture passes no registry, which is how every Stage 5
        test runs. Tools are opt-in: the attribute exists now, but it is
        ``None``, so nothing in this file silently acquired a live dependency.
        """
        assert agent.tools is None

    def test_the_agent_holds_no_conversation_state(self, agent: KnowledgeAgent):
        """Conversation context is Stage 8. Each question is independent."""
        first = agent.ask("What component handles card authentication?")
        second = agent.ask("What component handles card authentication?")
        assert first.text == second.text
        assert not hasattr(agent, "history")

    def test_the_decision_literal_has_exactly_the_stage_7_values(self):
        """Guards against a branch being added without a decision record."""
        from typing import get_args

        from app.agent.models import DecisionReason

        assert set(get_args(DecisionReason)) == {
            "knowledge_required",
            "additional_knowledge_required",
            "live_status_only",
            "knowledge_and_live_status_required",
            "insufficient_evidence",
            "no_searchable_content",
        }

    def test_the_tool_only_branch_exists_and_is_deliberate(self):
        """Stage 6 had no tool-only branch and said Stage 7 might add one.

        Stage 7 did, as a real choice with a guard on its costly direction: a
        tool-only plan whose reading finds nothing searches the documentation
        too (``docs/HANDOVER.md`` §7.C, rule 2).
        """
        from typing import get_args

        from app.agent.models import DecisionReason

        assert "live_status_only" in get_args(DecisionReason)

    def test_the_agent_package_imports_no_vendor_sdk(self):
        import ast
        from pathlib import Path

        forbidden = {"anthropic", "openai", "httpx", "requests", "socket", "urllib"}
        package = Path(__file__).resolve().parents[1] / "app" / "agent"
        for path in sorted(package.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots = {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    roots = {(node.module or "").split(".")[0]}
                else:
                    continue
                assert not roots & forbidden, f"{path.name} imports a vendor SDK"


# --- Models ---------------------------------------------------------------


class TestModels:
    def test_a_decision_requires_an_explanation(self):
        with pytest.raises(ValueError, match="explanation"):
            RetrievalDecision(
                retrieve=True, reason="knowledge_required", explanation=""
            )

    def test_an_unknown_reason_is_rejected(self):
        with pytest.raises(ValueError, match="reason"):
            RetrievalDecision(
                retrieve=True,
                reason="vibes",  # type: ignore[arg-type]
                explanation="Because it felt right.",
            )

    def test_an_answer_requires_non_empty_text(self, agent: KnowledgeAgent):
        answer = agent.ask("What component handles card authentication?")
        with pytest.raises(ValueError, match="text"):
            AgentAnswer.model_validate({**answer.model_dump(), "text": ""})

    def test_an_answer_always_carries_its_decision_and_its_retrieval_record(
        self, agent: KnowledgeAgent
    ):
        for question in (*SEED_QUESTIONS, "What is the capital of France?", "!!!"):
            answer = agent.ask(question)
            assert isinstance(answer.decision, RetrievalDecision)
            assert isinstance(answer.retrieval, RetrievalSummary)
