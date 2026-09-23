"""The conversation service: a session, a follow-up rule, and the agent.

``ConversationService.ask`` is the whole of Stage 8's request path::

    turns(session)  →  resolve_follow_up()  →  agent.ask(resolved, history)  →  append

**One question at a time per session** (Stage 9, guide §20.29). The whole path
runs under a per-session lock, so concurrent requests on one session cannot read
the same earlier turns and record the same turn number. Sessions never wait for
each other.

**The turn is stored only after the agent answered.** A provider timeout or a
broken tool propagates exactly as it does from the agent, and leaves the session
as it was: a failed question does not become context for the next one.

**What is logged.** ``conversation.turn`` records the resolution kind, the turn
number, counts, and the agent's route -- plus a short one-way fingerprint of the
session id, so turns of one conversation can be grouped without the log holding
the handle to it. Never the question, the carried identifiers or the answer.
"""

from __future__ import annotations

import threading
import weakref

from app.agent.agent import KnowledgeAgent
from app.conversation.context import resolve_follow_up
from app.conversation.models import ConversationAnswer, ConversationTurn
from app.conversation.store import InMemorySessionStore, SessionStore
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.observability import fingerprint
from app.core.tracing import traced

logger = get_logger(__name__)


@traced
def session_fingerprint(session_id: str) -> str:
    """A short, one-way identifier for a session, safe to write to a log.

    The same fingerprint Stage 10 uses for questions (guide §20.32).
    """
    return fingerprint(session_id)


class ConversationService:
    """Answers questions within sessions, resolving follow-ups first."""

    def __init__(
        self,
        agent: KnowledgeAgent,
        store: SessionStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Wire the service to an agent and a session store.

        Args:
            agent: The single-question knowledge agent.
            store: Where sessions live. Defaults to an in-memory store built from
                the settings.
            settings: Application settings. Defaults to the cached singleton.
        """
        self._agent = agent
        self._settings = settings or get_settings()
        self._store: SessionStore = (
            store
            if store is not None
            else InMemorySessionStore.from_settings(self._settings)
        )
        self._locks: weakref.WeakValueDictionary[str, threading.Lock] = (
            weakref.WeakValueDictionary()
        )
        self._locks_guard = threading.Lock()

    @property
    def agent(self) -> KnowledgeAgent:
        """The agent answering each resolved question."""
        return self._agent

    @property
    def store(self) -> SessionStore:
        """Where this service keeps sessions."""
        return self._store

    @traced
    def start(self) -> str:
        """Start a conversation and return its session id."""
        session_id = self._store.create()
        logger.info("conversation.started", session=session_fingerprint(session_id))
        return session_id

    @traced
    def ask(self, session_id: str, question: str) -> ConversationAnswer:
        """Answer ``question`` in the context of its session.

        Args:
            session_id: An id returned by :meth:`start`.
            question: The question as asked -- possibly a follow-up.

        Returns:
            The agent's answer with the conversation record behind it.

        Raises:
            ValueError: If the question is blank.
            SessionNotFoundError: If the session is unknown, expired or evicted.
            ToolError: If a selected tool fails. The turn is not stored.
            LLMError: If the provider fails. The turn is not stored.
        """
        if not question.strip():
            raise ValueError("Cannot answer an empty question.")

        with self._session_lock(session_id):
            return self._ask_locked(session_id, question)

    def _session_lock(self, session_id: str) -> threading.Lock:
        """The lock serialising one session's questions (guide §20.29).

        Held weakly: once no request holds it, an ended or expired session's
        lock is freed rather than kept for the life of the process.
        """
        with self._locks_guard:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[session_id] = lock
            return lock

    def _ask_locked(self, session_id: str, question: str) -> ConversationAnswer:
        """Read turns, ask the agent, record the turn. Caller holds the lock."""
        earlier = self._store.turns(session_id)
        context = resolve_follow_up(question, earlier, self._settings)
        answer = self._agent.ask(context.resolved_question, history=context.history)

        number = earlier[-1].number + 1 if earlier else 1
        self._store.append(
            session_id,
            ConversationTurn(
                number=number,
                question=question,
                resolved_question=context.resolved_question,
                topic=context.topic,
                answer_text=answer.text,
                decision=answer.decision.reason,
                refused=answer.refused,
            ),
        )
        logger.info(
            "conversation.turn",
            session=session_fingerprint(session_id),
            turn=number,
            resolution=context.resolution,
            carried_identifiers=len(context.carried),
            history_questions=len(context.history),
            history_dropped=context.history_dropped,
            decision=answer.decision.reason,
            refused=answer.refused,
        )
        return ConversationAnswer(
            session_id=session_id, turn=number, context=context, answer=answer
        )

    @traced
    def turns(self, session_id: str) -> tuple[ConversationTurn, ...]:
        """The session's answered turns, oldest first."""
        return self._store.turns(session_id)

    @traced
    def end(self, session_id: str) -> None:
        """End a conversation; its id stops working."""
        self._store.delete(session_id)
        logger.info("conversation.ended", session=session_fingerprint(session_id))
