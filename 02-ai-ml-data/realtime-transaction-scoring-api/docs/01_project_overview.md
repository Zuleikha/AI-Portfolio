# 01 — Project Overview

## What we're building

A binary classifier that scores credit card transactions and flags likely fraud.
Given a transaction, the model outputs a probability (0–1) and a yes/no decision.

## Why fraud detection is a good ML learning project

It hits every real-world ML challenge in one shot:

| Challenge | Why it appears here |
|-----------|-------------------|
| Class imbalance | Fraud is typically 0.1–1% of transactions |
| Threshold tuning | Precision vs recall has a direct dollar cost |
| Feature engineering | Raw fields alone are weak; velocity matters |
| Deployment | Low-latency inference, not batch |
| Monitoring | Distribution drift kills model performance silently |

## The problem framing

- **Input:** a single transaction (amount, merchant category, card type, time, velocity features)
- **Output:** `fraud_probability` (float) + `is_fraud` (bool based on configurable threshold)
- **Label:** `is_fraud` — 1 if the transaction was later confirmed fraudulent

## What this project is NOT

- A real-time streaming system (Kafka, Flink) — that's a separate layer
- A graph network model (though GNNs are state of the art for fraud)
- A complete MLOps setup with retraining pipelines

## Learning path

Read the docs in order. Each one builds on the last:

```
01 Overview → 02 Data → 03 Features → 04 Training → 05 Evaluation → 06 Threshold → 07 Deployment
```
