"""Conversation endpoints: start a session, ask, list turns, end.

**The session id travels in the JSON body, never the URL** (guide §20.30). URLs
end up in browser history and access logs; a session id is the key to a
conversation.

**The response already says what happened.** ``rag_used``, ``mcp_used``,
``sources_consulted`` and ``insufficient`` are computed here from the agent's
execution record, so the web page displays them and never re-derives them.

**Failures never leak internals.** An unknown session is 404 with the store's
fixed, id-free message. A tool, provider or embedding failure (the last added in
Stage 13) is 502 with a fixed sentence:
exception text from those layers can hold hostnames or provider detail and is
logged by type only.

**Input is bounded before the agent runs** (Stage 13). ``session_id`` has a
static length bound and a URL-safe alphabet, enforced by the request model. The
question's upper bound is a *setting* (``BKA_QUESTION_MAX_CHARS``) and settings
are per application, so a class-level ``Field(max_length=...)`` cannot read it;
the handler checks it first and answers 422 with a fixed sentence that never
repeats the question.

Route handlers are plain ``def``: the agent is synchronous, and FastAPI runs
``def`` handlers in its threadpool so one slow answer does not block the server.
They are not ``@traced`` (Problems §2); request tracing is Stage 10.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agent.models import DecisionReason, DecisionStep, RetrievalSummary
from app.api.dependencies import ConversationDep, SettingsDep
from app.conversation.models import (
    ConversationAnswer,
    ConversationTurn,
    ResolutionKind,
)
from app.conversation.store import SessionNotFoundError
from app.core.logging import get_logger
from app.core.tracing import traced
from app.llm.base import LLMError
from app.mcp.base import ToolError
from app.mcp.models import ToolResult
from app.rag.embeddings import EmbeddingError

logger = get_logger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["conversation"])

UPSTREAM_FAILURE = (
    "The answer could not be produced because a tool or the language model "
    "failed. Nothing was recorded; try the question again."
)
"""The only text a 502 response carries."""

QUESTION_TOO_LONG = "The question is longer than the {limit}-character limit."
"""The only text a too-long-question 422 carries: the limit, never the input."""

SESSION_ID_MAX_LENGTH = 64
"""Upper bound on a session id. Real ids are
``token_urlsafe(SESSION_ID_BYTES)`` in ``app.conversation.store``: 43 characters
for 32 bytes. The rest is headroom; a test pins that the real ids fit."""

SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]+$"
"""The URL-safe base64 alphabet ``secrets.token_urlsafe`` draws from."""


# --- Request bodies ---------------------------------------------------------


class SessionRef(BaseModel):
    """A request naming one session."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(
        min_length=1,
        max_length=SESSION_ID_MAX_LENGTH,
        pattern=SESSION_ID_PATTERN,
        description="An id from POST /api/sessions.",
    )


class AskRequest(SessionRef):
    """A question asked within a session."""

    question: str = Field(min_length=1, description="The question, as typed.")

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """Reject whitespace-only questions before they reach the agent."""
        if not value.strip():
            raise ValueError("The question must not be blank.")
        return value


# --- Responses --------------------------------------------------------------


class SessionCreated(BaseModel):
    """A newly started session."""

    session_id: str = Field(description="Send this in the body of later calls.")


class TurnView(BaseModel):
    """One answered turn, for the conversation display."""

    number: int
    question: str
    resolved_question: str
    answer_text: str
    decision: DecisionReason
    refused: bool


class TurnsResponse(BaseModel):
    """A session's turns, oldest first."""

    turns: list[TurnView]


class DecisionView(BaseModel):
    """The route actually taken, without tool argument values."""

    reason: DecisionReason
    explanation: str


