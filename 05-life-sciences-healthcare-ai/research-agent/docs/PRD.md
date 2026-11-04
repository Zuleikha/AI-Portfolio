# Research Agent: PRD

Status: Goal + Stage 3 **APPROVED by user 2026-11-04**. Stages 4 to 7: not yet specified.

## Goal

A LangGraph agent that searches PubMed, summarises the findings, checks every
claim against its citations, and writes an audit record for each run.

Evidence label: `PERSONAL PROJECT EXPERIENCE`. Uses public literature only. No patient data.

This is the PRD for the **whole project**. Each stage gets its own section here,
approved by the user before it is built.

## Stages

| Stage | What | Spec |
|---|---|---|
| 1 | Folder structure | Done, no spec needed (setup) |
| 2 | Environment and LangGraph install | Done, no spec needed (setup) |
| 3 | PubMed search tool | ✅ Section below, APPROVED |
| 4 | Summarise step | ⬜ Section to be added before build |
| 5 | Citation check step | ⬜ Section to be added before build |
| 6 | Graph, audit log, first run | ⬜ Section to be added before build |
| 7 | Tracing with Langfuse or LangSmith | ⬜ Section to be added before build |

---

## Stage 3: PubMed search tool

### What it does

Takes a search query and returns a `SearchResult`: the papers found, how many PubMed matched in total, and the query that was sent.

### Interface

```python
search_pubmed(query: str, max_results: int = 5) -> SearchResult
```

| `SearchResult` field | Type | Notes |
|---|---|---|
| `papers` | `list[Paper]` | Up to `max_results` papers, in ESearch order |
| `total_found` | `int` | ESearch `count`: all matches in PubMed, can be more than `len(papers)` |
| `query` | `str` | The exact query string sent to ESearch (not trimmed or changed) |

| `Paper` field | Type | Notes |
|---|---|---|
| `pmid` | `str` | PubMed ID, the citation key used later |
| `title` | `str` | |
| `abstract` | `str \| None` | `None` if PubMed has no abstract |
| `journal` | `str` | |
| `year` | `int \| None` | `None` if missing |
| `url` | `str` | `https://pubmed.ncbi.nlm.nih.gov/<pmid>/` |

`SearchResult` and `Paper` are frozen dataclasses.

### How it works

1. **ESearch** (`esearch.fcgi`, JSON) returns a list of PMIDs and the total `count`.
2. **EFetch** (`efetch.fcgi`, XML) returns the details for those PMIDs in one call.
3. Parse the XML into `Paper` objects, keeping ESearch's order, and wrap them in a `SearchResult`.

### Rules

| # | Rule |
|---|---|
| R1 | `query` must not be empty or only spaces. Otherwise raise `ValueError`. |
| R2 | `max_results` defaults to 5 and must be 1 to 50. Otherwise raise `ValueError`. |
| R3 | `NCBI_EMAIL` must be set (NCBI asks for it). If it is missing, raise `PubMedConfigError`. |
| R4 | `NCBI_API_KEY` is optional. Rate limit: 3 requests a second without the key, 10 with it. |
| R5 | No results means `SearchResult(papers=[], total_found=0, query=<query>)`, not an error. EFetch is not called. |
| R6 | HTTP 429, HTTP 5xx or a timeout: retry up to 3 attempts in total, with backoff. Then raise `PubMedError`. |
| R7 | Other HTTP errors, a response that can't be parsed, or a `count` that is missing or not a whole number: raise `PubMedError` straight away. Never return partial or empty results silently. |
| R8 | Never log the API key or the email. Logged URLs have those removed. |
| R9 | Settings are read from environment variables only (`.env` via python-dotenv). Nothing is hardcoded. |
| R10 | Every function uses `@traced`. |

### Supporting piece: `@traced`

There is no tracing in this project yet, so Stage 3 adds a small one:

- `research_agent/observability.py`
- Logs entry, exit, how long the call took, and errors to `runs/trace.log` (on disk, not through the proxy)
- Creates `runs/` (the log's parent folder) if it is missing
- `runs/trace.log` is never committed: `.gitignore` ignores the whole `runs/` folder
- Logs function names only, never arguments or return values (so no secrets or queries end up in the log)
- Stage 7 (Langfuse or LangSmith) builds on this; it does not replace it

### Tests (written first, all failing before the code exists)

All HTTP calls are mocked with `httpx.MockTransport`. The tests make **no real network calls**.

| Test | Checks |
|---|---|
| happy path | 2 PMIDs → `SearchResult` with 2 `Paper`s (all fields correct, order kept), `total_found` from `count`, `query` as sent |
| total above max_results | `count` 1234 with 2 PMIDs → `total_found == 1234`, 2 papers |
| no results | `SearchResult` with `papers=[]`, `total_found=0`; EFetch is not called |
| missing abstract / year | those fields are `None` |
| structured abstract | sections joined into one string |
| empty query | `ValueError` (R1) |
| default max_results | ESearch is asked for 5 results (`retmax=5`) (R2) |
| max_results 0 and 51 | `ValueError` (R2) |
| missing email | `PubMedConfigError` (R3) |
| 503 then 200 | retries, then succeeds (R6) |
| 503 three times | `PubMedError` (R6) |
| 400 | `PubMedError`, no retry (R7) |
| bad XML | `PubMedError` (R7) |
| API key not in logs | the logged text does not contain the key (R8) |
| rate limit | the gap between requests is at least 0.34s without a key and 0.1s with one (R4) |

`@traced` tests (`tests/test_observability.py`): logs name and duration to the file · never logs arguments or results · logs and re-raises errors · keeps the function name · works when `runs/` does not exist (creates it).

Test-only hooks (not part of the public interface): `search_pubmed(..., client=httpx.Client)` takes a mock client; `BACKOFF_BASE_SECONDS` is set to 0 in tests; the trace log path comes from `RESEARCH_AGENT_TRACE_LOG` (default `runs/trace.log`). `.env` is loaded by the entry point (Stage 6), not by the tool. Offline tests use a fake email; the `live` test reads the real `NCBI_EMAIL` / `NCBI_API_KEY` from `.env` (via `tests/conftest.py`) and fails if it sees the fake email.

Plus one **optional live test**, marked `@pytest.mark.live` and skipped by default
(NCBI is free; it is opt-in so tests stay offline).

### Out of scope for Stage 3

- Wrapping this as a LangGraph tool or node (Stage 6)
- Full text from PMC, MeSH filters, date filters, paging past 50 results
- Caching

### Done when

- All tests pass
- `ruff check`, `ruff format` and `mypy --strict` are clean (ruff and mypy are pinned in `requirements-dev.txt`)
- `PROGRESS.md` is updated and the work is committed
