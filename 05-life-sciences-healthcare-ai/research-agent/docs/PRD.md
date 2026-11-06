# Research Agent: PRD

Status: Goal + Stage 3 **APPROVED by user 2026-11-04**. Stage 4 **APPROVED by user 2026-11-04**. Demo script **APPROVED by user 2026-11-06**. Stage 3 revision **APPROVED by user 2026-11-06**. Stage 5 **APPROVED by user 2026-11-06**. Stages 6 and 7: not yet specified.

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
| 3r | Stage 3 revision: relevance sort (K1), authors, DOI | ✅ Section below, APPROVED |
| 4 | Summarise step | ✅ Section below, APPROVED |
| 5 | Citation check step | ✅ Section below, APPROVED |
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
| max_results 1 and 50 | accepted (R2) |
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

---

## Stage 3 revision: relevance sort, authors, DOI

Status: **APPROVED by user 2026-11-06** (R14 narrowed to application logs at approval). (Q6 to Q8 settled 2026-11-06: revise before Stage 5; citation = first 3 authors + "et al."; DOI optional).

### Why

| # | Problem | Source |
|---|---|---|
| 1 | Search returns the **newest** papers, not the most relevant (known issue K1). ESearch's default sort for PubMed is "most recent"; Stage 3 sends no `sort`. | Demo run 2026-11-06: all 5 papers from 2025-26, 3 of 10 claims off-topic |
| 2 | A reader cannot check a paper exists from the output: there are **no authors** and **no DOI**. The PubMed link (`url`) already exists. | User request 2026-11-06 |

Both come from the same EFetch XML already downloaded: **no extra API calls**.

### Interface change

`search_pubmed` signature is unchanged. `Paper` gets two new fields, **at the end, with defaults**,
so existing code and tests that build `Paper` keep working unchanged.

| New `Paper` field | Type | Default | Notes |
|---|---|---|---|
| `authors` | `list[str]` | `[]` | In the order PubMed lists them, e.g. `["Shrestha A", "Rai KB"]` |
| `doi` | `str \| None` | `None` | Bare DOI, e.g. `10.1000/xyz123` (no `https://doi.org/` prefix) |

### Rules

| # | Rule |
|---|---|
| R11 | ESearch always sends `sort=relevance` ("Best Match"), from a module constant. Never rely on the server default. |
| R12 | `authors` comes from `MedlineCitation/Article/AuthorList/Author`, in order. Each is `"<LastName> <Initials>"`; `LastName` only if there are no initials; a `CollectiveName` (group author) is used as written. An `Author` with neither is skipped. No `AuthorList` → `[]` (not an error). All authors are kept; shortening to 3 + "et al." is a display job (Stage 6). |
| R13 | `doi` comes from `PubmedData/ArticleIdList/ArticleId[@IdType="doi"]`; if absent, from `Article/ELocationID[@EIdType="doi"]`; if both absent, `None` (not an error). Whitespace trimmed. Not checked against doi.org (no extra call). |
| R14 | **Application logs only** (Python `logging`, `runs/trace.log`): authors, DOIs and titles are never logged; counts only. R8 and `@traced` still apply. This does **not** limit the audit record: the Stage 6 audit record (and the demo JSON) **must** include each paper's authors, DOI and title, so a reader can check the paper exists. |

### Tests (written first, failing before the code changes)

Same fake NCBI (`httpx.MockTransport`) as Stage 3. **All 25 existing Stage 3 tests stay unchanged and must still pass.**

| Test | Checks |
|---|---|
| sort sent | the ESearch request has `sort=relevance` (R11) |
| authors parsed | 2 authors → `["Shrestha A", "Rai KB"]`, in XML order (R12) |
| many authors kept | 5 authors → all 5 kept (R12) |
| last name only | an author with no initials → `"Shrestha"` (R12) |
| group author | `CollectiveName` → used as written (R12) |
| empty author skipped | an `Author` with no name parts is skipped (R12) |
| no author list | `authors == []` (R12) |
| DOI from ArticleIdList | → that DOI (R13) |
| DOI fallback | only `ELocationID` has it → that DOI (R13) |
| no DOI | `doi is None` (R13) |

The optional `live` test (free) gets one extra check: every paper has a `url` and the `authors` field
is a list. Run it once after the build, to confirm the real XML matches.

### Handed on to Stage 6 (not built here)

