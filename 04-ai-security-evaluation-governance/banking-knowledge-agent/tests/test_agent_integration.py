"""The agent end to end against the real embedding model and the real corpus.

Still free and still offline after the first model download: the embedder runs
locally and the provider is ``MockLLMProvider``, so no request leaves the machine
and nothing is billed.

What these tests can and cannot prove is worth being precise about. They prove
the agent *routes* correctly with real semantics -- that each seed question
reaches its own document, that the off-topic controls are refused rather than
answered from something adjacent, and that the passages the model would see are
the right ones. They cannot prove answer *quality*, because the mock does not
reason. That is Stage 11's evaluation set, and pretending otherwise here would
be the most flattering possible test of the least interesting property.
"""

from __future__ import annotations

import pytest

from app.agent.agent import KnowledgeAgent
from app.core.config import Settings
from app.llm.mock import MockLLMProvider
from app.llm.prompts import INSUFFICIENT_EVIDENCE
from app.llm.service import LLMService
from app.mcp.factory import build_tool_registry
from app.rag.pipeline import build_index

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def real_settings_module() -> Settings:
    """Settings for the real model. Module-scoped alongside the index."""
    return Settings(environment="test", log_to_file=False)


@pytest.fixture(scope="module")
def real_retriever(real_settings_module: Settings):
    """A retriever over the real corpus and the real model, built once.

    Module-scoped for the same reason as ``test_rag_integration.py``: loading
    the transformer and embedding 115 chunks costs seconds, and every test here
    reads from the index without mutating it.
    """
    return build_index(real_settings_module, persist=False)


@pytest.fixture
def real_agent(real_retriever, real_settings_module: Settings) -> KnowledgeAgent:
    """An agent over the real index, with a fresh mock provider per test.

    The index is shared; the provider is not, so ``call_count`` assertions
    measure one test's calls rather than the module's running total.

    Free and offline after the first model download: the embedder runs locally
    and the provider is in-process, so no request leaves the machine.
    """
    return KnowledgeAgent(
        real_retriever,
        LLMService(MockLLMProvider(), real_settings_module),
        real_settings_module,
    )


SEED_EXPECTATIONS = (
    (
        "Why would an ATM transaction fail after card authentication?",
        "atm-transaction-lifecycle",
    ),
    ("What component handles card authentication?", "card-authentication"),
    ("Which API is used for payment authorisation?", "payment-authorisation-api"),
    (
        "How would I troubleshoot a failed cash withdrawal?",
        "atm-cash-withdrawal-troubleshooting",
    ),
    (
        "What configuration controls transaction limits?",
        "transaction-limits-configuration",
    ),
)
"""The five seed questions and the document each one is about.

The document ids are the ones Stage 3 measured as rank 1 for these questions
(handover, *Measured results worth keeping*). Asserting them here means a
chunking, embedding or threshold change that quietly breaks the worked examples
fails a test instead of degrading a demo.
"""

OFF_TOPIC = (
    "What is the capital of France?",
    "How do I bake sourdough bread?",
    "What is the offside rule in football?",
)


class TestSeedQuestions:
    @pytest.mark.parametrize(("question", "document_id"), SEED_EXPECTATIONS)
    def test_each_seed_question_is_answered_from_its_own_document(
        self, real_agent: KnowledgeAgent, question, document_id
    ):
        answer = real_agent.ask(question)
        assert answer.is_grounded, f"{question!r} was not answered"
        assert answer.retrieval.documents[0] == document_id

    @pytest.mark.parametrize(("question", "document_id"), SEED_EXPECTATIONS)
    def test_each_seed_question_cites_that_document(
        self, real_agent: KnowledgeAgent, question, document_id
    ):
        answer = real_agent.ask(question)
        assert any(
            document_id in source for source in answer.sources
        ), f"{question!r} cited {answer.sources}, expected {document_id}"

    @pytest.mark.parametrize(("question", "_document_id"), SEED_EXPECTATIONS)
    def test_each_seed_question_clears_the_floor_comfortably(
        self, real_agent: KnowledgeAgent, question, _document_id
    ):
        answer = real_agent.ask(question)
        assert answer.retrieval.top_score is not None
        assert answer.retrieval.top_score > 0.5

    def test_every_seed_question_retrieves_and_generates(
        self, real_agent: KnowledgeAgent
    ):
        answers = real_agent.ask_many([question for question, _ in SEED_EXPECTATIONS])
        assert all(answer.decision.retrieve for answer in answers)
        assert all(answer.llm_called for answer in answers)
        assert not any(answer.refused for answer in answers)


