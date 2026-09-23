# ADR-0001 — XGBoost as the production model

- **Status:** Accepted
- **Date:** 2026-05-24 (recorded 2026-06-27)

## Context

The task is extreme-imbalance binary classification (0.17% fraud) over 30 features —
28 anonymised PCA components (V1–V28) plus `log_amount` and `hour_of_day`. A Logistic
Regression baseline was built first to set a score to beat.

Measured PR-AUC across candidates:

| Model | PR-AUC |
|---|---|
| Logistic Regression (balanced) | 0.71 |
| Logistic Regression + SMOTE | 0.76 |
| XGBoost (default) | 0.82 |
| **XGBoost + Optuna (150 trials)** | **0.88** |

## Decision

Use a tuned **XGBoost classifier** as the production model, served from the
versioned bundle at `outputs/models/bundle_v1/model.pkl`.

## Consequences

- **+** Captures non-linear interactions across V1–V28 that the linear model cannot.
- **+** Scale-invariant (no scaler needed — see [ADR-0003](ADR-0003-no-scaler.md)) and handles NaN natively.
- **+** `scale_pos_weight` gives direct control over the 575:1 imbalance.
- **+** Supports `eval_metric=aucpr`, aligning training with the evaluation metric that matters.
- **−** Less intrinsically interpretable than LR. Mitigated by SHAP analysis
  (`notebooks/05_shap_explainability.ipynb`) — offline, not on the response.
  The API returns a probability and a decision, not a reason.
