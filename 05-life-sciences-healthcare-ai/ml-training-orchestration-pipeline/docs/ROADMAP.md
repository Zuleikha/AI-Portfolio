# Roadmap

Known gaps, ordered by what would break first under real use. Each entry names
the files involved so the work is actionable rather than aspirational.

## Blocking a shared deployment

### `/train` accepts unbounded parameters
`TrainingRequest` has no upper limits. `sample_size=10**9` or `epochs=1000`
will exhaust the host, and there is no authentication in front of the endpoint.

- **Files:** `src/api.py`
- **Approach:** Pydantic `ge`/`le` constraints (`sample_size ≤ 10_000`,
  `epochs ≤ 5`, `batch_size ≤ 64`), plus an API-key dependency on the mutating
  routes.

### Concurrent training runs corrupt the shared config
`_run_pipeline` rewrites `config/pipeline.yaml` in place and then trains. Two
runs queued close together interleave read-modify-write and produce a corrupted
config — with no error, just a run trained on the wrong hyperparameters.

- **Files:** `src/api.py`
- **Approach:** short term, a module-level lock that returns `409` while a run
  is active. Long term, pass overrides through Dagster run config instead of
  mutating a file on disk.

### `dataset_name` is accepted and silently ignored
`_run_pipeline` patches `sample_size`, `epochs` and `batch_size` only. A request
naming a different dataset trains on whatever the YAML already said, and reports
success.

- **Files:** `src/api.py`
- **Approach:** patch `config["data"]["huggingface"]["dataset_name"]` too, or
  drop the field. Right now the API does not do what its schema claims.

## Serving performance

### Blocking inference on the async event loop
`predict` is `async def`, but the torch forward pass is CPU-bound and
synchronous, so every concurrent request stalls behind it.

- **Files:** `src/api.py`
- **Approach:** make the handler a plain `def` so FastAPI runs it in its
  threadpool, or `await asyncio.to_thread(...)`.

### Inference runs one text at a time
`predict()` tokenises and forward-passes each text in a loop — N forward passes
for N texts, when both the tokenizer and the model batch natively.

- **Files:** `src/api.py`
- **Approach:** one batched tokenizer call and one forward pass. Cap
  `len(texts)` (~64) so a large request cannot exhaust memory.

### Error detail leaked in 500 responses
- **Files:** `src/api.py`
- **Approach:** generic message to the client, full trace to the log.

## Quality

| Item | Files | Approach |
|---|---|---|
| Hardcoded `"models/trained_model"` paths | `src/api.py` | Use `settings.model_dir` |
| `train_runs` dict is unbounded and lost on restart | `src/api.py` | Cap its size; persistence is a larger change |
| `pickle.load` of model artefacts | `scripts/run_pipeline.py` | Move to `joblib`, validate paths, comment the trust boundary |
| `uvicorn --host 0.0.0.0` in the launcher script | `scripts/run_pipeline.py` | Default to `127.0.0.1`; `0.0.0.0` only inside a container |

## Longer term

- **The feedback loop is open.** Drift is detected (KS-test on features,
  chi-square on the prediction distribution) and written to
  `monitoring_results/drift_history.json`, but nothing acts on it. Stage 9 of
  the pipeline is monitoring without a trigger — closing it means a scheduled
  Dagster sensor that re-materialises `trained_model` when drift crosses the
  threshold.
- **No model registry promotion.** MLflow logs runs to a local file store. There
  is no staging/production promotion, so "which model is serving" is answered by
  a filesystem path rather than a registry.
- **Checkpoint cleanup.** A training run leaves a timestamped
  `models/training_output_*/` directory behind. Nothing prunes them.
- **No data validation library.** Cleaning is pandas null-drops and length
  filters. A schema contract would catch upstream dataset changes that currently
  pass through silently.
