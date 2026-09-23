# PRD — Real-Time Transaction Scoring API

> Product requirements for the fraud-detection scoring service.
> Source of truth for *what* this system is for. Code is the source of truth for
> *how* it behaves.

## 1. Goal

Score a single credit-card transaction for fraud risk and return a probability,
a binary decision, and **the threshold that produced it** — fast enough to sit
inline in a payment flow, and traceable enough that any decision can be
reconciled after the fact.

The threshold travels on the response because a decision without its cut-off is
not reproducible. Two instances running different thresholds against the same
model are two different systems, and the probability alone cannot distinguish
them.

## 2. Users and user stories

| User | Story |
|---|---|
| Payment / risk service | "I POST one transaction's features and get back a fraud probability and a yes/no decision in milliseconds." |
| Operator | "I call `/health` and can see which threshold this instance is scoring against, without sending a transaction through it." |
| ML engineer | "I can retrain from the recorded hyperparameters without ever overwriting the live model." |
| Reviewer / interviewer | "I can trace every decision — model choice, threshold, no scaler — to a documented rationale." |

## 3. Scope

**In scope**

- `POST /predict` — score one transaction (30 features: V1–V28, `log_amount`,
  `hour_of_day`)
- `GET /health` — liveness, and the active decision threshold
- Offline retraining (`src/train.py`) that writes a **candidate** artefact only,
  never the serving bundle

Two endpoints. That is the whole serving surface.

**Out of scope, deliberately**

- Authentication and rate limiting — belongs to a deployment layer this repo
  does not include
- Raw-data ingestion: callers supply the PCA features; the API does not run the
  PCA and cannot
- Real-time feature store / velocity features at serving time
- Streaming (Kafka / Flink) and batch scoring
- A live monitoring or drift pipeline — drift analysis exists in notebooks only
- An automated feedback / label-collection loop
- **Natural-language explanations.** The source project had a `POST /explain`
  endpoint that called a shared LLM gateway. It was removed on extraction: the
  gateway was sandbox infrastructure shared across unrelated projects, and on
  the deployed instance it was never reachable, so the endpoint always served a
  template fallback — an explanation feature that never explained anything. SHAP
  explainability lives in `notebooks/05_shap_explainability.ipynb`, where it is
  honest. See [DECISIONS.md](DECISIONS.md).

## 4. Success criteria

| Dimension | Target / current |
|---|---|
| Model quality | PR-AUC **0.8828**, ROC-AUC **0.9807** on a held-out 56,962-row test set |
| Operating point | Threshold **0.28** → precision **81.6%**, recall **85.7%**, F1 **83.6%** |
| Operational | Flags **0.18%** of transactions (84 TP / 19 FP / 14 FN on test) |
| Serving | Model loaded once at import; per-request scoring only |
| Reproducibility | Hyperparameters and metrics captured in `bundle_v1/metadata.json` |
| Tests | **112 tests** pass with no dataset download, no network and no secrets |

PR-AUC is the headline metric, not ROC-AUC. At a 0.17% positive rate the ROC
curve is dominated by true negatives and flatters almost any model.

## 5. Failure modes

| Failure | Behaviour | Mitigation |
|---|---|---|
| `model.pkl` missing or corrupt | Raises at import; the process refuses to start | The bundle is committed. Failing to start beats starting unhealthy — a scorer that cannot score has nothing useful to report |
| `threshold.json` missing | Raises at import, same path | Bundle is committed as one unit |
| Scoring raises at request time | `500` with a generic message; full trace to the log only | `try/except` in `/predict`; a test asserts the exception text is absent from the body |
| Malformed or missing field | `422` naming the field, before the model is reached | Pydantic; all 30 fields individually required, each pinned by a test |
| Out-of-distribution or adversarial input | Model still returns a score, which may be wrong | Documented limitation. The threshold is conservative, but the model cannot detect that it is out of its depth |
| Concept drift (fraud patterns shift) | Silent quality decay | **Gap** — no live monitoring. Notebook 08 only. Tracked in [ROADMAP.md](ROADMAP.md) |
| API and bundle thresholds diverge | Would produce unreconcilable decisions | Tests pin `/health` and `/predict` to the same value |

## 6. Security considerations

- **No direct identifiers in inputs.** V1–V28 are PCA components published with
  the dataset; `log_amount` and `hour_of_day` are derived. No card numbers,
  names or merchants — a card number cannot be expressed in the request body.
  This is not the same as anonymity: PCA is a rotation, not anonymisation.
- **No secrets in the serving path.** The API reads no environment variables at
  all.
- **Training credentials** (DagsHub, opt-in) come from environment variables
  only; `.env` is git-ignored. See [`.env.example`](../.env.example).
- **No auth on the endpoints** — acceptable for a portfolio demo, **not** for
  public exposure.

Full detail in [SECURITY.md](SECURITY.md).

## 7. Known gaps

Tracked in [ROADMAP.md](ROADMAP.md):

- Live monitoring / drift detection — only in `notebooks/08`
- Feedback loop for delayed chargeback labels
- CI pipeline (lint + test gate)
- Dual threshold source: `config.yaml` vs `bundle_v1/threshold.json`