The audit record must include each paper's `authors`, `doi` and `title` in full (R14).
Short citation for display and the audit record, built from `Paper`:
`<first 3 authors>, et al. <title> <journal>. <year>. <url>` (no "et al." when there are 3 or fewer;
`doi:<doi>` added when present).

### Out of scope

- Building the citation string (Stage 6)
- Checking DOIs against doi.org, affiliations, ORCID IDs
- Any other sort option or a sort setting for the user

### Done when

- 25 existing + 10 new Stage 3 tests pass; Stage 4 and demo tests still pass
- `ruff check`, `ruff format --check` and `mypy --strict` are clean
- K1 marked fixed in `PROGRESS.md`; work committed

### Checked against NCBI docs (2026-11-06)

- `sort=relevance` = "Best Match"; ESearch's PubMed default is "most recent" (NCBI Insights, 2022 PubMed E-utilities update). Our demo run matches this.

---

## Stage 4: Summarise step

Status: **APPROVED by user 2026-11-04** (Q1 and Q2: yes, as recommended)

### What it does

Takes the `SearchResult` from Stage 3 and asks Claude for a short summary. Every claim in the
summary lists the PMID(s) it came from. Only the abstracts given are used.

### Interface

```python
summarise(result: SearchResult, *, llm: Runnable | None = None) -> Summary
```

| `Summary` field | Type | Notes |
|---|---|---|
| `query` | `str` | Copied from `result.query` |
| `claims` | `list[Claim]` | In the order the model gave them |
| `used_pmids` | `list[str]` | Papers whose abstracts were sent to the model, in search order |
| `skipped` | `list[SkippedPaper]` | Papers not sent to the model, and why |
| `rejected` | `list[RejectedClaim]` | Claims the model returned that failed the PMID check (S5) |
| `model` | `str` | The `ANTHROPIC_MODEL` value used (for the audit log) |

| `Claim` field | Type | Notes |
|---|---|---|
| `text` | `str` | One factual statement |
| `pmids` | `list[str]` | At least one; each must be in `used_pmids` |

| `SkippedPaper` field | Type | Notes |
|---|---|---|
| `pmid` | `str` | |
| `reason` | `str` | `"no abstract"` |

| `RejectedClaim` field | Type | Notes |
|---|---|---|
| `text` | `str` | The claim as the model wrote it |
| `pmids` | `list[str]` | The PMIDs the model gave (may be empty) |
| `reason` | `str` | `"no PMID"` or `"unknown PMID: <ids>"` |

`Summary`, `Claim`, `SkippedPaper` and `RejectedClaim` are frozen dataclasses. Stage 5 (citation check) takes a `Summary`.

### How it works

1. Split `result.papers`: papers with an abstract are **used**; papers with `abstract=None` are **skipped** and recorded.
2. If no papers are used, return a `Summary` with `claims=[]` straight away. **The model is not called** (no cost).
3. Build the prompt: a **system** message with the rules (S4, S12), then a **user** message with each used abstract inside its own `<abstract pmid="...">` tag, with its title (S12).
4. Call Claude through `langchain-anthropic`: `ChatAnthropic(...).with_structured_output(<schema>, method="json_schema")`.
   This uses Anthropic's native structured output (needs `langchain-anthropic>=1.1.0`; pinned `1.7.9`).
   The schema is an internal Pydantic model: a list of `{text, pmids}`.
5. Check each claim (S5): good claims go to `claims`, bad ones to `rejected`. Return the `Summary`.

### Rules

