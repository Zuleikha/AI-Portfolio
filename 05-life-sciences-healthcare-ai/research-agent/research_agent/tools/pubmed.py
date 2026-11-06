"""PubMed search tool: NCBI E-utilities ESearch + EFetch (docs/PRD.md, Stage 3).

Settings come from environment variables only (R9). ``.env`` is loaded by the
entry point, not here:

- ``NCBI_EMAIL``   required (R3)
- ``NCBI_API_KEY`` optional; raises the rate limit from 3 to 10 requests/sec (R4)
"""

import logging
import os
import re
import threading
import time
import xml.etree.ElementTree as ET  # noqa: N817 - conventional alias
from dataclasses import dataclass, field
from typing import Any

import httpx

from research_agent.observability import traced

logger = logging.getLogger(__name__)

EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
ESEARCH_ENDPOINT = "esearch.fcgi"
EFETCH_ENDPOINT = "efetch.fcgi"
PUBMED_URL_TEMPLATE = "https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
TOOL_NAME = "research-agent"
SORT_ORDER = "relevance"  # R11: "Best Match"; the ESearch default is "most recent"

DEFAULT_MAX_RESULTS = 5
MIN_RESULTS = 1
MAX_RESULTS = 50

REQUESTS_PER_SECOND_NO_KEY = 3
REQUESTS_PER_SECOND_WITH_KEY = 10

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.5
TIMEOUT_SECONDS = 10.0
RETRYABLE_STATUS = frozenset({429})  # plus every 5xx

EMAIL_ENV = "NCBI_EMAIL"
API_KEY_ENV = "NCBI_API_KEY"


# ---------------------------------------------------------------- public types


class PubMedError(Exception):
    """PubMed could not be searched, or returned something unusable."""


class PubMedConfigError(PubMedError):
    """A required setting (environment variable) is missing."""


@dataclass(frozen=True)
class Paper:
    pmid: str
    title: str
    abstract: str | None
    journal: str
    year: int | None
    url: str
    authors: list[str] = field(default_factory=list)  # R12
    doi: str | None = None  # R13


@dataclass(frozen=True)
class SearchResult:
    papers: list[Paper]
    total_found: int
    query: str


# ---------------------------------------------------------------- secret redaction (R8)

_SECRET_PARAM = re.compile(r"(?P<key>api_key|email)=[^&\s\"']*")


