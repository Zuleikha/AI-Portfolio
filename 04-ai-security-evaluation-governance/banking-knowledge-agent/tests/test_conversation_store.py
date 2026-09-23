"""Stage 8: the session store -- lifecycle, limits and concurrency.

Every limit is tested against a fake clock, so expiry is asserted exactly rather
than by sleeping. Nothing here touches the agent, a model or the disk.
"""

from __future__ import annotations

import threading

import pytest

from app.conversation.models import ConversationTurn
from app.conversation.store import (
    InMemorySessionStore,
    SessionNotFoundError,
    SessionStore,
)
from app.core.config import Settings


class FakeClock:
    """A controllable monotonic clock."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def turn(number: int, question: str = "What does LIM-4001 mean?") -> ConversationTurn:
    return ConversationTurn(
        number=number,
        question=question,
        resolved_question=question,
        topic=question,
        answer_text="An answer.",
        decision="knowledge_required",
        refused=False,
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store(clock: FakeClock) -> InMemorySessionStore:
    return InMemorySessionStore(
        max_sessions=3, ttl_seconds=60.0, max_turns=4, clock=clock
    )


class TestLifecycle:
    def test_the_store_satisfies_the_protocol(self, store: InMemorySessionStore):
        typed: SessionStore = store
        assert typed.create()

    def test_a_new_session_has_no_turns(self, store: InMemorySessionStore):
        assert store.turns(store.create()) == ()

    def test_session_ids_are_unique_and_unguessable(self):
        many = InMemorySessionStore(max_sessions=500, ttl_seconds=60, max_turns=1)
        ids = {many.create() for _ in range(200)}
        assert len(ids) == 200
        assert all(len(session_id) >= 32 for session_id in ids)

    def test_turns_are_returned_in_the_order_they_were_appended(
        self, store: InMemorySessionStore
    ):
        session = store.create()
        store.append(session, turn(1, "first"))
        store.append(session, turn(2, "second"))
        assert [t.question for t in store.turns(session)] == ["first", "second"]

    def test_sessions_are_isolated(self, store: InMemorySessionStore):
        a, b = store.create(), store.create()
        store.append(a, turn(1))
        assert store.turns(b) == ()

    def test_a_deleted_session_is_gone(self, store: InMemorySessionStore):
        session = store.create()
        store.delete(session)
        with pytest.raises(SessionNotFoundError):
            store.turns(session)

    @pytest.mark.parametrize("operation", ["turns", "append", "delete"])
    def test_an_unknown_session_raises_rather_than_starting_a_new_one(
        self, store: InMemorySessionStore, operation: str
    ):
        with pytest.raises(SessionNotFoundError):
            if operation == "append":
                store.append("no-such-session", turn(1))
            else:
                getattr(store, operation)("no-such-session")

    def test_the_error_does_not_echo_the_session_id(self, store: InMemorySessionStore):
        with pytest.raises(SessionNotFoundError) as caught:
            store.turns("secret-looking-session-id")
        assert "secret-looking-session-id" not in str(caught.value)

    def test_session_count(self, store: InMemorySessionStore):
        store.create()
        store.create()
        assert store.session_count == 2


class TestLimits:
    def test_an_idle_session_expires_after_the_ttl(
        self, store: InMemorySessionStore, clock: FakeClock
    ):
        session = store.create()
        clock.advance(61)
        with pytest.raises(SessionNotFoundError):
            store.turns(session)

    def test_a_session_exactly_at_the_ttl_is_still_alive(
        self, store: InMemorySessionStore, clock: FakeClock
    ):
        session = store.create()
        clock.advance(60)
        assert store.turns(session) == ()

    def test_activity_keeps_a_session_alive(
        self, store: InMemorySessionStore, clock: FakeClock
    ):
        session = store.create()
        clock.advance(50)
        store.append(session, turn(1))
        clock.advance(50)
        assert len(store.turns(session)) == 1

    def test_the_least_recently_used_session_is_evicted_at_capacity(
        self, store: InMemorySessionStore
    ):
        a, b, c = store.create(), store.create(), store.create()
        store.turns(a)  # a is now more recent than b
        d = store.create()
        with pytest.raises(SessionNotFoundError):
            store.turns(b)
        for alive in (a, c, d):
            store.turns(alive)

    def test_expired_sessions_are_purged_before_anything_is_evicted(
        self, store: InMemorySessionStore, clock: FakeClock
    ):
        for _ in range(3):
            store.create()
        clock.advance(61)
        store.create()
        assert store.session_count == 1

    def test_only_the_newest_turns_are_kept(self, store: InMemorySessionStore):
        session = store.create()
        for number in range(1, 7):
            store.append(session, turn(number))
        assert [t.number for t in store.turns(session)] == [3, 4, 5, 6]

    @pytest.mark.parametrize(
        "limits",
        [
            {"max_sessions": 0, "ttl_seconds": 60, "max_turns": 1},
            {"max_sessions": 1, "ttl_seconds": 0, "max_turns": 1},
            {"max_sessions": 1, "ttl_seconds": 60, "max_turns": 0},
        ],
    )
    def test_nonsensical_limits_are_refused(self, limits: dict[str, float]):
        with pytest.raises(ValueError):
            InMemorySessionStore(**limits)  # type: ignore[arg-type]

    def test_from_settings_uses_the_configured_limits(self, llm_settings: Settings):
        settings = llm_settings.model_copy(
            update={
                "conversation_max_sessions": 2,
                "conversation_ttl_seconds": 5.0,
                "conversation_max_turns": 3,
            }
        )
        store = InMemorySessionStore.from_settings(settings)
        assert (store.max_sessions, store.ttl_seconds, store.max_turns) == (2, 5.0, 3)


class TestConcurrency:
    def test_concurrent_appends_are_not_lost(self):
        store = InMemorySessionStore(max_sessions=4, ttl_seconds=60, max_turns=1000)
        session = store.create()

        def work() -> None:
            for number in range(50):
                store.append(session, turn(number + 1))

        threads = [threading.Thread(target=work) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(store.turns(session)) == 400
