"""Where a conversation lives between questions: a bounded session store.

A protocol plus one in-memory implementation (guide §20.26). Everything runs
locally and a conversation is short-lived working state, so a database would be
infrastructure without a requirement; :class:`SessionStore` is the seam where one
would go.

**Every limit exists so memory cannot grow without end:** idle sessions expire,
the least recently used session is evicted at capacity, and each session keeps
only its newest turns.

**An unknown session is an error, never a new session.** Silently starting fresh
would make a follow-up lose its context and be answered as a different question
while looking entirely normal.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.conversation.models import ConversationTurn
from app.core.config import Settings, get_settings
from app.core.tracing import traced

SESSION_ID_BYTES = 32
"""Random bytes behind a session id -- 43 URL-safe characters, unguessable."""


class SessionNotFoundError(LookupError):
    """The session id is unknown, expired or evicted.

    The message never repeats the id: from Stage 9 a session id is a handle to a
    conversation, and error messages end up in responses and logs.
    """

    def __init__(self) -> None:
        """Build the fixed, id-free message."""
        super().__init__(
            "No active conversation session has that id. It may never have "
            "existed, may have expired while idle, or may have been evicted. "
            "Start a new session."
        )


class SessionStore(Protocol):
    """Anything that can hold conversation turns by session id."""

    def create(self) -> str:
        """Start a session and return its id."""
        ...

    def turns(self, session_id: str) -> tuple[ConversationTurn, ...]:
        """The session's turns, oldest first. Raises if the session is gone."""
        ...

    def append(self, session_id: str, turn: ConversationTurn) -> None:
        """Record an answered turn. Raises if the session is gone."""
        ...

    def delete(self, session_id: str) -> None:
        """End a session. Raises if the session is gone."""
        ...


@dataclass
class _Session:
    """One session's turns and when it was last used."""

    turns: deque[ConversationTurn]
    last_used: float


class InMemorySessionStore:
    """A thread-safe, bounded, in-process :class:`SessionStore`."""

    def __init__(
        self,
        max_sessions: int,
        ttl_seconds: float,
        max_turns: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Build a store with explicit limits.

        Args:
            max_sessions: Sessions kept at once; the least recently used goes.
            ttl_seconds: Idle time after which a session expires.
            max_turns: Turns kept per session; the oldest go.
            clock: Monotonic seconds. Injectable so tests control time.

        Raises:
            ValueError: If any limit is not positive.
        """
        if max_sessions < 1 or ttl_seconds <= 0 or max_turns < 1:
            raise ValueError(
                "Session store limits must be positive: "
                f"max_sessions={max_sessions}, ttl_seconds={ttl_seconds}, "
                f"max_turns={max_turns}."
            )
        self._max_sessions = max_sessions
        self._ttl_seconds = ttl_seconds
        self._max_turns = max_turns
        self._clock = clock
        self._sessions: OrderedDict[str, _Session] = OrderedDict()
        self._lock = threading.Lock()

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> InMemorySessionStore:
        """Build a store from the ``BKA_CONVERSATION_*`` settings."""
        resolved = settings or get_settings()
        return cls(
            max_sessions=resolved.conversation_max_sessions,
            ttl_seconds=resolved.conversation_ttl_seconds,
            max_turns=resolved.conversation_max_turns,
            clock=clock,
        )

    @property
    def max_sessions(self) -> int:
        """Sessions kept at once."""
        return self._max_sessions

    @property
    def ttl_seconds(self) -> float:
        """Idle seconds before a session expires."""
        return self._ttl_seconds

    @property
    def max_turns(self) -> int:
        """Turns kept per session."""
        return self._max_turns

    @property
    def session_count(self) -> int:
        """Live sessions, after expired ones are purged."""
        with self._lock:
            self._purge(self._clock())
            return len(self._sessions)

    @traced
    def create(self) -> str:
        """Start a session, evicting the least recently used one if full."""
        with self._lock:
            now = self._clock()
            self._purge(now)
            while len(self._sessions) >= self._max_sessions:
                self._sessions.popitem(last=False)
            session_id = secrets.token_urlsafe(SESSION_ID_BYTES)
            self._sessions[session_id] = _Session(
                turns=deque(maxlen=self._max_turns), last_used=now
            )
            return session_id

    @traced
    def turns(self, session_id: str) -> tuple[ConversationTurn, ...]:
        """The session's turns, oldest first."""
        with self._lock:
            return tuple(self._live(session_id).turns)

    @traced
    def append(self, session_id: str, turn: ConversationTurn) -> None:
        """Record a turn; the oldest is dropped beyond ``max_turns``."""
        with self._lock:
            self._live(session_id).turns.append(turn)

    @traced
    def delete(self, session_id: str) -> None:
        """End a session."""
        with self._lock:
            self._live(session_id)
            del self._sessions[session_id]

    def _live(self, session_id: str) -> _Session:
        """The session, refreshed as most recently used. Caller holds the lock."""
        now = self._clock()
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError
        if now - session.last_used > self._ttl_seconds:
            del self._sessions[session_id]
            raise SessionNotFoundError
        session.last_used = now
        self._sessions.move_to_end(session_id)
        return session

    def _purge(self, now: float) -> None:
        """Drop every expired session. Caller holds the lock."""
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.last_used > self._ttl_seconds
        ]
        for session_id in expired:
            del self._sessions[session_id]
