# Architecture Decision Records

Each ADR captures one significant, hard-to-reverse decision: the context, the choice, and its consequences.
Prose rationale also lives in [`../DECISIONS.md`](../DECISIONS.md); these ADRs are the formal, indexed records.

| ADR | Decision | Status |
|---|---|---|
| [0001](ADR-0001-xgboost-over-logistic-regression.md) | XGBoost as the production model (over Logistic Regression) | Accepted |
| [0002](ADR-0002-threshold-0_28.md) | Decision threshold 0.28 (not the cost-optimal 0.03) | Accepted |
| [0003](ADR-0003-no-scaler.md) | No feature scaler in the serving pipeline | Accepted |
| [0004](ADR-0004-optuna-tuning.md) | Optuna (150 trials) for hyperparameter tuning | Accepted |
| [0005](ADR-0005-candidate-retrain.md) | Retraining writes a candidate artefact, never overwrites production | Accepted |

## Numbering

ADRs 0001–0004 keep their original numbers. What is now **0005** was 0006 in the
source project: the original 0005 documented routing an `/explain` endpoint through
a shared LLM gateway, and both the ADR and the endpoint were removed when this
service was extracted. That gateway was sandbox infrastructure shared across
several unrelated projects, not part of this system — and on the deployed instance
it was never reachable anyway, so the endpoint always served its template fallback.
See [`../DECISIONS.md`](../DECISIONS.md).
