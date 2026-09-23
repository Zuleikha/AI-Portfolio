# Design Notes

Implementation detail behind the components in [ARCHITECTURE.md](ARCHITECTURE.md).

## Configuration in two layers

| Layer | File | Holds | Changed by |
|---|---|---|---|
| Environment | `.env` → `src/config.py` | Paths, tracking URI, tokens, log level | Deployment |
| Pipeline | `config/pipeline.yaml` | Dataset, hyperparameters, sequence length | A training request |

The split exists because `POST /train` rewrites the pipeline config in place
before materialising. Anything an API endpoint can rewrite must not be anywhere
near a credential.

`src/config.py` validates the environment layer at import via
`pydantic-settings`, so a malformed path fails at startup rather than three
stages into a training run.

## Data cleaning

Both splits are cleaned independently — the test split never sees a statistic
derived from the training split. Two rules:

- Drop rows with null text or null label.
- Keep text between 10 and 5000 characters. Below 10 there is no signal; above
  5000 the text is truncated at tokenisation anyway, so the extra characters
  cost memory for nothing.

These are pandas operations, not a schema contract. The limitation is recorded
in [DECISIONS.md](DECISIONS.md).

## Tokenisation as its own asset

`training_datasets` tokenises both splits and persists Arrow datasets to disk.
It is a separate asset rather than a step inside training, because tokenisation
is deterministic given the tokeniser and the cleaned data — so changing the
learning rate should not repeat it. This is the concrete payoff of the asset
model over a task DAG.

## Training

`MLOpsTrainer` wraps the HuggingFace `Trainer`. Around each run it opens an
MLflow run and logs parameters, metrics and artefacts, so a run that crashes
mid-training still leaves a record of what was attempted.

Two modes: a single standard run, and a grid search over a hyperparameter space.
The grid search logs each trial as a nested MLflow run.

## Evaluation

Accuracy, weighted F1, precision and recall. Weighted rather than macro because
the IMDB split is balanced but the pipeline is meant to survive a dataset that
is not — with an imbalanced set, macro F1 and accuracy tell contradictory
stories and weighted F1 stays interpretable.

Results are written to `docs/eval_results.json` and logged to MLflow. The JSON
file is the last run; MLflow is the history.

## Serving

`ModelService` loads the bundle once at startup and holds it in memory. Loading
per request would add seconds of latency; loading lazily would move the failure
from startup into the first user's request.

The consequence is that a new bundle on disk is invisible until restart. That is
the correct trade-off for a service that should not silently change behaviour
mid-flight, but it means deploying a model is a restart, not a file copy.

`/predict` returns `503` when no bundle is loaded, with a message naming
`/train`. A fresh clone has no model, so this is a normal state rather than an
error condition — and it is covered by a test.

## Metrics

Prometheus collectors are module-level in `src/api.py`. That is deliberate:
Prometheus client collectors register globally, so constructing them inside a
factory or a request handler raises a duplicate-registration error the second
time round.

The histogram wraps only the forward pass, not the whole request, so the number
reported is model latency rather than model latency plus JSON serialisation.

## Drift detection

Runs as a background task after the response is returned, so it never adds to
request latency.

- **Feature drift:** two-sample Kolmogorov–Smirnov test against the training
  reference distribution. Non-parametric, so it needs no assumption about
  shape.
- **Prediction drift:** chi-square over the predicted class distribution. A
  model whose output mix has shifted is worth knowing about even when the
  inputs look unchanged.

Both write to `monitoring_results/drift_history.json`. Nothing consumes it yet.

## Error handling

Training failures are caught per run and recorded against the `run_id`, so a
failed run reports `failed` with its error rather than vanishing. Prediction
failures increment the error counter and return `500`.
