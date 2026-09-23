# Architecture

> Module map, interfaces and contracts. Reflects the code as it actually is.

## Request flow

```
TRAINING (offline, src/train.py)
  creditcard.csv
    → build_model_features()      # log_amount = log1p(Amount)
                                  # hour_of_day = (Time // 3600) % 24
                                  # drop Time, Amount
    → train_test_split(stratify=y, test_size=0.2, random_state=42)
    → XGBClassifier(**bundle_v1/metadata.json)   # 445 trees, scale_pos_weight=577.3
    → evaluate PR-AUC / ROC-AUC at threshold 0.28
    → joblib.dump(candidate_path)   # NEVER overwrites the serving bundle

SERVING (online, api/main.py — uvicorn api.main:app)
  import time: joblib.load(bundle_v1/model.pkl)
               read bundle_v1/threshold.json  → 0.28

    GET  /health   → {"status": "ok", "threshold": 0.28}

    POST /predict  {V1..V28, log_amount, hour_of_day}
      → Pydantic validates              (422 on bad input)
      → model.predict_proba()[:, 1]     → fraud_probability
      → is_fraud = probability >= 0.28
      → {fraud_probability, is_fraud, threshold_used}
      → on internal failure: 500, generic message, trace to the log only
```

Two endpoints. That is the whole serving surface.

## One artefact, one threshold

The serving bundle is the single source of truth. `outputs/models/bundle_v1/`
holds the model, the threshold that was validated against it, and the feature
order it was trained on — so the three cannot drift apart.

| File | Holds |
|---|---|
| `model.pkl` | The trained XGBoost classifier |
| `threshold.json` | 0.28, plus the justification and the measured performance at both 0.28 and the notebook-optimal 0.03 |
| `metadata.json` | The hyperparameters, so `src/train.py` can reproduce the model |
| `feature_list.json` | The exact feature order the model expects |

The source project also kept a loose `outputs/models/best_xgb.pkl`, which was a
**byte-identical duplicate** of `bundle_v1/model.pkl` (verified by hash). Two
copies of the same artefact is two things that can diverge, so the extraction
kept the bundle and dropped the loose copy. The API now loads only from the
bundle.

## Module map

| Module | Responsibility | Hides |
|---|---|---|
| `config/config.yaml` | Single config file: data paths, feature list, model paths, training threshold | Where every tunable value lives |
| `src/features.py` | `build_model_features` (the production transform), plus offline-only `build_time_/velocity_features` and `build_preprocessor` | The `Time`/`Amount` → `log_amount`/`hour_of_day` mapping |
| `src/train.py` | Reproduce the bundle: load data, train XGBoost from the bundle's hyperparameters, write a **candidate** | XGBoost fit, opt-in MLflow/DagsHub logging |
| `src/predict.py` | Stand-alone scoring helper | Model load and DataFrame plumbing; unit-testable without a server |
| `api/main.py` | The FastAPI app: `/health`, `/predict` | Bundle load, Pydantic contract, error shaping |
| `app/main.py` | Local-dev entry point; re-exports `api.main:app` | Nothing — `api/main.py` is the single source of truth |
| `outputs/models/bundle_v1/` | The versioned serving artefact | Model provenance and the serving threshold |

## Interfaces and testable contracts

**`GET /health`**
- Out: `{status: "ok", threshold: float}`.
- The threshold is published here so an operator can confirm which cut-off a
  deployed instance is scoring against without sending a transaction.

**`POST /predict`**
- In: a JSON object with exactly the 30 required float fields. Extra fields are ignored.
- Out: `{fraud_probability: float, is_fraud: bool, threshold_used: float}` — and nothing else.
- Errors: `422` on a missing or non-numeric field; `500` on an internal scoring
  error, with a generic message. The exception text is logged, never returned.

**`predict.predict(dict) -> dict`** — requires `load_artifacts()` first; returns
the same three keys.

**`build_model_features(df) -> df`** — input has `Time` and `Amount`; output
drops them and adds `log_amount` and `hour_of_day`.

Invariants the suite pins:

- `/health` and `/predict` report the **same** threshold — a guard against the API and the bundle drifting.
- `threshold_used` equals the value in the bundle.
- `is_fraud` is exactly `fraud_probability >= threshold_used`.
- Scoring is deterministic: the same transaction scores identically twice, so no state leaks between requests.
- The response body has **no keys beyond** the documented three.
- A model failure returns 500 and the exception text does not appear in the body.
- Every one of the 30 feature fields is individually required.

## The input format is not raw transaction data

V1–V28 are **PCA components** from the Kaggle Credit Card Fraud dataset, not
merchant, card number or location. Raw bank data cannot be posted to this API
directly — it must first be transformed with the same PCA fitted on the original
dataset. The two remaining fields are derived:

- `log_amount` = `log1p(transaction_amount)`
- `hour_of_day` = hour extracted from the timestamp, 0–23

This is the single most common misunderstanding about the service, so it is
stated in the README, here, and in the PRD.

## Dependencies

- **Runtime:** FastAPI, uvicorn, pydantic, xgboost, scikit-learn, pandas, numpy, joblib, pyyaml.
- **Training / notebooks only:** Optuna, imbalanced-learn, SHAP, matplotlib, seaborn, dagshub, python-dotenv.
- **Test only:** pytest, httpx (for `fastapi.testclient`).

`httpx` was a **runtime** dependency in the source project because an
`/explain` endpoint called an external LLM gateway over HTTP. That endpoint was
removed during extraction (see [DECISIONS.md](DECISIONS.md)), so `httpx` is
now a test dependency only.

## Known structural issues

- **Dual threshold source.** `api/main.py` reads `bundle_v1/threshold.json`;
  `src/predict.py` reads `config/config.yaml`. Both say `0.28` today and they
  can drift. Serving is correct — it reads the bundle — but the two paths should
  be unified. Tracked in [ROADMAP.md](ROADMAP.md).
- **No authentication or rate limiting.** See [SECURITY.md](SECURITY.md).
- **Model loaded at import.** A missing or corrupt bundle raises at import and
  the process refuses to start, rather than starting unhealthy. Deliberate for a
  service whose only job is scoring: an instance that cannot score has nothing
  useful to report.
