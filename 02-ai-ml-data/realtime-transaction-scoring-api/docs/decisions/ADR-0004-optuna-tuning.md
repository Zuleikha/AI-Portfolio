# ADR-0004 — Optuna for hyperparameter tuning

- **Status:** Accepted
- **Date:** 2026-05-24 (recorded 2026-06-27)

## Context

XGBoost has many interacting hyperparameters; grid search is wasteful at this imbalance.
Tuning happened in `notebooks/04_xgboost_tuning.ipynb`.

## Decision

Use **Optuna** Bayesian optimisation — 150 trials, each scored by 5-fold CV **PR-AUC**.
All trials logged to MLflow via DagsHub. Final hyperparameters are recorded in
`outputs/models/bundle_v1/metadata.json` and re-used (not re-searched) by `src/train.py`.

Final values: `n_estimators=445`, `max_depth=6`, `learning_rate=0.0517`,
`scale_pos_weight=577.3`, `subsample=0.728`, `colsample_bytree=0.801`, `gamma=0.566`,
`min_child_weight=6`, `reg_alpha=0.210`, `reg_lambda=0.018`.

## Consequences

- **+** Bayesian search finds strong configs faster than grid/random.
- **+** PR-AUC objective matches the minority-class metric that matters.
- **+** `src/train.py` is reproducible — it loads the recorded hyperparameters rather than re-running a 150-trial search.
- **Scope note:** Optuna tuned the **model only**. The **threshold** is a separate post-training business decision ([ADR-0002](ADR-0002-threshold-0_28.md)) — Optuna never saw it.
