"""Tests for Stage 7: tracing (docs/PRD.md, "Stage 7", rules T1 to T11).

Offline: no tracing service, no cost. The LangSmith tracer is replaced by ``FakeTracer``
(a ``LangChainTracer`` that records runs instead of sending them) and the flush by a fake.
Test seams: ``research_agent.tracing.LangChainTracer`` and
``research_agent.tracing.wait_for_all_tracers`` (the names the module imports).
The opt-in ``live_paid`` test at the end sends a real trace (user OK each run, free plan, T7).
"""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tracers.langchain import LangChainTracer
from langchain_core.tracers.schemas import Run
from langsmith import Client
from langsmith import utils as ls_utils

from research_agent import tracing
from research_agent.graph import RunOutcome, run
from research_agent.tracing import TracingConfigError, redact, tracing_config, tracing_scope
from tests import test_citation_check as cc
from tests import test_summarise as su
from tests.conftest import refresh_langsmith_env
from tests.test_graph import (
    ABSTRACT_111,
    BAD_CLAIM,
    GOOD_CLAIM,
    QUERY,
    fake_ncbi,
    main_with,
    only_record,
    two_claims,
    two_verdicts,
)
from tests.test_pubmed import FakeNCBI

FAKE_LS_KEY = "ls-fake-key-123"
FAKE_PROJECT = "test-project"
DEAD_ENDPOINT = "http://127.0.0.1:9"  # refused at once: nothing can leave the machine
TRACE_OFF = {"enabled": False, "backend": None, "project": None}


# ---------------------------------------------------------------- fakes


class FakeTracer(LangChainTracer):
    """Records each run it would send. Never posts anything."""

    instances: list[FakeTracer] = []

    def __init__(self, project_name: str | None = None, **kwargs: Any) -> None:
        self.given_client: Client | None = kwargs.pop("client", None)  # checked by T13 test
        super().__init__(
            project_name=project_name,
            client=Client(api_url=DEAD_ENDPOINT, api_key=FAKE_LS_KEY),
            **kwargs,
        )
        self.sent: list[Run] = []
        FakeTracer.instances.append(self)

    def _persist_run_single(self, run: Run) -> None:
        self.sent.append(run)

    def _update_run_single(self, run: Run) -> None:  # type: ignore[override]
        pass


@pytest.fixture
def fake_tracer(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[FakeTracer]]:
    """Tracing set up as for ``--trace``, but with ``FakeTracer`` and a no-op flush."""
    monkeypatch.setenv("LANGSMITH_API_KEY", FAKE_LS_KEY)
    monkeypatch.setenv("LANGSMITH_PROJECT", FAKE_PROJECT)
    monkeypatch.setenv("LANGSMITH_ENDPOINT", DEAD_ENDPOINT)
    refresh_langsmith_env()
    FakeTracer.instances = []
    monkeypatch.setattr(tracing, "LangChainTracer", FakeTracer)
    monkeypatch.setattr(tracing, "wait_for_all_tracers", lambda: None)
    yield FakeTracer.instances


def spy(inner: Runnable[Any, Any], seen: list[bool]) -> Runnable[Any, Any]:
    """Wrap a fake model: record whether tracing is on at the moment it is called."""

    def call(messages: list[BaseMessage]) -> Any:
        seen.append(bool(ls_utils.tracing_is_enabled()))
        return inner.invoke(messages)

    return RunnableLambda(call)


def go(tmp_path: Path, *, trace: bool = False, seen: list[bool] | None = None) -> RunOutcome:
    seen = [] if seen is None else seen
    return run(
        QUERY,
        runs_dir=tmp_path / "runs",
        client=fake_ncbi().client(),
        summarise_llm=spy(two_claims().runnable(), seen),
        check_llm=spy(two_verdicts().runnable(), seen),
        trace=trace,
    )


# ---------------------------------------------------------------- off by default (T1)


