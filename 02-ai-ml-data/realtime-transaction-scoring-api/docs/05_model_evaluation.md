# 05 — Model Evaluation

## Why accuracy is useless here

A model that predicts "legit" for every transaction scores 99.83% accuracy.
It catches zero fraud. Accuracy is meaningless with imbalanced classes.

## The metrics that matter

### Precision

Of all transactions the model flagged as fraud, how many actually were?

```
Precision = TP / (TP + FP)
```

Low precision → too many false alarms → customers blocked on legitimate purchases → churn.

### Recall (Sensitivity)

Of all actual fraud cases, how many did the model catch?

```
Recall = TP / (TP + FN)
```

Low recall → fraud slips through → direct financial loss.

### F1 Score

Harmonic mean of precision and recall. Useful single number, but hides the tradeoff.

### ROC-AUC

Area under the Receiver Operating Characteristic curve.
Measures how well the model ranks fraud above legit **regardless of threshold**.
A score of 1.0 is perfect; 0.5 is random.

Good for comparing models. Not useful for choosing a threshold.

### PR-AUC (Precision-Recall AUC)

Area under the Precision-Recall curve.
More informative than ROC-AUC when classes are heavily imbalanced —
it focuses on the minority class performance.

## The confusion matrix

```
                  Predicted Legit    Predicted Fraud
Actual Legit      TN (correct)       FP (false alarm)
Actual Fraud      FN (miss)          TP (caught)
```

| Cell | Business meaning |
|------|-----------------|
| TN | Transaction approved, customer happy |
| FP | Transaction blocked, customer frustrated — churn risk |
| FN | Fraud goes through — financial loss |
| TP | Fraud blocked — money saved |

The ratio of FP cost to FN cost determines your optimal threshold.
See doc 06 for how to calculate it.

## Evaluation code pattern

```python
from sklearn.metrics import classification_report, roc_auc_score, average_precision_score

y_prob = model.predict_proba(X_test)[:, 1]
y_pred = (y_prob >= threshold).astype(int)

print(f"ROC-AUC:  {roc_auc_score(y_test, y_prob):.4f}")
print(f"PR-AUC:   {average_precision_score(y_test, y_prob):.4f}")
print(classification_report(y_test, y_pred))
```

Always evaluate at the **production threshold**, not 0.5.
Reporting metrics at 0.5 when you'll deploy at 0.3 is misleading.
