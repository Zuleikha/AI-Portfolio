"""The agent's decisions: what to gather, whether to gather more, and when to stop.

``prompt.md`` §15 asks the agent to decide between answering from knowledge,
retrieving more, calling a tool, using both, and refusing. Every one of those
choices is made here, by deterministic rules, and nowhere else. The agent in
:mod:`app.agent.agent` executes; this module decides::

    question
       │
       ▼  decide()               THE PLAN
       │    no searchable content ─────────────────▶ no_searchable_content
       │    selector finds no tool call ───────────▶ knowledge_required
       │    tool calls + asks for an explanation ──▶ knowledge_and_live_status_required
       │    tool calls + asks only for a reading ──▶ live_status_only
       │
       ▼  (the agent runs the tools)
       │    live_status_only and a tool found nothing ─▶ search the documentation too
       │
       ▼  retrieval_is_weak() + refinement_terms()   RETRIEVE MORE?
       │    confident first search ─────────────────▶ one pass
       │    weak, and a documented component to add ▶ ONE refined second pass
       │    weak, nothing to add ───────────────────▶ one pass
       │
       ▼  (the service answers, or refuses through Stage 4's single guard)
       │
       ▼  conclude()             THE ROUTE ACTUALLY TAKEN
                                 plus a DecisionStep for every choice point

**No model makes any of these decisions — by the user's decision**
(``docs/HANDOVER.md`` §7.B). Stage 5 argued an LLM router was not worth a model
call per question when there was one option; Stage 7 has five, and the question
was put to the user with a model-driven selector as an option. It was declined:
a paid call per question, non-deterministic routing, and a selector that could
only be proven against the mock.

**Question form, not topic.** Stage 5 rejected a topic-keyword classifier for
retrieval, and that rejection stands. :func:`asks_for_explanation` reads
something different: whether the question asks *why / how / what it means* or
only for a reading. That distinction only matters once a tool call has already
been selected on an identifier, and the costly direction of getting it wrong — a
live reading with no documentation where documentation was needed — is guarded
twice: an explanation cue always keeps retrieval, and a tool-only plan whose
reading finds nothing searches the documentation anyway.

**Retrieve more is measured, bounded and cannot invent relevance.** The threshold
comes from the real model (``HANDOVER.md`` §7.C). The second search never lowers
the calibrated floor; it adds one documented component name to the query, taken
either from the tools or from the best passage that *already cleared the floor*.
An off-topic question clears nothing, so it has nothing to be refined with and is
refused exactly as before. There is one extra search at most, never a loop.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from app.agent.models import (
    AgentDecision,
    DecisionOutcome,
    DecisionReason,
    DecisionStep,
    DecisionStepName,
)
from app.agent.tool_policy import COMPONENT_NAMES, ToolSelector
from app.core.tracing import traced
from app.mcp.models import ToolInvocation, ToolResult
from app.rag.models import RetrievalResult

SEARCHABLE_MINIMUM = 1
"""Alphanumeric characters a question needs before searching is worth doing."""

EXPLANATION_CUE = re.compile(
    r"\b(why|how|explain|explains|explained|explanation|mean|means|meaning|"
    r"cause|causes|caused|reason|troubleshoot|troubleshooting|diagnose|fix|"
    r"resolve|remediate|should|recommend|recommended|documented|default|"
    r"difference|differ|differs|control|controls|affect|affects)\b",
    re.IGNORECASE,
)
"""Words that ask for an explanation rather than a reading.