| # | Rule |
|---|---|
| S1 | Input is a Stage 3 `SearchResult`. |
| S2 | Papers with `abstract=None` are never sent to the model and never guessed. Each one is listed in `skipped` with reason `"no abstract"`. |
| S3 | No usable abstracts (including zero papers) → `Summary(claims=[])`, no model call. |
| S4 | The prompt tells the model: use **only** the abstracts given, no outside knowledge; every claim must cite the PMID(s) it came from; if the abstracts support nothing, return no claims. The model is given **no tools**. |
| S5 | Every claim must have at least one PMID, and every PMID must be in `used_pmids`. A claim that fails goes to `rejected` with its reason; the other claims are kept. A claim with one good and one unknown PMID is rejected **whole** (never trimmed: it may depend on the unknown one). Rejected claims are never fixed or silently dropped; the count is logged. A reply that does not match the schema at all still raises `SummariseError`. (Stage 5 checks whether the abstracts really support each claim.) |
| S6 | Model ID comes from `ANTHROPIC_MODEL` (env). If it is missing, raise `SummariseConfigError` before any call. `ANTHROPIC_API_KEY` is read from env by `langchain-anthropic`. Nothing is hardcoded. |
| S7 | Retries: use `ChatAnthropic`'s built-in retries (it retries 429, 5xx and network errors with backoff; it does not retry 401 or 404). Set `max_retries` and `timeout` from module constants, not the default 6 retries. A failure after that → `SummariseError`. |
| S8 | Do not set `temperature`, `top_p` or `top_k`: newer Claude models reject non-default values with a 400 error. Set `max_tokens` from a module constant. |
| S9 | Never log abstracts, the prompt, the model's reply or the API key. Log counts only (papers used, skipped, claims, rejected). |
| S10 | Every function uses `@traced`. |
| S11 | Each real model call costs money. Offline tests never call the API. The live test is opt-in with its own marker and needs the user's OK before each run. |
| S12 | **Abstracts are data, not instructions** (prompt injection protection). Rules live only in the system message. Each abstract sits inside `<abstract pmid="...">...</abstract>`, and the system message says text inside these tags is source material to summarise, never instructions to follow. Any `<abstract` or `</abstract` text inside an abstract or title is neutralised before sending, so an abstract cannot close its own tag. Backed up by: no tools (S4), the fixed output schema, the PMID check (S5) and the Stage 5 citation check. |

### Tests (written first, all failing before the code exists)

The model is replaced by a fake `Runnable` (passed as `llm=`) that returns a scripted reply and
records the messages it was sent. The tests make **no API calls** and cost nothing.

| Test | Checks |
|---|---|
| happy path | 2 papers → claims with their PMIDs, `used_pmids` in search order, `skipped=[]`, `query` and `model` copied |
| abstract None skipped | 1 of 2 has no abstract → it is in `skipped` with `"no abstract"`, and its PMID is not in the prompt (S2) |
| nothing usable | all abstracts `None`, and zero papers → `claims=[]`, fake model never called (S3) |
| prompt content | the prompt contains each used abstract with its PMID, and the "only these abstracts, no outside knowledge" rule (S4) |
| unknown PMID | a claim cites a PMID that was not sent → it is in `rejected` with `"unknown PMID: ..."`; good claims are kept (S5) |
| no PMID | a claim with an empty `pmids` list → in `rejected` with `"no PMID"` (S5) |
| mixed PMIDs | a claim citing one good and one unknown PMID → rejected whole, not trimmed (S5) |
| skipped PMID cited | a claim citing a skipped paper's PMID → rejected as unknown (S2, S5) |
| bad schema | the reply does not match the schema → `SummariseError` (S5) |
| missing model setting | `ANTHROPIC_MODEL` unset → `SummariseConfigError`, fake model never called (S6) |
| default model setup | without `llm=`, the built model uses the `ANTHROPIC_MODEL` value, json_schema output, and no temperature (S6, S8). Built only, not called |
| model error | the fake raises → `SummariseError` (S7) |
| abstracts in tags | each used abstract is inside its own `<abstract pmid="...">` tag in the user message; the rules are only in the system message (S12) |
| tag escape blocked | an abstract containing `</abstract>` and "Ignore previous instructions" → the tag text is neutralised, so the abstract stays inside its own tag (S12) |
| tag escape in title blocked | a title containing `</abstract>` and "Ignore previous instructions" → the tag text is neutralised, so the title stays inside its own tag (S12) |
| no tools | the default model is built with no tools bound (S4) |
| nothing secret logged | log text has no abstract text, prompt text or API key (S9) |

Plus one **optional paid live test**, marked `@pytest.mark.live_paid`, skipped by default and not
run by `-m live`. It needs the user's OK before each run (S11).

Test-only hook (not part of the public interface): `summarise(..., llm=...)` takes the fake model.

### Open questions (settled 2026-11-04)

