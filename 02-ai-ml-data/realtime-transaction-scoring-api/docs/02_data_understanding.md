# 02 — Data Understanding

## Dataset

We use the [Kaggle Credit Card Fraud Detection dataset](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud)
(or a synthetic equivalent). It contains 284,807 transactions, 492 of which are fraud.

## Class imbalance

```
Legit:  284,315  (99.83%)
Fraud:      492   (0.17%)
```

This is not a data quality problem — it's reality. Most fraud detection datasets look like this.

**Why this matters for ML:**
- A model that predicts "legit" for everything gets 99.83% accuracy. That number is meaningless.
- Standard accuracy is not a useful metric here. Use precision, recall, F1, ROC-AUC, PR-AUC.
- The model must learn from 492 positive examples scattered in 284k — without balance correction it will almost always predict the majority class.

## How we handle imbalance

Three common strategies (we use SMOTE):

| Strategy | What it does | Trade-off |
|----------|-------------|-----------|
| Class weights | Penalises misclassifying minority class more | Fast, no new samples |
| Undersampling | Randomly drop majority class rows | Loses information |
| SMOTE | Synthesises new minority class examples | Adds information, risk of overfitting |

SMOTE is applied **inside the training pipeline**, on the training fold only. If you apply it before the train/test split you contaminate the test set and your evaluation metrics are optimistically wrong.

## EDA checklist

Before touching a model, always look at:

1. **Missing values** — are any features always null for fraud?
2. **Amount distribution** — fraud often clusters at unusual amounts
3. **Time patterns** — fraud spikes at certain hours
4. **Correlation with label** — which raw features separate fraud from legit?

See `notebooks/01_eda.ipynb` for the full analysis.
