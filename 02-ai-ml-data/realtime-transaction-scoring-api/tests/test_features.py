"""
Unit tests for src/features.py — feature engineering utilities.

No model or data files required: all tests use in-memory DataFrames.
Run: pytest tests/test_features.py
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.compose import ColumnTransformer

import features

# ─── helpers ──────────────────────────────────────────────────────────────────


def make_card_df(n=3, base="2024-01-01 10:00:00", interval_hours=2.0, amount=100.0, card_id="C1"):
    ts = [pd.Timestamp(base) + pd.Timedelta(hours=i * interval_hours) for i in range(n)]
    return pd.DataFrame({"card_id": card_id, "timestamp": ts, "amount": float(amount)})


def make_config(numeric=None, categorical=None):
    return {
        "features": {
            "numeric": numeric
            if numeric is not None
            else ["V1", "V2", "log_amount", "hour_of_day"],
            "categorical": categorical if categorical is not None else [],
        }
    }


# ─── build_model_features ─────────────────────────────────────────────────────


class TestBuildModelFeatures:
    def make_raw_df(self):
        return pd.DataFrame(
            {
                "Time": [0.0, 3600.0, 90000.0],  # hours 0, 1, 25 → 0, 1, 1
                "Amount": [0.0, 100.0, 1000.0],
                "V1": [0.1, 0.2, 0.3],
            }
        )

    def test_adds_log_amount_and_hour_of_day(self):
        out = features.build_model_features(self.make_raw_df())
        assert "log_amount" in out.columns
        assert "hour_of_day" in out.columns

    def test_drops_time_and_amount(self):
        out = features.build_model_features(self.make_raw_df())
        assert "Time" not in out.columns
        assert "Amount" not in out.columns

    def test_log_amount_is_log1p(self):
        out = features.build_model_features(self.make_raw_df())
        assert out["log_amount"].iloc[0] == pytest.approx(0.0)
        assert out["log_amount"].iloc[1] == pytest.approx(np.log1p(100.0))

    def test_hour_of_day_wraps_at_24(self):
        out = features.build_model_features(self.make_raw_df())
        assert out["hour_of_day"].tolist() == [0, 1, 1]

    def test_does_not_mutate_input(self):
        df = self.make_raw_df()
        features.build_model_features(df)
        assert "Time" in df.columns and "Amount" in df.columns


# ─── build_time_features ──────────────────────────────────────────────────────


class TestBuildTimeFeatures:
    def test_adds_hour_of_day_column(self):
        df = pd.DataFrame({"timestamp": ["2024-01-15 14:30:00"]})
        out = features.build_time_features(df)
        assert "hour_of_day" in out.columns

    def test_adds_day_of_week_column(self):
        df = pd.DataFrame({"timestamp": ["2024-01-15 14:30:00"]})
        out = features.build_time_features(df)
        assert "day_of_week" in out.columns

    def test_correct_hour_extracted(self):
        df = pd.DataFrame({"timestamp": ["2024-01-15 14:30:00"]})
        out = features.build_time_features(df)
        assert out["hour_of_day"].iloc[0] == 14

    def test_midnight_hour_is_zero(self):
        df = pd.DataFrame({"timestamp": ["2024-01-15 00:00:00"]})
        out = features.build_time_features(df)
        assert out["hour_of_day"].iloc[0] == 0

    def test_23_hour_boundary(self):
        df = pd.DataFrame({"timestamp": ["2024-01-15 23:59:59"]})
        out = features.build_time_features(df)
        assert out["hour_of_day"].iloc[0] == 23

    def test_correct_day_of_week_monday(self):
        # 2024-01-15 is a Monday → dayofweek == 0
        df = pd.DataFrame({"timestamp": ["2024-01-15 08:00:00"]})
        out = features.build_time_features(df)
        assert out["day_of_week"].iloc[0] == 0

    def test_correct_day_of_week_sunday(self):
        # 2024-01-14 is a Sunday → dayofweek == 6
        df = pd.DataFrame({"timestamp": ["2024-01-14 08:00:00"]})
        out = features.build_time_features(df)
        assert out["day_of_week"].iloc[0] == 6

    def test_multiple_rows_extracted_independently(self):
        df = pd.DataFrame({"timestamp": ["2024-01-15 06:00:00", "2024-01-15 23:00:00"]})
        out = features.build_time_features(df)
        assert out["hour_of_day"].tolist() == [6, 23]

    def test_does_not_mutate_input_dataframe(self):
        df = pd.DataFrame({"timestamp": ["2024-01-15 14:30:00"]})
        original_cols = list(df.columns)
        features.build_time_features(df)
        assert list(df.columns) == original_cols

    def test_accepts_string_timestamps(self):
        df = pd.DataFrame({"timestamp": ["2024-03-20 12:00:00"]})
        out = features.build_time_features(df)
        assert "hour_of_day" in out.columns


# ─── build_velocity_features ──────────────────────────────────────────────────


class TestBuildVelocityFeatures:
    def test_output_has_all_velocity_columns(self):
        df = make_card_df(n=1)
        out = features.build_velocity_features(df)
        for col in [
            "transactions_last_1h",
            "transactions_last_24h",
            "amount_mean_last_24h",
            "amount_std_last_24h",
        ]:
            assert col in out.columns, f"Missing: {col}"

    def test_first_transaction_all_zeros(self):
        df = make_card_df(n=1)
        out = features.build_velocity_features(df)
        assert out["transactions_last_1h"].iloc[0] == 0
        assert out["transactions_last_24h"].iloc[0] == 0
        assert out["amount_mean_last_24h"].iloc[0] == 0.0
        assert out["amount_std_last_24h"].iloc[0] == 0.0

    def test_counts_transactions_inside_1h_window(self):
        # transactions 20 min apart → each subsequent one sees the prior ones
        df = make_card_df(n=3, interval_hours=1 / 3)
        out = features.build_velocity_features(df)
        assert out["transactions_last_1h"].iloc[1] == 1
        assert out["transactions_last_1h"].iloc[2] == 2

    def test_transactions_outside_1h_not_counted(self):
        # 2-hour gap → nothing in the 1h window
        df = make_card_df(n=3, interval_hours=2)
        out = features.build_velocity_features(df)
        assert out["transactions_last_1h"].iloc[1] == 0
        assert out["transactions_last_1h"].iloc[2] == 0

    def test_counts_transactions_in_24h_window(self):
        # 2-hour gap → prior transactions fall inside the 24h window
        df = make_card_df(n=3, interval_hours=2)
        out = features.build_velocity_features(df)
        assert out["transactions_last_24h"].iloc[1] == 1
        assert out["transactions_last_24h"].iloc[2] == 2

    def test_transactions_outside_24h_not_counted(self):
        # 25-hour gap → prior transaction is outside the 24h window
        df = make_card_df(n=2, interval_hours=25)
        out = features.build_velocity_features(df)
        assert out["transactions_last_24h"].iloc[1] == 0

    def test_amount_mean_24h_is_correct(self):
        df = pd.DataFrame(
            {
                "card_id": ["C1", "C1"],
                "timestamp": ["2024-01-01 10:00:00", "2024-01-01 12:00:00"],
                "amount": [100.0, 200.0],
            }
        )
        out = features.build_velocity_features(df)
        # second transaction sees mean of [100.0] in prior 24h
        assert out["amount_mean_last_24h"].iloc[1] == pytest.approx(100.0)

    def test_amount_std_zero_for_single_prior_transaction(self):
        df = make_card_df(n=2, interval_hours=2)
        out = features.build_velocity_features(df)
        # one prior transaction → std is 0 (not NaN)
        assert out["amount_std_last_24h"].iloc[1] == 0.0

    def test_amount_std_nan_filled_with_zero(self):
        df = make_card_df(n=1)
        out = features.build_velocity_features(df)
        assert out["amount_std_last_24h"].isna().sum() == 0

    def test_velocity_does_not_bleed_across_cards(self):
        df_c1 = make_card_df(n=3, card_id="C1", interval_hours=0.25)
        df_c2 = make_card_df(n=1, card_id="C2")
        df = pd.concat([df_c1, df_c2], ignore_index=True)
        out = features.build_velocity_features(df)

        c2 = out[out["card_id"] == "C2"]
        assert c2["transactions_last_1h"].iloc[0] == 0
        assert c2["transactions_last_24h"].iloc[0] == 0

    def test_does_not_mutate_input_columns(self):
        df = make_card_df(n=2)
        original_cols = list(df.columns)
        features.build_velocity_features(df)
        assert list(df.columns) == original_cols


# ─── build_preprocessor ───────────────────────────────────────────────────────


class TestBuildPreprocessor:
    def test_returns_column_transformer(self):
        cfg = make_config()
        assert isinstance(features.build_preprocessor(cfg), ColumnTransformer)

    def test_numeric_output_has_mean_near_zero(self):
        cfg = make_config(numeric=["a", "b"], categorical=[])
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [10.0, 20.0, 30.0]})
        preprocessor = features.build_preprocessor(cfg)
        out = preprocessor.fit_transform(df)
        assert abs(out[:, 0].mean()) < 1e-10

    def test_output_row_count_matches_input(self):
        cfg = make_config(numeric=["x"], categorical=[])
        df = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
        preprocessor = features.build_preprocessor(cfg)
        out = preprocessor.fit_transform(df)
        assert out.shape[0] == 3

    def test_empty_categorical_no_error(self):
        cfg = make_config(numeric=["x"], categorical=[])
        df = pd.DataFrame({"x": [1.0, 2.0]})
        preprocessor = features.build_preprocessor(cfg)
        out = preprocessor.fit_transform(df)
        assert out.shape[0] == 2

    def test_unfitted_transformer_raises_on_transform(self):
        from sklearn.exceptions import NotFittedError

        cfg = make_config(numeric=["x"], categorical=[])
        df = pd.DataFrame({"x": [1.0, 2.0]})
        preprocessor = features.build_preprocessor(cfg)
        with pytest.raises(NotFittedError):
            preprocessor.transform(df)