| # | Rule | Question | Decision |
|---|---|---|---|
| Q1 | S5 | Instead of failing the whole summary on one bad PMID, should we reject only that claim and record it in a `rejected` list (claim text + reason) on `Summary`? | ✅ **Yes (user agreed).** Keep good claims, record bad ones in `rejected`. A claim with mixed good and unknown PMIDs is rejected whole. Schema failures still raise. See S5. |
| Q2 | S4 | Should S4 add a rule that abstracts are **data, not instructions** (prompt injection protection), e.g. the model must ignore any instructions found inside an abstract? | ✅ **Yes, with layers (user agreed).** A prompt rule alone is not enough: add tags, tag-escape protection and no tools, backed by the schema, S5 and Stage 5. See S12. |

### Out of scope for Stage 4

- Checking that each claim is supported by its abstract (Stage 5)
- Wrapping this as a LangGraph node (Stage 6)
- Streaming, caching, prompt caching, choosing between models

### Done when

- All tests pass
- `ruff check`, `ruff format --check` and `mypy --strict` are clean
- `PROGRESS.md` is updated and the work is committed

### Checked against current docs (Context7, 2026-11-04)

- `with_structured_output(schema, method="json_schema")` = Anthropic native structured output; needs `langchain-anthropic>=1.1.0`
- Default `max_retries` is 6; retries 429, 5xx and network errors; not 401 or 404
- Newer Claude models return 400 for non-default `temperature`, `top_p` or `top_k`

---

## Stage 5: Citation check

Status: **APPROVED by user 2026-11-06** (C-Q1 to C-Q5 settled as recommended). Built on decisions
Q1 to Q5 and the design review (`PROGRESS.md`, "Settled decisions").

### What it does

Takes the Stage 4 `Summary` and the Stage 3 `SearchResult`. For **each claim**, asks Claude
whether the cited abstract(s) support it, and to quote the exact text it relied on. Code then
checks the quotes and numbers. A claim passes only if the model says **supported** *and* every
code check passes. The model's verdict alone never passes a claim.

Why (demo run 2026-11-06): all 10 real claims passed the Stage 4 PMID check, which proves
*which paper* a claim names, not that the paper *supports* it.

### Interface

```python
check_citations(summary: Summary, result: SearchResult, *,
                llm: Runnable | None = None) -> CheckedSummary
```

| `CheckedSummary` field | Type | Notes |
|---|---|---|
| `query` | `str` | Copied from `summary.query` |
| `verified` | `list[VerifiedClaim]` | Claims that passed, in input order |
| `failed` | `list[FailedClaim]` | Claims that failed, in input order, with every reason |
| `summary` | `Summary` | The Stage 4 summary, unchanged (keeps `skipped` and `rejected` for the audit log) |
| `check_model` | `str` | The `ANTHROPIC_CHECK_MODEL` value used |

| `Quote` field | Type | Notes |
|---|---|---|
| `pmid` | `str` | The abstract the quote is from |
| `text` | `str` | Exact text from that abstract, as the model returned it |

| `VerifiedClaim` field | Type | Notes |
|---|---|---|
| `text` | `str` | The claim |
| `pmids` | `list[str]` | As cited in Stage 4 |
| `quotes` | `list[Quote]` | The evidence, each one checked |

| `FailedClaim` field | Type | Notes |
|---|---|---|
| `text` | `str` | The claim |
| `pmids` | `list[str]` | As cited in Stage 4 |
| `quotes` | `list[Quote]` | What the model returned (may be empty) |
| `reasons` | `list[str]` | **All** reasons it failed (C4 to C9), never empty |
| `explanation` | `str` | The model's short note, cut by code to `MAX_EXPLANATION_CHARS` (300) (audit only; C-Q5) |

All are frozen dataclasses. Stage 6 takes a `CheckedSummary`.

### How it works

1. No claims → return `CheckedSummary(verified=[], failed=[])`. **No model call.**
2. More than `MAX_CLAIMS` claims → raise `CitationCheckError` before any call (C2, C-Q2).
3. For each claim, in order:
   1. Look up the cited papers' abstracts in `result.papers`.
   2. Build the prompt: a **system** message with the rules, then a **user** message with the claim in a `<claim>` tag and **only its cited** abstracts in `<abstract pmid="...">` tags.
   3. Call Claude (`ANTHROPIC_CHECK_MODEL`), structured output: `{verdict, quotes: [{pmid, text}], explanation}`.
   4. Run the code checks (C4 to C9) and collect every reason.
   5. No reasons and verdict `supported` → `verified`; otherwise → `failed`.

### Rules

