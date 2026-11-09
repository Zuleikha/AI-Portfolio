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
