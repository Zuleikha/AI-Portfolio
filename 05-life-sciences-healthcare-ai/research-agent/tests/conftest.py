"""Shared test setup.

- Offline tests: a clean, fake environment. They never read the real `.env`.
- `live` tests: the real NCBI settings from `.env` (free; opt-in: pytest -m live).
- `live_paid` tests: the real Anthropic settings from `.env` (COSTS MONEY;
  opt-in: pytest -m live_paid, with the user's OK before each run).

The trace log always goes to a temp folder. All env changes are undone after each test.
"""

from pathlib import Path

import pytest
from dotenv import dotenv_values

FAKE_EMAIL = "tester@example.com"
FAKE_MODEL = "claude-test-model"
FAKE_CHECK_MODEL = "claude-test-check-model"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
NCBI_SETTINGS = ("NCBI_EMAIL", "NCBI_API_KEY")
ANTHROPIC_SETTINGS = ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "ANTHROPIC_CHECK_MODEL")


def _load_real(monkeypatch: pytest.MonkeyPatch, names: tuple[str, ...]) -> None:
    if not ENV_FILE.is_file():
        pytest.fail(f"live test needs {ENV_FILE.name} with {', '.join(names)}")
    real = dotenv_values(ENV_FILE)
    for name in names:
        value = (real.get(name) or "").strip()
        if value:
            monkeypatch.setenv(name, value)
        else:
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def clean_env(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    trace_log = tmp_path / "trace.log"
    monkeypatch.setenv("RESEARCH_AGENT_TRACE_LOG", str(trace_log))

    # Offline defaults: fake values, never real credentials.
    monkeypatch.setenv("NCBI_EMAIL", FAKE_EMAIL)
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_MODEL", FAKE_MODEL)
    monkeypatch.setenv("ANTHROPIC_CHECK_MODEL", FAKE_CHECK_MODEL)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    if request.node.get_closest_marker("live"):
        _load_real(monkeypatch, NCBI_SETTINGS)
    if request.node.get_closest_marker("live_paid"):
        _load_real(monkeypatch, ANTHROPIC_SETTINGS)
    return trace_log
