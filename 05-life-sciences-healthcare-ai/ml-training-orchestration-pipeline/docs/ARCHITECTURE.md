# Architecture

## Two entry points, one pipeline

```
                    ┌─────────────────────────────────────────┐
  POST /train ──────►  FastAPI (src/api.py)                   │
                    │    patches config/pipeline.yaml         │
                    │    BackgroundTasks ─► materialize()     │
                    └───────────────────┬─────────────────────┘
                                        │
  dagster dev ──────────────────────────┤ same assets, either way
                                        ▼
                    ┌─────────────────────────────────────────┐
                    │  Dagster assets (src/dagster_definitions)│
                    │                                          │
                    │  pipeline_config → dataset_info          │
                    │      → raw_dataset                       │
                    │      → processed_train_data              │
                    │        processed_test_data               │
                    │      → model_config                      │
                    │      → pretrained_model_setup            │
                    │      → training_datasets                 │
                    │      → trained_model ───────┐            │
                    └─────────────────────────────┼────────────┘
                                                  │
                          ┌───────────────────────┼──────────────┐
                          ▼                       ▼              ▼
                   models/trained_model/    MLflow run    docs/eval_results.json
                          │
                          ▼
                   ModelService (hot-reloaded by the API)
                          │
  POST /predict ──────────┴──► predictions ──► DriftDetector (background task)
```

The same nine assets run whether they were triggered by an HTTP call or by a
human clicking **Materialize** in the Dagster UI. There is no second code path.

## The nine assets

| # | Asset | Produces | Notes |
|---|---|---|---|
| 1 | `pipeline_config` | Parsed config dict | Read from `config/pipeline.yaml` at run time |
| 2 | `dataset_info` | Dataset metadata | Resolves the HuggingFace dataset reference |
| 3 | `raw_dataset` | `data/processed/*.parquet` | Downloads from the HuggingFace Hub |
| 4 | `processed_train_data` | Cleaned train split | Null-drop, length filter (10–5000 chars) |
| 5 | `processed_test_data` | Cleaned test split | Same rules, applied independently |
| 6 | `model_config` | Model hyperparameters | Architecture, labels, sequence length |
| 7 | `pretrained_model_setup` | `models/pretrained/` | Downloads base weights and tokenizer |
| 8 | `training_datasets` | `data/processed/tokenized/` | Arrow datasets, tokenised for both splits |
| 9 | `trained_model` | `models/trained_model/` + MLflow run | Fine-tunes, evaluates, logs, saves the bundle |

Assets over ops matters here: Dagster tracks *what exists* rather than *what
ran*. Re-materialising `trained_model` after changing only the learning rate
reuses the tokenised datasets instead of re-downloading IMDB.

## Module map

| Module | File | Responsibility |
|---|---|---|
| Orchestration | `src/dagster_definitions.py` | All nine assets and the `Definitions` object |
| Serving | `src/api.py` | HTTP routes, `ModelService`, Prometheus instrumentation |
| Config | `src/config.py` | `pydantic-settings` loader plus YAML pipeline config |
| Data | `src/data/` | Ingestion, `TextDataProcessor`, HuggingFace helpers |
| Training | `src/training/trainer.py` | `MLOpsTrainer` — MLflow-tracked standard and grid-search training |
| Evaluation | `src/evaluation/evaluator.py` | Accuracy, weighted F1, precision, recall, plots |
| Registry | `src/models/model_manager.py` | `ModelManager`, `HuggingFaceModel`, `CustomModel` |
| Monitoring | `src/monitoring/drift_detector.py` | KS-test on features, chi-square on prediction distribution |

## The serving bundle

The API loads `models/trained_model/` at startup. The minimum viable bundle is:

| File | Without it |
|---|---|
| `model.safetensors` | `/predict` returns 503 — no weights |
| `config.json` | `AutoModelForSequenceClassification.from_pretrained()` raises |
| `tokenizer.json` | `AutoTokenizer.from_pretrained()` raises — no tokenisation |
| `tokenizer_config.json` | Tokenizer loads with the wrong special tokens |

`training_args.bin` and `training_summary.yaml` are also written. Neither is
needed to serve; the first lets a run be resumed, the second is human-readable
provenance.

The bundle is cached in memory at startup, so replacing the files on disk does
nothing until the process restarts.

## Asynchronous training

`POST /train` cannot block — a fine-tuning run takes minutes to hours. It
therefore writes a `run_id` into an in-memory registry, hands the work to
`BackgroundTasks`, and returns immediately. The caller polls
`/train/status/{run_id}`.

The trade-off taken: that registry is a plain dict. It is lost on restart and
never evicted. For a single-instance deployment that is acceptable and
documented; for more than one replica it is wrong, because a poll can land on a
process that never saw the run.

## Observability

Prometheus counters and histograms are defined at module scope in `src/api.py`
and exposed at `/metrics` in exposition format: request counts per route, error
counts, and a prediction-latency histogram.

Drift detection runs as a background task on each prediction. It compares the
incoming feature distribution against the training reference with a
Kolmogorov–Smirnov test, and the prediction distribution with a chi-square test.
Results accumulate in `monitoring_results/drift_history.json`.

Nothing consumes that signal automatically — see [ROADMAP.md](ROADMAP.md).

## What is not in the repository

`models/`, `data/` and `mlruns/` are git-ignored. They are outputs of a
training run: large, binary, and fully reproducible from `POST /train`. A
checked-in model bundle would be stale the moment any upstream asset changed,
and would put a several-hundred-megabyte binary in a repository people clone to
read the code.