class _RedactSecretsFilter(logging.Filter):
    """Removes ``api_key`` and ``email`` values from log lines.

    httpx logs the full request URL at INFO, and that URL carries both values.
    """

    @traced
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _SECRET_PARAM.sub(r"\g<key>=REDACTED", message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


_httpx_logger = logging.getLogger("httpx")
if not any(isinstance(f, _RedactSecretsFilter) for f in _httpx_logger.filters):
    _httpx_logger.addFilter(_RedactSecretsFilter())


# ---------------------------------------------------------------- rate limit (R4)

_rate_lock = threading.Lock()
_last_request_at: float | None = None


@traced
def _wait_for_rate_limit(has_api_key: bool) -> None:
    """Sleeps so requests are at least 1/3 s apart (1/10 s with an API key)."""
    global _last_request_at
    per_second = REQUESTS_PER_SECOND_WITH_KEY if has_api_key else REQUESTS_PER_SECOND_NO_KEY
    min_gap = 1.0 / per_second
    with _rate_lock:
        now = time.monotonic()
        if _last_request_at is not None:
            wait = _last_request_at + min_gap - now
            if wait > 0:
                time.sleep(wait)
        _last_request_at = time.monotonic()


# ---------------------------------------------------------------- HTTP with retries (R6, R7)


@traced
def _is_retryable(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUS or status_code >= 500


@traced
def _get(
    client: httpx.Client, endpoint: str, params: dict[str, str], has_api_key: bool
) -> httpx.Response:
    """GET with rate limiting; retries 429 / 5xx / timeouts up to MAX_ATTEMPTS."""
    last_problem = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            time.sleep(BACKOFF_BASE_SECONDS * 2 ** (attempt - 2))
        _wait_for_rate_limit(has_api_key)
        try:
            response = client.get(EUTILS_BASE_URL + endpoint, params=params)
        except httpx.TimeoutException:
            last_problem = "timeout"
            logger.warning("%s attempt %d/%d: timeout", endpoint, attempt, MAX_ATTEMPTS)
            continue
        except httpx.HTTPError as exc:
            raise PubMedError(f"{endpoint}: request failed ({type(exc).__name__})") from exc

        logger.debug(
            "%s attempt %d/%d: HTTP %d", endpoint, attempt, MAX_ATTEMPTS, response.status_code
        )
        if response.is_success:
            return response
        if _is_retryable(response.status_code):
            last_problem = f"HTTP {response.status_code}"
            continue
        raise PubMedError(f"{endpoint}: HTTP {response.status_code}")

    raise PubMedError(f"{endpoint}: gave up after {MAX_ATTEMPTS} attempts ({last_problem})")


# ---------------------------------------------------------------- parsing


@traced
def _parse_esearch(response: httpx.Response) -> tuple[list[str], int]:
    """Returns (PMIDs in ranked order, total count)."""
    try:
        data: Any = response.json()
        result = data["esearchresult"]
        pmids = result["idlist"]
        count_raw = result["count"]
    except (ValueError, KeyError, TypeError) as exc:
        raise PubMedError("esearch: unexpected response shape") from exc

    if not isinstance(pmids, list) or not all(isinstance(p, str) for p in pmids):
        raise PubMedError("esearch: idlist is not a list of strings")
    if not isinstance(count_raw, str) or not count_raw.isdigit():
        raise PubMedError("esearch: count is missing or not a whole number")
    return pmids, int(count_raw)


@traced
def _text(element: ET.Element | None) -> str | None:
    """All text inside an element (keeps inline markup like <i>), or None if empty."""
    if element is None:
        return None
    text = "".join(element.itertext()).strip()
    return text or None


@traced
def _parse_abstract(article: ET.Element) -> str | None:
    parts: list[str] = []
    for node in article.findall("Abstract/AbstractText"):
        body = _text(node)
        if body is None:
            continue
        label = node.get("Label")
        parts.append(f"{label}: {body}" if label else body)
    return "\n".join(parts) or None


@traced
def _parse_year(article: ET.Element) -> int | None:
    year = _text(article.find("Journal/JournalIssue/PubDate/Year"))
    return int(year) if year is not None and year.isdigit() else None


@traced
def _parse_author(author: ET.Element) -> str | None:
    """``"<LastName> <Initials>"``, a group name as written, or None (R12)."""
    group = _text(author.find("CollectiveName"))
    if group is not None:
        return group
    last = _text(author.find("LastName"))
    if last is None:
        return None
    initials = _text(author.find("Initials"))
    return f"{last} {initials}" if initials else last


@traced
def _parse_authors(article: ET.Element) -> list[str]:
    names = (_parse_author(a) for a in article.findall("AuthorList/Author"))
    return [name for name in names if name is not None]


@traced
def _parse_doi(node: ET.Element, article: ET.Element) -> str | None:
    """ArticleIdList first, then ELocationID, else None (R13)."""
    return _text(node.find("PubmedData/ArticleIdList/ArticleId[@IdType='doi']")) or _text(
        article.find("ELocationID[@EIdType='doi']")
    )


@traced
def _parse_paper(node: ET.Element) -> Paper:
    pmid = _text(node.find("MedlineCitation/PMID"))
    article = node.find("MedlineCitation/Article")
    if pmid is None or article is None:
        raise PubMedError("efetch: article without PMID or Article element")
    title = _text(article.find("ArticleTitle"))
    journal = _text(article.find("Journal/Title"))
    if title is None or journal is None:
        raise PubMedError(f"efetch: PMID {pmid} has no title or journal")
    return Paper(
        pmid=pmid,
        title=title,
        abstract=_parse_abstract(article),
        journal=journal,
        year=_parse_year(article),
        url=PUBMED_URL_TEMPLATE.format(pmid=pmid),
        authors=_parse_authors(article),
        doi=_parse_doi(node, article),
    )


@traced
def _parse_efetch(response: httpx.Response, pmids: list[str]) -> list[Paper]:
    """Parses EFetch XML and returns papers in the given PMID order."""
    try:
        root = ET.fromstring(response.text)  # noqa: S314 - stdlib expat, no external entities
    except ET.ParseError as exc:
        raise PubMedError("efetch: response is not valid XML") from exc

    by_pmid = {paper.pmid: paper for paper in map(_parse_paper, root.findall("PubmedArticle"))}
    missing = [p for p in pmids if p not in by_pmid]
    if missing:
        raise PubMedError(f"efetch: {len(missing)} requested PMID(s) missing from response")
    return [by_pmid[p] for p in pmids]


# ---------------------------------------------------------------- public function


@traced
def search_pubmed(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    *,
    client: httpx.Client | None = None,
) -> SearchResult:
    """Searches PubMed and returns up to ``max_results`` papers.

    ``client`` is a test hook (PRD "Test-only hooks"); leave it out in normal use.
    """
    if not query.strip():
        raise ValueError("query must not be empty")
    if not MIN_RESULTS <= max_results <= MAX_RESULTS:
        raise ValueError(f"max_results must be {MIN_RESULTS} to {MAX_RESULTS}")

    email = os.environ.get(EMAIL_ENV, "").strip()
    if not email:
        raise PubMedConfigError(f"{EMAIL_ENV} is not set")
    api_key = os.environ.get(API_KEY_ENV, "").strip()

    common = {"db": "pubmed", "tool": TOOL_NAME, "email": email}
    if api_key:
        common["api_key"] = api_key

    owns_client = client is None
    http = client if client is not None else httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        search = _get(
            http,
            ESEARCH_ENDPOINT,
            {
                **common,
                "term": query,
                "retmax": str(max_results),
                "sort": SORT_ORDER,
                "retmode": "json",
            },
            bool(api_key),
        )
        pmids, total_found = _parse_esearch(search)
        if not pmids:
            return SearchResult(papers=[], total_found=total_found, query=query)

        fetch = _get(
            http,
            EFETCH_ENDPOINT,
            {**common, "id": ",".join(pmids), "retmode": "xml"},
            bool(api_key),
        )
        papers = _parse_efetch(fetch, pmids)
    finally:
        if owns_client:
            http.close()

    return SearchResult(papers=papers, total_found=total_found, query=query)
