"""Conversation context: follow-up questions that keep their meaning (Stage 8).

This package *wraps* the knowledge agent; the agent never imports it::

    session id + question
       │
       ▼  SessionStore.turns()          earlier turns (unknown id → error)
       ▼  resolve_follow_up()           rules: standalone / substituted /
       │                                carried identifiers / carried topic
       ▼  KnowledgeAgent.ask(resolved_question, history=earlier questions)
       │                                history only when it was used
       ▼  SessionStore.append()         only after a successful answer
       ▼
    ConversationAnswer   session · turn · context · the unchanged AgentAnswer

Two properties are the point, both recorded in ``docs/HANDOVER.md`` §8.B-§8.C:

**Only earlier questions are ever used** -- by the rules and by the model. Earlier
answers are kept for display and never read back, so nothing the model wrote and
nothing a tool returned can steer a later search or reach a later prompt.

**History is not evidence.** It has its own fence in the prompt, it is sent only
when the question needed it, and it never lets the agent answer without a passage
or a tool result.
"""

from __future__ import annotations

from app.conversation.context import find_identifiers, resolve_follow_up
from app.conversation.factory import get_conversation_service
from app.conversation.models import (
    ConversationAnswer,
    ConversationContext,
    ConversationTurn,
    ResolutionKind,
)
from app.conversation.service import ConversationService, session_fingerprint
from app.conversation.store import (
    InMemorySessionStore,
    SessionNotFoundError,
    SessionStore,
)

__all__ = [
    "ConversationAnswer",
    "ConversationContext",
    "ConversationService",
    "ConversationTurn",
    "InMemorySessionStore",
    "ResolutionKind",
    "SessionNotFoundError",
    "SessionStore",
    "find_identifiers",
    "get_conversation_service",
    "resolve_follow_up",
    "session_fingerprint",
]
