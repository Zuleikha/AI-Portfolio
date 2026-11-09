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
| `tools/pubmed.py` | Search PubMed (relevance order), return `Paper`s with authors, DOI and link | `observability` only | 3, 3r |
| `observability.py` | `@traced` decorator, writes to `runs/trace.log` | standard library only | 3 |
| `state.py` | Shared types passed between nodes (`Summary`, `CheckedSummary` and their parts); graph state added in Stage 6 | `tools` (for `Paper`) | 4 to 6 |
| `nodes/search.py` | Graph node that calls the PubMed tool | `tools`, `state`, `observability` | 6 |
| `llm_common.py` | Shared Claude helpers: env settings, chat model builder, tag neutraliser | `observability` only | 5 (C-Q1) |
| `nodes/summarise.py` | Graph node: summary with PMID citations | `state`, `llm_common`, `observability`; `tools` (types: `Paper`, `SearchResult`) | 4 |
| `nodes/citation_check.py` | Graph node: verifies every claim (model verdict + quote and number checks) | `state`, `llm_common`, `observability`; `tools` (types: `Paper`, `SearchResult`) | 5 |
| `audit/run_log.py` | Writes one audit record per run | `state`, `observability` | 6 |
| `graph.py` | Connects the nodes (LangGraph) | `nodes`, `state`, `audit` | 6 |
| `scripts/demo_run.py` | Stop-gap demo: real search + summary → `runs/demo_<UTC>.json` (paid, needs `--yes`). Replaced by Stage 6 | `tools`, `nodes.summarise`, `observability` | demo |

**Rules**

- Dependencies point one way: `graph` → `nodes` → `tools`. A tool never imports a node.
- A node never imports another node. Types shared between nodes live in `state.py`; each node re-exports its own result types, so `nodes.summarise.Summary` etc. still work.
- Only `tools/` talks to NCBI. Only `nodes/summarise.py` and `nodes/citation_check.py` talk to Claude.
- Data leaves the project only through those two external calls. Everything else stays on local disk.

## Config

All settings come from environment variables (`.env`, template in `.env.example`):
`NCBI_EMAIL`, `NCBI_API_KEY` (optional), `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`,
`ANTHROPIC_CHECK_MODEL` (Stage 5).

## Not in this design

Web UI, database, deployment, PMC full text. Each needs a PRD change first.
