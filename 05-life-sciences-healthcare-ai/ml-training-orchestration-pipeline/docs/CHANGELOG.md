# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0]

Initial release.

### Added

- Nine-stage Dagster asset pipeline: config resolution, dataset ingestion,
  independent cleaning of both splits, tokenisation, pretrained model setup and
  fine-tuning with inline evaluation.
- Transformer fine-tuning through a HuggingFace `Trainer` wrapper, supporting
  both a single run and a grid search over a hyperparameter space.
- MLflow tracking of parameters, metrics and artefacts for every run, with grid
  search trials logged as nested runs.
- Evaluation reporting accuracy, weighted F1, precision and recall, written to
  `docs/eval_results.json` and logged to MLflow.
- FastAPI serving layer with `/predict`, `/train`, `/train/status/{run_id}`,
  `/health` and `/metrics`.
- Non-blocking training: `POST /train` returns a `run_id` immediately and the
  run proceeds in the background.
- Prometheus instrumentation — request counters, error counters and a
  prediction-latency histogram.
- Drift detection running as a post-response background task: KS-test on input
  features, chi-square on the prediction distribution.
- `pydantic-settings` environment configuration alongside a YAML pipeline
  config that a training request can override.
- Docker image and a Compose file bringing up the API, the Dagster UI and the
  MLflow UI together.
- Tests covering the serving layer, data processing, the model manager and
  pipeline integration, with the model and orchestration mocked.
