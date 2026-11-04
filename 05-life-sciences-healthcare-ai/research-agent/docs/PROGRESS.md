# Research Agent: Progress

## Project goal

Build a LangGraph agent that searches PubMed, summarises the findings, checks every claim against its citations, and writes an audit record for each run.

## Docs

- Spec: `docs/PRD.md` · Architecture: `docs/ARCHITECTURE.md` · Overview: `README.md`

## Stages

- [x] 1. Check the repo and set up the folder structure
- [x] 2. Set up the environment and install LangGraph
- [ ] 3. Build the PubMed search tool **(built: 23 tests green, ruff + mypy clean; NOT committed)**
- [x] 4. Build the summarise step **(42 tests green, ruff + mypy clean; ⚠️ paid live test NOT yet run)**
- [ ] 5. Build the citation check step
- [ ] 6. Connect the steps into a graph, add the audit log, and run it
- [ ] 7. Add tracing with Langfuse or LangSmith

## Session log

| Date | What was done | Next step |
|------|---------------|-----------|
| 2026-11-03 | Inspected the AI-Portfolio repo and created the `research-agent/` scaffold: placeholder modules, `.env.example`, `requirements.txt`, `.gitignore` (ignores `.env` and `runs/`). No agent logic yet. | Stage 2: create a virtual environment, pin and install requirements, confirm LangGraph imports. |
| 2026-11-03 | Stage 2: venv on Python 3.14.4 (installed python3.14-venv). Pinned packages in requirements.txt. Added ANTHROPIC_MODEL to .env.example. Haiku test call worked. | Stage 3: PubMed search tool |
| 2026-11-04 | Added missing docs: `docs/PRD.md` (goal + full Stage 3 spec: interface, rules R1 to R10, 13 offline tests), `docs/ARCHITECTURE.md` (modules, import rules, data flow), `README.md`. No code yet. | User approves the Stage 3 spec, then write the failing tests (TDD). |
| 2026-11-04 | Stage 3 spec approved. Added ruff 0.17.3 + mypy 2.4.1, `pyproject.toml` (pytest/ruff/mypy strict config). Wrote failing tests: `tests/test_pubmed.py` (13 + 1 opt-in live), `tests/test_observability.py` (4), `tests/conftest.py`. Red: ImportError (no code yet). Tests lint-clean. | Build `research_agent/observability.py` + `tools/pubmed.py` until tests pass; then ruff + mypy clean; commit. |
| 2026-11-04 | Spec back to DRAFT (user: not approved). PRD: `SearchResult(papers, total_found, query)`, default `max_results=5`. ruff + mypy moved to `requirements-dev.txt`. Tests updated to `SearchResult` (+ total-above-max and default-5 tests); still red (ImportError). | User reviews PRD Stage 3 and lists the other earlier changes; approve, then build. |
| 2026-11-04 | Stage 3 spec APPROVED by user. PRD: whole-project stages table; `@traced` creates `runs/` if missing, `runs/trace.log` gitignored (existing `runs/` rule). Added test for missing `runs/`. Red: 16 pubmed + 5 observability tests fail at import. | Build `observability.py` + `tools/pubmed.py` until green; ruff + mypy clean; ask before commit. |
| 2026-11-04 | Built `research_agent/observability.py` and `tools/pubmed.py` to the approved spec. 23 passed (1 live deselected); ruff check, ruff format --check, mypy --strict clean. Found httpx logs full URLs (incl. api_key/email) at INFO, so added a redaction filter on the `httpx` logger (R8); verified the R8 test fails without it. | User reviews; on OK commit Stage 3 (Definition of Done). Optional: run live test `pytest -m live`. |
| 2026-11-04 | Live test: found it used the conftest fake email (`.env` never loaded). Fixed conftest: `live` tests read real NCBI settings from `.env`; live test asserts email is not the fake. `pytest -m live`: 1 passed (BRCA1 query, total_found 16,705). Offline: 23 passed. ruff/mypy clean. | User OK → commit Stage 3. Then Stage 4 spec. |
| 2026-11-04 | Stage 4 spec drafted in `docs/PRD.md` (DRAFT, NOT approved). Checked langchain-anthropic docs via Context7. No tests, no code. | User reviews Stage 4 spec. |
| 2026-11-04 | Stage 4: added open questions Q1 (reject-only-bad-claim list vs fail whole summary) and Q2 (abstracts are data, not instructions). Still DRAFT. | User answers Q1, Q2. |
| 2026-11-04 | Committed Stage 3 PRD boundary-test row only (`f4efb06`, not pushed). Stage 4 draft: Q1 + Q2 recommendations (yes; reject-whole mixed claims; layered injection defence S12); `rejected` list, 7 test rows added/changed. Still DRAFT. | User decides Q1/Q2; approve Stage 4; push `f4efb06` on OK. |
| 2026-11-04 | Stage 4 spec APPROVED (Q1 + Q2 yes). Pushed `f4efb06`. Stage 4 PRD not committed yet. | Write Stage 4 failing tests (tests/test_summarise.py), show red. |
| 2026-11-04 | Stage 4 failing tests: `tests/test_summarise.py` (16 offline + 1 `live_paid`). conftest: offline fake ANTHROPIC_MODEL, no API key; `live_paid` loads real Anthropic settings. pyproject: `live_paid` marker, excluded by default. Red: ImportError. Stage 3: 25 passed. Added PRD row "skipped PMID cited". | User OK → build `nodes/summarise.py`. |
| 2026-11-04 | Built `nodes/summarise.py`. 42 passed (25 Stage 3 + 17 Stage 4), 2 deselected (live, live_paid). ruff + mypy --strict clean (enabled pydantic mypy plugin; test imports ChatAnthropic directly, typing only). `-m live` collects only the NCBI test. Paid test NOT run. | User: commit, run paid test (OK needed), or review. |
| 2026-11-04 | Stage 4 committed and pushed. ⚠️ Paid live test (`pytest -m live_paid`) NOT yet run: needs user OK (costs money). | Stage 5 spec (citation check); optionally run the paid live test with user OK. |
