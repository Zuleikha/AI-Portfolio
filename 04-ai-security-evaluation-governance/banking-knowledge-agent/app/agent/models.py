"""Data contracts for the knowledge agent.

The records one agent run produces::

    question  --policy-->     AgentDecision        the route taken, and why
              --policy-->     DecisionStep x n     each choice point and its outcome
    decision  --retriever-->  RetrievalSummary     what the search(es) actually found
    decision  --registry-->   ToolCallSummary x n  what each tool call did
    all       --service-->    AgentAnswer          the answer, plus that whole record

``AgentAnswer`` wraps rather than replaces
:class:`~app.llm.models.GroundedAnswer`. The LLM layer's contract stays the LLM
layer's; the agent adds the *execution record* on top of it. Flattening the two
would have put agent concerns — which route was taken, what retrieval considered
— into a model that the LLM layer owns and that knows nothing about routing.

**Why the execution record is a first-class value rather than a log line.**
``prompt.md`` §15 requires the API and the web interface to show what actually
happened: retrieval performed, documents used, tools called, final answer. If
that information only exists in ``logs/app.log``, Stage 9 has to scrape its own
logs to render a page. Returning it means the agent's decisions are assertable in
a test and displayable in a UI without either party parsing prose.

**Stage 7: decisions, not chain-of-thought.** ``prompt.md`` §15 forbids exposing
hidden reasoning and asks for useful execution information instead. A
:class:`DecisionStep` is the second kind of thing: a named choice point, the
outcome a deterministic rule produced there, and a *fixed* sentence for that
outcome. Two questions that take the same route are recorded in the same words
— there is no per-question reasoning text anywhere in the record, because none is
ever produced.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.llm.models import GroundedAnswer
from app.mcp.models import ToolInvocation, ToolResult
from app.rag.models import RetrievalResult

DecisionReason = Literal[
    "knowledge_required",
    "additional_knowledge_required",
    "live_status_only",
    "knowledge_and_live_status_required",
    "insufficient_evidence",
    "no_searchable_content",
]
"""The route the agent took for one question.

Stage 5 had two values and Stage 6 added a third. Stage 7 **extends the same
literal** to cover every path ``prompt.md`` §15 names, rather than introducing a
parallel type — one question still produces one routing decision:

======================================  =====================================
§15 path                                value
======================================  =====================================
Answer from knowledge                   ``knowledge_required``
Retrieve additional knowledge           ``additional_knowledge_required``
Call an MCP tool                        ``live_status_only``
Use both knowledge and tools            ``knowledge_and_live_status_required``
Refuse when evidence is insufficient    ``insufficient_evidence``
Refuse: nothing to search for           ``no_searchable_content``
======================================  =====================================

**The tool-only value is new, and it is now a real choice.** Stage 6 refused to
add one, arguing that a live reading needs documentation to be interpretable.
That argument holds for a question asking *why* or *what it means*; it does not
hold for "is CoreBankingAdapter healthy?", whose complete answer is the reading.
Stage 7 can tell those two question forms apart, and it guards the costly
direction of getting it wrong: a tool-only plan whose reading finds nothing
searches the documentation too, and is recorded as using both.
"""

DecisionStepName = Literal[
    "plan",
    "consult_documentation",
    "retrieve_more",
    "evidence",
]
"""The choice points an agent run can pass through, in the order they occur.

``plan`` and ``evidence`` are always recorded. ``consult_documentation`` is
recorded only for a tool-only plan, and ``retrieve_more`` only when a search ran.
"""

DecisionOutcome = Literal[
    "knowledge_required",
    "additional_knowledge_required",
    "live_status_only",
    "knowledge_and_live_status_required",
    "insufficient_evidence",
    "no_searchable_content",
    "performed",
    "not_needed",
    "no_refinement_available",
    "sufficient",
    "insufficient",
]
"""What a rule decided at one choice point.

