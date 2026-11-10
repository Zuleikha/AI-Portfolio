"""The graph: search → summarise → check, plus one audit record per run (docs/PRD.md, Stage 6).

``run`` streams the graph so it keeps every finished step. If a step fails, the record
still keeps what finished before it (a paid summary is not lost), then the step's error
is re-raised (G6).
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, cast

import httpx
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from research_agent.audit.run_log import build_audit_record, new_run_id, write_audit_record
from research_agent.nodes.citation_check import check_node
from research_agent.nodes.search import search_node
from research_agent.nodes.summarise import summarise_node
from research_agent.observability import traced
from research_agent.state import CheckedSummary, GraphState
from research_agent.tracing import trace_info, tracing_config, tracing_scope

logger = logging.getLogger(__name__)

RUN_MAX_RESULTS = 5  # G3
DEFAULT_RUNS_DIR = Path("runs")

# Step name → the state key it fills, in graph order.
STEPS = (("search", "search"), ("summarise", "summary"), ("check", "checked"))


@dataclass(frozen=True)
class RunOutcome:
    path: Path
    status: str
    checked: CheckedSummary | None


@traced
def build_graph(
    *,
    client: httpx.Client | None = None,
    summarise_llm: Runnable[Any, Any] | None = None,
    check_llm: Runnable[Any, Any] | None = None,
) -> CompiledStateGraph[GraphState, None, GraphState, GraphState]:
    """``START → search → summarise → check → END``. Arguments are test hooks."""
    builder = StateGraph(GraphState)
    builder.add_node("search", partial(search_node, client=client))
    builder.add_node("summarise", partial(summarise_node, llm=summarise_llm))
    builder.add_node("check", partial(check_node, llm=check_llm))
    builder.add_edge(START, "search")
    builder.add_edge("search", "summarise")
    builder.add_edge("summarise", "check")
    builder.add_edge("check", END)
    return builder.compile()


@traced
def _failed_step(state: GraphState) -> str:
    """The first step whose result is missing from the last good state."""
    for step, key in STEPS:
        if key not in state:
            return step
    return STEPS[-1][0]


@traced
def run(
    query: str,
    *,
    max_results: int = RUN_MAX_RESULTS,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    client: httpx.Client | None = None,
    summarise_llm: Runnable[Any, Any] | None = None,
    check_llm: Runnable[Any, Any] | None = None,
    trace: bool = False,
) -> RunOutcome:
    """Run the graph once and write its audit record (G5, G6, G12). Hooks are for tests.

    ``trace=True`` sends a trace to LangSmith (Stage 7); off by default, even against
    ``LANGSMITH_TRACING=true`` (T1). A missing key fails before any call (T2).
    """
    created_at = datetime.now(UTC)
    run_id = new_run_id(created_at)
    config = tracing_config(run_id, enabled=trace)  # T2: before any PubMed or model call
    trace_entry = trace_info(enabled=trace)
    graph = build_graph(client=client, summarise_llm=summarise_llm, check_llm=check_llm)
    state: GraphState = {"query": query, "max_results": max_results}

    try:
        with tracing_scope(enabled=trace):
            for snapshot in graph.stream(state, config=config, stream_mode="values"):
                # stream_mode="values" yields the full graph state after each step.
                state = cast(GraphState, snapshot)
    except Exception as exc:
        step = _failed_step(state)
        logger.error("run failed at step %s (%s)", step, type(exc).__name__)
        record = build_audit_record(
            run_id=run_id,
            created_at=created_at,
            finished_at=datetime.now(UTC),
            state=state,
            error=(step, exc),
            trace=trace_entry,
        )
        logger.info("injection warnings: %d", len(record["injection_warnings"]))
        try:
            write_audit_record(record, runs_dir)
        except Exception as write_exc:  # G6: never hide the step's error behind this one
            logger.error("audit record not written (%s)", type(write_exc).__name__)
        raise

    record = build_audit_record(
        run_id=run_id,
        created_at=created_at,
        finished_at=datetime.now(UTC),
        state=state,
        error=None,
        trace=trace_entry,
    )
    logger.info("injection warnings: %d", len(record["injection_warnings"]))  # count only (G9)
    path = write_audit_record(record, runs_dir)
    logger.info("run ok: %s", record["counts"])
    return RunOutcome(path=path, status="ok", checked=state.get("checked"))
