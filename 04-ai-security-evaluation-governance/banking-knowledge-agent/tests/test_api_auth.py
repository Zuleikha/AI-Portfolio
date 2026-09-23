"""Stage 13: the optional shared API key (guide §20.50).

Pins ``docs/stage13-contract.md`` §2: with a key configured, ``/api`` and
``/metrics`` answer 401 unless the ``X-API-Key`` header matches; ``/health`` and
the static page stay open; a missing and a wrong key look identical; the key
never reaches a log. No model is loaded -- a fake conversation service is
injected. The rate limit is switched off so it cannot interfere.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.security import API_KEY_HEADER, AUTH_REQUIRED
from app.core.config import PROJECT_ROOT, Settings
from app.core.logging import APP_LOG_FILENAME, reset_logging
from app.core.observability import AUTH_FAILURES_TOTAL, get_metrics, reset_metrics
from app.main import create_app

KEY = "stage13-test-key-7f3a9c"
WRONG = "stage13-wrong-key-000000"
SESSION_ID = "s" * 43
STATIC_DIR = PROJECT_ROOT / "app" / "web" / "static"

# --- Helpers ----------------------------------------------------------------


class FakeService:
    """Just enough of a conversation service to start a session."""

    def start(self) -> str:
        return SESSION_ID


def build_settings(tmp_path: Path, api_key: str | None) -> Settings:
    return Settings(
        environment="test",
        log_dir=tmp_path / "logs",
        log_to_file=True,
        log_format="json",
        rate_limit_per_minute=0,
        api_key=SecretStr(api_key) if api_key is not None else None,
    )


def make_client(settings: Settings) -> TestClient:
    service: Any = FakeService()
    app = create_app(settings, conversation_service=service)
    assert isinstance(app.state.conversation, FakeService)
    return TestClient(app)


def auth_failures() -> int:
    counters: dict[str, int] = get_metrics().snapshot()["counters"]
    return counters.get(AUTH_FAILURES_TOTAL, 0)


def log_records(path: Path, event: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    parsed = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    return [r for r in parsed if r["event"] == event]


@pytest.fixture(autouse=True)
def fresh_state() -> Iterator[None]:
    reset_logging()
    reset_metrics()
    yield
    reset_metrics()
    reset_logging()


@pytest.fixture
def keyed_settings(tmp_path: Path) -> Settings:
    return build_settings(tmp_path, KEY)


@pytest.fixture
def keyed(keyed_settings: Settings) -> Iterator[TestClient]:
    with make_client(keyed_settings) as client:
        yield client


@pytest.fixture
def app_log(keyed_settings: Settings) -> Path:
    return keyed_settings.log_dir / APP_LOG_FILENAME


# --- No key configured --------------------------------------------------------


class TestNoKeyConfigured:
    def test_the_api_is_open(self, tmp_path):
        with make_client(build_settings(tmp_path, None)) as client:
            response = client.post("/api/sessions")
        assert response.status_code == 201
        assert response.json() == {"session_id": SESSION_ID}

    def test_metrics_are_open(self, tmp_path):
        with make_client(build_settings(tmp_path, None)) as client:
            assert client.get("/metrics").status_code == 200

    def test_a_stray_header_is_ignored(self, tmp_path):
        with make_client(build_settings(tmp_path, None)) as client:
            response = client.post("/api/sessions", headers={API_KEY_HEADER: WRONG})
        assert response.status_code == 201
        assert auth_failures() == 0


# --- Key configured -----------------------------------------------------------


class TestKeyConfigured:
    def test_a_missing_key_is_401(self, keyed):
        response = keyed.post("/api/sessions")
        assert response.status_code == 401
        assert response.json() == {"detail": AUTH_REQUIRED}

    def test_a_wrong_key_is_401(self, keyed):
        response = keyed.post("/api/sessions", headers={API_KEY_HEADER: WRONG})
        assert response.status_code == 401
        assert response.json() == {"detail": AUTH_REQUIRED}

    @pytest.mark.parametrize("bad", ["", " ", KEY + "x", KEY[:-1], KEY.upper()])
    def test_near_misses_are_401(self, keyed, bad):
        response = keyed.post("/api/sessions", headers={API_KEY_HEADER: bad})
        assert response.status_code == 401

    def test_missing_and_wrong_look_identical(self, keyed):
        missing = keyed.post("/api/sessions")
        wrong = keyed.post("/api/sessions", headers={API_KEY_HEADER: WRONG})
        assert missing.content == wrong.content
        assert missing.headers["www-authenticate"] == wrong.headers["www-authenticate"]

    def test_a_401_names_the_scheme(self, keyed):
        response = keyed.post("/api/sessions")
        assert response.headers["www-authenticate"] == "ApiKey"

    def test_the_right_key_passes(self, keyed):
        response = keyed.post("/api/sessions", headers={API_KEY_HEADER: KEY})
        assert response.status_code == 201
        assert response.json() == {"session_id": SESSION_ID}

    @pytest.mark.parametrize(
        "path", ["/api/sessions/ask", "/api/sessions/turns", "/api/sessions/end"]
    )
    def test_every_conversation_route_is_protected(self, keyed, path):
        response = keyed.post(path, json={"session_id": SESSION_ID, "question": "hi"})
        assert response.status_code == 401

    def test_auth_runs_before_body_validation(self, keyed):
        # A keyless caller learns nothing about the request shape.
        response = keyed.post("/api/sessions/ask", json={"nonsense": True})
        assert response.status_code == 401

    def test_metrics_need_the_key(self, keyed):
        assert keyed.get("/metrics").status_code == 401
        allowed = keyed.get("/metrics", headers={API_KEY_HEADER: KEY})
        assert allowed.status_code == 200

    def test_health_stays_open(self, keyed):
        response = keyed.get("/health")
        assert response.status_code == 200

    @pytest.mark.parametrize("path", ["/", "/app.js", "/styles.css"])
    def test_the_web_page_stays_open(self, keyed, path):
        # The page must load so the user can type the key into it.
        assert keyed.get(path).status_code == 200


# --- Observability ------------------------------------------------------------


class TestAuthObservability:
    def test_each_rejection_is_counted(self, keyed):
        keyed.post("/api/sessions")
        keyed.post("/api/sessions", headers={API_KEY_HEADER: WRONG})
        keyed.get("/metrics")
        assert auth_failures() == 3

    def test_a_success_is_not_counted(self, keyed):
        keyed.post("/api/sessions", headers={API_KEY_HEADER: KEY})
        assert auth_failures() == 0

    def test_a_rejection_is_logged_with_a_reason_only(self, keyed, app_log):
        keyed.post("/api/sessions")
        keyed.post("/api/sessions", headers={API_KEY_HEADER: WRONG})
        rejected = log_records(app_log, "api.auth_rejected")
        assert [r["reason"] for r in rejected] == ["missing", "invalid"]

    def test_no_key_value_reaches_the_log(self, keyed, app_log):
        keyed.post("/api/sessions", headers={API_KEY_HEADER: WRONG})
        keyed.post("/api/sessions", headers={API_KEY_HEADER: KEY})
        keyed.get("/metrics", headers={API_KEY_HEADER: KEY})
        text = app_log.read_text("utf-8")
        assert "api.auth_rejected" in text
        assert KEY not in text
        assert WRONG not in text


# --- The web page -------------------------------------------------------------


class TestWebPageKey:
    def test_the_script_sends_the_key_header(self):
        script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        assert API_KEY_HEADER in script
        assert "sessionStorage" in script

    def test_the_script_never_logs(self):
        script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        assert "console." not in script

    def test_the_page_has_a_labelled_password_box(self):
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        assert 'id="api-key"' in html
        assert 'type="password"' in html
        assert 'for="api-key"' in html
