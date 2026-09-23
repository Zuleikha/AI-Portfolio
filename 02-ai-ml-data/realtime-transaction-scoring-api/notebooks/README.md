# Notebooks

The record of how the model was arrived at. Run in order — each builds on
outputs saved by the previous one.

These are **not** part of the service. They are excluded from linting and no
serving code imports them. They are kept because the reasoning behind the model
is more interesting than the model, and because a threshold chosen for a
documented reason is only credible if the working is visible.

## Execution order

| # | Notebook | What it does |
|---|---|---|
| 01 | `01_eda.ipynb` | Explores the raw dataset: class imbalance, amount distributions, fraud-by-hour patterns, top PCA feature separability. |
| 02 | `02_baseline_model.ipynb` | Trains a default logistic regression to establish a PR-AUC baseline to beat. |
| 03 | `03_imbalance_handling.ipynb` | Compares SMOTE, random undersampling, class weights and SMOTE+Tomek; keeps the best-scoring strategy. |
| 04 | `04_xgboost_tuning.ipynb` | Replaces logistic regression with XGBoost and tunes across 150 Optuna trials, every run logged to MLflow. Reaches PR-AUC 0.88. |
| 05 | `05_shap_explainability.ipynb` | SHAP summary, beeswarm, waterfall, force and dependence plots for the tuned model. |
| 06 | `06_threshold_tuning.ipynb` | Sweeps thresholds 0.01–0.99 against a business cost matrix. **Finds 0.03 cost-optimal — which was then rejected.** See below. |
| 07 | `07_api_and_deployment.ipynb` | Smoke-tests the `/predict` endpoint locally against a running server. |
| 08 | `08_monitoring_and_drift.ipynb` | PSI, KS-statistic data drift, prediction drift and performance drift — offline, against a saved split. |

## Notebook 06 does not choose the threshold

The sweep in notebook 06 minimises a cost matrix ($500 per missed fraud, $10 per
false alarm) and lands on **0.03**. The shipped threshold is **0.28**.

That gap is deliberate and is the most interesting decision in the project:
0.03 catches 4 more frauds for **4.4× the false alarms** (84 vs 19), and every
false alarm is a human analyst review — a cost the $10 proxy does not capture.

The notebook is the analysis. The decision, its justification and the measured
performance at *both* thresholds live in
`outputs/models/bundle_v1/threshold.json` and
[`docs/DECISIONS.md`](../docs/DECISIONS.md) — deliberately next to the artefact,
not in a notebook that can drift away from what is deployed.

## Model files these notebooks write are not committed

Only the reviewed serving bundle, `outputs/models/bundle_v1/`, is in the
repository. Everything the notebooks save to `outputs/models/` is a local
intermediate and is git-ignored:

| Notebook | Writes |
|---|---|
| 02 | `baseline_lr.joblib`, `baseline_scaler.joblib` |
| 03 | `best_imbalance_model.pkl`, `imbalance_results.pkl` |
| 04 | the tuned XGBoost model — used by notebooks 05, 06 and 07 |
| 05, 06, 08 | figures only, no models |

`baseline_scaler.joblib` in particular belongs to the **logistic regression
baseline only** and must never be applied to XGBoost inputs — see
[ADR-0003](../docs/decisions/ADR-0003-no-scaler.md).

Figures under `outputs/figures/` **are** committed, since they are the visual
record of the analysis.

## Running them

The dataset is not redistributed. Download the Kaggle Credit Card Fraud dataset
to `data/raw/creditcard.csv`, then:

```bash
pip install -e ".[train]"
jupyter lab
```

Notebook 04 logs to MLflow. Tracking is opt-in — see
[`.env.example`](../.env.example).
