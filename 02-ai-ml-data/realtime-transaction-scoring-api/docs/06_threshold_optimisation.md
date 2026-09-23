# 06 — Threshold Optimisation

## The default 0.5 threshold is almost never right in production

When sklearn calls `model.predict(X)` it uses 0.5 as the cutoff.
That default exists because it's mathematically convenient — it makes no assumptions
about your business. In almost every real application, the right threshold is not 0.5.

For fraud detection with 0.17% fraud rate, the model's predicted probabilities will
cluster near 0. A threshold of 0.5 will flag almost nothing. You need a lower threshold.

## The precision-recall tradeoff

Moving the threshold changes the business outcome:

```
Threshold ↓  →  Recall ↑  (catch more fraud)   Precision ↓ (more false alarms)
Threshold ↑  →  Precision ↑ (fewer false alarms)  Recall ↓ (miss more fraud)
```

There is no free lunch. Every threshold is a business decision, not a technical one.

```
          Precision
    1.0 |---.
        |    \
        |     \
        |      \
    0.0 |_______\___
              0.0  1.0  Recall
```

The PR curve above shows this tradeoff across all thresholds.
The area under it (PR-AUC) measures overall model quality independent of threshold.

## Picking a threshold using business costs

Define:
- **Cost of a false negative (FN):** the average loss when fraud slips through (e.g. €150)
- **Cost of a false positive (FP):** the cost of wrongly blocking a customer (e.g. €5 — support call, churn risk)

The optimal threshold minimises total expected cost:

```python
import numpy as np

fn_cost = 150  # fraud gets through
fp_cost = 5  # customer wrongly blocked

costs = []
thresholds = np.linspace(0.01, 0.99, 100)

for t in thresholds:
    y_pred = (y_prob >= t).astype(int)
    fp = ((y_pred == 1) & (y_test == 0)).sum()
    fn = ((y_pred == 0) & (y_test == 1)).sum()
    total_cost = fp * fp_cost + fn * fn_cost
    costs.append(total_cost)

optimal_threshold = thresholds[np.argmin(costs)]
print(f"Optimal threshold: {optimal_threshold:.2f}")
```

**fn_cost / fp_cost = 30** means each missed fraud is 30× more expensive than a false alarm.
That pushes the threshold down — you'd rather block 30 legitimate transactions than miss one fraud.

## What the confusion matrix looks like at different thresholds

For a model with ROC-AUC = 0.97, test set of 56,962 legit / 98 fraud:

| Threshold | TP (fraud caught) | FP (false alarms) | FN (missed fraud) | Precision | Recall |
|-----------|:-----------------:|:-----------------:|:-----------------:|:---------:|:------:|
| 0.10 | 95 | 820 | 3 | 10.4% | 96.9% |
| 0.30 | 91 | 180 | 7 | 33.6% | 92.9% |
| 0.50 | 80 | 45  | 18 | 64.0% | 81.6% |
| 0.70 | 65 | 12  | 33 | 84.4% | 66.3% |

At 0.50 you miss 18 fraud cases. At 0.30 you miss only 7 — at the cost of 135 more false alarms.
Whether that trade is worth it depends on fn_cost vs fp_cost. **That is a business decision.**

## How this connects to the API

The threshold lives in `config/config.yaml`:

```yaml
prediction:
  threshold: 0.28
```

`src/predict.py` reads it from the config at inference time. (The deployed `api/main.py`
reads the same value from `outputs/models/bundle_v1/threshold.json` — both hold 0.28; keep
them in sync.) To change the threshold you update the config file and restart the server.
No code change, no retraining, no redeployment of the model artefact.

This separation is intentional:
- The model artefact (`outputs/models/bundle_v1/model.pkl`) captures learned patterns — change it only when you retrain.
- The threshold captures a business decision — change it independently, as often as needed.

In production, threshold changes often go through A/B tests or champion/challenger frameworks
before being applied globally.