class AnswerResponse(BaseModel):
    """An answer and everything the page needs to show how it was produced."""

    turn: int = Field(description="Position in the session, from 1.")
    question: str = Field(description="The question as asked.")
    resolved_question: str = Field(description="What the agent actually answered.")
    resolution: ResolutionKind
    is_follow_up: bool
    carried: tuple[str, ...] = Field(description="Identifiers carried forward.")
    history_sent: int = Field(description="Earlier questions sent to the model.")
    history_dropped: int
    text: str = Field(description="The answer shown to the user.")
    sources: tuple[str, ...] = Field(description="Document citations.")
    rag_used: bool = Field(description="Whether the knowledge base was searched.")
    mcp_used: bool = Field(description="Whether any MCP tool was called.")
    sources_consulted: bool = Field(description="Whether any source is cited.")
    insufficient: bool = Field(description="Refused for want of evidence.")
    llm_called: bool
    decision: DecisionView
    steps: tuple[DecisionStep, ...]
    retrieval: RetrievalSummary
    tools: tuple[ToolResult, ...] = Field(description="Full tool results.")


@traced
def turn_view(turn: ConversationTurn) -> TurnView:
    """Project a stored turn onto its display fields."""
    return TurnView(
        number=turn.number,
        question=turn.question,
        resolved_question=turn.resolved_question,
        answer_text=turn.answer_text,
        decision=turn.decision,
        refused=turn.refused,
    )


@traced
def answer_view(result: ConversationAnswer) -> AnswerResponse:
    """Flatten a conversation answer into the page's response."""
    answer = result.answer
    context = result.context
    return AnswerResponse(
        turn=result.turn,
        question=context.question,
        resolved_question=context.resolved_question,
        resolution=context.resolution,
        is_follow_up=context.is_follow_up,
        carried=context.carried,
        history_sent=len(context.history),
        history_dropped=context.history_dropped,
        text=answer.text,
        sources=answer.sources,
        rag_used=answer.retrieval.performed,
        mcp_used=bool(answer.tool_results),
        sources_consulted=bool(answer.sources),
        insufficient=answer.refused,
        llm_called=answer.llm_called,
        decision=DecisionView(
            reason=answer.decision.reason,
            explanation=answer.decision.explanation,
        ),
        steps=answer.decisions,
        retrieval=answer.retrieval,
        tools=answer.tool_results,
    )


def _not_found(exc: SessionNotFoundError) -> HTTPException:
    """404 carrying the store's fixed message, which never repeats the id."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


# --- Routes -----------------------------------------------------------------


@router.post(
    "",
    response_model=SessionCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Start a conversation",
)
def create_session(service: ConversationDep) -> SessionCreated:
    """Start a session and return its id."""
    return SessionCreated(session_id=service.start())


@router.post("/ask", response_model=AnswerResponse, summary="Ask within a session")
def ask(
    body: AskRequest, service: ConversationDep, settings: SettingsDep
) -> AnswerResponse:
    """Answer a question in its session's context."""
    limit = settings.question_max_chars
    if len(body.question) > limit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=QUESTION_TOO_LONG.format(limit=limit),
        )
    try:
        result = service.ask(body.session_id, body.question)
    except SessionNotFoundError as exc:
        raise _not_found(exc) from exc
    except (ToolError, LLMError, EmbeddingError) as exc:
        logger.warning("api.ask_failed", error_type=type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=UPSTREAM_FAILURE
        ) from exc
    return answer_view(result)


@router.post("/turns", response_model=TurnsResponse, summary="List a session's turns")
def turns(body: SessionRef, service: ConversationDep) -> TurnsResponse:
    """Return the session's answered turns, oldest first."""
    try:
        stored = service.turns(body.session_id)
    except SessionNotFoundError as exc:
        raise _not_found(exc) from exc
    return TurnsResponse(turns=[turn_view(turn) for turn in stored])


@router.post(
    "/end",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="End a conversation",
)
def end(body: SessionRef, service: ConversationDep) -> Response:
    """End the session; its id stops working."""
    try:
        service.end(body.session_id)
    except SessionNotFoundError as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
