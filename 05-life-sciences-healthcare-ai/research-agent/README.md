# Research Agent (in progress)

A LangGraph agent that searches PubMed, summarises the findings, checks every
claim against its citations, and writes an audit record for each run.

**Status:** personal project, under construction. Not deployed. See `docs/PROGRESS.md`.

## Docs

| File | What it covers |
|---|---|
| `docs/PRD.md` | What each stage must do (the spec) |
| `docs/ARCHITECTURE.md` | Modules, data flow, scope rules |
| `docs/PROGRESS.md` | Stage checklist and session log |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your own values
pytest
```

Uses public PubMed data only. No patient data.
