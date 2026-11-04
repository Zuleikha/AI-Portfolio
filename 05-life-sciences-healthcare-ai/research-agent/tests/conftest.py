"""Shared test setup.

- Offline tests: a clean, fake environment. They never read the real `.env`.
- `live` tests: the real NCBI settings from the project's `.env` (opt-in: pytest -m live).

The trace log always goes to a temp folder. All env changes are undone after each test.
"""

from pathlib import Path

import pytest
from dotenv import dotenv_values

FAKE_EMAIL = "tester@example.com"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
NCBI_SETTINGS = ("NCBI_EMAIL", "NCBI_API_KEY")


@pytest.fixture(autouse=True)
def clean_env(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    trace_log = tmp_path / "trace.log"
    monkeypatch.setenv("RESEARCH_AGENT_TRACE_LOG", str(trace_log))

    if request.node.get_closest_marker("live"):
        if not ENV_FILE.is_file():
            pytest.fail(f"live test needs {ENV_FILE.name} with NCBI_EMAIL")
        real = dotenv_values(ENV_FILE)
        for name in NCBI_SETTINGS:
            value = (real.get(name) or "").strip()
            if value:
                monkeypatch.setenv(name, value)
            else:
                monkeypatch.delenv(name, raising=False)
        return trace_log

    monkeypatch.setenv("NCBI_EMAIL", FAKE_EMAIL)
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    return trace_log
