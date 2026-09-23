"""Stage 11 runner, report and CLI (11.B, 11.D).

Free and offline: hashing embedder, mock provider. These tests assert that the
evaluation *runs and scores correctly*; retrieval quality with the real model
is gated in ``test_eval_integration.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from app.agent.agent import KnowledgeAgent
from app.core.config import Settings
from app.eval.__main__ import main
from app.eval.dataset import EvalCase, EvalDataset, Thresholds, load_dataset
from app.eval.report import render_report
from app.eval.runner import INVARIANT_CHECKS, run_evaluation
from app.llm.base import LLMResponseError
from app.llm.mock import MockLLMProvider
from app.llm.models import LLMResponse
from app.llm.service import LLMService

SMALL = EvalDataset(
    version="test",
    thresholds=Thresholds(recall_at_k=0.0, mrr=0.0, path_accuracy=0.0),
    cases=(
        EvalCase(
            id="know-001",
            category="knowledge",
            question="card authentication",
            expected_path="knowledge_required",
            expected_docs=("card-authentication",),
        ),
        EvalCase(
            id="tool-001",
            category="tool",
            question="Look up error code LIM-4001",
            expected_path="live_status_only",
            expected_tools=("look_up_error_code",),
        ),
        EvalCase(
            id="fail-001",
            category="failure",
            question="???",
            expected_path="no_searchable_content",
        ),
    ),
)


class TestRunEvaluation:
    def test_every_case_is_reported(self, tool_agent):
        report = run_evaluation(SMALL, tool_agent, k=5)
        assert [case.case_id for case in report.cases] == [
            "know-001",
            "tool-001",
            "fail-001",
        ]
        assert report.mode == "mock"
        assert report.k == 5

    def test_retrieval_is_scored_only_where_documents_are_expected(self, tool_agent):
        report = run_evaluation(SMALL, tool_agent, k=5)
        assert report.scores.retrieval_cases == 1
        by_id = {case.case_id: case for case in report.cases}
        assert by_id["know-001"].reciprocal_rank is not None
        assert by_id["tool-001"].reciprocal_rank is None
        assert by_id["tool-001"].hit is None

    def test_path_accuracy_is_the_share_of_correct_routes(self, tool_agent):
        report = run_evaluation(SMALL, tool_agent, k=5)
        correct = sum(case.path_correct for case in report.cases)
        assert report.scores.path_accuracy == correct / len(report.cases)

    def test_check_tallies_add_up(self, tool_agent):
        report = run_evaluation(SMALL, tool_agent, k=5)
        for name, tally in report.scores.checks.items():
            ran = [c for case in report.cases for c in case.checks if c.name == name]
            assert tally.total == len(ran)
            assert tally.passed == sum(c.passed for c in ran)

    def test_latency_is_recorded(self, tool_agent):
        report = run_evaluation(SMALL, tool_agent, k=5)
        assert all(case.latency_ms >= 0.0 for case in report.cases)

    def test_the_shipped_dataset_holds_every_invariant(self, tool_agent):
        # Routing, refusal and citation rules do not depend on embedding quality,
        # so they must hold even with the non-semantic hashing embedder.
        report = run_evaluation(
            load_dataset(Settings().eval_dataset_path), tool_agent, k=5
        )
        broken = [
            (case.case_id, check.name, check.detail)
            for case in report.cases
            for check in case.checks
            if check.name in INVARIANT_CHECKS and not check.passed
        ]
        assert broken == []

    def test_live_readings_route_correctly_without_semantics(self, tool_agent):
        dataset = load_dataset(Settings().eval_dataset_path)
        report = run_evaluation(dataset, tool_agent, k=5)
        tool_cases = [case for case in report.cases if case.category == "tool"]
        assert tool_cases
        assert all(case.path_correct for case in tool_cases), [
            (case.case_id, case.actual_path) for case in tool_cases
        ]


class TestFloors:
    def test_scores_below_the_floors_are_named(self, tool_agent):
        strict = SMALL.model_copy(
            update={
                "thresholds": Thresholds(recall_at_k=1.0, mrr=1.0, path_accuracy=1.0)
            }
        )
        failing = strict.model_copy(
            update={
                "cases": (
                    *SMALL.cases,
                    SMALL.cases[1].model_copy(
                        update={
                            "id": "tool-002",
                            "expected_path": "insufficient_evidence",
                            "expected_tools": (),
                        }
                    ),
                )
            }
        )
        report = run_evaluation(failing, tool_agent, k=5)
        failed = report.failed_floors()
        assert "path_accuracy" in failed

    def test_an_invented_citation_fails_even_with_zero_floors(
        self, retriever, llm_settings, unguarded_llm_service
    ):
        # The service would withhold it (14.B); this checks the second line.
        provider = MockLLMProvider(responses=["See [9]."])
        agent = KnowledgeAgent(retriever, unguarded_llm_service(provider), llm_settings)
        one = SMALL.model_copy(update={"cases": SMALL.cases[:1]})
        report = run_evaluation(one, agent, k=5)
        assert "citations" in report.failed_floors()

    def test_a_withheld_answer_is_scored_as_a_citation_failure(
        self, retriever, llm_settings
    ):
        # 14.E: through the real service the answer is withheld (14.B); the
        # run carries on and that question fails its citation check.
        provider = MockLLMProvider(responses=["See [9].", "See [1]."])
        agent = KnowledgeAgent(
            retriever, LLMService(provider, llm_settings), llm_settings
        )
        two = SMALL.model_copy(
            update={
                "cases": (
                    SMALL.cases[0],
                    SMALL.cases[0].model_copy(update={"id": "know-002"}),
                )
            }
        )
        report = run_evaluation(two, agent, k=5)

        withheld, answered = report.cases
        assert "citations" in report.failed_floors()
        assert not withheld.passed
        citations = next(c for c in withheld.checks if c.name == "citations")
        assert not citations.passed
        assert "[9]" in citations.detail
        assert "withheld" in citations.detail
        assert answered.passed, "the run must continue past the withheld answer"

    def test_a_withheld_answer_keeps_its_real_route(self, retriever, llm_settings):
        provider = MockLLMProvider(responses=["See [1].", "See [9]."])
        agent = KnowledgeAgent(
            retriever, LLMService(provider, llm_settings), llm_settings
        )
        one = SMALL.model_copy(update={"cases": SMALL.cases[:1]})
        (answered,) = run_evaluation(one, agent, k=5).cases
        (case,) = run_evaluation(one, agent, k=5).cases
        assert case.actual_path == answered.actual_path
        assert case.path_correct
        assert case.hit is not None, "retrieval is still scored"

    def test_any_other_llm_failure_still_stops_the_run(self, retriever, llm_settings):
        # Only an invented citation is a score; a broken model is not.
        provider = MockLLMProvider(
            responses=[
                LLMResponse(
                    text="cut",
                    provider_id="mock",
                    model_id="m",
                    stop_reason="max_tokens",
                )
            ]
        )
        agent = KnowledgeAgent(
            retriever, LLMService(provider, llm_settings), llm_settings
        )
        one = SMALL.model_copy(update={"cases": SMALL.cases[:1]})
        with pytest.raises(LLMResponseError, match="truncated"):
            run_evaluation(one, agent, k=5)

    def test_a_wrong_refusal_is_a_score_not_an_invariant(self, tool_agent):
        # Whether an off-topic question is refused depends on retrieval scores,
        # so it lowers path accuracy instead of failing as an invariant.
        wrong_case = SMALL.cases[1].model_copy(
            update={"expected_path": "insufficient_evidence", "expected_tools": ()}
        )
        report = run_evaluation(
            SMALL.model_copy(update={"cases": (wrong_case,)}), tool_agent, k=5
        )
        assert report.scores.checks["refusal"].passed == 0
        assert report.scores.path_accuracy == 0.0
        assert "refusal" not in report.failed_floors()

    def test_a_passing_run_has_no_failed_floors(self, tool_agent):
        report = run_evaluation(
            SMALL.model_copy(update={"cases": SMALL.cases[1:]}), tool_agent, k=5
        )
        assert report.failed_floors() == ()


class TestRenderReport:
    def test_the_scorecard_shows_scores_floors_and_misses(self, tool_agent):
        text = render_report(run_evaluation(SMALL, tool_agent, k=5))
        for expected in ("recall@5", "MRR", "path accuracy", "floor", "know-001"):
            assert expected in text

    def test_the_scorecard_names_the_mode(self, tool_agent):
        assert "mock" in render_report(run_evaluation(SMALL, tool_agent, k=5))


def _small_file(tmp_path: Path) -> Path:
    path = tmp_path / "small.yaml"
    path.write_text(
        'version: "test"\n'
        "thresholds: {recall_at_k: 0.0, mrr: 0.0, path_accuracy: 0.0}\n"
        "cases:\n"
        "  - {id: tool-001, category: tool, question: Look up error code LIM-4001,\n"
        "     expected_path: live_status_only, expected_tools: [look_up_error_code]}\n"
        "  - {id: fail-001, category: failure, question: '???',\n"
        "     expected_path: no_searchable_content}\n",
        encoding="utf-8",
    )
    return path


class TestCli:
    def test_free_mode_prints_a_scorecard(self, tmp_path, rag_settings, capsys):
        code = main(["--dataset", str(_small_file(tmp_path))], settings=rag_settings)
        out = capsys.readouterr().out
        assert code == 0
        assert "path accuracy" in out
        assert "tool-001" in out or "2/2" in out

    def test_free_mode_never_builds_a_paid_provider(
        self, tmp_path, rag_settings, capsys
    ):
        # A paid provider with no key cannot be constructed. Free mode must not
        # try: it always uses the mock, whatever BKA_LLM_PROVIDER says.
        paid = rag_settings.model_copy(update={"llm_provider": "anthropic"})
        code = main(["--dataset", str(_small_file(tmp_path))], settings=paid)
        out = capsys.readouterr().out
        assert code == 0
        assert "--paid" in out

    def test_paid_is_refused_while_the_provider_is_the_mock(self, rag_settings, capsys):
        code = main(["--paid"], settings=rag_settings)
        assert code == 2
        assert "REFUSED" in capsys.readouterr().out

    def test_paid_is_refused_without_a_key(self, rag_settings, capsys):
        paid = rag_settings.model_copy(update={"llm_provider": "anthropic"})
        code = main(["--paid"], settings=paid)
        out = capsys.readouterr().out
        assert code == 2
        assert "BKA_LLM_API_KEY" in out

    def test_paid_prints_the_question_count_before_anything_runs(
        self, tmp_path, rag_settings, capsys, monkeypatch
    ):
        paid = rag_settings.model_copy(
            update={
                "llm_provider": "anthropic",
                "llm_api_key": SecretStr("not-a-real-key"),
            }
        )

        def refuse(*_args, **_kwargs):
            raise RuntimeError("stop before any provider is built")

        monkeypatch.setattr("app.eval.__main__.get_llm_service", refuse)
        with pytest.raises(RuntimeError, match="stop before"):
            main(["--paid", "--dataset", str(_small_file(tmp_path))], settings=paid)
        out = capsys.readouterr().out
        assert "PAID" in out
        assert "2 question" in out

    def test_a_bad_dataset_fails_loudly(self, tmp_path, rag_settings):
        from app.eval.dataset import DatasetError

        with pytest.raises(DatasetError):
            main(["--dataset", str(tmp_path / "absent.yaml")], settings=rag_settings)