| # | Rule |
|---|---|
| C1 | **One model call per claim** (Q1). Claims are checked independently; the model only sees that claim's cited abstracts, never the others. |
| C2 | **Spend cap:** more than `MAX_CLAIMS` (module constant, proposed 20) → `CitationCheckError` before any call. No claims → no call. |
| C3 | Model ID from `ANTHROPIC_CHECK_MODEL` (Q2; may hold the same value as `ANTHROPIC_MODEL`). Missing → `CitationCheckConfigError` before any call. `ANTHROPIC_API_KEY` as in Stage 4. Same `max_retries`, `timeout`, `max_tokens` approach and no `temperature`/`top_p`/`top_k` (S7, S8). No tools. |
| C4 | Verdict is `"supported"` or `"not_supported"` only. `not_supported` → reason `not supported`. |
| C5 | Verdict `supported` with no quotes → reason `no quote`. |
| C6 | Each quote's `pmid` must be one the claim cites → else reason `quote from uncited PMID: <id>`, and that quote gets **no** C7 check (rule A, 2026-11-06). |
| C7 | Each quote must appear in **that** PMID's original abstract after normalising both: Unicode NFKC, all dash types to `-`, whitespace collapsed, case ignored. Else reason `quote not found: <pmid>`. Quotes shorter than `MIN_QUOTE_CHARS` (proposed 20, after normalising) → reason `quote too short: <pmid>` (C-Q3). |
| C8 | **Numbers** (Q3): every standalone number in the claim must appear as a standalone number in the **good quotes** (joined): only quotes that pass C6 and C7 (cited, found, long enough) count (rule B, 2026-11-06). Standalone = digits not touching a letter, so `B12`, `HbA1c`, `IC50` are ignored; `21.7%`, `69`, `318`, `2` (in "type 2") count. Thousands commas are removed before comparing (`1,000` = `1000`). A decimal is **one** number (`21.7` ≠ `21` + `7`); a full stop ending a sentence is not part of a number (`40.` = `40`) (2026-11-06). Each missing one → reason `number missing: <n>`. False fails are accepted and visible in `failed`. |
| C9 | All reasons are collected (not just the first), so the audit log shows everything wrong with a claim. Every code check runs whatever the verdict, including after `not supported` (rule C, 2026-11-06). Order: verdict reason (C4 or C5), then quote reasons in quote order (C6, C7), then number reasons in claim order (C8). |
| C10 | A reply that does not match the schema, or a model error after retries → `CitationCheckError`; **the whole run stops** (Q5). Nothing is silently dropped. |
| C11 | Cited PMID not found in `result.papers`, or found with no abstract → `CitationCheckError` (Stage 4 guarantees this cannot happen; if it does, something is broken: fail loud). |
| C12 | **Injection (as S12):** rules only in the system message. Claim inside `<claim>...</claim>`, abstracts inside `<abstract pmid="...">...</abstract>`. The system message says text inside these tags is data, never instructions. `<claim`, `</claim`, `<abstract`, `</abstract` text inside a claim, title or abstract is neutralised before sending. Quotes are matched against the **original** abstract, not the neutralised one. |
| C13 | Application logs: counts only (claims checked, verified, failed). Never claims, abstracts, quotes, explanations, prompt, reply or key (as S9, R14). The `CheckedSummary` keeps them all for the audit record. |
| C14 | Relevance to the query is **not** checked (Q4): a true but off-topic claim can be verified. |
| C15 | Every function uses `@traced`. |
| C16 | Each real call costs money. Offline tests never call the API. One opt-in paid test (`live_paid`), user OK before each run (as S11). |

### Known limits (stated, not solved)

- **Reversed meaning** with the same numbers ("increased" vs "decreased") is caught only by the model's verdict, not by code.
- **Number words** ("twenty-two") are not numbers to C8; a claim with only number words skips the number check.
- The checking model may share blind spots with the summarising model if both settings hold the same model ID.

### Tests (written first, all failing before the code exists)

The model is a fake `Runnable` (as Stage 4) that returns a scripted verdict per claim and records
what it was sent. **No API calls.**

