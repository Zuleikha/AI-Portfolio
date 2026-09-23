# ML Training Orchestration Pipeline

> Part of [ai-portfolio](../../README.md) · Personal project · **Life Sciences / Healthcare AI**

**In one line:** one API call downloads a biomedical dataset, trains a model, evaluates it and serves it, with every step tracked.

## Why it matters

Training a model once is easy. Doing it repeatably, with a record of how each result was made, is the hard part.

## Key results

| | |
|---|---|
| Task | Spot adverse drug reactions in MEDLINE case-report sentences (ADE Corpus V2) |
| Model | BiomedBERT, pretrained on biomedical literature; bert-base-uncased kept as the baseline to beat |
| Orchestration | Dagster assets with full lineage |
| Tracking | MLflow |
| Monitoring | Drift checks on live inputs, exposed as Prometheus metrics |
| Tests | 24 |

## The key decision

No trained model is stored in the repo. It is a reproducible build output, and `/predict` honestly returns 503 until a training run finishes.

## Honest limits

- Drift is detected but does not trigger retraining
- Training-run state is lost on restart
- A personal project, not a regulated pharmacovigilance system

## Run it

```bash
pip install -e ".[dev]"
docker compose up
```

API at http://localhost:8000/docs · Dagster at http://localhost:3000 · MLflow at http://localhost:5000

---

📄 **Full technical README:** [README_FULL.md](README_FULL.md) (pipeline stages, dataset choice, drift detection)

🕘 **Development history:** [earlier repository](https://github.com/Zuleikha/ml-training-orchestration-pipeline) with the full commit history. This folder is the current version.
