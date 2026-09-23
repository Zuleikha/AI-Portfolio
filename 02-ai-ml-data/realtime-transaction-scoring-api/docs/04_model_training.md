# 04 — Model Training

## Algorithm choice: Random Forest

We use `RandomForestClassifier`. Why not XGBoost, a neural network, or logistic regression?

| Algorithm | Pros | Cons |
|-----------|------|------|
| Logistic Regression | Interpretable, fast | Weak on non-linear patterns |
| Random Forest | Handles mixed types, robust, fast | Less accurate than boosting |
| XGBoost / LightGBM | State of the art accuracy | Harder to tune, slower to iterate |
| Neural Network | Captures complex patterns | Needs lots of data, slow to iterate |

**RandomForest is the right starting point.** It requires minimal tuning to get a useful baseline,
handles the mix of numeric and categorical features well, and produces calibrated probabilities
when `predict_proba` is used. Replace it with XGBoost once you have a working pipeline.

## The training pipeline structure

```
Raw data
  → build_time_features()       # adds hour_of_day, day_of_week
  → build_velocity_features()   # adds rolling window counts/stats
  → ColumnTransformer           # scales + encodes
  → SMOTE                       # balances minority class
  → RandomForestClassifier      # fits the model
```

Everything from the ColumnTransformer onwards is wrapped in an `imblearn.Pipeline`.
This ensures SMOTE only sees training data, never validation or test data.

## Key parameters explained

```python
RandomForestClassifier(
    n_estimators=200,  # 200 trees — more = more stable but slower
    class_weight="balanced",  # also weight minority class, works alongside SMOTE
    random_state=42,  # reproducibility
    n_jobs=-1,  # use all CPU cores
)
```

`class_weight="balanced"` + SMOTE is belt-and-braces. In practice one or the other is enough —
we use both here because the imbalance is extreme (0.17%).

## Train/test split

```python
train_test_split(X, y, test_size=0.2, stratify=y)
```

`stratify=y` ensures both splits have the same fraud ratio.
Without it, a random split might put all 492 fraud cases in train and none in test.

## What to check after training

1. ROC-AUC > 0.95 on test set (this dataset is achievable)
2. No huge gap between train and test AUC (overfitting signal)
3. Feature importances — velocity features should rank high
4. Calibration plot — do predicted probabilities match actual fraud rates?
