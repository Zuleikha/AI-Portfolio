# Real-Time Transaction Scoring API

Scores one payment transaction for fraud risk and returns the probability, the
binary decision, and **the threshold that produced it**.

The threshold ships on every response because a decision without its cut-off is
not reproducible. Two services running different thresholds against the same
model are two different systems, and you cannot tell them apart from the
probability alone.

## The interesting part: 0.28 is not a default

A cost sweep across thresholds 0.01–0.99 (`notebooks/06_threshold_tuning.ipynb`)
found **0.03** to be cost-optimal under a $500-per-missed-fraud /
$10-per-false-alarm matrix. **It was rejected.** Both were then measured against
the same 56,962-transaction held-out test set:

| | Threshold **0.28** (shipped) | Threshold 0.03 (cost-optimal) |
|---|---|---|
| Fraud caught | 84 / 98 | 88 / 98 |
| Fraud missed | 14 | 10 |
| **False alarms** | **19** | **84** |
| Precision | **81.6%** | 51.2% |
| Recall | 85.7% | **89.8%** |
| **F1** | **83.6%** | 65.2% |
| Transactions flagged | 0.18% | 0.30% |

0.03 buys **4 more frauds** for **4.4× the false alarms**. Every false alarm is
a human analyst review, and investigation capacity is finite — a cost the $10
proxy does not capture. At 0.03 roughly one in two flagged transactions is
legitimate, which is not an operable service.

The full justification, and the measured numbers at both thresholds, are stored
alongside the model in `outputs/models/bundle_v1/threshold.json` — not in a
notebook that can drift away from what is deployed.

## Model

| | |
|---|---|
| Algorithm | XGBoost, 445 trees, `scale_pos_weight=577.3` |
| Tuning | Optuna, 150 Bayesian trials, 5-fold CV, optimising PR-AUC |
| Data | Kaggle Credit Card Fraud — 284,807 transactions, **575:1 imbalance** |
| PR-AUC | **0.8828** |
| ROC-AUC | 0.9807 |
| Operating point | Catches **86%** of fraud while flagging **0.18%** of all traffic |

PR-AUC is the headline, not ROC-AUC. At a 0.17% positive rate the ROC curve is
dominated by the true negatives and flatters almost any model.

## ⚠️ The input is not raw transaction data

`V1`–`V28` are **PCA components** published with the Kaggle dataset — not
merchant, card number, country or MCC. **Raw bank data cannot be posted to this
API.** It must first be transformed with the same PCA fitted on the original
dataset, which is not distributed with it.

The two remaining fields are derived and are plain:

| Field | Derivation |
|---|---|
| `log_amount` | `log1p(transaction_amount)` |
| `hour_of_day` | hour from the timestamp, `0–23` |

This is the single most common misunderstanding about the service, so it is
stated here, in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and in
[docs/PRD.md](docs/PRD.md).

## Stack

| Layer | Choice |
|---|---|
| API | FastAPI, Pydantic v2 (all 30 fields individually required) |
| Model | XGBoost via `joblib`, loaded once at import |
| Serving artefact | Versioned bundle — model + threshold + feature order together |
| Config | `config/config.yaml`, one file |
| Tests | pytest, **112 tests**, no network, no dataset download |

## Run it

```bash
pip install -e ".[dev]"
uvicorn api.main:app --reload      # → http://localhost:8000
```

Interactive docs at `/docs`. The model is loaded at import: a missing or corrupt
bundle stops the process starting rather than starting it unhealthy.

## API

Two endpoints. That is the whole serving surface.

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness **and the active threshold** |
| `POST` | `/predict` | Score one transaction |

```bash
curl http://localhost:8000/health
```

```json
{ "status": "ok", "threshold": 0.28 }
```

`/health` publishes the threshold so an operator can confirm what a deployed
instance is scoring against without sending a transaction through it.

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"V1":-1.36,"V2":-0.07,"V3":2.54,"V4":1.38,"V5":-0.34,"V6":0.46,
       "V7":0.24,"V8":0.10,"V9":0.36,"V10":0.09,"V11":-0.55,"V12":-0.62,
       "V13":-0.99,"V14":-0.31,"V15":1.47,"V16":-0.47,"V17":0.21,"V18":0.03,
       "V19":0.40,"V20":0.25,"V21":-0.02,"V22":0.28,"V23":-0.11,"V24":0.07,
       "V25":0.13,"V26":-0.19,"V27":0.13,"V28":-0.02,
       "log_amount":5.01,"hour_of_day":0}'
```

```json
{
  "fraud_probability": 0.0012,
  "is_fraud": false,
  "threshold_used": 0.28
}
```

Three keys, always. Errors: `422` if any of the 30 fields is missing or
non-numeric; `500` on an internal scoring failure, with a generic message — the
exception text goes to the log, never to the caller.

## One artefact, one threshold

`outputs/models/bundle_v1/` is the single source of truth for serving:

| File | Holds |
|---|---|
| `model.pkl` | The trained classifier |
| `threshold.json` | 0.28, the justification, and measured performance at both candidate thresholds |
| `metadata.json` | The hyperparameters, so training can reproduce the model |
| `feature_list.json` | The exact feature order the model expects |

They travel together so they cannot drift apart. The source project also kept a
loose `outputs/models/best_xgb.pkl` that was a **byte-identical duplicate**
(hash-verified) of the bundle's model — two copies of one artefact is two things
that can diverge, so it was dropped on extraction.

Retraining (`src/train.py`) writes to `outputs/models/retrain_candidate.pkl`.
**It never overwrites the serving bundle.** Promotion is a deliberate manual
step.

## Tests

```bash
pytest -q
```

112 tests, fully offline. What the API suite actually pins:

- `/health` and `/predict` report the **same** threshold — a guard against the
  API and the bundle drifting apart
- `is_fraud` is exactly `fraud_probability >= threshold_used`
- Scoring is **deterministic** — the same transaction scores identically twice,
  so no state leaks between requests
- The response body has **no keys beyond** the documented three
- A model failure returns 500 and the exception text does not appear in the body
- Each of the 30 fields is individually required

## Repository layout

```
api/main.py               FastAPI app: /health, /predict
app/main.py               local-dev entry point, re-exports api.main:app
src/features.py           build_model_features — the production transform
src/train.py              reproduce the bundle; writes a candidate, never production
src/predict.py            stand-alone scoring helper, testable without a server
config/config.yaml        data paths, feature list, model paths, training threshold
outputs/models/bundle_v1/ the versioned serving artefact
notebooks/                01 EDA → 08 monitoring & drift; how the model was arrived at
docs/                     architecture, decisions, ADRs, security, roadmap
```

The notebooks are kept as the record of how the model was reached — imbalance
strategies compared, SHAP explainability, the threshold sweep, drift analysis.
They are excluded from linting; they are a record, not a service.

## Known limits

No authentication and no rate limiting — this is a portfolio demo, not a
deployed product. `src/predict.py` reads its threshold from `config.yaml` while
the API reads the bundle; both say 0.28 today but the two paths should be
unified. Drift detection exists only in notebook 08, not as a live pipeline.
The dataset is not redistributed here. All tracked in
[docs/ROADMAP.md](docs/ROADMAP.md) and [docs/SECURITY.md](docs/SECURITY.md).

## Licence

MIT — see [LICENSE](LICENSE).