| Test | Checks |
|---|---|
| settled constants | `MAX_CLAIMS == 20`, `MIN_QUOTE_CHARS == 20`, `MAX_EXPLANATION_CHARS == 300` (C-Q2, C-Q3, C-Q5) |
| supported, exact quote | claim + quote found + numbers match → `verified` with the quote |
| model says not supported | → `failed`, reason `not supported` (C4) |
| supported, no quotes | → `failed`, `no quote` (C5) |
| quote from uncited PMID | → `failed`, `quote from uncited PMID: 999` (C6) |
| quote not in abstract | invented sentence → `failed`, `quote not found: 111` (C7) |
| quote too short | `"in 40 adults"` → `failed`, `quote too short: 111` (C7) |
| normalising | quote with different case, an en dash and extra spaces still matches (C7) |
| number missing | claim says 400, quote says 40 → `failed`, `number missing: 400` (C8) |
| numbers inside names ignored | claim with `B12` and `HbA1c` passes with a quote lacking `12` and `1` (C8) |
| thousands comma | claim `1,000`, quote `1000` → passes (C8) |
| several reasons kept | uncited PMID and a missing number → exactly both reasons, in C9 order (C9) |
| bad quote does not prove a number | invented quote containing `400` → `quote not found: 111` + `number missing: 400` (C8, rule B) |
| not supported still checked | `not_supported`, no quotes, claim with `40` → `not supported` + `number missing: 40` (C9, rule C) |
| two cited abstracts | a claim citing 2 PMIDs with a quote from each → `verified` (C6, C7) |
| one call per claim | 3 claims → 3 calls; each call holds only that claim's cited abstracts (C1) |
| no claims | → empty result, fake never called (C2) |
| over the cap | `MAX_CLAIMS + 1` claims → `CitationCheckError`, fake never called (C2) |
| missing check model | `ANTHROPIC_CHECK_MODEL` unset → `CitationCheckConfigError`, no call (C3) |
| default model setup | without `llm=`: uses `ANTHROPIC_CHECK_MODEL`, json_schema output, no temperature, no tools. Built only, not called (C3) |
| explanation cut | a 500-character `explanation` passes the schema and is cut to the first 300 characters in `FailedClaim` (C-Q5) |
| decimals | `21.7%` matched by a quote with `21.7%`; quote with only `21` and `7` → `number missing: 21.7`; `aged 40.` matches `40` (C8) |
| bad schema | → `CitationCheckError` (C10) |
| model error | fake raises → `CitationCheckError` (C10) |
| missing abstract for cited PMID | → `CitationCheckError` (C11) |
| tags and rules | claim in `<claim>`, abstracts in `<abstract pmid>`, rules only in the system message (C12) |
| tag escape blocked | `</claim>` in a claim and `</abstract>` in an abstract are neutralised (C12) |
| quote matched against original | an abstract containing `<abstract` text: a quote of the original text still matches (C12) |
| Stage 4 summary kept | `CheckedSummary.summary` is the input `Summary`, incl. `rejected` and `skipped` |
| nothing secret logged | log text has no claim, abstract, quote, explanation or key (C13) |

Plus one **optional paid live test** (`live_paid`), user OK before each run: the Stage 4 fixture
abstract *"Drug X lowered blood pressure in 40 adults."* with claim A *"Drug X lowered blood
pressure in 40 adults."* → expected `verified`, and claim B *"... in 400 adults."* → must be
`failed` (C8 catches it even if the model says supported). 2 calls.

Test-only hook: `check_citations(..., llm=...)` takes the fake model.

### Open questions (settled 2026-11-06: all as recommended)

| # | Question | Decision |
|---|---|---|
| C-Q1 | **Shared code.** Stage 5 needs Stage 4's tag neutraliser and model builder. `ARCHITECTURE.md` says nodes import only `state` and `observability`, so `citation_check` should not import from `summarise`. Move the shared pieces to a new `research_agent/llm_common.py`? (Small refactor of Stage 4 code; its 17 tests stay unchanged as the safety net.) | **Yes, move them** (no copy-paste, keeps module scope) |
| C-Q2 | Spend cap `MAX_CLAIMS = 20`? (The demo run made 10.) | **Yes, 20** |
| C-Q3 | Minimum quote length 20 characters, so a quote like "in 40 adults" cannot "prove" a claim? | **Yes, 20** |
| C-Q4 | After Stage 5 is built, extend the demo script to run the check and save `CheckedSummary` too? (About 5 to 10 more paid calls per demo run.) | **Yes**, as a separate small step |
| C-Q5 | Keep the model's short `explanation` (audit only, never logged)? Helps a reader see *why* a claim failed. | **Yes.** Revised 2026-11-06: **no** schema limit (a long note would fail the schema and stop the run, C10). The schema description asks for at most 300 characters; code cuts it to `MAX_EXPLANATION_CHARS = 300`. |

