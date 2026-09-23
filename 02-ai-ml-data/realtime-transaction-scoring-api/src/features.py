"""
Feature engineering for fraud detection.

Raw transaction data → model-ready feature matrix.
"""

import numpy as np
import pandas as pd
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def build_model_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive the serving features from the raw Kaggle creditcard.csv schema.

    Matches the preprocessing recorded in outputs/models/bundle_v1/metadata.json:
    log_amount = log1p(Amount), hour_of_day = (Time // 3600) % 24,
    then Time and Amount are dropped.
    """
    df = df.copy()
    df["log_amount"] = np.log1p(df["Amount"])
    df["hour_of_day"] = (df["Time"] // 3600) % 24
    return df.drop(columns=["Time", "Amount"])


def build_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extract hour and day from a UTC timestamp column."""
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour_of_day"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    return df


def build_velocity_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Count transactions and compute amount stats in rolling windows per card.

    In a real system these would be read from a feature store (Redis / Feast)
    so they're available at inference time without scanning history.
    Here we compute them offline for training.

    Known limitation: the per-card window scan is O(n^2) in transactions per
    card — fine for offline experimentation, too slow for large datasets.
    Not used by the production pipeline (creditcard.csv has no card_id).
    """
    df = df.sort_values(["card_id", "timestamp"]).copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    for _card_id, group in df.groupby("card_id"):
        idx = group.index
        ts = group["timestamp"]

        txn_1h, txn_24h, mean_24h, std_24h = [], [], [], []

        # Windows are strictly backward-looking (`ts < t`): a transaction never
        # counts itself, so these are usable at scoring time without leakage.
        for t in ts:
            window_1h = group[(ts >= t - pd.Timedelta(hours=1)) & (ts < t)]
            window_24h = group[(ts >= t - pd.Timedelta(hours=24)) & (ts < t)]
            txn_1h.append(len(window_1h))
            txn_24h.append(len(window_24h))
            mean_24h.append(window_24h["amount"].mean() if len(window_24h) else 0.0)
            std_24h.append(window_24h["amount"].std() if len(window_24h) > 1 else 0.0)

        df.loc[idx, "transactions_last_1h"] = txn_1h
        df.loc[idx, "transactions_last_24h"] = txn_24h
        df.loc[idx, "amount_mean_last_24h"] = mean_24h
        df.loc[idx, "amount_std_last_24h"] = std_24h

    df["amount_std_last_24h"] = df["amount_std_last_24h"].fillna(0.0)
    return df


def build_preprocessor(config: dict) -> ColumnTransformer:
    """Returns a fitted-ready sklearn ColumnTransformer."""
    numeric_features = config["features"]["numeric"]
    categorical_features = config["features"]["categorical"]

    numeric_transformer = StandardScaler()
    categorical_transformer = OneHotEncoder(handle_unknown="ignore", sparse_output=False)

    return ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, numeric_features),
            ("cat", categorical_transformer, categorical_features),
        ]
    )
