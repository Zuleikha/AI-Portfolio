# ADR-0003 — No feature scaler in the serving pipeline

- **Status:** Accepted
- **Date:** 2026-05-24 (recorded 2026-06-27)

## Context

A `StandardScaler` (`outputs/models/baseline_scaler.joblib`) was fitted for the
Logistic Regression baseline (notebook 02). The production model is XGBoost.

## Decision

Serve XGBoost on **unscaled** features. Ship **no scaler** in the bundle.
`baseline_scaler.joblib` must never be applied to XGBoost inputs.

## Consequences

- **+** XGBoost tree splits depend on rank order, not magnitude — scaling has no effect on quality.
- **+** Removes a preprocessing step and a class of training/serving-skew bugs.
- **−** A future contributor might wrongly assume a scaler is needed. Mitigated by explicit warnings in `BUNDLE_SPEC.md`, `DECISIONS.md`, and `CLAUDE.md`.
- **Guardrail:** applying the LR scaler to XGBoost inputs would change values without improving accuracy and make notebook metrics non-reproducible via the API.