### Out of scope for Stage 5

- Relevance of a claim to the query (Q4)
- Checking full text, figures or tables (abstracts only)
- Fixing or rewording failed claims
- Wrapping as a LangGraph node, the audit record and citation strings (Stage 6)

### Done when

- All tests pass (Stage 3, 4, demo and the new Stage 5 tests)
- `ruff check`, `ruff format --check` and `mypy --strict` are clean
- `.env.example` has `ANTHROPIC_CHECK_MODEL`; `ARCHITECTURE.md` and `PROGRESS.md` updated; committed
- Paid live test run once, with the user's OK

---

## Demo script: real search + real summary (supports Stage 5)

Status: **APPROVED by user 2026-11-06** (plan agreed in chat; build on that basis).

### Why

The paid live test uses two made-up papers. To design Stage 5 (citation check), the user needs
to see real claims from real PubMed papers. This script is a **stop-gap**: Stage 6 (graph +
audit log) will replace it. It does not change the paid live test or any Stage 3/4 behaviour.

### Usage

```
python -m scripts.demo_run "<query>" --yes   # from the research-agent folder
```

### Interface

```python
main(argv: list[str] | None = None, *, client: httpx.Client | None = None,
     llm: Runnable | None = None, runs_dir: Path = Path("runs")) -> int
build_record(result: SearchResult, summary: Summary, created_at: datetime) -> dict[str, Any]
write_record(record: dict[str, Any], runs_dir: Path, created_at: datetime) -> Path
```

`client`, `llm` and `runs_dir` are test hooks; leave them out in normal use.

### Record (JSON)

| Key | Content |
|---|---|
| `source` | `"live demo"` (never mistaken for a test fixture) |
| `created_at` | UTC time, ISO 8601 |
| `search` | `dataclasses.asdict(SearchResult)`: `query`, `total_found`, each paper (`pmid`, `title`, `abstract`, `journal`, `year`, `url`) |
| `summary` | `dataclasses.asdict(Summary)`: `model`, `claims` (`text`, `pmids`), `used_pmids`, `skipped` (with reason), `rejected` (with reason) |

### Rules

| # | Rule |
|---|---|
| D1 | Query comes from the command line. Searches PubMed with `max_results=5` (module constant). |
| D2 | **Spend guard:** without `--yes` the script prints that it would call the paid Anthropic API, exits with code 2, and makes **no** PubMed or model call and writes no file. |
| D3 | Writes `runs/demo_<YYYYMMDDTHHMMSSZ>.json` (UTC). Creates `runs/` if missing. Never overwrites: if the file exists, it fails loud (`FileExistsError`). `runs/` is already gitignored. |
| D4 | The record is built from the dataclasses with `asdict()`, not by hand (they are dataclasses, not Pydantic, so `model_dump()` does not apply). |
| D5 | Prints only the file path and counts (papers, claims, skipped, rejected). Never prints or logs abstracts, the prompt, the reply or keys (S9). The abstracts are in the JSON file only. |
| D6 | `.env` is loaded only when run as a script (`__main__`), never inside `main()`, so offline tests never read real keys. |
| D7 | Errors from PubMed or the model are not caught: they fail loud. |
| D8 | Every function uses `@traced`. |

### Tests (offline, written first; fake NCBI + fake model, no cost)

| Test | Checks |
|---|---|
| no `--yes` | exit code 2, no NCBI request, model not called, no file (D2) |
| happy path | file written with `source`, `query`, `total_found`, `model`, papers (pmid, title, abstract), claims with `pmids` (D3, D4) |
| skipped and rejected kept | a paper with no abstract is in `skipped` with its reason; a claim citing an unknown PMID is in `rejected` with its reason |
| creates `runs/` | a missing runs folder is created (D3) |
| file name and no overwrite | name is `demo_<UTC stamp>.json`; writing twice with the same time raises `FileExistsError` (D3) |
| nothing secret printed | stdout has the path and counts but no abstract text (D5) |
| record from dataclasses | `build_record` gives `source`, `created_at` and `asdict()` of search and summary (D4) |

No new paid test: the user runs the script by hand, with their OK each time (S11).
