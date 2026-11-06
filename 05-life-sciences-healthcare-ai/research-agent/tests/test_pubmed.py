"""Stage 3 tests for the PubMed search tool. Spec: docs/PRD.md, rules R1 to R10.

Every HTTP call goes to a fake NCBI built with httpx.MockTransport.
No test here touches the network, except the opt-in `live` test at the end.
"""

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
import pytest

from research_agent.tools import pubmed
from research_agent.tools.pubmed import (
    Paper,
    PubMedConfigError,
    PubMedError,
    SearchResult,
    search_pubmed,
)
from tests.conftest import FAKE_EMAIL

# ---------------------------------------------------------------- fake NCBI


def article_xml(
    pmid: str,
    title: str,
    journal: str = "Test Journal",
    year: str | None = "2021",
    abstract: str | None = "An abstract.",
    sections: list[tuple[str, str]] | None = None,
    article_extra: str = "",
    pubmed_data: str = "",
) -> str:
    """One <PubmedArticle> in the shape EFetch returns.

    ``article_extra`` goes inside <Article> (AuthorList, ELocationID);
    ``pubmed_data`` is a <PubmedData> block. Both default to nothing.
    """
    if sections is not None:
        abstract_xml = (
            "<Abstract>"
            + "".join(
                f'<AbstractText Label="{label}">{text}</AbstractText>' for label, text in sections
            )
            + "</Abstract>"
        )
    elif abstract is not None:
        abstract_xml = f"<Abstract><AbstractText>{abstract}</AbstractText></Abstract>"
    else:
        abstract_xml = ""
    year_xml = f"<Year>{year}</Year>" if year is not None else ""
    return f"""
    <PubmedArticle>
      <MedlineCitation>
        <PMID>{pmid}</PMID>
        <Article>
          <Journal>
            <JournalIssue><PubDate>{year_xml}</PubDate></JournalIssue>
            <Title>{journal}</Title>
          </Journal>
          <ArticleTitle>{title}</ArticleTitle>
          {abstract_xml}
          {article_extra}
        </Article>
      </MedlineCitation>
      {pubmed_data}
    </PubmedArticle>"""


def efetch_body(*articles: str) -> str:
    return "<?xml version='1.0'?><PubmedArticleSet>" + "".join(articles) + "</PubmedArticleSet>"


def esearch_json(pmids: list[str], count: int | None = None) -> dict[str, object]:
    total = len(pmids) if count is None else count
    return {"esearchresult": {"count": str(total), "idlist": pmids}}


Responder = Callable[[httpx.Request], httpx.Response]


@dataclass
class FakeNCBI:
    """Routes esearch/efetch requests and records what was asked."""

    esearch: Responder
    efetch: Responder
    requests: list[httpx.Request] = field(default_factory=list)
    times: list[float] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.times.append(time.monotonic())
        if request.url.path.endswith("esearch.fcgi"):
            return self.esearch(request)
        if request.url.path.endswith("efetch.fcgi"):
            return self.efetch(request)
        raise AssertionError(f"unexpected URL {request.url}")

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))

    def calls_to(self, endpoint: str) -> int:
        return sum(1 for r in self.requests if r.url.path.endswith(endpoint))


def ok_search(pmids: list[str], count: int | None = None) -> Responder:
    return lambda _req: httpx.Response(200, json=esearch_json(pmids, count))


def ok_fetch(*articles: str) -> Responder:
    return lambda _req: httpx.Response(200, text=efetch_body(*articles))


