"""Data contracts for conversation context (Stage 8).

::

    ConversationTurn      one answered question, as the store keeps it
    ConversationContext   how the current question was resolved, and what
                          history it sends -- the Stage 8 execution record
    ConversationAnswer    session + turn + context + the unchanged AgentAnswer

``ConversationAnswer`` wraps :class:`~app.agent.models.AgentAnswer` rather than
extending it, for the reason ``AgentAnswer`` wraps ``GroundedAnswer``: each layer
keeps its own contract, and the agent's record stays about one question.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.models import AgentAnswer, DecisionReason

ResolutionKind = Literal[
    "standalone",
    "substituted_identifier",
    "carried_identifiers",
    "carried_topic",
]
"""How a question was turned into one that stands on its own.

===========================  ===================================================
value                        meaning
===========================  ===================================================
``standalone``               used as asked; no history is sent
``substituted_identifier``   "what about X?" -- X swapped into the previous question
``carried_identifiers``      "is it healthy?" -- the previous question's
                             identifiers appended
``carried_topic``            "what should I check first on that?" -- the previous
                             topic appended
===========================  ===================================================
"""


class ConversationTurn(BaseModel):
    """One answered question in a session.

    ``answer_text`` is kept so a conversation can be displayed (Stage 9). It is
    **never read by the follow-up rules and never sent to the model** -- a test
    asserts both.
    """

    model_config = ConfigDict(frozen=True)

    number: int = Field(ge=1, description="Position in the session, from 1.")
    question: str = Field(min_length=1, description="The question as asked.")
    resolved_question: str = Field(
        min_length=1, description="The standalone question the agent answered."
    )
    topic: str = Field(
        min_length=1,
        description=(
            "The standalone question a later topic follow-up refers to. Stored so "
            "a chain of topic follow-ups never grows the query."
        ),
    )
    answer_text: str = Field(min_length=1, description="For display only.")
    decision: DecisionReason = Field(description="The route the agent took.")
    refused: bool = Field(description="Whether the agent declined to answer.")


class ConversationContext(BaseModel):
    """How the current question was resolved, and the history it carries.

    Safe to return and display. Not logged: it holds question text and carried
    identifier values; the log line records the resolution kind and counts only.
    """

    model_config = ConfigDict(frozen=True)

    question: str = Field(min_length=1, description="The question as asked.")
    resolved_question: str = Field(
        min_length=1, description="What the agent routes, searches and answers."
    )
    resolution: ResolutionKind = Field(description="Which rule resolved it.")
    carried: tuple[str, ...] = Field(
        default=(), description="Identifiers carried from the previous question."
    )
    topic: str = Field(min_length=1, description="The topic this turn stores.")
    history: tuple[str, ...] = Field(
        default=(),
        description="Earlier questions sent to the model, oldest first.",
    )
    history_dropped: int = Field(
        default=0,
        ge=0,
        description="Earlier questions in the window left out by the character budget.",
    )

    @property
    def is_follow_up(self) -> bool:
        """Whether earlier turns were used to understand this question."""
        return self.resolution != "standalone"


class ConversationAnswer(BaseModel):
    """An agent answer together with the conversation record behind it."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(min_length=1, description="The session answered in.")
    turn: int = Field(ge=1, description="This question's position in the session.")
    context: ConversationContext = Field(description="How the question was resolved.")
    answer: AgentAnswer = Field(description="The agent's answer, unmodified.")

    @property
    def text(self) -> str:
        """The answer shown to the user."""
        return self.answer.text
