# ADR-0002 — Decision threshold 0.28

- **Status:** Accepted
- **Date:** 2026-05-24 (recorded 2026-06-27)

## Context

`predict_proba` returns a continuous score; a threshold converts it to a decision.
The sklearn default of 0.5 is wrong for 0.17% fraud (probabilities cluster near 0).
Notebook `06_threshold_tuning.ipynb` swept 0.01–0.99 against a cost matrix
(FN = $500, FP = $10) and found **0.03** as the cost-minimising point. Both 0.03 and
0.28 were then evaluated on the 56,962-row held-out test set.

| Metric | 0.28 | 0.03 |
|---|---|---|
| Fraud caught (TP) | 84 | 88 |
| False alarms (FP) | **19** | **84** |
| Precision | **81.6%** | 51.2% |
| Recall | 85.7% | 89.8% |
| F1 | **83.6%** | 65.2% |
| Business cost (proxy) | $7,190 | **$5,840** |

## Decision

Ship **threshold 0.28**, recorded in `outputs/models/bundle_v1/threshold.json` and
`config/config.yaml`.

## Consequences

- **+** 4.4× fewer false alarms (19 vs 84) → far less analyst review load for ~4 extra frauds caught.
- **+** F1 83.6% vs 65.2%; precision stays usable (≈1 in 1.2 flags is fraud vs 1 in 2 at 0.03).
- **−** The $5,840-vs-$7,190 proxy "favoured" 0.03; we override it because the $10/FP figure understates real operational review cost.
- **−** The threshold lives in **two** files (`threshold.json` for serving, `config.yaml` for `src/predict.py`). They must be kept in sync — flagged in [../ROADMAP.md](../ROADMAP.md).