A ``plan`` step's outcome is the planned :data:`DecisionReason`; the other steps
use the plain outcomes. One closed literal rather than one per step, so a step
is a single flat record a UI can render in a loop.
"""


class AgentDecision(BaseModel):
    """The route for one question: search, tools, or neither.

    Recorded even when the answer is a refusal, because *why* the agent did not
    search is a different diagnosis from *what* the search failed to find.

    **From Stage 7, ``AgentAnswer.decision`` is the route actually taken** — whether
    a search really ran, which tool calls were really made. The *planned* route is
    the first :class:`DecisionStep`, and the two differ exactly when the agent
    changed course: a tool-only plan that pulled in documentation, a knowledge
    plan that needed a second search, a search that found nothing.

    Renamed from ``RetrievalDecision`` in Stage 6, when it stopped being only
    about retrieval. :data:`RetrievalDecision` remains as an alias so that
    nothing written against the Stage 5 name has to change.
    """

    model_config = ConfigDict(frozen=True)

    retrieve: bool = Field(description="Whether the knowledge base was searched.")
    tools: tuple[ToolInvocation, ...] = Field(
        default=(),
        description="Tool calls the agent decided to make, in call order.",
    )
    reason: DecisionReason = Field(description="The rule that produced this decision.")
    explanation: str = Field(
        min_length=1,
        description="One sentence a human can read, safe to show in a UI or a log.",
    )

    @property
    def uses_tools(self) -> bool:
        """Whether this decision calls at least one tool."""
        return bool(self.tools)


RetrievalDecision = AgentDecision
"""Stage 5's name for :class:`AgentDecision`.

