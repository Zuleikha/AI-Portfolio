# ML Training Orchestration Pipeline

An end-to-end training system: one API call downloads a dataset, cleans it,
tokenises it, fine-tunes a transformer, evaluates it, and hands the resulting
bundle to a serving layer that monitors its own inputs for drift.

The pipeline is expressed as Dagster **assets** rather than a task DAG, so each
stage is a materialised artefact with lineage, not a step that ran once.

## The task

**Adverse drug event (ADE) detection** — given a sentence from a MEDLINE case
report, decide whether it describes an adverse reaction to a drug. This is the
core classification step behind pharmacovigilance, the regulated process by which
drug safety signals are found in literature and case reports.

The pairing is deliberate: the dataset is drawn from biomedical literature, and
**BiomedBERT** (formerly PubMedBERT) is pretrained on PubMed abstracts and PMC
full text — the same corpus family. `bert-base-uncased` is kept in
`config/config.yaml` as the general-domain baseline, because a domain model is
only worth its cost if it beats one.

| | |
|---|---|
| Dataset | `SetFit/ade_corpus_v2_classification` — 17,637 train / 5,879 test |
| Labels | binary: `0 = Not-Related`, `1 = Related` |
| Class balance | ~71% / 29% — report precision and recall, not accuracy alone |
| Licence | ⚠️ **not declared upstream.** Used for training only; see "Data provenance" |

## Stack

| Concern | Choice |
|---|---|
| Orchestration | Dagster `@asset` + `Definitions` |
| Training | HuggingFace `Trainer`, `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext` |
| Dataset | ADE Corpus V2 — adverse drug event classification, via HuggingFace Datasets |
| Experiment tracking | MLflow (local file store by default) |
| Serving | FastAPI + `BackgroundTasks` |
| Monitoring | `prometheus-client` counters and histograms; KS-test drift detection |
| Config | `pydantic-settings` + YAML |

## The nine stages

```
pipeline_config ─► dataset_info ─► raw_dataset
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
     processed_train_data                            processed_test_data
              └───────────────────────┬───────────────────────┘
                                      ▼
                       model_config ─► pretrained_model_setup
                                      ▼
                              training_datasets
                                      ▼
                               trained_model  ──► MLflow run + models/trained_model/
                                      ▼
                              FastAPI /predict
```

Each box is a Dagster asset in `src/dagster_definitions.py`. Re-materialising
one re-computes only what depends on it.

Open [docs/architecture.html](docs/architecture.html) in a browser for the
diagram, or [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the detail.

## Run it

```bash
pip install -e ".[dev]"
```

Three surfaces, all optional to each other:

```bash
# Serving API           → http://localhost:8000/docs
uvicorn src.api:app --reload

# Orchestration UI      → http://localhost:3000
dagster dev -f src/dagster_definitions.py

# Experiment tracking   → http://localhost:5000
mlflow ui
```

Or bring all three up together:

```bash
docker compose up
```

### Train a model

```bash
curl -X POST http://localhost:8000/train \
  -H "Content-Type: application/json" \
  -d '{"dataset_name": "SetFit/ade_corpus_v2_classification", "sample_size": 500, "epochs": 1, "batch_size": 16}'
```

Returns a `run_id` immediately — training runs in the background. Poll it:

```bash
curl http://localhost:8000/train/status/<run_id>
```

Watch the same run materialise stage by stage in the Dagster UI, and compare it
against previous runs in MLflow.

### Predict

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"texts": ["This film was a masterpiece."], "return_probabilities": true}'
```

## API

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness and whether a model bundle is loaded |
| `GET` | `/metrics` | Prometheus exposition format |
| `POST` | `/predict` | Sentiment predictions, optionally with class probabilities |
| `POST` | `/train` | Start a run in the background, return a `run_id` |
| `GET` | `/train/status/{run_id}` | Poll a run |

## No model in the repo

`models/` is empty and git-ignored. A trained bundle is a build output, not
source — it is several hundred megabytes, it is reproducible from `POST /train`,
and a checked-in binary would be stale the moment anything upstream changed.
The same applies to `data/` and `mlruns/`.

Until a run completes, `/predict` returns `503` by design. That is the honest
state of an untrained deployment, and it is covered by a test.

## Tests

```bash
pytest -q
```

The model and the orchestration layer are mocked, so the suite needs no GPU, no
dataset download, and no trained bundle.

## Repository layout

```
src/dagster_definitions.py   all nine assets and the Definitions object
src/api.py                   FastAPI serving layer
src/config.py                pydantic-settings loader
src/data/                    ingestion, processing, HuggingFace helpers
src/training/                MLflow-tracked Trainer wrapper
src/evaluation/              metrics and evaluation plots
src/models/                  model manager and registry integration
src/monitoring/              KS-test and chi-square drift detection
config/                      pipeline hyperparameters, Dagster and project config
scripts/                     Dagster launcher, full-pipeline CLI runner
```

## Data provenance

The ADE Corpus V2 dataset carries **no declared licence** — neither the canonical
`ade-benchmark-corpus/ade_corpus_v2` repository nor the `SetFit` mirror states one.
It is used here for **model training only**. The corpus is not vendored into this
repository; it is downloaded from the Hugging Face Hub at run time and cached
locally. No derived dataset is redistributed.

Underlying source: MEDLINE case reports, annotated by Gurulingappa et al. (2012).

⚠️ Note for reuse: `datasets >= 5.0` rejects bare dataset ids. Loading
`ade_corpus_v2` fails with `HfUriError`; use the namespaced id
`ade-benchmark-corpus/ade_corpus_v2`, or the pre-split `SetFit` mirror this
pipeline defaults to.

## Known limits

Drift is detected and recorded but does not trigger retraining — the feedback
loop is open. Training-run state is in-memory and lost on restart. Both are in
[docs/ROADMAP.md](docs/ROADMAP.md) with the rest of the backlog.

## Licence

MIT — see [LICENSE](LICENSE).
