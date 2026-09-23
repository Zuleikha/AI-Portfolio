# Roadmap

Known limits and the work that would close them, ordered by what a reviewer
would notice first. Everything here is a real property of the code, not a
placeholder.

## 🟠 Structural

### 1. Two threshold sources

`api/main.py` reads `outputs/models/bundle_v1/threshold.json`.
`src/predict.py` reads `config/config.yaml`.

Both say `0.28` today. They can drift, and nothing fails if they do — the API
would keep serving the bundle value while the offline helper silently used a
different one.

**Serving is correct**: the API reads the bundle, which is the artefact the
threshold was validated against. The fix is to make `config.yaml` stop carrying
a threshold at all and have `src/predict.py` read the bundle too, so there is
one source. The test suite already pins `/health` and `/predict` to the same
value, which catches API-side drift but not this.

### 2. No live drift monitoring

`notebooks/08_monitoring_and_drift.ipynb` computes PSI, KS-statistic data drift
and prediction drift — but offline, against a saved split. There is no
scheduled job, no label capture, and no alerting.

A live version needs infrastructure this repo does not contain: a scheduled
runner, somewhere to write metrics, and a feedback loop that captures confirmed
fraud outcomes weeks after the transaction. Deliberately out of scope; a fraud
model with no label-latency story is a bigger claim than this repo can support.

### 3. Manual model promotion

`src/train.py` writes `outputs/models/retrain_candidate.pkl` and **never**
overwrites the serving bundle — see
[ADR-0005](decisions/ADR-0005-candidate-retrain.md). Promotion is a human
copying a file.

That is the right default for a model whose failure mode is invisible, but it
means there is no registry, no automated evaluation gate, and no rollback
record. An MLflow model registry with a promotion gate on PR-AUC would be the
next step, and needs a CI runner and tracking credentials.

## 🟡 Serving

### 4. No authentication, no rate limiting

The API is open. See [SECURITY.md](SECURITY.md). It is a portfolio demo, not a
deployed product; adding auth without a real deployment target would be
decoration.

### 5. `/health` does not report model version

It reports `status` and `threshold`. It cannot tell you *which* model is loaded.
`bundle_v1/metadata.json` has the information; the response contract is
deliberately frozen, so adding a field is a versioned change rather than a
patch.

### 6. Single-transaction scoring only

`/predict` takes one transaction. There is no batch endpoint. For a real fraud
system, per-request scoring is the correct shape — but backfilling or scoring a
day's traffic means one HTTP call per row.

## 🟢 Code

### 7. `build_velocity_features` is O(n²) per card

`src/features.py` scans a rolling window inside a per-card loop. It is
**unused by the production pipeline** — the Kaggle dataset has no `card_id`, so
nothing calls it. Kept because it documents what real velocity features would
look like, and it is honest about the cost in its own docstring.

In a real system these come from a feature store (Redis, Feast) so they are
available at inference time without scanning history.

### 8. `build_preprocessor` is dead in the serving path

It builds a `StandardScaler` + `OneHotEncoder` `ColumnTransformer`. XGBoost
needs neither — see [ADR-0003](decisions/ADR-0003-no-scaler.md). It exists for
the Logistic Regression baseline in `notebooks/02_baseline_model.ipynb`.

### 9. Numbered docs overlap the ADRs

`docs/01_project_overview.md` … `07_api_and_deployment.md` are the narrative
walk-through; `docs/decisions/` holds the formal ADRs; `DECISIONS.md` holds the
prose rationale. Three views of overlapping material. They do not contradict
each other, but they are three places to update.

## Data

The Kaggle Credit Card Fraud dataset is **not redistributed** in this repo —
`data/raw/` holds only a `.gitkeep`. Reproducing training means downloading it
yourself. `src/train.py` reads the path from `config/config.yaml`.

## Not planned

- **Explanations on the response.** The source project had an `/explain`
  endpoint that routed through a shared LLM gateway. It was removed on
  extraction: the gateway was sandbox infrastructure shared across unrelated
  projects, and on the deployed instance it was never reachable, so the endpoint
  always served a template fallback. SHAP explainability lives in
  `notebooks/05_shap_explainability.ipynb`, where it is honest.
- **Changing the response contract.** `fraud_probability`, `is_fraud`,
  `threshold_used` — three keys, pinned by tests. Any change is a new version.
