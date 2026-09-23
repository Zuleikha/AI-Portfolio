"""Run the agent over the dataset and score what it did.

For each question the runner:

1. scores **retrieval** directly on the agent's retriever (only when the case
   names expected documents), so recall and MRR measure ranking alone;
2. asks the **agent**, timing the call;
3. applies the **rule checks** in :mod:`app.eval.metrics`.

**Invariant checks gate at 100%** regardless of the floors: a refusal that
consulted a model, or a citation pointing at nothing, is never an acceptable
rate. The soft floors (``docs/HANDOVER.md`` 11.C) apply to recall@k, MRR and
path accuracy, which vary with the embedding model and the corpus. *Whether* an
off-topic question is refused is one of those varying scores — it depends on
where its best passage lands against the retrieval floor — so it counts through
path accuracy rather than as an invariant.

An exception from the agent propagates. An evaluation that silently skipped the
question that crashed would report a better score than the system deserves.
**One exception is a score, not a crash (14.E):** an answer the service withheld
for invented citations (:class:`~app.llm.base.LLMInvalidCitationError`) fails
that question's ``citations`` check — itself an invariant, so the run still
fails — and the remaining questions are still asked.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.agent.agent import KnowledgeAgent
from app.agent.models import DecisionReason
from app.core.logging import get_logger
from app.core.observability import elapsed_ms
from app.core.tracing import traced
from app.eval.dataset import Category, EvalCase, EvalDataset, Thresholds
from app.eval.metrics import (
    CheckName,
    CheckResult,
    check_answer,
    check_withheld_answer,
    hit_at_k,
    mean_reciprocal_rank,
    path_matches,
    ranked_documents,
    recall_at_k,
    reciprocal_rank,
)
from app.llm.base import LLMInvalidCitationError

logger = get_logger(__name__)

Mode = Literal["mock", "paid"]
"""``mock``: free, rule checks on the mock provider. ``paid``: a real model (11.B)."""

_ROUTE: TypeAdapter[DecisionReason] = TypeAdapter(DecisionReason)
"""Validates the route string a withheld-answer error carries (14.E)."""

INVARIANT_CHECKS: frozenset[CheckName] = frozenset({"refusal_honest", "citations"})
"""Checks that must pass for every question, whatever the floors say."""


class CaseResult(BaseModel):
    """What happened for one question."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    category: Category
    expected_path: DecisionReason
    actual_path: DecisionReason
    ranked_documents: tuple[str, ...] = ()
    hit: bool | None = Field(default=None, description="None: no documents expected.")
    reciprocal_rank: float | None = None
    checks: tuple[CheckResult, ...]
    latency_ms: float = Field(ge=0.0)

    @property
    def path_correct(self) -> bool:
        """Whether the route taken matched the route expected."""
        return path_matches(self.expected_path, self.actual_path)

    @property
    def passed(self) -> bool:
        """Whether every check ran for this question passed."""
        return all(check.passed for check in self.checks)


class CheckTally(BaseModel):
    """How many questions one check ran on, and how many passed."""

    model_config = ConfigDict(frozen=True)

    passed: int = Field(ge=0)
    total: int = Field(ge=0)


class Scores(BaseModel):
    """The aggregate scores for one run."""

    model_config = ConfigDict(frozen=True)

    recall_at_k: float | None = Field(
        description="None: no question expects documents."
    )
    mrr: float | None
    retrieval_cases: int = Field(ge=0)
    path_accuracy: float = Field(ge=0.0, le=1.0)
    checks: dict[str, CheckTally]


class EvalReport(BaseModel):
    """A complete evaluation run: every question, the scores and the floors."""

    model_config = ConfigDict(frozen=True)

    mode: Mode
    k: int = Field(ge=1)
    dataset_version: str
    thresholds: Thresholds
    cases: tuple[CaseResult, ...]
    scores: Scores

    @traced
    def failed_floors(self) -> tuple[str, ...]:
        """Names of every gate this run fails: a floor, or a broken invariant."""
        scores, floors = self.scores, self.thresholds
        failed: list[str] = []
        if scores.recall_at_k is not None and scores.recall_at_k < floors.recall_at_k:
            failed.append("recall_at_k")
        if scores.mrr is not None and scores.mrr < floors.mrr:
            failed.append("mrr")
        if scores.path_accuracy < floors.path_accuracy:
            failed.append("path_accuracy")
        for name in sorted(INVARIANT_CHECKS):
            tally = scores.checks.get(name)
            if tally is not None and tally.passed < tally.total:
                failed.append(name)
        return tuple(failed)


