"""Scoring: retrieval rank metrics and rule checks on one answer.

**Retrieval** (``docs/HANDOVER.md`` 11.C) is scored on distinct documents in rank
order. *recall@k* is the share of questions with an expected document in the top
*k*; *MRR* averages ``1 / rank`` of the first expected document (0 when absent).
An empty score list raises rather than returning 0: "no questions were scored"
and "every question missed" are different findings.

**Answers** (11.B) are checked by rules that need no model:

==========  ==============================================================
check       passes when
==========  ==============================================================
path        the route taken matches (a refined search still counts as a
            knowledge answer)
tools       every expected tool was called
documents   an expected document was among those retrieved
refusal     refused exactly when a refusal was expected — a *score*: whether
            an off-topic question clears the retrieval floor depends on the
            embedding model, so it is gated through path accuracy
refusal_    an answer that did refuse used no model and says the fixed
honest      insufficient-evidence sentence — an *invariant*
citations   every ``[n]`` / ``[Tn]`` points at evidence actually supplied —
            a citation to nothing is the mechanical sign of hallucination.
            Since 14.B the service withholds such an answer; the runner
            scores it with :func:`check_withheld_answer` (14.E)
mentions    each required fact appears in the text given (the retrieved
            evidence in free mode, the answer itself in paid mode)
==========  ==============================================================
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.models import AgentAnswer, DecisionReason
from app.core.tracing import traced
from app.eval.dataset import REFUSAL_PATHS, EvalCase
from app.llm.citations import invalid_citations
from app.llm.prompts import INSUFFICIENT_EVIDENCE
from app.rag.models import RetrievalResult

CheckName = Literal[
    "path", "tools", "documents", "refusal", "refusal_honest", "citations", "mentions"
]
"""The rule checks :func:`check_answer` can run."""

KNOWLEDGE_ANSWER_PATHS: frozenset[str] = frozenset(
    {"knowledge_required", "additional_knowledge_required"}
)
"""Routes that are the same answer to a user: one search or a refined second one.

