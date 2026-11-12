# Research Agent

A LangGraph agent that searches PubMed, summarises the findings, checks every
claim against its citations, and writes an audit record for each run.

**Status:** personal project, complete (Stages 1 to 7). Not deployed. See `docs/PROGRESS.md`.

## Demo

![One real run: search, summarise, check, audit record](docs/demo.gif)

One real run (2026-11-12), recorded with asciinema (`docs/demo.cast`). The intro and heading
are added to the recording; the run output is unchanged.

## What this project demonstrates

*PERSONAL PROJECT EXPERIENCE · not deployed*

| Capability | Evidence |
|---|---|
| Checkable LLM output | Claude must quote its source; code checks every quote and number (`nodes/citation_check.py`) |
| System design | 3-step LangGraph flow, typed state, import rules (`docs/ARCHITECTURE.md`) |
| Safety | Spend guard, call caps, injection warnings, secrets redacted |
| Audit | One JSON record per run, even on failure; opt-in LangSmith tracing |
| Discipline | Spec approved before each stage; tests first; real-run bugs fixed (K2 to K4) |

Transferable to literature review: every statement traces back to a source.

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

## Run the agent (costs money)

Real PubMed search (5 papers) → Claude summary → citation check of every claim.
Prints the verified claims with their citations and saves a full audit record to
`runs/<run id>.json` (gitignored). Calls the paid Anthropic API (at most 21 calls per run),
so it refuses to run without `--yes`.

```bash
python -m research_agent "metformin side effects" --yes
```

The graph diagram is in `docs/ARCHITECTURE.md`. To redraw it after changing the graph
(free, no API call):

```bash
python -m scripts.draw_graph
```

Uses public PubMed data only. No patient data.
