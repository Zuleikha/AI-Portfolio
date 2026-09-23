"""Real-time transaction scoring API.

Scores one payment transaction for fraud risk with an XGBoost classifier and
returns the probability, the binary decision, and the threshold that produced
it. The threshold is published on every response because a decision without
its cut-off is not reproducible.
"""

import json
import logging
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

# Anchor to the project root so the API starts regardless of the working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# One model artefact, not two. The serving bundle is the single source of truth:
# the model, the threshold that was validated against it, and the feature order
# it was trained on all travel together and cannot drift apart.
BUNDLE_DIR = PROJECT_ROOT / "outputs" / "models" / "bundle_v1"
MODEL_PATH = BUNDLE_DIR / "model.pkl"
THRESHOLD_PATH = BUNDLE_DIR / "threshold.json"

THRESHOLD: float = json.loads(THRESHOLD_PATH.read_text())["threshold"]

app = FastAPI(
    title="Real-Time Transaction Scoring API",
    description=(
        "Scores a credit card transaction for fraud using an XGBoost classifier "
        "trained on the Kaggle Credit Card Fraud dataset. Returns a probability, "
        "a binary decision, and the decision threshold used."
    ),
    version="1.0",
)

try:
    model = joblib.load(MODEL_PATH)
    logger.info("Model loaded from %s (threshold=%s)", MODEL_PATH, THRESHOLD)
except Exception as exc:  # pragma: no cover - startup failure, not a request path
    raise RuntimeError(f"Failed to load model from {MODEL_PATH}: {exc}") from exc


class Transaction(BaseModel):
    """One transaction in the Kaggle dataset's feature space.

    V1-V28 are PCA components, not raw transaction fields. Raw bank data must
    be transformed with the same PCA fitted on the original dataset before it
    can be scored here.
    """

    V1: float
    V2: float
    V3: float
    V4: float
    V5: float
    V6: float
    V7: float
    V8: float
    V9: float
    V10: float
    V11: float
    V12: float
    V13: float
    V14: float
    V15: float
    V16: float
    V17: float
    V18: float
    V19: float
    V20: float
    V21: float
    V22: float
    V23: float
    V24: float
    V25: float
    V26: float
    V27: float
    V28: float
    log_amount: float
    hour_of_day: float


@app.get("/health")
def health() -> dict:
    """Liveness, plus the threshold the service is scoring against."""
    return {"status": "ok", "threshold": THRESHOLD}


def _score(txn: Transaction) -> dict:
    """Score a transaction. Returns probability, decision and threshold used."""
    frame = pd.DataFrame([txn.model_dump()])
    probability = float(model.predict_proba(frame)[:, 1][0])
    return {
        "fraud_probability": round(probability, 4),
        "is_fraud": bool(probability >= THRESHOLD),
        "threshold_used": THRESHOLD,
    }


@app.post("/predict")
def predict(txn: Transaction) -> dict:
    """Score one transaction.

    Raises:
        HTTPException: 500 if scoring fails. The internal error is logged with
            its trace and never returned to the caller.
    """
    try:
        return _score(txn)
    except Exception:
        logger.exception("Scoring failed for a /predict request")
        raise HTTPException(status_code=500, detail="Internal scoring error") from None
