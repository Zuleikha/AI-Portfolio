# 07 — API and Deployment

## A notebook and a service are different shapes

```
Notebook                          Service
─────────────────────────────────────────────────────────────
Runs top to bottom, once          Runs indefinitely, many requests
Loads the model per cell run      Loads the model once, at import
You call it                       A load balancer calls it
No validation                     Pydantic rejects malformed input
No readiness signal               /health says "I can score"
```

## The request lifecycle

```
Client (another service, curl)
  │
  ▼
POST /predict  { "V1": -1.36, ..., "V28": -0.02,
                 "log_amount": 5.01, "hour_of_day": 0 }
  │
  ▼
Pydantic validates — 30 required floats.
A missing or non-numeric field is a 422 before the model is reached.
  │
  ▼
pd.DataFrame([txn.model_dump()])
  │
  ▼
model.predict_proba(frame)[:, 1][0]   → 0.0012
  │
  ▼
is_fraud = probability >= THRESHOLD   # 0.28, read from the bundle at import
  │
  ▼
{ "fraud_probability": 0.0012, "is_fraud": false, "threshold_used": 0.28 }
```

Three keys, always. A test asserts the response carries **no fourth key** — a
response contract that quietly grows is one that clients start depending on by
accident.

## The model is loaded at import, not per request

```python
THRESHOLD: float = json.loads(THRESHOLD_PATH.read_text())["threshold"]
model = joblib.load(MODEL_PATH)
```

Both happen at module import in `api/main.py`. Every request reuses the same
in-memory object; loading inside the endpoint would pay a disk read and a
deserialise on every call.

The consequence is deliberate: **a missing or corrupt bundle stops the process
starting.** For a service whose only job is scoring, an instance that cannot
score has nothing useful to report, so failing loudly at boot beats passing a
health check and returning wrong answers.

Paths are anchored to the repo, not the working directory:

```python
PROJECT_ROOT = Path(__file__).resolve().parents[1]
```

so the app starts identically from anywhere.

## What `/health` is for

```python
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "threshold": THRESHOLD}
```

Two audiences:

1. **The orchestrator.** Kubernetes, an ALB or a platform health check polls it.
   A non-200 means stop routing here. New deployments take traffic only after
   they pass; crashed instances get replaced; rolling deploys hold the old
   version up until the new one is healthy.

2. **A human operator.** The threshold is published so you can confirm what a
   running instance is actually scoring against without pushing a transaction
   through it. This matters more than it sounds: the model and the threshold are
   two separate things that can be deployed out of step, and only one of them
   shows up in a version tag.

There is no separate "model loaded" check, because the process cannot reach the
point of answering `/health` without the model loaded — the import would have
failed.

## Deployment shape

Not deployed. This repository is a portfolio demonstration and runs locally:

```bash
pip install -e ".[dev]"
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

If it were deployed, three things would need deciding:

| Concern | Note |
|---|---|
| **Build** | `pip install .` — dependencies come from `pyproject.toml`, every one capped at the next major so a fresh build cannot silently pick up a breaking release |
| **The model artefact** | `bundle_v1/` is **committed to git** (937 KB), so a rebuild-from-git deploy has it. That works at this size; past a few MB the model belongs in object storage or a registry, fetched at startup and version-pinned |
| **Auth and TLS** | Neither exists here. Both belong upstream — see [SECURITY.md](SECURITY.md) |

The alternative of training during the build is a bad idea for this service: it
makes every deploy produce a *different* model, so the artefact you tested is
never the artefact you shipped. `src/train.py` deliberately writes
`retrain_candidate.pkl` and never the serving bundle, for the same reason —
see [ADR-0005](decisions/ADR-0005-candidate-retrain.md).

## What monitoring would come next

### 1. Prediction distribution

Log every `fraud_probability` and watch the daily mean. A shift from 0.12 to
0.05 means something changed — fraud patterns, the input features, or a bug.
Which of the three is the interesting question, and the distribution alone
cannot answer it.

### 2. Data drift

Compare incoming feature distributions to the training distribution.
`notebooks/08_monitoring_and_drift.ipynb` already computes PSI and KS
statistics — offline, against a saved split. Making it live needs a scheduled
runner and somewhere to write metrics.

### 3. The label feedback loop

This is the hard one, and it is why the two above are not enough.

In fraud, **labels arrive late**. A transaction confirmed fraudulent today was
made three weeks ago. So a live pipeline needs to:

1. Capture confirmed fraud from chargebacks and investigations
2. Join them back to the logged predictions
3. Compute *actual* precision and recall over a trailing window
4. Alert when recall drops below the operating target

Without it, the model can degrade for weeks before anyone notices — the
predictions keep looking plausible the whole time. A fraud service with no
label-latency story is claiming more than it can support, which is why it is
listed as a gap in [ROADMAP.md](ROADMAP.md) rather than sketched as a feature.