A cue about the *form* of the question, not its banking topic: "why", "what does
it mean", "how do I fix". It is consulted only after a tool call has been
selected on an identifier, so it never decides whether to search a question that
names nothing a tool can act on — those always search.
"""

MAX_REFINEMENT_TERMS = 2
"""Most tool-named components a refined search query may gain."""

COMPONENT_FIELDS: tuple[str, ...] = ("component", "stage_component")
"""Tool payload fields that name the component a reading is about."""

_PLAN_KNOWLEDGE = (
    "Answers must be grounded in the documentation, so the knowledge base was "
    "searched for supporting passages."
)
_PLAN_NO_SEARCH = (
    "The question contains no searchable words, so the knowledge base was not "
    "searched."
)
_ROUTE_ADDITIONAL = (
    "The first documentation search was weak, so a refined second search was run "
    "and the passages from both were used."
)
_ROUTE_INSUFFICIENT = (
    "Neither the documentation nor any support tool supplied evidence, so the "
    "agent declined to answer rather than guess."
)

STEP_EXPLANATIONS: Mapping[tuple[DecisionStepName, DecisionOutcome], str] = {
    ("consult_documentation", "not_needed"): (
        "Every support tool found what it was asked about, so the documentation "
        "was not searched."
    ),
    ("consult_documentation", "performed"): (
        "A support tool found nothing for part of the question, so the "
        "documentation was searched as well."
    ),
    ("retrieve_more", "not_needed"): (
        "The first documentation search was confident, so it was not repeated."
    ),
    ("retrieve_more", "no_refinement_available"): (
        "The first documentation search was weak, but no documented component was "
        "available to refine it with, so an identical search was not repeated."
    ),
    ("retrieve_more", "performed"): (
        "The first documentation search was weak, so it was repeated once with a "
        "documented component added to the query."
    ),
    ("evidence", "sufficient"): (
        "Supporting evidence was available, so the model was asked to answer "
        "from it."
    ),
    ("evidence", "insufficient"): (
        "No passage and no tool result was available, so the agent refused "
        "without calling the model."
    ),
}
"""The fixed sentence for every non-plan outcome.

