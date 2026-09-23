"""Stage 9: one question at a time per session (``docs/HANDOVER.md`` §9.B).

Closes Stage 8 unfinished #3: two concurrent questions on one session must not
both read the same earlier turns and record the same turn number.
"""

from __future__ import annotations

import threading
import time

import pytest

from app.agent.agent import KnowledgeAgent
from app.agent.models import AgentAnswer
from app.conversation.service import ConversationService
from app.conversation.store import InMemorySessionStore
from app.core.config import Settings
from app.llm.base import LLMTimeoutError

QUESTION = "Status of TXN-19990101-000001?"
SLOW_SECONDS = 0.2


class SlowAgent:
    """Delegates to a real agent after a pause, widening any race window."""

    def __init__(self, inner: KnowledgeAgent, blocker: threading.Event | None = None):
        self._inner = inner
        self._blocker = blocker

    def ask(self, question: str, history: tuple[str, ...] = ()) -> AgentAnswer:
        if self._blocker is not None and question.startswith("BLOCK"):
            assert self._blocker.wait(timeout=5), "test blocker never released"
        else:
            time.sleep(SLOW_SECONDS)
        return self._inner.ask(question.removeprefix("BLOCK "), history=history)


class FailOnceAgent:
    """Raises a provider timeout on the first question, then delegates."""

    def __init__(self, inner: KnowledgeAgent) -> None:
        self._inner = inner
        self._failed = False

    def ask(self, question: str, history: tuple[str, ...] = ()) -> AgentAnswer:
        if not self._failed:
            self._failed = True
            raise LLMTimeoutError("simulated timeout")
        return self._inner.ask(question, history=history)


def build(agent: object, settings: Settings) -> ConversationService:
    return ConversationService(
        agent,  # type: ignore[arg-type]
        InMemorySessionStore.from_settings(settings),
        settings,
    )


def run_concurrently(*targets) -> list[BaseException]:
    errors: list[BaseException] = []

    def wrap(target):
        def run() -> None:
            try:
                target()
            except BaseException as exc:
                errors.append(exc)

        return run

    threads = [threading.Thread(target=wrap(target)) for target in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    return errors


class TestPerSessionLock:
    def test_concurrent_questions_on_one_session_get_distinct_turns(
        self, tool_agent, llm_settings
    ):
        service = build(SlowAgent(tool_agent), llm_settings)
        session_id = service.start()
        results: list[int] = []

        def one() -> None:
            results.append(service.ask(session_id, QUESTION).turn)

        errors = run_concurrently(one, one, one)

        assert errors == []
        assert sorted(results) == [1, 2, 3]
        assert [turn.number for turn in service.turns(session_id)] == [1, 2, 3]

    def test_different_sessions_do_not_wait_for_each_other(
        self, tool_agent, llm_settings
    ):
        release = threading.Event()
        service = build(SlowAgent(tool_agent, blocker=release), llm_settings)
        blocked = service.start()
        free = service.start()
        finished: list[str] = []

        def ask_blocked() -> None:
            service.ask(blocked, f"BLOCK {QUESTION}")
            finished.append("blocked")

        def ask_free() -> None:
            service.ask(free, QUESTION)
            finished.append("free")
            release.set()

        errors = run_concurrently(ask_blocked, ask_free)

        assert errors == []
        assert finished == ["free", "blocked"]

    def test_a_failed_question_releases_the_session_lock(
        self, tool_agent, llm_settings
    ):
        service = build(FailOnceAgent(tool_agent), llm_settings)
        session_id = service.start()
        with pytest.raises(LLMTimeoutError):
            service.ask(session_id, QUESTION)

        errors = run_concurrently(lambda: service.ask(session_id, QUESTION))

        assert errors == []
        assert [turn.number for turn in service.turns(session_id)] == [1]
