# AGENTS.md

Instructions for AI coding agents working in this repository.

## What this is

A Dagster-orchestrated transformer fine-tuning pipeline with MLflow tracking
and a FastAPI serving layer.

## Ground rules

- **No hardcoded config.** Deployment values come from `src/config.py`
  (`pydantic-settings`); pipeline hyperparameters come from
  `config/pipeline.yaml`. Never put a credential in the YAML — `POST /train`
  rewrites that file.
- **No `print()` in `src/`.** Use `logging.getLogger(__name__)`. The API runs
  under uvicorn where stdout is not structured.
- **New assets must be added to `all_assets`** in `src/dagster_definitions.py`.
  An asset missing from that list is invisible to both the Dagster UI and the
  `materialize()` call `/train` triggers.
- **Prometheus collectors stay at module scope.** The client registry is global;
  constructing a collector inside a function raises a duplicate-registration
  error on the second call.
- **One serving implementation.** `src/api.py` is the entry point. Do not add a
  parallel API module.

## Before you commit

```bash
ruff check .
ruff format --check .
pytest -q
```

All three must pass. The suite mocks the model and the orchestration layer, so
a failure is a real failure — it does not mean you are missing a GPU.

## Files that need care

| File | Why |
|---|---|
| `src/dagster_definitions.py` | The whole pipeline; an asset signature change breaks materialisation |
| `src/api.py` | The HTTP contract and the model cache |
| `config/pipeline.yaml` | Rewritten in place by `POST /train` — never edit while a run is active |
| `workspace.yaml` | How Dagster finds the definitions |

## What not to commit

`models/`, `data/`, `mlruns/`, `dagster_home/` and `monitoring_results/` are
git-ignored and must stay that way. They are training outputs — large, binary
and reproducible. Never `git add -f` them.

## Testing conventions

- The model and `materialize()` are mocked. Tests must not download a dataset,
  train anything, or require a GPU.
- `/predict` returning 503 on an untrained system is expected behaviour with a
  test pinning it. Do not "fix" it by shipping a model bundle.

## Decisions

`docs/DECISIONS.md` records why the system is shaped this way, including what
each choice costs. If you reverse one of those decisions, update that file in
the same change.
