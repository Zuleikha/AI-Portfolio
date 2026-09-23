"""Render an :class:`~app.eval.runner.EvalReport` as a plain-text scorecard.

Plain ASCII, so it reads the same in a Windows console, a CI log and a pasted
message. Question text is not printed: case ids are the stable handle, and the
dataset file is one lookup away.
"""

from __future__ import annotations

from statistics import median

from app.core.cli import RULE
from app.core.tracing import traced
from app.eval.runner import EvalReport

_CHECK_ORDER = (
    "path",
    "tools",
    "documents",
    "refusal",
    "refusal_honest",
    "citations",
    "mentions",
)


@traced
def render_report(report: EvalReport) -> str:
    """The scorecard for one run: scores against floors, checks, every case."""
    scores, floors = report.scores, report.thresholds
    mode = "mock (free)" if report.mode == "mock" else "paid (real model)"
    failed = report.failed_floors()
    lines = [
        RULE,
        f"Evaluation - dataset v{report.dataset_version} - "
        f"{len(report.cases)} questions - mode: {mode}",
        RULE,
        f"Retrieval ({scores.retrieval_cases} questions with expected documents)",
        _score_line(f"recall@{report.k}", scores.recall_at_k, floors.recall_at_k),
        _score_line("MRR", scores.mrr, floors.mrr),
        "Routing",
        _score_line("path accuracy", scores.path_accuracy, floors.path_accuracy),
        "Checks (passed/ran)",
    ]
    for name in _CHECK_ORDER:
        tally = scores.checks.get(name)
        if tally is not None:
            lines.append(f"  {name:<14}{tally.passed:>3}/{tally.total:<3}")

    latencies = [case.latency_ms for case in report.cases]
    lines.append(
        f"Latency per question: median {median(latencies):.1f} ms, "
        f"max {max(latencies):.1f} ms"
    )

    lines.append("")
    lines.append(
        f"  {'case':<10}{'category':<11}{'route':<7}{'hit':<6}{'RR':<6}failed checks"
    )
    for case in report.cases:
        hit = "-" if case.hit is None else ("yes" if case.hit else "NO")
        rank = "-" if case.reciprocal_rank is None else f"{case.reciprocal_rank:.2f}"
        route = "ok" if case.path_correct else "WRONG"
        failures = "; ".join(
            f"{check.name}: {check.detail}" for check in case.checks if not check.passed
        )
        lines.append(
            f"  {case.case_id:<10}{case.category:<11}{route:<7}"
            f"{hit:<6}{rank:<6}{failures}"
        )

    lines.append(RULE)
    lines.append(f"Result: FAIL ({', '.join(failed)})" if failed else "Result: PASS")
    return "\n".join(lines)


@traced
def _score_line(label: str, value: float | None, floor: float) -> str:
    """One score against its floor."""
    if value is None:
        return f"  {label:<14}n/a    floor {floor:.3f}  (nothing to score)"
    verdict = "PASS" if value >= floor else "FAIL"
    return f"  {label:<14}{value:.3f}  floor {floor:.3f}  {verdict}"