Whether a search is refined depends on a measured score
(``Settings.agent_confident_score``), so a dataset cannot fairly demand either.
"""


class CheckResult(BaseModel):
    """The outcome of one rule check on one answer."""

    model_config = ConfigDict(frozen=True)

    name: CheckName
    passed: bool
    detail: str = Field(description="Why it passed or failed. Names ids, never text.")


@traced
def ranked_documents(result: RetrievalResult) -> tuple[str, ...]:
    """Distinct document ids behind a retrieval, best-ranked first."""
    return tuple(dict.fromkeys(scored.chunk.document_id for scored in result.chunks))


@traced
def reciprocal_rank(ranked: Sequence[str], expected: Iterable[str]) -> float:
    """``1 / rank`` of the best-ranked expected document, or 0.0 if none appears."""
    wanted = set(expected)
    for rank, document in enumerate(ranked, start=1):
        if document in wanted:
            return 1.0 / rank
    return 0.0


@traced
def hit_at_k(ranked: Sequence[str], expected: Iterable[str], k: int) -> bool:
    """Whether any expected document is among the first ``k`` ranked documents."""
    return bool(set(ranked[:k]) & set(expected))


@traced
def recall_at_k(hits: Sequence[bool]) -> float:
    """The share of questions that hit.

    Raises:
        ValueError: If there is nothing to score.
    """
    if not hits:
        raise ValueError("recall@k needs at least one scored question.")
    return sum(hits) / len(hits)


@traced
def mean_reciprocal_rank(ranks: Sequence[float]) -> float:
    """The mean of the per-question reciprocal ranks.

    Raises:
        ValueError: If there is nothing to score.
    """
    if not ranks:
        raise ValueError("MRR needs at least one scored question.")
    return sum(ranks) / len(ranks)


@traced
def path_matches(expected: str, actual: str) -> bool:
    """Whether the route taken is the route expected."""
    if expected == actual:
        return True
    return expected in KNOWLEDGE_ANSWER_PATHS and actual in KNOWLEDGE_ANSWER_PATHS


@traced
def missing_mentions(text: str, facts: Iterable[str]) -> tuple[str, ...]:
    """Required facts absent from ``text``, ignoring case, in the order given."""
    folded = text.casefold()
    return tuple(fact for fact in facts if fact.casefold() not in folded)


@traced
def check_answer(
    case: EvalCase, answer: AgentAnswer, *, mention_text: str
) -> tuple[CheckResult, ...]:
    """Run every rule check that applies to ``case`` against ``answer``.

    Args:
        case: The expectations.
        answer: What the agent returned.
        mention_text: Where required facts are looked for — the retrieved
            evidence in free mode, the answer text in paid mode.

    Returns:
        ``path``, ``refusal``, ``refusal_honest`` and ``citations`` always;
        ``tools``, ``documents`` and ``mentions`` when the case expects them.
    """
    actual = answer.decision.reason
    checks = [
        CheckResult(
            name="path",
            passed=path_matches(case.expected_path, actual),
            detail=f"expected {case.expected_path}, got {actual}",
        )
    ]

    if case.expected_tools:
        called = {summary.tool for summary in answer.tools}
        missing = [tool for tool in case.expected_tools if tool not in called]
        checks.append(
            CheckResult(
                name="tools",
                passed=not missing,
                detail=(
                    f"not called: {', '.join(missing)}"
                    if missing
                    else "every expected tool was called"
                ),
            )
        )

    if case.expected_docs:
        retrieved = set(answer.retrieval.documents)
        found = [doc for doc in case.expected_docs if doc in retrieved]
        checks.append(
            CheckResult(
                name="documents",
                passed=bool(found),
                detail=(
                    f"retrieved {', '.join(found)}"
                    if found
                    else f"none of {', '.join(case.expected_docs)} retrieved"
                ),
            )
        )

    checks.append(_refusal_check(case, answer))
    checks.append(_honest_refusal_check(answer))

    invented = invalid_citations(answer.text, answer.chunks_used, answer.tools_used)
    checks.append(
        CheckResult(
            name="citations",
            passed=not invented,
            detail=(
                f"cites evidence that was not supplied: {' '.join(invented)}"
                if invented
                else "every citation points at supplied evidence"
            ),
        )
    )

    if case.must_mention:
        absent = missing_mentions(mention_text, case.must_mention)
        checks.append(
            CheckResult(
                name="mentions",
                passed=not absent,
                detail=(
                    f"missing: {', '.join(absent)}"
                    if absent
                    else "every required fact is present"
                ),
            )
        )
    return tuple(checks)


@traced
def check_withheld_answer(
    case: EvalCase, actual: DecisionReason, markers: Sequence[str]
) -> tuple[CheckResult, ...]:
    """The checks for an answer the service withheld for invented citations.

    Since 14.B there is no answer to inspect, only the route and the markers
    (14.E). ``path`` is scored normally; ``citations`` fails and names the
    markers. The other checks need answer content, so they are not run.

    Args:
        case: The expectations.
        actual: The route the agent took before the answer was withheld.
        markers: The invalid citation markers, e.g. ``("[9]",)``.
    """
    return (
        CheckResult(
            name="path",
            passed=path_matches(case.expected_path, actual),
            detail=f"expected {case.expected_path}, got {actual}",
        ),
        CheckResult(
            name="citations",
            passed=False,
            detail=(
                "answer withheld: cites evidence that was not supplied: "
                f"{' '.join(markers)}"
            ),
        ),
    )


@traced
def _refusal_check(case: EvalCase, answer: AgentAnswer) -> CheckResult:
    """Refused exactly when a refusal was expected."""
    expected = case.expected_path in REFUSAL_PATHS
    if answer.refused == expected:
        detail = "refused as expected" if expected else "answered as expected"
    elif answer.refused:
        detail = "refused but should have answered"
    else:
        detail = "answered but should have refused"
    return CheckResult(name="refusal", passed=answer.refused == expected, detail=detail)


@traced
def _honest_refusal_check(answer: AgentAnswer) -> CheckResult:
    """A refusal consulted no model and used the fixed sentence."""
    if not answer.refused:
        return CheckResult(name="refusal_honest", passed=True, detail="not a refusal")
    honest = not answer.llm_called and INSUFFICIENT_EVIDENCE in answer.text
    return CheckResult(
        name="refusal_honest",
        passed=honest,
        detail=(
            "refused without a model, in the fixed sentence"
            if honest
            else "refusal consulted a model or did not use the fixed sentence"
        ),
    )