@traced
def run_evaluation(
    dataset: EvalDataset,
    agent: KnowledgeAgent,
    *,
    k: int,
    mode: Mode = "mock",
) -> EvalReport:
    """Ask every question in ``dataset`` and score the run.

    Args:
        dataset: The validated question set.
        agent: The agent under evaluation. Its provider decides what the run
            costs; the caller chooses it (``python -m app.eval`` uses the mock
            unless ``--paid``).
        k: Rank cut-off for recall@k and the retrieval depth scored.
        mode: Where required facts are looked for: retrieved evidence (``mock``)
            or the answer text (``paid``).

    Returns:
        The full report.
    """
    results = tuple(run_case(case, agent, k=k, mode=mode) for case in dataset.cases)
    return EvalReport(
        mode=mode,
        k=k,
        dataset_version=dataset.version,
        thresholds=dataset.thresholds,
        cases=results,
        scores=score(results),
    )


@traced
def run_case(
    case: EvalCase, agent: KnowledgeAgent, *, k: int, mode: Mode
) -> CaseResult:
    """Score retrieval, ask the agent and check the answer for one question."""
    ranked: tuple[str, ...] = ()
    hit: bool | None = None
    rank_score: float | None = None
    evidence = ""
    if case.expected_docs:
        retrieval = agent.retriever.retrieve(case.question, k=k)
        ranked = ranked_documents(retrieval)
        hit = hit_at_k(ranked, case.expected_docs, k)
        rank_score = reciprocal_rank(ranked, case.expected_docs)
        evidence = "\n".join(scored.chunk.content for scored in retrieval.chunks)

    started = time.perf_counter()
    actual: DecisionReason
    try:
        answer = agent.ask(case.question)
    except LLMInvalidCitationError as exc:
        # 14.E: a withheld answer is a failed citation check for this question,
        # not the end of the run. Every other error still propagates.
        if exc.route is None:
            raise
        actual = _ROUTE.validate_python(exc.route)
        checks = check_withheld_answer(case, actual, exc.markers)
    else:
        actual = answer.decision.reason
        mention_text = answer.text if mode == "paid" else evidence
        checks = check_answer(case, answer, mention_text=mention_text)
    latency = elapsed_ms(started)

    result = CaseResult(
        case_id=case.id,
        category=case.category,
        expected_path=case.expected_path,
        actual_path=actual,
        ranked_documents=ranked,
        hit=hit,
        reciprocal_rank=rank_score,
        checks=checks,
        latency_ms=latency,
    )
    # Ids, routes and numbers only: never the question or answer text (10.A).
    logger.info(
        "eval.case",
        case_id=case.id,
        category=case.category,
        expected_path=case.expected_path,
        actual_path=result.actual_path,
        passed=result.passed,
        latency_ms=latency,
    )
    return result


@traced
def score(results: Sequence[CaseResult]) -> Scores:
    """Aggregate per-question results into the run's scores.

    Raises:
        ValueError: If there are no results — a dataset always has a case, so
            this is a caller bug, not an empty score.
    """
    if not results:
        raise ValueError("Cannot score an evaluation with no results.")
    hits = [result.hit for result in results if result.hit is not None]
    ranks = [
        result.reciprocal_rank
        for result in results
        if result.reciprocal_rank is not None
    ]
    tallies: dict[str, CheckTally] = {}
    for result in results:
        for check in result.checks:
            tally = tallies.get(check.name, CheckTally(passed=0, total=0))
            tallies[check.name] = CheckTally(
                passed=tally.passed + int(check.passed), total=tally.total + 1
            )
    return Scores(
        recall_at_k=recall_at_k(hits) if hits else None,
        mrr=mean_reciprocal_rank(ranks) if ranks else None,
        retrieval_cases=len(ranks),
        path_accuracy=sum(result.path_correct for result in results) / len(results),
        checks=tallies,
    )
