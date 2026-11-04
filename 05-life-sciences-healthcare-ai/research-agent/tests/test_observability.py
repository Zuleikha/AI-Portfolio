"""Stage 3 tests for the @traced decorator. Spec: docs/PRD.md, "Supporting piece"."""

from pathlib import Path

import pytest

from research_agent.observability import traced


def test_traced_logs_name_and_duration_to_file(clean_env: Path) -> None:
    @traced
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5
    log = clean_env.read_text()
    assert "add" in log
    assert "ms" in log  # duration is recorded


def test_traced_never_logs_arguments_or_results(clean_env: Path) -> None:
    @traced
    def echo(secret: str) -> str:
        return secret

    echo("TOP-SECRET-VALUE")
    assert "TOP-SECRET-VALUE" not in clean_env.read_text()


def test_traced_logs_and_reraises_errors(clean_env: Path) -> None:
    @traced
    def boom() -> None:
        raise RuntimeError("bad thing")

    with pytest.raises(RuntimeError):
        boom()
    log = clean_env.read_text()
    assert "boom" in log
    assert "RuntimeError" in log


def test_traced_keeps_function_name() -> None:
    @traced
    def named() -> None:
        return None

    assert named.__name__ == "named"


def test_traced_creates_missing_log_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    log_path = tmp_path / "runs" / "trace.log"
    assert not log_path.parent.exists()
    monkeypatch.setenv("RESEARCH_AGENT_TRACE_LOG", str(log_path))

    @traced
    def hello() -> str:
        return "hi"

    assert hello() == "hi"
    assert "hello" in log_path.read_text()
