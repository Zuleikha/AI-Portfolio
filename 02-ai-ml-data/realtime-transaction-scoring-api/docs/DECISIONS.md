# Technical Decisions

Key decisions made during model development and deployment. Explains *why*, not *what*.

---

## Decision 1: XGBoost Chosen as Final Model

### Alternatives evaluated

| Model | PR-AUC | Notes |
|---|---|---|
| Logistic Regression (balanced weights) | 0.71 | Interpretable but too weak on non-linear feature interactions |
| Logistic Regression + SMOTE | 0.76 | Imbalance handling improved recall; model capacity still the bottleneck |
| XGBoost (default params) | 0.82 | Gradient boosting captured interactions the linear model could not |
| **XGBoost + Optuna (150 trials)** | **0.88** | Best model — retained for production |

### Why XGBoost won

- **Non-linear patterns:** Fraud signals in V1–V28 involve interactions across multiple features simultaneously. Tree boosting captures these where a linear model cannot.
- **Scale-invariant:** No feature scaling required. Eliminates a preprocessing step that could introduce training/serving skew.
- **Native imbalance handling:** `scale_pos_weight` directly controls the class weight ratio. Set to 577.3 to reflect the 575:1 imbalance in training data.
- **Handles NaN natively:** No imputer required. XGBoost learns the optimal split direction for missing values during training.
- **PR-AUC optimisation:** XGBoost supports `eval_metric: aucpr` directly, aligning training optimisation with the evaluation metric that matters for imbalanced classification.

---

## Decision 2: Threshold Set to 0.28

### Background

`model.predict_proba()` returns a continuous fraud probability. A threshold converts this to a binary decision. The default sklearn threshold of 0.5 is almost always wrong for imbalanced data — at 0.17% fraud rate, probabilities cluster near zero and a 0.5 cutoff misses nearly all fraud.

### Threshold analysis

Notebook `06_threshold_tuning.ipynb` swept thresholds from 0.01 to 0.99 against a business cost matrix:
- False Negative (FN) cost: **$500** — fraud approved, loss absorbed
- False Positive (FP) cost: **$10** — legitimate transaction blocked, customer friction

The sweep identified **0.03** as the cost-minimising threshold under this matrix. Both thresholds were then evaluated against the 56,962-transaction held-out test set:

### Full comparison: 0.28 vs 0.03

| Metric | Threshold 0.28 | Threshold 0.03 |
|---|---|---|
| TP — fraud caught | 84 / 98 | 88 / 98 |
| FN — fraud missed | 14 | 10 |
| FP — false alarms | **19** | **84** |
| TN — correct legit | 56,845 | 56,780 |
| Precision | **81.6%** | 51.2% |
| Recall | 85.7% | **89.8%** |
| **F1 Score** | **83.6%** | 65.2% |
| Transactions flagged | 103 (0.18%) | 172 (0.30%) |
| Business cost (FN=$500, FP=$10) | $7,190 | **$5,840** |

### Why 0.03 was rejected despite lower cost matrix score

The cost matrix advantage of 0.03 ($5,840 vs $7,190) rests entirely on the $10/FP proxy. In practice:

1. **4.4× more false alarms:** 0.03 generates 84 false alarms vs 19 at 0.28. Each false alarm requires a human analyst review. At scale, the operational cost of 84 reviews per 57k transactions far exceeds the $10 proxy used in the cost model.

2. **Marginal fraud benefit:** 0.03 catches 4 additional fraud cases. The value of catching 4 more frauds does not justify 4.4× the false alarm volume when investigation capacity is finite.

3. **F1 collapses at 0.03:** F1 of 65.2% vs 83.6% at 0.28. The precision drop at 0.03 (51.2% — roughly 1 in 2 flagged transactions is not fraud) indicates the model is flagging large numbers of near-zero probability transactions unnecessarily.

4. **No calibration of the cost matrix:** The $10/FP and $500/FN values are approximate. When operational investigation cost is included alongside the cost matrix proxy, the economic advantage of 0.03 narrows or reverses.

**Conclusion:** 0.28 was retained. It delivers a strong, balanced result (F1 83.6%) with a false alarm rate manageable in a real operational environment.

---

## Decision 3: No Scaler Used

### Why XGBoost does not require scaling

XGBoost builds an ensemble of decision trees. Each tree splits on a single feature at a threshold. The split decision depends only on the *rank order* of feature values, not their magnitude. Multiplying every feature value by 1000 produces exactly the same tree structure and predictions.

Scaling features before XGBoost has no effect on model quality. It adds preprocessing complexity and introduces a risk of training/serving skew if the scaler is fitted incorrectly or applied inconsistently.

### Why the baseline scaler must not be used with XGBoost

`notebooks/02_baseline_model.ipynb` fits a `StandardScaler` on the training split for a `LogisticRegression` model and saves it as `outputs/models/baseline_scaler.joblib`. It belongs to the baseline pipeline only, and it is a local notebook artefact — not committed, and not part of the serving bundle.

Logistic Regression is a distance-based model. Its decision boundary is sensitive to feature scale. The scaler was required there. It is irrelevant — and potentially harmful if misapplied — to the XGBoost model, which was trained on unscaled features.

Applying `baseline_scaler.joblib` to XGBoost inference inputs would:
- Change input values without improving predictions
- Create a mismatch between how the model was trained and how it is served
- Make evaluation results from the notebooks non-reproducible via the API

---

## Decision 4: Optuna Used for Hyperparameter Tuning

### What Optuna tuned

Optuna ran 150 Bayesian optimisation trials, each evaluating a candidate set of XGBoost hyperparameters via 5-fold cross-validation. The objective metric was **PR-AUC** (average precision score), chosen because it is sensitive to minority class performance at extreme imbalance.

All trials were logged to MLflow via DagsHub.

**Parameters tuned and final values:**

| Parameter | Final Value | What it controls |
|---|---|---|
| `n_estimators` | 445 | Number of boosting rounds (trees) |
| `max_depth` | 6 | Maximum tree depth — controls model complexity |
| `learning_rate` | 0.0517 | Shrinkage — smaller = more conservative updates |
| `scale_pos_weight` | 577.3 | Upweights the fraud (positive) class during training |
| `colsample_bytree` | 0.801 | Fraction of features sampled per tree |
| `subsample` | 0.728 | Fraction of training rows sampled per tree |
| `gamma` | 0.566 | Minimum loss reduction required to make a split |
| `min_child_weight` | 6 | Minimum sum of instance weight in a leaf |
| `reg_alpha` | 0.210 | L1 regularisation term |
| `reg_lambda` | 0.018 | L2 regularisation term |

### What Optuna did NOT tune: the threshold

Optuna operated entirely within the training loop. It had no access to — and no control over — the classification threshold. The threshold is applied *after* `predict_proba()` returns a score. It is a post-training business decision, not a model parameter.

The threshold was set separately in `06_threshold_tuning.ipynb` via a cost-matrix sweep (Decision 2 above). Optuna never saw it and could not have tuned it. This separation is intentional: model parameters capture statistical patterns in data; the threshold captures the acceptable risk tolerance of the business.