class TestRefusalWithRealSemantics:
    @pytest.mark.parametrize("question", OFF_TOPIC)
    def test_an_off_topic_question_is_refused_not_answered(
        self, real_agent: KnowledgeAgent, question
    ):
        answer = real_agent.ask(question)
        assert answer.refused is True
        assert answer.text == INSUFFICIENT_EVIDENCE
        assert answer.sources == ()

    @pytest.mark.parametrize("question", OFF_TOPIC)
    def test_an_off_topic_question_costs_no_model_call(
        self, real_agent: KnowledgeAgent, question
    ):
        provider = real_agent.llm_service.provider
        real_agent.ask(question)
        assert getattr(provider, "call_count", None) == 0

    @pytest.mark.parametrize("question", OFF_TOPIC)
    def test_an_off_topic_question_is_still_searched_before_being_refused(
        self, real_agent: KnowledgeAgent, question
    ):
        """The agent does not pre-judge relevance; the calibrated floor does."""
        answer = real_agent.ask(question)
        assert answer.decision.retrieve is True
        assert answer.retrieval.performed is True
        assert answer.retrieval.candidates_considered > 0


@pytest.fixture
def real_tool_agent(real_retriever, real_settings_module: Settings) -> KnowledgeAgent:
    """The real index plus all six tools, with a fresh mock provider per test."""
    return KnowledgeAgent(
        real_retriever,
        LLMService(MockLLMProvider(), real_settings_module),
        real_settings_module,
        tools=build_tool_registry(),
    )


DECISION_EXPECTATIONS = (
    ("What component handles card authentication?", "knowledge_required", 1),
    ("Why did the withdrawal reverse?", "additional_knowledge_required", 2),
    ("Is CoreBankingAdapter healthy?", "live_status_only", 0),
    ("What does error code LIM-4001 mean?", "knowledge_and_live_status_required", 1),
    ("What does SWX-7004 mean?", "knowledge_and_live_status_required", 2),
    (
        "What is the status of transaction TXN-19990101-000001?",
        "knowledge_and_live_status_required",
        2,
    ),
    ("What is the capital of France?", "insufficient_evidence", 1),
)
"""Each §15 path with the real model, as measured on 2026-09-14.

``docs/HANDOVER.md`` §7.C/§7.D records the scores behind these: the withdrawal
and SWX-7004 questions top out at 0.490 and 0.442 before refinement, below the
0.50 threshold, and rise to 0.640 and 0.603 after it. Pinning them means a
corpus, model or threshold change that silently moves a question onto a
different path fails here instead of changing the demo unnoticed.
"""


class TestDecisionPathsWithRealSemantics:
    @pytest.mark.parametrize(("question", "reason", "passes"), DECISION_EXPECTATIONS)
    def test_each_path_is_taken_with_the_real_model(
        self, real_tool_agent: KnowledgeAgent, question, reason, passes
    ):
        answer = real_tool_agent.ask(question)
        assert answer.decision.reason == reason
        assert answer.retrieval.passes == passes

    def test_a_refined_search_clears_the_confidence_threshold(
        self, real_tool_agent: KnowledgeAgent, real_settings_module: Settings
    ):
        """The second search is worth running: it lands above the bar it missed."""
        answer = real_tool_agent.ask("Why did the withdrawal reverse?")
        assert answer.retrieved_more
        assert answer.retrieval.top_score is not None
        assert answer.retrieval.top_score >= real_settings_module.agent_confident_score

    @pytest.mark.parametrize("question", OFF_TOPIC)
    def test_an_off_topic_question_is_never_refined_into_an_answer(
        self, real_tool_agent: KnowledgeAgent, question
    ):
        """Nothing cleared the floor, so there is nothing to refine with."""
        answer = real_tool_agent.ask(question)
        assert answer.refused
        assert answer.retrieval.passes == 1
        assert ("retrieve_more", "no_refinement_available") in [
            (step.step, step.outcome) for step in answer.decisions
        ]


class TestParaphrase:
    @pytest.mark.parametrize(
        ("question", "document_id"),
        [
            (
                "money left the account but no cash came out of the machine",
                "atm-cash-withdrawal-troubleshooting",
            ),
            (
                "how does the system check that a card is genuine",
                "card-authentication",
            ),
        ],
    )
    def test_a_paraphrase_still_finds_the_right_document(
        self, real_agent: KnowledgeAgent, question, document_id
    ):
        """The reason embeddings were chosen over lexical search (guide 20.3.1)."""
        answer = real_agent.ask(question)
        assert answer.is_grounded
        assert document_id in answer.retrieval.documents
