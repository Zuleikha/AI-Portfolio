# Security

## Current posture

Designed to run locally or behind a trusted boundary. **Not hardened for public
exposure** — the gaps are listed rather than implied.

| Control | Status |
|---|---|
| Secrets in environment variables only | ✅ Implemented |
| `.env` git-ignored | ✅ Implemented |
| Config validated at import | ✅ Implemented |
| Request bodies schema-validated | ✅ Implemented (Pydantic v2) |
| Model artefacts and data kept out of git | ✅ Implemented |
| Authentication | ❌ Not implemented |
| Training parameter limits | ❌ Not implemented |
| Concurrency control on training | ❌ Not implemented |
| Generic error responses | ❌ Exception text returned to the client |

## Threats

### Unauthenticated training
`POST /train` is open and its parameters are unbounded. `sample_size=10**9` or
`epochs=1000` will exhaust CPU, memory and disk on the host. This is the most
serious issue in the project: it is a one-request denial of service against
anyone who can reach the port.

### Concurrent runs corrupting configuration
`_run_pipeline` rewrites `config/pipeline.yaml` in place. Two overlapping runs
interleave read-modify-write, and the result is a run trained on hyperparameters
nobody requested — reported as a success.

### Untrusted deserialisation
`src/models/model_manager.py` uses `torch.load()`, and `scripts/run_pipeline.py`
uses `pickle.load()`. Both execute arbitrary code when given a hostile file.
They are safe only because they read artefacts this pipeline produced. **Do not
point either at a checkpoint from an untrusted source.**

### Information disclosure
Prediction failures return `str(exc)` in the HTTP 500 body, which can expose
filesystem paths and library internals.

### Model provenance
`pretrained_model_setup` downloads weights from the HuggingFace Hub at run time.
The model reference is configuration, so a changed config pulls different
weights. Pin the revision if the supply chain matters to you.

## Secrets

The public path needs no credentials — the dataset is public and MLflow writes
to a local file store.

`HUGGINGFACE_TOKEN` is the only secret, and only for gated or private models.
It is read from the environment by `src/config.py`, never logged, and never
written into `config/pipeline.yaml`.

## Data handling

The pipeline processes a public dataset by default. If you point it at your own
data, note that:

- Cleaned and tokenised data is written to `data/` in plaintext.
- Text samples may appear in MLflow artefacts and in evaluation output.
- The drift detector retains a reference distribution derived from training
  data.

None of this leaves the machine unless you configure a remote MLflow server.

## Reporting

Open a GitHub issue for anything that is not itself sensitive. For a genuine
vulnerability, contact the maintainer directly rather than filing publicly.
