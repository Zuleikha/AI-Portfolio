"""Tests for the demo script (docs/PRD.md, "Demo script", rules D1 to D8).

PubMed is a fake NCBI (httpx.MockTransport) and the model is a fake Runnable.
No test here touches the network or costs money.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from research_agent.nodes.summarise import Summary
from research_agent.tools import pubmed
from scripts.demo_run import build_record, main, write_record
from tests.test_pubmed import FakeNCBI, article_xml, ok_fetch, ok_search
from tests.test_summarise import FakeLLM, llm_reply

ABSTRACT_111 = "Drug X lowered blood pressure in 40 adults."
QUERY = "drug x blood pressure"
STAMP = datetime(2026, 11, 6, 10, 11, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pubmed, "BACKOFF_BASE_SECONDS", 0.0)


def fake_ncbi() -> FakeNCBI:
    """PMID 111 has an abstract; PMID 222 has none (so it is skipped)."""
    return FakeNCBI(
        esearch=ok_search(["111", "222"], count=57),
        efetch=ok_fetch(
            article_xml("111", "Drug X trial", abstract=ABSTRACT_111),
            article_xml("222", "Drug X letter", abstract=None),
        ),
    )


def run(tmp_path: Path, ncbi: FakeNCBI, llm: FakeLLM, *args: str) -> int:
    return main(
        [QUERY, *args], client=ncbi.client(), llm=llm.runnable(), runs_dir=tmp_path / "runs"
    )


def only_record(runs_dir: Path) -> dict[str, Any]:
    files = list(runs_dir.glob("demo_*.json"))
    assert len(files) == 1
    data: dict[str, Any] = json.loads(files[0].read_text(encoding="utf-8"))
    return data


def test_without_yes_makes_no_calls_and_writes_nothing(tmp_path: Path) -> None:  # D2
    ncbi, llm = fake_ncbi(), FakeLLM(reply=llm_reply())
    assert run(tmp_path, ncbi, llm) == 2
    assert ncbi.requests == []
    assert llm.calls == []
    assert not (tmp_path / "runs").exists()


def test_happy_path_writes_full_record(tmp_path: Path) -> None:  # D1, D3, D4
    ncbi = fake_ncbi()
    llm = FakeLLM(reply=llm_reply(("Drug X lowered blood pressure.", ["111"])))
    assert run(tmp_path, ncbi, llm, "--yes") == 0

    record = only_record(tmp_path / "runs")
    assert record["source"] == "live demo"
    assert record["search"]["query"] == QUERY
    assert record["search"]["total_found"] == 57
    first = record["search"]["papers"][0]
    assert (first["pmid"], first["title"], first["abstract"]) == (
        "111",
        "Drug X trial",
        ABSTRACT_111,
    )
    summary = record["summary"]
    assert summary["model"]
    assert summary["claims"] == [{"text": "Drug X lowered blood pressure.", "pmids": ["111"]}]


def test_skipped_and_rejected_kept_with_reasons(tmp_path: Path) -> None:
    llm = FakeLLM(
        reply=llm_reply(("Good claim.", ["111"]), ("Made-up claim.", ["999"])),
    )
    assert run(tmp_path, fake_ncbi(), llm, "--yes") == 0

    summary = only_record(tmp_path / "runs")["summary"]
    assert summary["skipped"] == [{"pmid": "222", "reason": "no abstract"}]
    assert len(summary["rejected"]) == 1
    rejected = summary["rejected"][0]
    assert rejected["text"] == "Made-up claim."
    assert rejected["pmids"] == ["999"]
    assert "unknown PMID" in rejected["reason"]


def test_creates_missing_runs_folder(tmp_path: Path) -> None:  # D3
    runs_dir = tmp_path / "a" / "b" / "runs"
    record = {"source": "live demo"}
    path = write_record(record, runs_dir, STAMP)
    assert path.parent == runs_dir
    assert path.is_file()


def test_file_name_is_utc_stamp_and_never_overwritten(tmp_path: Path) -> None:  # D3
    path = write_record({"source": "live demo"}, tmp_path, STAMP)
    assert path.name == "demo_20261106T101112Z.json"
    assert re.fullmatch(r"demo_\d{8}T\d{6}Z\.json", path.name)
    with pytest.raises(FileExistsError):
        write_record({"source": "other"}, tmp_path, STAMP)
    assert json.loads(path.read_text(encoding="utf-8"))["source"] == "live demo"


def test_build_record_uses_dataclasses() -> None:  # D4
    result = pubmed.SearchResult(papers=[], total_found=0, query=QUERY)
    summary = Summary(query=QUERY, claims=[], used_pmids=[], skipped=[], rejected=[], model="m")
    record = build_record(result, summary, STAMP)
    assert record["created_at"] == STAMP.isoformat()
    assert record["search"] == {"papers": [], "total_found": 0, "query": QUERY}
    assert record["summary"]["model"] == "m"


def test_prints_path_and_counts_but_no_abstract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:  # D5
    llm = FakeLLM(reply=llm_reply(("Drug X lowered blood pressure.", ["111"])))
    assert run(tmp_path, fake_ncbi(), llm, "--yes") == 0

    out = capsys.readouterr().out
    assert "demo_" in out
    assert "claims: 1" in out
    assert ABSTRACT_111 not in out
