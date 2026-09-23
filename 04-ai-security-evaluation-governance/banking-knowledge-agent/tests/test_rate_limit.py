"""Stage 13: the per-client, fixed-window rate limit (guide §20.51).

Unit tests drive :class:`FixedWindowRateLimiter` with a fake clock, so no test
sleeps. API tests build a real app around a stub conversation service that
never loads the embedding model or the index. Offline and free.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.rate_limit import (
    RATE_LIMITED,
    WINDOW_SECONDS,
    FixedWindowRateLimiter,
)
from app.api.security import API_KEY_HEADER, AUTH_REQUIRED
from app.conversation.models import ConversationTurn
from app.conversation.service import ConversationService
from app.conversation.store import SessionNotFoundError
from app.core.config import Settings
from app.core.logging import APP_LOG_FILENAME, reset_logging
from app.core.observability import (
    RATE_LIMITED_TOTAL,
    fingerprint,
    get_metrics,
    reset_metrics,
)
from app.main import create_app

TEST_CLIENT_HOST = "testclient"
"""The client address Starlette's TestClient reports."""

# --- Helpers ----------------------------------------------------------------


class FakeClock:
    """A monotonic clock the test moves by hand."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class StubService(ConversationService):
    """Starts sessions without an agent, a model or an index."""

    def __init__(self) -> None:  # deliberately no super().__init__()
        self.started = 0

    def start(self) -> str:
        self.started += 1
        return f"session-{self.started}"

    def turns(self, session_id: str) -> tuple[ConversationTurn, ...]:
        raise SessionNotFoundError

    def end(self, session_id: str) -> None:
        raise SessionNotFoundError


def records(path: Path, event: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    parsed = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    return [r for r in parsed if r["event"] == event]


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "log_dir": tmp_path / "logs",
        "log_to_file": True,
        "log_format": "json",
        "rate_limit_per_minute": 2,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(autouse=True)
def fresh_state() -> Iterator[None]:
    reset_metrics()
    reset_logging()
    yield
    reset_logging()
    reset_metrics()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def limiter(clock: FakeClock) -> FixedWindowRateLimiter:
    return FixedWindowRateLimiter(3, window_seconds=60.0, clock=clock)


# --- Unit: the limiter ------------------------------------------------------


class TestFixedWindowRateLimiter:
    def test_default_window_is_one_minute(self) -> None:
        assert WINDOW_SECONDS == 60.0
        assert FixedWindowRateLimiter(1).window_seconds == WINDOW_SECONDS

    def test_allows_up_to_the_limit(self, limiter: FixedWindowRateLimiter) -> None:
        assert [limiter.check("a") for _ in range(3)] == [None, None, None]

    def test_blocks_the_request_after_the_limit(
        self, limiter: FixedWindowRateLimiter
    ) -> None:
        for _ in range(3):
            limiter.check("a")
        wait = limiter.check("a")
        assert wait is not None
        assert wait > 0

    def test_wait_is_the_time_left_in_the_window(
        self, limiter: FixedWindowRateLimiter, clock: FakeClock
    ) -> None:
        limiter.check("a")  # window opens here
        clock.advance(15.5)
        limiter.check("a")
        limiter.check("a")
        assert limiter.check("a") == pytest.approx(44.5)

    def test_blocked_requests_keep_being_blocked(
        self, limiter: FixedWindowRateLimiter, clock: FakeClock
    ) -> None:
        for _ in range(4):
            limiter.check("a")
        clock.advance(30)
        assert limiter.check("a") == pytest.approx(30.0)

    def test_the_limit_resets_when_the_window_ends(
        self, limiter: FixedWindowRateLimiter, clock: FakeClock
    ) -> None:
        for _ in range(4):
            limiter.check("a")
        clock.advance(60)
        assert [limiter.check("a") for _ in range(3)] == [None, None, None]
        assert limiter.check("a") is not None

    def test_clients_are_counted_independently(
        self, limiter: FixedWindowRateLimiter
    ) -> None:
        for _ in range(3):
            limiter.check("a")
        assert limiter.check("a") is not None
        assert limiter.check("b") is None

    def test_expired_clients_are_pruned(
        self, limiter: FixedWindowRateLimiter, clock: FakeClock
    ) -> None:
        for n in range(50):
            limiter.check(f"client-{n}")
        assert limiter.tracked_clients == 50
        clock.advance(61)
        limiter.check("newcomer")
        assert limiter.tracked_clients == 1

    def test_live_clients_survive_pruning(
        self, limiter: FixedWindowRateLimiter, clock: FakeClock
    ) -> None:
        limiter.check("old")
        clock.advance(30)
        for _ in range(3):
            limiter.check("live")
        clock.advance(31)  # "old" expired, "live" has 29 s left
        limiter.check("newcomer")
        assert limiter.tracked_clients == 2
        assert limiter.check("live") == pytest.approx(29.0)

    @pytest.mark.parametrize("limit", [0, -1])
    def test_rejects_a_limit_below_one(self, limit: int) -> None:
        with pytest.raises(ValueError, match="limit"):
            FixedWindowRateLimiter(limit)

    @pytest.mark.parametrize("window", [0.0, -5.0])
    def test_rejects_a_non_positive_window(self, window: float) -> None:
        with pytest.raises(ValueError, match="window"):
            FixedWindowRateLimiter(1, window_seconds=window)

    def test_concurrent_requests_never_exceed_the_limit(self) -> None:
        limiter = FixedWindowRateLimiter(100, clock=FakeClock())
        allowed = 0
        allowed_lock = threading.Lock()
        barrier = threading.Barrier(8)

        def worker() -> None:
            nonlocal allowed
            barrier.wait()
            for _ in range(50):
                if limiter.check("shared") is None:
                    with allowed_lock:
                        allowed += 1

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert allowed == 100


# --- API: the dependency on a real app ----------------------------------------


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings, conversation_service=StubService())) as c:
        yield c


class TestRateLimitedApi:
    def test_the_request_after_the_limit_gets_429(self, api: TestClient) -> None:
        assert api.post("/api/sessions").status_code == 201
        assert api.post("/api/sessions").status_code == 201
        response = api.post("/api/sessions")
        assert response.status_code == 429
        assert response.json() == {"detail": RATE_LIMITED}

    def test_retry_after_is_a_whole_number_of_seconds(self, api: TestClient) -> None:
        for _ in range(2):
            api.post("/api/sessions")
        retry_after = api.post("/api/sessions").headers["Retry-After"]
        assert retry_after.isdigit()
        assert 1 <= int(retry_after) <= 60

    def test_limit_applies_across_conversation_routes(self, api: TestClient) -> None:
        assert api.post("/api/sessions").status_code == 201
        turns = api.post("/api/sessions/turns", json={"session_id": "x"})
        assert turns.status_code == 404
        response = api.post("/api/sessions/end", json={"session_id": "x"})
        assert response.status_code == 429

    def test_each_429_is_counted(self, api: TestClient) -> None:
        for _ in range(4):
            api.post("/api/sessions")
        counters = get_metrics().snapshot()["counters"]
        assert counters[RATE_LIMITED_TOTAL] == 2

    def test_the_log_carries_a_fingerprint_never_the_address(
        self, api: TestClient, settings: Settings
    ) -> None:
        for _ in range(3):
            api.post("/api/sessions")
        app_log = settings.log_dir / APP_LOG_FILENAME
        [event] = records(app_log, "api.rate_limited")
        assert event["client"] == fingerprint(TEST_CLIENT_HOST)
        assert TEST_CLIENT_HOST not in app_log.read_text("utf-8")

    def test_health_is_never_limited(self, api: TestClient) -> None:
        for _ in range(10):
            assert api.get("/health").status_code == 200

    def test_zero_turns_the_limit_off(self, tmp_path: Path) -> None:
        app = create_app(
            make_settings(tmp_path, rate_limit_per_minute=0),
            conversation_service=StubService(),
        )
        assert app.state.rate_limiter is None
        with TestClient(app) as client:
            for _ in range(10):
                assert client.post("/api/sessions").status_code == 201
        assert RATE_LIMITED_TOTAL not in get_metrics().snapshot()["counters"]

    def test_each_app_has_its_own_limiter(self, settings: Settings) -> None:
        first = create_app(settings, conversation_service=StubService())
        second = create_app(settings, conversation_service=StubService())
        assert isinstance(first.state.rate_limiter, FixedWindowRateLimiter)
        assert first.state.rate_limiter is not second.state.rate_limiter

    def test_the_limit_is_checked_before_the_api_key(self, tmp_path: Path) -> None:
        # Depends on unit U1's key check: with a wrong key, the requests
        # within the limit get 401, and the one beyond it gets 429, so
        # wrong-key guessing is capped too.
        app = create_app(
            make_settings(tmp_path, api_key="right-key"),
            conversation_service=StubService(),
        )
        with TestClient(app) as client:
            wrong = {API_KEY_HEADER: "wrong-key"}
            first = client.post("/api/sessions", headers=wrong)
            second = client.post("/api/sessions", headers=wrong)
            third = client.post("/api/sessions", headers=wrong)
        assert first.status_code == 401
        assert first.json() == {"detail": AUTH_REQUIRED}
        assert second.status_code == 401
        assert third.status_code == 429
        assert third.json() == {"detail": RATE_LIMITED}