def status(code: int) -> Responder:
    return lambda _req: httpx.Response(code, text="error")


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry backoff is set to 0 so retry tests run fast. The rate limit stays real."""
    monkeypatch.setattr(pubmed, "BACKOFF_BASE_SECONDS", 0.0)


# ---------------------------------------------------------------- happy paths


def test_happy_path_returns_papers_in_esearch_order() -> None:
    # EFetch returns them in a different order; ESearch's ranking must win.
    fake = FakeNCBI(
        esearch=ok_search(["222", "111"]),
        efetch=ok_fetch(
            article_xml("111", "First title", journal="J One", year="2019", abstract="Abs one."),
            article_xml("222", "Second title", journal="J Two", year="2023", abstract="Abs two."),
        ),
    )
    result = search_pubmed("crispr off-target", max_results=2, client=fake.client())

    assert isinstance(result, SearchResult)
    assert result.query == "crispr off-target"
    assert result.total_found == 2
    assert fake.requests[0].url.params["term"] == "crispr off-target"
    assert result.papers == [
        Paper(
            pmid="222",
            title="Second title",
            abstract="Abs two.",
            journal="J Two",
            year=2023,
            url="https://pubmed.ncbi.nlm.nih.gov/222/",
        ),
        Paper(
            pmid="111",
            title="First title",
            abstract="Abs one.",
            journal="J One",
            year=2019,
            url="https://pubmed.ncbi.nlm.nih.gov/111/",
        ),
    ]


def test_total_found_can_exceed_papers_returned() -> None:
    fake = FakeNCBI(
        esearch=ok_search(["1", "2"], count=1234),
        efetch=ok_fetch(article_xml("1", "A"), article_xml("2", "B")),
    )
    result = search_pubmed("q", max_results=2, client=fake.client())
    assert result.total_found == 1234
    assert len(result.papers) == 2


def test_no_results_returns_empty_search_result_and_skips_efetch() -> None:  # R5
    fake = FakeNCBI(esearch=ok_search([]), efetch=status(500))
    result = search_pubmed("zzzz nothing matches", client=fake.client())
    assert result == SearchResult(papers=[], total_found=0, query="zzzz nothing matches")
    assert fake.calls_to("efetch.fcgi") == 0


def test_default_max_results_is_5() -> None:  # R2
    fake = FakeNCBI(esearch=ok_search([]), efetch=status(500))
    search_pubmed("q", client=fake.client())
    assert fake.requests[0].url.params["retmax"] == "5"


def test_missing_abstract_and_year_become_none() -> None:
    fake = FakeNCBI(
        esearch=ok_search(["1"]),
        efetch=ok_fetch(article_xml("1", "No abstract", year=None, abstract=None)),
    )
    [paper] = search_pubmed("q", client=fake.client()).papers
    assert paper.abstract is None
    assert paper.year is None


def test_structured_abstract_sections_joined() -> None:
    fake = FakeNCBI(
        esearch=ok_search(["1"]),
        efetch=ok_fetch(
            article_xml("1", "T", sections=[("BACKGROUND", "Why."), ("RESULTS", "What.")])
        ),
    )
    [paper] = search_pubmed("q", client=fake.client()).papers
    assert paper.abstract == "BACKGROUND: Why.\nRESULTS: What."


# ---------------------------------------------------------------- input rules


@pytest.mark.parametrize("query", ["", "   "])
def test_empty_query_raises_value_error(query: str) -> None:  # R1
    with pytest.raises(ValueError):
        search_pubmed(query)


@pytest.mark.parametrize("max_results", [0, 51])
def test_max_results_out_of_range_raises_value_error(max_results: int) -> None:  # R2
    with pytest.raises(ValueError):
        search_pubmed("q", max_results=max_results)


@pytest.mark.parametrize("max_results", [1, 50])
def test_max_results_at_edges_is_accepted(max_results: int) -> None:  # R2
    fake = FakeNCBI(esearch=ok_search(["1"]), efetch=ok_fetch(article_xml("1", "T")))
    result = search_pubmed("q", max_results=max_results, client=fake.client())
    assert len(result.papers) == 1


def test_missing_email_raises_config_error(monkeypatch: pytest.MonkeyPatch) -> None:  # R3
    monkeypatch.delenv("NCBI_EMAIL")
    fake = FakeNCBI(esearch=ok_search(["1"]), efetch=ok_fetch(article_xml("1", "T")))
    with pytest.raises(PubMedConfigError):
        search_pubmed("q", client=fake.client())
    assert fake.requests == []  # fail before any network call


# ---------------------------------------------------------------- errors and retries


def test_503_then_200_retries_and_succeeds() -> None:  # R6
    replies = iter([httpx.Response(503), httpx.Response(200, json=esearch_json(["1"]))])
    fake = FakeNCBI(esearch=lambda _r: next(replies), efetch=ok_fetch(article_xml("1", "T")))
    result = search_pubmed("q", client=fake.client())
    assert [p.pmid for p in result.papers] == ["1"]
    assert fake.calls_to("esearch.fcgi") == 2


def test_503_three_times_raises_pubmed_error() -> None:  # R6
    fake = FakeNCBI(esearch=status(503), efetch=ok_fetch())
    with pytest.raises(PubMedError):
        search_pubmed("q", client=fake.client())
    assert fake.calls_to("esearch.fcgi") == 3


def test_400_raises_without_retry() -> None:  # R7
    fake = FakeNCBI(esearch=status(400), efetch=ok_fetch())
    with pytest.raises(PubMedError):
        search_pubmed("q", client=fake.client())
    assert fake.calls_to("esearch.fcgi") == 1


def test_bad_xml_raises_pubmed_error() -> None:  # R7
    fake = FakeNCBI(
        esearch=ok_search(["1"]),
        efetch=lambda _r: httpx.Response(200, text="<PubmedArticleSet><broken"),
    )
    with pytest.raises(PubMedError):
        search_pubmed("q", client=fake.client())


# ---------------------------------------------------------------- secrets and rate limit


def test_api_key_and_email_never_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:  # R8
    monkeypatch.setenv("NCBI_API_KEY", "SECRET-KEY-123")
    fake = FakeNCBI(esearch=ok_search(["1"]), efetch=ok_fetch(article_xml("1", "T")))
    with caplog.at_level(logging.DEBUG):
        search_pubmed("q", client=fake.client())

    assert caplog.records, "expected the tool to log its requests"
    assert "SECRET-KEY-123" not in caplog.text
    assert "tester@example.com" not in caplog.text
    # The key is still sent to NCBI, just not logged.
    assert fake.requests[0].url.params["api_key"] == "SECRET-KEY-123"


@pytest.mark.parametrize(
    ("api_key", "min_gap"),
    [(None, 1 / 3), ("SOME-KEY", 1 / 10)],
    ids=["no-key-3-per-sec", "with-key-10-per-sec"],
)
def test_rate_limit_gap_between_requests(
    monkeypatch: pytest.MonkeyPatch, api_key: str | None, min_gap: float
) -> None:  # R4
    if api_key is not None:
        monkeypatch.setenv("NCBI_API_KEY", api_key)
    fake = FakeNCBI(esearch=ok_search(["1"]), efetch=ok_fetch(article_xml("1", "T")))
    search_pubmed("q", client=fake.client())

    assert len(fake.times) == 2
    assert fake.times[1] - fake.times[0] >= min_gap - 0.005  # small clock tolerance


# ---------------------------------------------------------------- Stage 3 revision (R11 to R13)


def author(last: str | None = None, initials: str | None = None) -> str:
    parts = (f"<LastName>{last}</LastName>" if last else "") + (
        f"<Initials>{initials}</Initials>" if initials else ""
    )
    return f"<Author>{parts}</Author>"


def author_list(*authors: str) -> str:
    return "<AuthorList>" + "".join(authors) + "</AuthorList>"


def doi_id(doi: str) -> str:
    return (
        '<PubmedData><ArticleIdList><ArticleId IdType="pubmed">1</ArticleId>'
        f'<ArticleId IdType="doi">{doi}</ArticleId></ArticleIdList></PubmedData>'
    )


def doi_elocation(doi: str) -> str:
    return f'<ELocationID EIdType="doi" ValidYN="Y">{doi}</ELocationID>'


def one_paper(article_extra: str = "", pubmed_data: str = "") -> Paper:
    xml = article_xml("1", "T", article_extra=article_extra, pubmed_data=pubmed_data)
    fake = FakeNCBI(esearch=ok_search(["1"]), efetch=ok_fetch(xml))
    return search_pubmed("q", client=fake.client()).papers[0]


def test_esearch_sends_relevance_sort() -> None:  # R11
    fake = FakeNCBI(esearch=ok_search(["1"]), efetch=ok_fetch(article_xml("1", "T")))
    search_pubmed("q", client=fake.client())
    assert fake.requests[0].url.params["sort"] == "relevance"


def test_authors_parsed_in_order() -> None:  # R12
    extra = author_list(author("Shrestha", "A"), author("Rai", "KB"))
    assert one_paper(article_extra=extra).authors == ["Shrestha A", "Rai KB"]


def test_all_authors_kept() -> None:  # R12
    names = [("A1", "X"), ("A2", "X"), ("A3", "X"), ("A4", "X"), ("A5", "X")]
    extra = author_list(*(author(last, ini) for last, ini in names))
    assert one_paper(article_extra=extra).authors == ["A1 X", "A2 X", "A3 X", "A4 X", "A5 X"]


def test_author_without_initials_is_last_name_only() -> None:  # R12
    extra = author_list(author("Shrestha"))
    assert one_paper(article_extra=extra).authors == ["Shrestha"]


def test_group_author_used_as_written() -> None:  # R12
    extra = author_list(
        author("Rai", "KB"),
        "<Author><CollectiveName>BRCA Study Group</CollectiveName></Author>",
    )
    assert one_paper(article_extra=extra).authors == ["Rai KB", "BRCA Study Group"]


def test_author_with_no_name_is_skipped() -> None:  # R12
    extra = author_list(author("Rai", "KB"), "<Author></Author>")
    assert one_paper(article_extra=extra).authors == ["Rai KB"]


def test_no_author_list_gives_empty_list() -> None:  # R12
    assert one_paper().authors == []


def test_doi_from_article_id_list() -> None:  # R13
    paper = one_paper(
        pubmed_data=doi_id(" 10.1000/main "),
        article_extra=doi_elocation("10.1000/fallback"),
    )
    assert paper.doi == "10.1000/main"


def test_doi_falls_back_to_elocation_id() -> None:  # R13
    assert one_paper(article_extra=doi_elocation("10.1000/fallback")).doi == "10.1000/fallback"


def test_no_doi_gives_none() -> None:  # R13
    assert one_paper().doi is None


# ---------------------------------------------------------------- live (opt-in)


@pytest.mark.live
def test_live_pubmed_search() -> None:
    """Real NCBI call (free). Run with: pytest -m live

    Uses the real NCBI_EMAIL from `.env` (see conftest), never the fake one.
    """
    email = os.environ.get("NCBI_EMAIL", "")
    assert email, "NCBI_EMAIL missing from .env"
    assert email != FAKE_EMAIL, "live test is using the conftest fake email"

    result = search_pubmed("BRCA1 breast cancer", max_results=3)
    assert 1 <= len(result.papers) <= 3
    assert result.total_found >= len(result.papers)
    assert all(p.pmid.isdigit() for p in result.papers)
    # Stage 3 revision: the real XML gives a link and an authors list for each paper.
    assert all(p.url == f"https://pubmed.ncbi.nlm.nih.gov/{p.pmid}/" for p in result.papers)
    assert all(isinstance(p.authors, list) for p in result.papers)
