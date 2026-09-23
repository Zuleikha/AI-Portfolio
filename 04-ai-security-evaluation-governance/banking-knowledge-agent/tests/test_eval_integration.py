"""The Stage 11 evaluation gates with the real embedding model (11.C).

Free and offline after the first model download: the embedder is local and the
provider is the in-process mock. Floors live in ``data/eval/questions.yaml`` and
are set a little under the scores measured when Stage 11 was built, so a real
regression fails here and a harmless wobble does not.
"""

from __future__ import annotations

import pytest

from app.agent.agent import KnowledgeAgent
from app.core.config import Settings
from app.eval.dataset import EvalDataset, load_dataset
from app.eval.runner import INVARIANT_CHECKS, EvalReport, run_evaluation
from app.llm.mock import MockLLMProvider
from app.llm.service import LLMService
from app.mcp.factory import build_tool_registry
from app.rag.pipeline import build_index

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def dataset() -> EvalDataset:
    return load_dataset(Settings().eval_dataset_path)


@pytest.fixture(scope="module")
def report(dataset: EvalDataset) -> EvalReport:
    settings = Settings(environment="test", log_to_file=False)
    agent = KnowledgeAgent(
        build_index(settings, persist=False),
        LLMService(MockLLMProvider(), settings),
        settings,
        tools=build_tool_registry(),
    )
    return run_evaluation(dataset, agent, k=settings.retrieval_top_k)


def test_recall_at_k_meets_its_floor(report, dataset):
    assert report.scores.recall_at_k is not None
    assert report.scores.recall_at_k >= dataset.thresholds.recall_at_k


def test_mrr_meets_its_floor(report, dataset):
    assert report.scores.mrr is not None
    assert report.scores.mrr >= dataset.thresholds.mrr


def test_path_accuracy_meets_its_floor(report, dataset):
    assert report.scores.path_accuracy >= dataset.thresholds.path_accuracy


def test_every_invariant_holds(report):
    broken = [
        (case.case_id, check.name, check.detail)
        for case in report.cases
        for check in case.checks
        if check.name in INVARIANT_CHECKS and not check.passed
    ]
    assert broken == []


def test_no_floor_fails(report):
    assert report.failed_floors() == ()


def test_the_floors_are_not_left_at_zero(dataset):
    # Zero floors gate nothing. They were set from a measured run.
    assert dataset.thresholds.recall_at_k > 0.0
    assert dataset.thresholds.mrr > 0.0
    assert dataset.thresholds.path_accuracy > 0.0
