# Real-Time Transaction Scoring API

> Part of [ai-portfolio](../../README.md) · Personal project · **AI/ML & Data**

**In one line:** an API that scores a card payment for fraud risk, and tells you the exact cut-off it used to decide.

## Why it matters

A fraud score on its own can't be checked or repeated. This API returns the score, the yes/no decision **and the threshold behind it**, so every decision can be reproduced.

## Key results

| | |
|---|---|
| Data | 284,807 anonymised card transactions (public Kaggle set). Only 1 in 575 is fraud |
| Model | XGBoost, tuned with Optuna |
| Catches | **86%** of fraud |
| Flags | **0.18%** of all transactions |
| Tests | 112, all run offline |

## The key decision

The "cheapest on paper" threshold (0.03) caught 4 more frauds but raised **4.4× more false alarms**. I shipped 0.28 instead, because every false alarm costs a human analyst's time.

## Honest limits

- Input is anonymised data (PCA features), not raw bank data
- No login or rate limiting: a demo, not a live product
- Drift monitoring exists in a notebook only

## Run it

```bash
pip install -e ".[dev]"
uvicorn api.main:app --reload
```

Then open http://localhost:8000/docs

---

📄 **Full technical README:** [README_FULL.md](README_FULL.md) (model details, API examples, tests, file layout)

🕘 **Development history:** [earlier repository](https://github.com/Zuleikha/realtime-transaction-scoring-api) with the full commit history. This folder is the current version.