Fixed on purpose: the record is what a rule decided, not reasoning written for
one question. Two runs down the same route are recorded in the same words.
"""


@traced
def decide(question: str, selector: ToolSelector | None = None) -> AgentDecision:
    """Plan how ``question`` should be answered: search, tools, both, or neither.

    Args:
        question: The user's question. Must not be blank.
        selector: Chooses tool calls. ``None`` means the agent has no tools, and
            every searchable question plans a documentation search, exactly as
            in Stage 5.

    Returns:
        The plan: whether to search, which tool calls to make, the rule that
        produced it, and a sentence safe to display. The route actually taken
        may differ; see :func:`conclude`.

    Raises:
        ValueError: If the question is blank. A blank question is not a routing
            outcome — there is nothing to route — so it fails at the boundary
            rather than becoming a refusal that looks like a considered answer.
    """
    if not question.strip():
        raise ValueError("Cannot decide how to answer an empty question.")

    if sum(character.isalnum() for character in question) < SEARCHABLE_MINIMUM:
        return AgentDecision(
            retrieve=False,
            tools=(),
            reason="no_searchable_content",
            explanation=_PLAN_NO_SEARCH,
        )

    tools = selector.select(question) if selector is not None else ()
    if not tools:
        return AgentDecision(
            retrieve=True,
            tools=(),
            reason="knowledge_required",
            explanation=_PLAN_KNOWLEDGE,
        )

    named = _tool_names(tools)
    if asks_for_explanation(question):
        return AgentDecision(
            retrieve=True,
            tools=tools,
            reason="knowledge_and_live_status_required",
            explanation=(
                "The question asks for an explanation of something a support tool "
                "can look up, so the knowledge base was searched and the live "
                f"system was queried through: {named}."
            ),
        )

    return AgentDecision(
        retrieve=False,
        tools=tools,
        reason="live_status_only",
        explanation=(
            "The question asks for a reading of the live system rather than an "
            "explanation, so the support tools were queried through: "
            f"{named}."
        ),
    )


@traced
def decide_retrieval(question: str) -> AgentDecision:
    """Stage 5's name for :func:`decide`, planning without tools.

    Retained so that Stage 5's tests and any caller written against the older
    name keep working.
    """
    return decide(question)


@traced
def asks_for_explanation(question: str) -> bool:
    """Whether ``question`` asks why, how, or what something means."""
    return EXPLANATION_CUE.search(question) is not None


@traced
def retrieval_is_weak(result: RetrievalResult, confident_score: float) -> bool:
    """Whether a completed search is weak enough to try refining.

    Args:
        result: The first search.
        confident_score: ``Settings.agent_confident_score``.

    Returns:
        True when nothing cleared the floor, or the best score is below
        ``confident_score``. A score exactly at the threshold is confident.
    """
    return result.top_score is None or result.top_score < confident_score


@traced
def refinement_terms(
    question: str,
    first_pass: RetrievalResult,
    invocations: Sequence[ToolInvocation] = (),
    tool_results: Sequence[ToolResult] = (),
    vocabulary: Sequence[str] = COMPONENT_NAMES,
) -> tuple[str, ...]:
    """Documented component names a weak search can be refined with.

    In priority order:

    1. Components the tools named — a ``component`` argument, or the component a
       **successful** reading reports — at most :data:`MAX_REFINEMENT_TERMS`.
    2. Otherwise, the component of the highest-ranked passage that cleared the
       floor and belongs to a documented component (``Platform`` documents are
       skipped). If the question already names it, there is nothing to add.

    **Only members of ``vocabulary`` can be returned.** A tool payload is
    untrusted, and the refined query is embedded and written to the
    ``rag.retrieved`` log line; vetting every term against a closed list means no
    payload text can reach either.

    Args:
        question: The question as asked.
        first_pass: The weak search being refined.
        invocations: The tool calls made.
        tool_results: What those calls reported.
        vocabulary: The documented component names.

    Returns:
        The terms to append, or an empty tuple when there is nothing to add.
    """
    canonical = {name.casefold(): name for name in vocabulary}
    asked = question.casefold()

    def documented(value: object) -> str | None:
        """The canonical component for ``value``, or None if undocumented."""
        if not isinstance(value, str):
            return None
        return canonical.get(value.casefold())

    named: list[str] = []
    for invocation in invocations:
        component = documented(invocation.arguments.get("component"))
        if component is not None:
            named.append(component)
    for result in tool_results:
        if not result.ok:
            continue
        for field in COMPONENT_FIELDS:
            component = documented(result.data.get(field))
            if component is not None:
                named.append(component)

    from_tools = tuple(
        name for name in dict.fromkeys(named) if name.casefold() not in asked
    )[:MAX_REFINEMENT_TERMS]
    if from_tools:
        return from_tools

    for scored in first_pass.chunks:
        component = documented(scored.chunk.metadata.component)
        if component is None:
            continue
        return () if component.casefold() in asked else (component,)
    return ()


@traced
def record_step(step: DecisionStepName, outcome: DecisionOutcome) -> DecisionStep:
    """The record of one non-plan choice point, with its fixed sentence.

    Raises:
        KeyError: If the pair is not a combination a rule can produce. That is a
            bug in the agent, and it fails loudly rather than recording a step
            with an invented explanation.
    """
    return DecisionStep(
        step=step, outcome=outcome, explanation=STEP_EXPLANATIONS[(step, outcome)]
    )


@traced
def conclude(
    plan: AgentDecision, *, searched: bool, passes: int, refused: bool
) -> AgentDecision:
    """The route actually taken, given the plan and what then happened.

    Args:
        plan: The decision :func:`decide` returned.
        searched: Whether the documentation was searched at all.
        passes: How many searches ran (0, 1 or 2).
        refused: Whether the service refused for want of evidence.

    Returns:
        The plan itself when nothing changed course; otherwise a decision with
        the route taken and its own fixed explanation.
    """
    if plan.reason == "no_searchable_content":
        return plan

    reason: DecisionReason
    if refused:
        reason = "insufficient_evidence"
    elif plan.tools and searched:
        reason = "knowledge_and_live_status_required"
    elif plan.tools:
        reason = "live_status_only"
    elif passes > 1:
        reason = "additional_knowledge_required"
    else:
        reason = "knowledge_required"

    if reason == plan.reason and searched == plan.retrieve:
        return plan

    explanations: dict[DecisionReason, str] = {
        "insufficient_evidence": _ROUTE_INSUFFICIENT,
        "additional_knowledge_required": _ROUTE_ADDITIONAL,
        "knowledge_and_live_status_required": (
            "A support tool found nothing for part of the question, so the "
            "documentation was searched as well; tools queried: "
            f"{_tool_names(plan.tools)}."
        ),
    }
    return AgentDecision(
        retrieve=searched,
        tools=plan.tools,
        reason=reason,
        explanation=explanations.get(reason, plan.explanation),
    )


def _tool_names(tools: Sequence[ToolInvocation]) -> str:
    """Distinct tool names, sorted. Names only — never argument values."""
    return ", ".join(sorted({invocation.tool for invocation in tools}))
