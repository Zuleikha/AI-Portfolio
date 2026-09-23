"""
Retrain the fraud detection model on the Kaggle creditcard.csv dataset.

Reproduces the bundle_v1 pipeline: derive log_amount / hour_of_day, train
XGBoost with the hyperparameters recorded in bundle_v1/metadata.json, and
evaluate PR-AUC / ROC-AUC at the configured threshold.

The trained model is written to model.candidate_path — it never overwrites
the production model at model.path. Promote a candidate manually after review.

MLflow/DagsHub logging is opt-in: set TRACK_WITH_DAGSHUB=1 (requires
DAGSHUB_REPO_OWNER / DAGSHUB_REPO_NAME or the defaults in .env).

Run from the project root: python src/train.py
"""

import json
import logging
import os
import sys
from pathlib import Path

# Make sibling modules (features.py) importable no matter where this is run from
sys.path.insert(0, str(Path(__file__).resolve().parent))

import joblib
import pandas as pd
from dotenv import load_dotenv
from sklearn.metrics import average_precision_score, classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from features import build_model_features, load_config

logger = logging.getLogger(__name__)


def _maybe_init_tracking() -> bool:
    """Initialise DagsHub/MLflow only when explicitly enabled via env var."""
    if os.environ.get("TRACK_WITH_DAGSHUB") != "1":
        return False
    import dagshub

    dagshub.init(
        repo_owner=os.environ.get("DAGSHUB_REPO_OWNER", "Zuleikha"),
        repo_name=os.environ.get("DAGSHUB_REPO_NAME", "fraud-detection-ML-project"),
        mlflow=True,
    )
    return True


def _load_hyperparams(metadata_path: str) -> dict:
    """Read the production XGBoost hyperparameters from the bundle metadata."""
    metadata = json.loads(Path(metadata_path).read_text())
    model_meta = metadata["model"]
    return {
        "n_estimators": model_meta["n_estimators"],
        "max_depth": model_meta["max_depth"],
        "learning_rate": model_meta["learning_rate"],
        "scale_pos_weight": model_meta["scale_pos_weight"],
        "random_state": model_meta["random_state"],
        "objective": model_meta["objective"],
        "eval_metric": model_meta["eval_metric"],
    }


def train(config_path: str = "config/config.yaml") -> dict:
    """Train a candidate model and return its evaluation metrics."""
    cfg = load_config(config_path)
    tracking = _maybe_init_tracking()

    logger.info("Loading data from %s", cfg["data"]["raw_path"])
    df = pd.read_csv(cfg["data"]["raw_path"])
    df = build_model_features(df)

    feature_cols = cfg["features"]["numeric"] + cfg["features"]["categorical"]
    X = df[feature_cols]
    y = df["Class"]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=cfg["data"]["test_size"],
        random_state=cfg["data"]["random_state"],
        stratify=y,
    )

    params = _load_hyperparams(cfg["model"]["bundle_metadata"])
    model = XGBClassifier(n_jobs=-1, **params)

    logger.info("Training XGBoost (%d estimators) on %d rows", params["n_estimators"], len(X_train))
    model.fit(X_train, y_train)

    y_prob = model.predict_proba(X_test)[:, 1]
    threshold = cfg["prediction"]["threshold"]
    y_pred = (y_prob >= threshold).astype(int)

    metrics = {
        "pr_auc": average_precision_score(y_test, y_prob),
        "roc_auc": roc_auc_score(y_test, y_prob),
        "threshold": threshold,
    }
    logger.info("PR-AUC: %.4f | ROC-AUC: %.4f", metrics["pr_auc"], metrics["roc_auc"])
    logger.info(
        "Classification report at threshold=%s:\n%s",
        threshold,
        classification_report(y_test, y_pred, target_names=["Legit", "Fraud"]),
    )

    if tracking:
        import mlflow

        with mlflow.start_run(run_name="retrain_candidate"):
            mlflow.log_params(params)
            mlflow.log_metrics({k: v for k, v in metrics.items()})

    candidate_path = cfg["model"]["candidate_path"]
    Path(candidate_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, candidate_path)
    logger.info("Candidate model saved to %s (production model untouched)", candidate_path)

    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()
    train()
