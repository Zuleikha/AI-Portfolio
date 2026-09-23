# 03 — Feature Engineering

## Why raw fields aren't enough

A single transaction row tells you: amount, merchant, card type, time.
That's not enough signal. A €500 electronics purchase at 2am is suspicious —
but only if the card's normal pattern is €30 supermarket purchases at noon.
**Context comes from history.**

## Feature categories

### 1. Time features

Extracted from the timestamp:
- `hour_of_day` (0–23) — fraud spikes at unusual hours
- `day_of_week` (0–6) — weekend patterns differ

These are simple but effective. A 3am transaction is higher risk regardless of amount.

### 2. Velocity features

Computed from the card's recent history:

| Feature | Window | What it captures |
|---------|--------|-----------------|
| `transactions_last_1h` | 1 hour | Burst activity (card testing) |
| `transactions_last_24h` | 24 hours | Daily usage anomaly |
| `amount_mean_last_24h` | 24 hours | Normal spend level |
| `amount_std_last_24h` | 24 hours | Spend variability |

A fraudster who steals a card often does multiple small test transactions before a large one.
`transactions_last_1h = 5` + `amount = €0.01` is a classic card-testing signature.

### 3. Categorical features

- `merchant_category` — gambling, electronics, travel are higher risk
- `card_type` — credit vs debit vs prepaid have different fraud profiles

These are one-hot encoded. `handle_unknown='ignore'` means unseen categories at inference don't crash the pipeline.

## The preprocessing pipeline

```python
ColumnTransformer(
    [
        ("num", StandardScaler(), numeric_features),
        ("cat", OneHotEncoder(...), categorical_features),
    ]
)
```

StandardScaler is necessary for distance-based models (SVM, k-NN, logistic regression).
RandomForest doesn't need it — but it doesn't hurt and keeps the pipeline consistent
if you swap algorithms later.

## Production note: feature stores

In a real system, velocity features live in a **feature store** (Redis, Feast, Tecton).
At inference time, you look up `card_id` and get pre-computed values in <5ms.
Here we compute them offline for training purposes only.
