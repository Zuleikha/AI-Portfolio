"""The knowledge agent: a technical question in, a source-backed answer out.

This is the component that owns a complete request. Stages 3 and 4 each built one
half and were deliberately kept ignorant of the other — the retriever has no LLM
dependency, and ``LLMService`` does not retrieve. The agent is the seam between
them and the MCP tools, and it is a thin one on purpose: every *choice* is made in
:mod:`app.agent.policy`, and this module only carries each one out::

    question
       │
       ▼  decide(question, selector)         PLAN      policy.py
       │
       ├── tools planned ──▶ ToolRegistry.invoke_all()             LIVE READINGS
       │
       ├── live_status_only, every reading found something ──▶ no search
       ├── live_status_only, a reading found nothing ────────▶ search anyway
       │
       ├── search ──▶ Retriever.retrieve(question)                 DOCUMENTATION
       │                 weak and refinable? ──▶ ONE refined second search, merged
       │
       ▼  LLMService.answer(question, retrieval, tool_results)  ← Stage 4's guard
       │        no evidence of either kind  ──▶  refuse, ZERO provider calls
       │
       ▼  conclude(plan, ...)                ROUTE     policy.py
       ▼
    AgentAnswer   answer + sources + decision + decisions + retrieval + tools

The two kinds of evidence stay separate the whole way through: separate
collection, separate fences in the prompt, separate fields on the answer.

**One refusal path, and it is Stage 4's.** When the agent does not search, it
does not write its own refusal. It builds an empty
:class:`~app.rag.models.RetrievalResult` and hands that to the service, which
takes the guard it already had: the fixed insufficient-evidence sentence, and no
model call. The API, the web interface and Stage 11's evaluation harness all
detect refusals by that exact sentence. Two sources for it is one too many.

**The agent does not soften failures.** A provider timeout, a rate limit, a
truncated generation or a broken tool raises out of here as the typed error its
layer defined. Converting an infrastructure failure into "the knowledge base does
not contain enough information" would be a lie of exactly the kind this project
exists to prevent.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.agent.models import (
    AgentAnswer,
    AgentDecision,
    DecisionOutcome,
    DecisionStep,
    RetrievalSummary,
    ToolCallSummary,
)
from app.agent.policy import (
    conclude,
    decide,
    record_step,
    refinement_terms,
    retrieval_is_weak,
)
from app.agent.tool_policy import RuleToolSelector, ToolSelector
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.observability import fingerprint
from app.core.tracing import traced
from app.llm.base import LLMInvalidCitationError
from app.llm.service import LLMService
from app.mcp.models import ToolResult
from app.mcp.registry import ToolRegistry
from app.rag.models import RetrievalResult, ScoredChunk
from app.rag.retriever import Retriever

logger = get_logger(__name__)


class KnowledgeAgent:
    """Answers technical questions from the synthetic banking knowledge base.

    Every collaborator is injected, exactly as one layer down: the tests run this
    class with a hashing embedder and :class:`~app.llm.mock.MockLLMProvider`, and
    production passes a sentence-transformers retriever and whichever provider is
    configured. Neither this class nor its callers change between the two.
    """

    def __init__(
        self,
        retriever: Retriever,
        llm_service: LLMService,
        settings: Settings | None = None,
        tools: ToolRegistry | None = None,
        selector: ToolSelector | None = None,
    ) -> None:
        """Wire the agent to its knowledge source, its model and its tools.

        Args:
            retriever: The RAG layer, already indexed.
            llm_service: The generation layer, already bound to a provider.
            settings: Application settings. Defaults to the cached singleton.
            tools: The MCP tool registry. ``None`` means the agent has no tools
                and behaves exactly as it did in Stage 5.
            selector: Chooses tool calls. ``None`` builds a
                :class:`~app.agent.tool_policy.RuleToolSelector` from ``tools``,
                so the agent can only ever select a tool it can call.

        Raises:
            ValueError: If a selector is supplied without a registry. It could
                choose tools this agent has no way to call, and that is a
                composition error to refuse here rather than at the first
                question that needs a tool.

        Note:
            New parameters are appended, never inserted, so that call sites
            passing earlier arguments positionally keep their meaning.
        """
        if selector is not None and tools is None:
            raise ValueError(
                "A tool selector was supplied without a tool registry, so it could "
                "choose tools this agent cannot call. Pass tools= as well, or build "
                "the agent with app.agent.factory.get_agent()."
            )
        self._retriever = retriever
        self._llm = llm_service
        self._settings = settings or get_settings()
        self._tools = tools
        if selector is not None:
            self._selector: ToolSelector | None = selector
        elif tools is not None:
            self._selector = RuleToolSelector(tools.specs())
        else:
            self._selector = None

    @property
    def retriever(self) -> Retriever:
        """The knowledge source this agent searches."""
        return self._retriever

    @property
    def llm_service(self) -> LLMService:
        """The generation layer this agent answers through."""
        return self._llm

    @property
    def tools(self) -> ToolRegistry | None:
        """The tool registry this agent can call, if it has one."""
        return self._tools

    @property
    def selector(self) -> ToolSelector | None:
        """What chooses this agent's tool calls, if it has tools."""
        return self._selector

    @traced
    def ask(self, question: str, history: Sequence[str] = ()) -> AgentAnswer:
        """Answer one technical question, or say why it cannot be answered.

        The agent stays single-question. Stage 8's conversation layer resolves a
        follow-up *before* calling this, and passes the earlier questions it used
        as ``history``, which is handed to the LLM service unchanged and plays no
        part in any routing decision here.

        Args:
            question: The question, in natural language.
            history: Earlier questions of the conversation, oldest first. Empty
                by default, which is exactly the Stage 7 behaviour.

        Returns:
            The answer together with the route taken, every choice point on the
            way, and the retrieval and tool records behind it. A refusal is a
            valid, successful return value — not an error.

        Raises:
            ValueError: If the question is blank.
            EmbeddingError: If the question cannot be embedded.
            ToolError: If a selected tool fails. Deliberately propagated.
            LLMError: If the provider fails or returns an unusable generation.
                Deliberately propagated: a broken model is not the same
                situation as an undocumented answer.
        """
        if not question.strip():
            raise ValueError("Cannot answer an empty question.")

        plan = decide(question, self._selector)
        steps: list[DecisionStep] = [
            DecisionStep(step="plan", outcome=plan.reason, explanation=plan.explanation)
        ]

        tool_results, tool_summaries = self._run_tools(plan)

        searched = plan.retrieve
        if plan.reason == "live_status_only":
            searched = any(not result.ok for result in tool_results)
            steps.append(
                record_step(
                    "consult_documentation", "performed" if searched else "not_needed"
                )
            )

        if searched:
            retrieval, passes, retrieve_more = self._search(
                question, plan, tool_results
            )
            steps.append(retrieve_more)
            summary = RetrievalSummary.from_result(retrieval, passes=passes)
        else:
            retrieval, passes = self._no_evidence(question), 0
            summary = RetrievalSummary.not_performed()

        try:
            grounded = self._llm.answer(
                question, retrieval, tool_results, tuple(history)
            )
        except LLMInvalidCitationError as exc:
            # 14.E: the model did answer, so this is the route it answered on.
            # The evaluation scores the withheld answer against it.
            exc.route = conclude(
                plan, searched=searched, passes=passes, refused=False
            ).reason
            raise
        evidence: DecisionOutcome = "insufficient" if grounded.refused else "sufficient"
        steps.append(record_step("evidence", evidence))
        decision = conclude(
            plan, searched=searched, passes=passes, refused=grounded.refused
        )

        logger.info(
            "agent.answered",
            # The question, the passages, the tool payloads, the answer text and
            # every explanation sentence are withheld here. The question appears
            # only as a fingerprint and a length (guide §20.32), so a tool-only
            # answer -- which never reaches the retriever -- is still traceable;
            # the rest is content. Route and shape only -- step names and
            # outcomes, tool NAMES and argument NAMES are shape; argument VALUES
            # and payloads are not.
            question_hash=fingerprint(question),
            question_length=len(question),
            plan=plan.reason,
            decision=decision.reason,
            route=[f"{step.step}:{step.outcome}" for step in steps],
            retrieval_performed=summary.performed,
            retrieval_passes=summary.passes,
            candidates=summary.candidates_considered,
            chunks_returned=summary.chunks_returned,
            chunks_used=grounded.chunks_used,
            top_score=summary.top_score,
            tools_called=len(tool_summaries),
            tools=[call.tool for call in tool_summaries],
            tools_found=[call.tool for call in tool_summaries if call.ok],
            history_questions=len(history),
            refused=grounded.refused,
            llm_called=grounded.llm_called,
            documents=list(summary.documents),
        )

        return AgentAnswer(
            question=question,
            text=grounded.text,
            sources=grounded.sources,
            decision=decision,
            decisions=tuple(steps),
            retrieval=summary,
            tools=tool_summaries,
            tool_results=tool_results,
            answer=grounded,
        )

    @traced
    def ask_many(self, questions: list[str]) -> tuple[AgentAnswer, ...]:
        """Answer several questions in order. Used by the CLI and by evaluation."""
        return tuple(self.ask(question) for question in questions)

    def _search(
        self,
        question: str,
        plan: AgentDecision,
        tool_results: tuple[ToolResult, ...],
    ) -> tuple[RetrievalResult, int, DecisionStep]:
        """Search, and search once more if the first pass is weak and refinable.

        Returns:
            The retrieval to answer from (merged when a second pass ran), how many
            passes ran, and the ``retrieve_more`` step recording why.
        """
        first = self._retriever.retrieve(question)
        if not retrieval_is_weak(first, self._settings.agent_confident_score):
            return first, 1, record_step("retrieve_more", "not_needed")

        terms = refinement_terms(question, first, plan.tools, tool_results)
        if not terms:
            return first, 1, record_step("retrieve_more", "no_refinement_available")

        second = self._retriever.retrieve(f"{question} {' '.join(terms)}")
        return (
            self._merge(question, first, second),
            2,
            record_step("retrieve_more", "performed"),
        )

    def _merge(
        self, question: str, first: RetrievalResult, second: RetrievalResult
    ) -> RetrievalResult:
        """Combine two passes: one entry per chunk at its best score, best first.

        Capped at ``retrieval_top_k`` so a second search widens the *choice* of
        passages without widening the prompt. The floor is not touched: both
        passes already applied it. Ties keep first-pass order, so the merge is
        deterministic.
        """
        best: dict[str, ScoredChunk] = {}
        for scored in (*first.chunks, *second.chunks):
            kept = best.get(scored.chunk.chunk_id)
            if kept is None or scored.score > kept.score:
                best[scored.chunk.chunk_id] = scored
        ranked = sorted(best.values(), key=lambda item: item.score, reverse=True)
        return RetrievalResult(
            query=question,
            chunks=tuple(ranked[: self._settings.retrieval_top_k]),
            candidates_considered=max(
                first.candidates_considered, second.candidates_considered
            ),
            min_score=first.min_score,
        )

    def _run_tools(
        self, decision: AgentDecision
    ) -> tuple[tuple[ToolResult, ...], tuple[ToolCallSummary, ...]]:
        """Execute the tool calls the plan asked for.

        Returns both the full results — which go into the prompt and back to the
        caller — and their summaries, which are what gets logged.

        **A tool failure is not softened, for the same reason an LLM failure is
        not.** If a registered tool raises, the :class:`~app.mcp.base.ToolError`
        propagates out of :meth:`ask`. A tool reporting ``ok=False`` is *not* a
        failure and does not raise: "no transaction has that reference" is a
        finding, and it is passed to the model to report.
        """
        if not decision.tools:
            return (), ()
        if self._tools is None:
            # Unreachable through the constructor, which refuses a selector
            # without a registry. Kept as a loud invariant rather than trusted.
            raise RuntimeError(
                f"The plan selected {len(decision.tools)} tool call(s), but this "
                "agent was built without a tool registry."
            )

        results = self._tools.invoke_all(decision.tools)
        summaries = tuple(
            ToolCallSummary.from_call(invocation, result)
            for invocation, result in zip(decision.tools, results, strict=True)
        )
        return results, summaries

    def _no_evidence(self, question: str) -> RetrievalResult:
        """Build the empty result that routes a no-search question to the guard.

        Nothing was searched, so ``candidates_considered`` is 0 and
        ``min_score`` is the configured floor that was never applied. The object
        exists only to carry "there is no evidence" into the one component that
        knows what to do about it.
        """
        return RetrievalResult(
            query=question,
            chunks=(),
            candidates_considered=0,
            min_score=self._settings.retrieval_min_score,
        )