Kept as an alias rather than removed. The rename is worth making — the object
decides more than retrieval now — but breaking every existing import to record
that would be a cost paid by readers of Stage 5's tests for no benefit to them.
"""


class DecisionStep(BaseModel):
    """One choice point in an agent run, and what the rule there decided.

    The record ``prompt.md`` §15 asks for in place of chain-of-thought. Every
    field is produced by a deterministic rule in :mod:`app.agent.policy`: the step
    name, a closed outcome, and the fixed sentence for that outcome (the ``plan``
    step carries the plan's own explanation). Nothing here is written per
    question, and no step repeats an argument value.
    """

    model_config = ConfigDict(frozen=True)

    step: DecisionStepName = Field(description="Which choice point this was.")
    outcome: DecisionOutcome = Field(description="What the rule decided there.")
    explanation: str = Field(
        min_length=1, description="The fixed sentence for this outcome."
    )


class RetrievalSummary(BaseModel):
    """What the retrieval step considered and returned.

    Kept separate from the chunks themselves so a caller can show *"searched 115
    passages, none cleared 0.25"* without holding, serialising or rendering the
    document text. That distinction matters from Stage 9 onward: the summary is
    safe to display and to log; the passages are document content and are not.
    """

    model_config = ConfigDict(frozen=True)

    performed: bool = Field(description="Whether a search was actually run.")
    passes: int = Field(
        default=0,
        ge=0,
        description="Searches run: 0, 1, or 2 when a weak first pass was refined.",
    )
    candidates_considered: int = Field(
        default=0, ge=0, description="Passages the store scored before the floor."
    )
    chunks_returned: int = Field(
        default=0, ge=0, description="Passages that cleared the floor."
    )
    top_score: float | None = Field(
        default=None, description="Best cosine score, or None when nothing matched."
    )
    min_score: float | None = Field(
        default=None, description="Floor applied, or None when no search was run."
    )
    documents: tuple[str, ...] = Field(
        default=(),
        description="Distinct document ids behind the matches, best-match order.",
    )

    @classmethod
    def from_result(cls, result: RetrievalResult, passes: int = 1) -> RetrievalSummary:
        """Summarise a completed retrieval, which may merge two passes."""
        seen: dict[str, None] = {}
        for scored in result.chunks:
            seen.setdefault(scored.chunk.document_id, None)
        return cls(
            performed=True,
            passes=passes,
            candidates_considered=result.candidates_considered,
            chunks_returned=len(result.chunks),
            top_score=result.top_score,
            min_score=result.min_score,
            documents=tuple(seen),
        )

    @classmethod
    def not_performed(cls) -> RetrievalSummary:
        """Summarise a run in which the agent decided not to search."""
        return cls(performed=False)


class ToolCallSummary(BaseModel):
    """What one tool call did, without its payload.

    The tool-layer counterpart of :class:`RetrievalSummary`, and split from
    :class:`~app.mcp.models.ToolResult` on the same *security* line: shape is
    safe to log, content is not. A tool payload in this project is synthetic, but
    the same tool pointed at a real system would return account identifiers,
    balances and terminal locations, and a summary that carried them would put
    them into every log line that recorded a request.

    The full results travel on :attr:`AgentAnswer.tool_results`, which is
    returned to the caller and never logged.

    **It deliberately carries no ``reason``.** The obvious design put the
    policy's explanation here — *"The question names the transaction reference
    TXN-20260911-004473"* — which is exactly the kind of sentence a UI wants and
    exactly the wrong thing to put in an object whose whole promise is that it is
    safe to log: the explanation names the identifier the argument list was
    careful to omit. A test caught it. The reason lives on
    :attr:`AgentDecision.tools`, which is returned and displayed but never
    written to a log line.
    """

    model_config = ConfigDict(frozen=True)

    tool: str = Field(min_length=1, description="Which tool was called.")
    ok: bool = Field(description="Whether the tool found what was asked for.")
    arguments: tuple[str, ...] = Field(
        default=(),
        description="Argument NAMES supplied. Values are deliberately absent.",
    )
    error_code: str | None = Field(
        default=None, description="Stable failure code when ok is False."
    )
    fields: int = Field(
        default=0, ge=0, description="How many fields the payload carried."
    )

    @classmethod
    def from_call(
        cls, invocation: ToolInvocation, result: ToolResult
    ) -> ToolCallSummary:
        """Summarise one completed call, dropping every argument value."""
        return cls(
            tool=result.tool,
            ok=result.ok,
            arguments=tuple(sorted(invocation.arguments)),
            error_code=result.error_code,
            fields=len(result.data),
        )


class AgentAnswer(BaseModel):
    """An answer together with the complete record of how it was produced.

    A caller can tell these apart without reading the prose:

    * a **grounded answer** — :attr:`is_grounded`; a model was consulted and at
      least one retrieved passage was in front of it;
    * a **live reading** — :attr:`used_live_information` with
      ``retrieval.performed`` false; the tools answered and nothing was searched;
    * a **refusal after searching** — :attr:`refused` with
      ``retrieval.performed`` true; the corpus was searched and had nothing
      close enough;
    * a **refusal without searching** — :attr:`refused` with
      ``retrieval.performed`` false; the question had nothing to search for.

    All four are correct outcomes. :attr:`decisions` records how each was reached.
    """

    model_config = ConfigDict(frozen=True)

    question: str = Field(min_length=1, description="The question that was asked.")
    text: str = Field(min_length=1, description="The answer shown to the user.")
    sources: tuple[str, ...] = Field(
        default=(), description="Citations for the passages placed in the prompt."
    )
    decision: AgentDecision = Field(description="The route actually taken.")
    decisions: tuple[DecisionStep, ...] = Field(
        default=(),
        description="Each choice point, in order: the plan first, evidence last.",
    )
    retrieval: RetrievalSummary = Field(description="What retrieval considered.")
    tools: tuple[ToolCallSummary, ...] = Field(
        default=(),
        description="Shape of each tool call. Safe to log; carries no payload.",
    )
    tool_results: tuple[ToolResult, ...] = Field(
        default=(),
        description="Full tool results, for display. Returned, never logged.",
    )
    answer: GroundedAnswer = Field(
        description="The LLM layer's own result, unmodified, including provenance."
    )

    @property
    def refused(self) -> bool:
        """Whether the agent declined to answer for want of evidence."""
        return self.answer.refused

    @property
    def llm_called(self) -> bool:
        """Whether a model was actually consulted."""
        return self.answer.llm_called

    @property
    def is_grounded(self) -> bool:
        """Whether the answer was generated from at least one retrieved passage."""
        return self.answer.is_grounded

    @property
    def chunks_used(self) -> int:
        """Passages actually placed in the prompt."""
        return self.answer.chunks_used

    @property
    def prompt_version(self) -> str:
        """Version of the system instructions behind this answer."""
        return self.answer.prompt_version

    @property
    def tools_used(self) -> int:
        """Live tool results placed in the prompt."""
        return self.answer.tools_used

    @property
    def used_live_information(self) -> bool:
        """Whether any part of this answer came from a tool rather than a document.

        The question ``prompt.md`` §14 requires a reader to be able to answer,
        exposed as one boolean so a Stage 9 interface does not have to infer it.
        """
        return bool(self.tool_results)

    @property
    def retrieved_more(self) -> bool:
        """Whether a weak first search was refined and run a second time."""
        return self.retrieval.passes > 1
