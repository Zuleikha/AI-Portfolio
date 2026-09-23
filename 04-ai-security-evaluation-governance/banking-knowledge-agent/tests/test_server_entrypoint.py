"""Stage 14.A: ``python -m app`` starts uvicorn from the application settings.

``BKA_HOST`` / ``BKA_PORT`` were validated but read by no code (12.G). The
entry point is the one place they are applied. uvicorn itself is replaced by a
recorder, so nothing binds a port.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.__main__ import APP_IMPORT_PATH, main
from app.core.config import Settings


class RecordingRunner:
    """Stands in for ``uvicorn.run`` and remembers how it was called."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, app: str, **kwargs: Any) -> None:
        self.calls.append((app, kwargs))


@pytest.fixture
def runner() -> RecordingRunner:
    return RecordingRunner()


def test_host_and_port_come_from_settings(runner):
    settings = Settings(_env_file=None, host="0.0.0.0", port=9123)
    assert main([], run=runner, settings_factory=lambda: settings) == 0
    assert runner.calls == [
        (
            APP_IMPORT_PATH,
            {"host": "0.0.0.0", "port": 9123, "access_log": True, "reload": False},
        )
    ]


def test_environment_variables_reach_uvicorn(monkeypatch, runner):
    monkeypatch.setenv("BKA_HOST", "0.0.0.0")
    monkeypatch.setenv("BKA_PORT", "9200")
    main([], run=runner, settings_factory=lambda: Settings(_env_file=None))
    _, kwargs = runner.calls[0]
    assert (kwargs["host"], kwargs["port"]) == ("0.0.0.0", 9200)


def test_defaults_bind_localhost_only(monkeypatch, runner):
    monkeypatch.delenv("BKA_HOST", raising=False)
    monkeypatch.delenv("BKA_PORT", raising=False)
    main([], run=runner, settings_factory=lambda: Settings(_env_file=None))
    _, kwargs = runner.calls[0]
    assert (kwargs["host"], kwargs["port"]) == ("127.0.0.1", 8000)


def test_access_log_can_be_disabled(runner):
    # 13.H: the container passes this flag.
    main(
        ["--no-access-log"],
        run=runner,
        settings_factory=lambda: Settings(_env_file=None),
    )
    assert runner.calls[0][1]["access_log"] is False


def test_reload_is_opt_in(runner):
    main(["--reload"], run=runner, settings_factory=lambda: Settings(_env_file=None))
    assert runner.calls[0][1]["reload"] is True


def test_an_invalid_port_fails_before_uvicorn_starts(monkeypatch, runner):
    monkeypatch.setenv("BKA_PORT", "70000")
    with pytest.raises(ValidationError):
        main([], run=runner, settings_factory=lambda: Settings(_env_file=None))
    assert runner.calls == []


def test_the_import_path_names_the_real_app():
    module_name, _, attribute = APP_IMPORT_PATH.partition(":")
    assert (module_name, attribute) == ("app.main", "app")
