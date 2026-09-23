"""Stage 11 scoring: retrieval metrics and answer rule checks (11.B, 11.C).

Free and offline. Real agent answers come from the ``agent``/``tool_agent``
fixtures (hashing embedder, mock provider); a scripted mock stands in for a
model that invents a citation.
"""

from __future__ import annotations

import pytest

from app.agent.agent import KnowledgeAgent
from app.eval.dataset import EvalCase
from app.eval.metrics import (
    check_answer,
    hit_at_k,
    mean_reciprocal_rank,
    missing_mentions,
    path_matches,
    ranked_documents,
    recall_at_k,
    reciprocal_rank,
)
from app.llm.citations import invalid_citations
from app.llm.mock import MockLLMProvider


def _case(**fields) -> EvalCase:
    base = {"id": "test-001", "category": "knowledge", "question": "q"}
    return EvalCase.model_validate(base | fields)


def _by_name(checks):
    return {check.name: check for check in checks}


class TestRankMetrics:
    def test_first_place_scores_one(self):
        assert reciprocal_rank(("a", "b"), ("a",)) == 1.0

    def test_third_place_scores_a_third(self):
        assert reciprocal_rank(("x", "y", "a"), ("a",)) == pytest.approx(1 / 3)

    def test_the_best_ranked_expected_document_counts(self):
        assert reciprocal_rank(("x", "b", "a"), ("a", "b")) == 0.5

    def test_absent_scores_zero(self):
        assert reciprocal_rank(("x", "y"), ("a",)) == 0.0

    def test_hit_inside_k(self):
        assert hit_at_k(("x", "a"), ("a",), k=2)

    def test_miss_outside_k(self):
        assert not hit_at_k(("x", "y", "a"), ("a",), k=2)

    def test_recall_is_the_share_of_hits(self):
        assert recall_at_k([True, False, True, True]) == 0.75

    def test_mrr_is_the_mean(self):
        assert mean_reciprocal_rank([1.0, 0.5, 0.0]) == 0.5

    @pytest.mark.parametrize("metric", [recall_at_k, mean_reciprocal_rank])
    def test_an_empty_score_is_an_error_not_zero(self, metric):
        with pytest.raises(ValueError):
            metric([])

    def test_ranked_documents_are_distinct_in_rank_order(self, retrieval):
        ranked = ranked_documents(retrieval)
        expected = tuple(dict.fromkeys(s.chunk.document_id for s in retrieval.chunks))
        assert ranked == expected
        assert len(set(ranked)) == len(ranked)


class TestCitations:
    def test_citations_within_the_evidence_are_valid(self):
        assert invalid_citations("See [1] and [2].", chunks_used=2, tools_used=0) == ()

    def test_a_passage_number_beyond_the_evidence_is_invented(self):
        assert invalid_citations("See [3].", chunks_used=2, tools_used=0) == ("[3]",)

    def test_passage_zero_is_invalid(self):
        assert invalid_citations("See [0].", chunks_used=2, tools_used=0) == ("[0]",)

    def test_a_tool_citation_without_tools_is_invented(self):
        assert invalid_citations("Live: [T1].", chunks_used=1, tools_used=0) == (
            "[T1]",
        )

    def test_tool_citations_within_the_readings_are_valid(self):
        assert invalid_citations("[1][T1][T2]", chunks_used=1, tools_used=2) == ()


class TestPathMatching:
    def test_an_exact_route_matches(self):
        assert path_matches("live_status_only", "live_status_only")

    def test_a_refined_search_still_counts_as_a_knowledge_answer(self):
        assert path_matches("knowledge_required", "additional_knowledge_required")

    def test_a_refusal_is_not_a_knowledge_answer(self):
        assert not path_matches("knowledge_required", "insufficient_evidence")

    def test_a_knowledge_answer_is_not_a_hybrid_one(self):
        assert not path_matches(
            "knowledge_and_live_status_required", "knowledge_required"
        )


class TestMentions:
    def test_matching_ignores_case(self):
        assert missing_mentions("The HSM pool", ("hsm", "pool")) == ()

    def test_absent_facts_are_returned_in_order(self):
        assert missing_mentions("nothing here", ("b", "a")) == ("b", "a")


class TestCheckAnswer:
    def test_a_no_search_refusal_passes_every_check(self, tool_agent: KnowledgeAgent):
        answer = tool_agent.ask("???")
        checks = check_answer(
            _case(category="failure", expected_path="no_searchable_content"),
            answer,
            mention_text=answer.text,
        )
        assert all(check.passed for check in checks), checks
        assert {"path", "refusal", "citations"} <= set(_by_name(checks))

    def test_a_live_reading_passes_path_and_tools(self, tool_agent: KnowledgeAgent):
        answer = tool_agent.ask("Look up error code LIM-4001")
        case = _case(
            category="tool",
            expected_path="live_status_only",
            expected_tools=["look_up_error_code"],
        )
        checks = _by_name(check_answer(case, answer, mention_text=answer.text))
        assert checks["path"].passed
        assert checks["tools"].passed
        assert checks["citations"].passed

    def test_a_missing_tool_fails_and_is_named(self, tool_agent: KnowledgeAgent):
        answer = tool_agent.ask("Look up error code LIM-4001")
        case = _case(
            category="tool",
            expected_path="live_status_only",
            expected_tools=["check_transaction_status"],
        )
        tools = _by_name(check_answer(case, answer, mention_text=answer.text))["tools"]
        assert not tools.passed
        assert "check_transaction_status" in tools.detail

    def test_an_answer_that_should_have_been_refused_fails(
        self, tool_agent: KnowledgeAgent
    ):
        answer = tool_agent.ask("Look up error code LIM-4001")
        case = _case(category="off_topic", expected_path="insufficient_evidence")
        checks = _by_name(check_answer(case, answer, mention_text=answer.text))
        assert not checks["refusal"].passed
        assert not checks["path"].passed

    def test_an_invented_citation_is_caught(
        self, retriever, llm_settings, unguarded_llm_service
    ):
        # A "model" that cites passage 9 when at most 5 passages can be supplied.
        # The service would withhold it (14.B); this checks the second line.
        provider = MockLLMProvider(responses=["The answer is in [1] and [9]."])
        agent = KnowledgeAgent(retriever, unguarded_llm_service(provider), llm_settings)
        answer = agent.ask("card authentication")
        assert not answer.refused, "precondition: the hashing index matches this"
        case = _case(
            expected_path="knowledge_required", expected_docs=["card-authentication"]
        )
        citations = _by_name(check_answer(case, answer, mention_text=answer.text))[
            "citations"
        ]
        assert not citations.passed
        assert "[9]" in citations.detail

    def test_facts_are_checked_against_the_text_given(self, tool_agent: KnowledgeAgent):
        answer = tool_agent.ask("???")
        case = _case(
            expected_path="knowledge_required",
            expected_docs=["card-authentication"],
            must_mention=["AuthorizationService", "PIN"],
        )
        mentions = _by_name(
            check_answer(case, answer, mention_text="AuthorizationService only")
        )["mentions"]
        assert not mentions.passed
        assert "PIN" in mentions.detail

    def test_documents_are_checked_against_what_was_retrieved(
        self, tool_agent: KnowledgeAgent
    ):
        answer = tool_agent.ask("???")  # nothing searched, so nothing retrieved
        case = _case(
            expected_path="knowledge_required", expected_docs=["card-authentication"]
        )
        documents = _by_name(check_answer(case, answer, mention_text=""))["documents"]
        assert not documents.passed
