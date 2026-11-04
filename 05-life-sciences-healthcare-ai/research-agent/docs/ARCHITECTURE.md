# Research Agent: Architecture

Status: **DRAFT** (2026-11-04). Spec: `docs/PRD.md`.

## Flow

```
query
  │
  ▼
[search node] ──uses──▶ tools/pubmed.py ──HTTP──▶ NCBI E-utilities (free, public)
  │
  ▼
[summarise node] ──▶ Claude (Anthropic API, paid; cost cap set by user)
  │
  ▼
[citation_check node] ──▶ checks each claim against the abstracts of its cited PMIDs
  │
  ▼
audit/run_log.py ──▶ runs/<run-id>.json (on disk, gitignored)
```

## Modules and scope

| Module | Job | May import | Stage |
|---|---|---|---|
| `tools/pubmed.py` | Search PubMed, return `Paper`s | `observability` only | 3 |
| `observability.py` | `@traced` decorator, writes to `runs/trace.log` | standard library only | 3 |
| `state.py` | Shared graph state (typed) | `tools` (for `Paper`) | 4 to 6 |
| `nodes/search.py` | Graph node that calls the PubMed tool | `tools`, `state`, `observability` | 6 |
| `nodes/summarise.py` | Graph node: summary with PMID citations | `state`, `observability` | 4 |
| `nodes/citation_check.py` | Graph node: verifies every claim | `state`, `observability` | 5 |
| `audit/run_log.py` | Writes one audit record per run | `state`, `observability` | 6 |
| `graph.py` | Connects the nodes (LangGraph) | `nodes`, `state`, `audit` | 6 |

**Rules**

- Dependencies point one way: `graph` → `nodes` → `tools`. A tool never imports a node.
- Only `tools/` talks to NCBI. Only `nodes/summarise.py` and `nodes/citation_check.py` talk to Claude.
- Data leaves the project only through those two external calls. Everything else stays on local disk.

## Config

All settings come from environment variables (`.env`, template in `.env.example`):
`NCBI_EMAIL`, `NCBI_API_KEY` (optional), `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`.

## Not in this design

Web UI, database, deployment, PMC full text. Each needs a PRD change first.