def test_off_by_default(tmp_path: Path) -> None:  # T1
    config = tracing_config("RID", enabled=False)
    assert not any(isinstance(h, LangChainTracer) for h in config.get("callbacks") or [])
    assert "run_id" not in (config.get("metadata") or {})

    seen: list[bool] = []
    go(tmp_path, seen=seen)
    assert seen and not any(seen)  # every model call ran with tracing off


def test_env_cannot_switch_it_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # T1
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", FAKE_LS_KEY)
    monkeypatch.setenv("LANGSMITH_ENDPOINT", DEAD_ENDPOINT)
    refresh_langsmith_env()
    assert ls_utils.tracing_is_enabled()  # the env really does ask for tracing

    seen: list[bool] = []
    go(tmp_path, seen=seen)
    assert seen and not any(seen)
    assert only_record(tmp_path)["trace"] == TRACE_OFF


def test_scope_flushes_on_exit(monkeypatch: pytest.MonkeyPatch) -> None:  # T8
    flushes: list[int] = []
    monkeypatch.setattr(tracing, "wait_for_all_tracers", lambda: flushes.append(1))

    with tracing_scope(enabled=True):
        assert ls_utils.tracing_is_enabled()
    assert flushes == [1]

    with pytest.raises(ValueError, match="boom"), tracing_scope(enabled=True):
        raise ValueError("boom")
    assert flushes == [1, 1]


# ---------------------------------------------------------------- entry point (G1, T2)


def test_trace_without_yes_runs_nothing(tmp_path: Path) -> None:  # G1
    ncbi, summ, check = fake_ncbi(), two_claims(), two_verdicts()
    assert main_with(tmp_path, ncbi, summ, check, "--trace") == 2
    assert ncbi.requests == []
    assert summ.calls == []
    assert check.calls == []
    assert not (tmp_path / "runs").exists()


def test_trace_without_key_fails_before_any_call(tmp_path: Path) -> None:  # T2
    ncbi: FakeNCBI = fake_ncbi()
    summ: su.FakeLLM = two_claims()
    check: cc.FakeLLM = two_verdicts()
    with pytest.raises(TracingConfigError):
        main_with(tmp_path, ncbi, summ, check, "--yes", "--trace")
    assert ncbi.requests == []
    assert summ.calls == []
    assert check.calls == []
    assert not (tmp_path / "runs").exists()


# ---------------------------------------------------------------- link to the record (T3)


def test_run_id_in_trace_config(fake_tracer: list[FakeTracer]) -> None:  # T3
    config = tracing_config("RID", enabled=True)
    assert config["metadata"]["run_id"] == "RID"
    assert config["run_name"] == "research-agent"
    assert config["tags"] == ["research-agent", "stage-7"]
    tracers = [h for h in config.get("callbacks") or [] if isinstance(h, LangChainTracer)]
    assert len(tracers) == 1
    assert tracers[0].project_name == FAKE_PROJECT


def test_record_says_trace_off(tmp_path: Path) -> None:  # T3
    go(tmp_path)
    assert only_record(tmp_path)["trace"] == TRACE_OFF


def test_record_says_trace_on(tmp_path: Path, fake_tracer: list[FakeTracer]) -> None:  # T3, T4
    seen: list[bool] = []
    go(tmp_path, trace=True, seen=seen)
    record = only_record(tmp_path)
    assert record["trace"] == {"enabled": True, "backend": "langsmith", "project": FAKE_PROJECT}
    assert seen and all(seen)  # both model steps ran with tracing on

    assert len(fake_tracer) == 1
    tracer = fake_tracer[0]
    tracer.wait_for_futures()
    root = [r for r in tracer.sent if r.parent_run_id is None]
    assert len(root) == 1
    assert root[0].name == "research-agent"
    assert root[0].extra["metadata"]["run_id"] == record["run_id"]
    names = {r.name for r in tracer.sent}
    assert {"search", "summarise", "check"} <= names  # the graph steps (T4)


