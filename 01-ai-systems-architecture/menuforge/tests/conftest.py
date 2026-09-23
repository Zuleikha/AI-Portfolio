"""Shared fixtures.

**Database:** tests need somewhere to write. If ``DATABASE_URL`` is already set
(as it is in CI, where a Postgres service runs) the suite uses it. Otherwise it
falls back to a throwaway file-backed SQLite database so the suite runs locally
with no infrastructure.

That fallback is a deliberate, known compromise — DECISIONS.md D-002 rejects
SQLite precisely because it diverges from Postgres. CI is the run that counts;
the local run is for fast feedback. Note the database must be **file**-backed:
``sqlite://`` gives every connection its own empty in-memory database, so a write
on one session is invisible to the next.
"""

from __future__ import annotations

import io
import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# The client reads this at call time. Tests never make a real API call, but the
# key must exist for the client to be constructed.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-a-real-credential")

REPO_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give every test the repo's own config and no inherited settings cache.

    Pinning the directory keeps the suite independent of the working directory
    it was launched from. Autouse because the cache is process-wide: without it,
    whichever test loaded settings first would decide them for every test after.
    """
    from menuforge.config.settings import reset_settings

    monkeypatch.setenv("MENUFORGE_CONFIG_DIR", str(REPO_CONFIG_DIR))
    reset_settings()
    yield
    reset_settings()


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the app at an empty database and create its tables."""
    from menuforge.tools import database as db

    if not os.environ.get("DATABASE_URL"):
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'menuforge.db'}")

    db.reset_engine()
    db.Base.metadata.drop_all(bind=db.get_engine())
    db.init_db()
    yield
    db.reset_engine()


@pytest.fixture
def log_capture() -> Iterator[io.StringIO]:
    """Capture log output through the real formatter and redaction filter.

    `caplog` inspects records before formatting, so it cannot prove what actually
    reaches a sink. This fixture attaches menuforge's own handler stack to a
    buffer, which is the only way to test the redaction guarantee honestly.
    """
    from menuforge.observability.logging import JsonFormatter, SecretRedactingFilter

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretRedactingFilter())
    handler.set_name("test-capture")

    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    yield buffer
    root.removeHandler(handler)
    root.setLevel(previous_level)
