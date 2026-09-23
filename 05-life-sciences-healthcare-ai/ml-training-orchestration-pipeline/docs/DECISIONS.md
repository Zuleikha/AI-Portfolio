# Decisions

Why the system is built the way it is. Each entry states the alternative that
was rejected and what the choice costs, because a decision with no cost is
usually a decision that was never made.

## Dagster assets, not ops or jobs

An `@op`/`@job` DAG models *what ran*. An `@asset` graph models *what exists*.
The second is the better fit here: the tokenised dataset either exists and is
current, or it does not. Re-running after a learning-rate change should re-use
it rather than re-download IMDB.

**Cost:** assets are a heavier mental model than a task queue, and the framework
is opinionated about how state is tracked.

## MLflow, not Weights & Biases

MLflow runs against a local file store with no account, no API key and no
network. That keeps the project cloneable and runnable by anyone.

**Cost:** no hosted comparison UI out of the box, and the local store has no
concept of team access.

## `BackgroundTasks`, not a task queue

Training takes minutes to hours, so `POST /train` returns a `run_id`
immediately and the caller polls. A Celery or RQ worker would be the
industrial answer, but it adds a broker, a worker process and a deployment
topology to a system that runs as one container.

**Cost:** the run registry is in-memory. It is lost on restart, and with more
than one replica a poll can hit a process that never saw the run. This is the
single largest thing standing between the current design and a multi-instance
deployment.

## pandas cleaning, not a validation framework

Null-drops and length filters, written directly. Great Expectations or Pandera
would give schema contracts and a validation report.

**Cost:** a change in the upstream dataset's shape passes through silently. This
is a real gap, not a preference — see [ROADMAP.md](ROADMAP.md).

## Prometheus, not a drift-monitoring product

Counters, histograms and a `/metrics` endpoint, plus a hand-written
`DriftDetector` using a KS-test on features and chi-square on the prediction
distribution. Evidently would have provided richer reports.

**Cost:** no drift dashboard, and the statistical tests are the two obvious ones
rather than a considered suite.

## `pydantic-settings` plus YAML, not one or the other

Environment variables carry deployment-specific values and are type-validated
at import. `config/pipeline.yaml` carries the hyperparameters a run mutates.

**Cost:** two places to look for configuration. The split is deliberate —
secrets and environment never belong in a file that an API endpoint rewrites —
but it has to be explained, which is what this paragraph is for.

## A single serving implementation

There is one FastAPI app, `src/api.py`. Keeping a second "deployment" variant
alongside it would mean two files drifting apart and no clear answer to which
one runs in production.

**Cost:** the drift-detection integration and the serving layer now live in the
same module rather than being separable.

## Model artefacts stay out of git

`models/`, `data/` and `mlruns/` are ignored. A trained bundle is a build
output: several hundred megabytes, binary, and reproducible from `POST /train`.

**Cost:** a fresh clone cannot serve until it has trained something. `/predict`
returning 503 on a clean checkout is the visible consequence, and it is tested
rather than hidden.