def test_default_project(
    tmp_path: Path, fake_tracer: list[FakeTracer], monkeypatch: pytest.MonkeyPatch
) -> None:  # T12
    monkeypatch.delenv("LANGSMITH_PROJECT")
    refresh_langsmith_env()
    go(tmp_path, trace=True)
    assert only_record(tmp_path)["trace"]["project"] == "research-agent"
    assert [t.project_name for t in fake_tracer] == ["research-agent"]


# ---------------------------------------------------------------- secrets (T5, T9)


def test_redact_strips_secrets(monkeypatch: pytest.MonkeyPatch) -> None:  # T5
    secrets = {
        "ANTHROPIC_API_KEY": "sk-ant-fake-999",
        "NCBI_API_KEY": "ncbi-fake-777",
        "NCBI_EMAIL": "secret.person@example.org",
        "LANGSMITH_API_KEY": FAKE_LS_KEY,
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)
    data = {
        "url": "https://eutils.ncbi.nlm.nih.gov/efetch.fcgi?db=pubmed&api_key=URLSECRET1&id=111",
        "messages": [f"key {secrets['ANTHROPIC_API_KEY']} here", {"n": secrets["NCBI_API_KEY"]}],
        "who": f"mail {secrets['NCBI_EMAIL']}",
        "tracing": FAKE_LS_KEY,
        "count": 5,
        "text": ABSTRACT_111,
    }
    cleaned = redact(data)
    flat = repr(cleaned)
    for secret in ("URLSECRET1", *secrets.values()):
        assert secret not in flat
    assert "db=pubmed" in cleaned["url"] and "id=111" in cleaned["url"]
    assert cleaned["count"] == 5
    assert cleaned["text"] == ABSTRACT_111  # normal text kept
    assert data["tracing"] == FAKE_LS_KEY  # input not changed in place


def test_redact_wired_into_tracer(fake_tracer: list[FakeTracer]) -> None:  # T13
    tracing_config("RID", enabled=True)
    assert len(fake_tracer) == 1
    client = fake_tracer[0].given_client
    assert client is not None
    assert client._hide_inputs is redact
    assert client._hide_outputs is redact


def test_tracing_failure_does_not_stop_run(
    tmp_path: Path,
    fake_tracer: list[FakeTracer],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:  # T8
    def broken_flush() -> None:
        raise RuntimeError("service down at secret-detail-xyz")

    monkeypatch.setattr(tracing, "wait_for_all_tracers", broken_flush)
    with caplog.at_level(logging.WARNING):
        outcome = go(tmp_path, trace=True)
    assert outcome.status == "ok"
    assert only_record(tmp_path)["status"] == "ok"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("RuntimeError" in r.getMessage() for r in warnings)
    assert "secret-detail-xyz" not in caplog.text  # class name only


def test_nothing_secret_logged_with_tracing_on(
    tmp_path: Path,
    clean_env: Path,
    fake_tracer: list[FakeTracer],
    caplog: pytest.LogCaptureFixture,
) -> None:  # T9
    with caplog.at_level(logging.DEBUG):
        go(tmp_path, trace=True)
    text = caplog.text + clean_env.read_text(encoding="utf-8")
    for secret in (ABSTRACT_111, GOOD_CLAIM, BAD_CLAIM, "Says 40, not 400.", FAKE_LS_KEY):
        assert secret not in text


# ---------------------------------------------------------------- paid (user OK each run)


@pytest.mark.live_paid
def test_live_paid_traced_run(tmp_path: Path) -> None:
    """Real PubMed + real Claude + real LangSmith trace. COSTS MONEY. User OK each run.

    Free LangSmith plan only (T7). After it passes, the user checks the trace in the
    LangSmith UI by hand (``run_id`` in metadata).
    """
    outcome = run(
        "metformin type 2 diabetes HbA1c randomized",
        max_results=2,
        runs_dir=tmp_path / "runs",
        trace=True,
    )
    record = only_record(tmp_path)
    assert outcome.status == "ok"
    assert record["trace"]["enabled"] is True
    assert record["trace"]["backend"] == "langsmith"
    print(f"run_id for the LangSmith UI: {record['run_id']}")
