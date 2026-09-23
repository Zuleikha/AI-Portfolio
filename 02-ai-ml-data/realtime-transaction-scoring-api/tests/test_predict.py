"""
Unit tests for src/predict.py.

All tests mock the model so no real model file is required.
Run: pytest tests/test_predict.py
"""

from unittest.mock import MagicMock

import numpy as np
import pytest

import predict as predict_module

FEATURE_NAMES = [f"V{i}" for i in range(1, 29)] + ["log_amount", "hour_of_day"]
SAMPLE_TRANSACTION = {name: 0.0 for name in FEATURE_NAMES}


def _arm(prob: float, threshold: float = 0.3):
    """Inject a mock model + config into the module globals."""
    mock = MagicMock()
    mock.predict_proba.return_value = np.array([[1 - prob, prob]])
    predict_module._model = mock
    predict_module._config = {"prediction": {"threshold": threshold}}
    return mock


@pytest.fixture(autouse=True)
def reset_globals():
    """Wipe module-level globals before each test to prevent state bleed."""
    predict_module._model = None
    predict_module._config = None
    yield
    predict_module._model = None
    predict_module._config = None


# ─── response shape ────────────────────────────────────────────────────────────


class TestResponseShape:
    def test_returns_all_required_keys(self):
        _arm(0.3)
        result = predict_module.predict(SAMPLE_TRANSACTION)
        assert {"fraud_probability", "is_fraud", "threshold_used"} <= result.keys()

    def test_fraud_probability_is_float(self):
        _arm(0.42)
        assert isinstance(predict_module.predict(SAMPLE_TRANSACTION)["fraud_probability"], float)

    def test_is_fraud_is_bool(self):
        _arm(0.5)
        assert isinstance(predict_module.predict(SAMPLE_TRANSACTION)["is_fraud"], bool)

    def test_threshold_used_matches_config(self):
        _arm(0.3, threshold=0.28)
        assert predict_module.predict(SAMPLE_TRANSACTION)["threshold_used"] == 0.28

    def test_fraud_probability_in_unit_interval(self):
        _arm(0.77)
        p = predict_module.predict(SAMPLE_TRANSACTION)["fraud_probability"]
        assert 0.0 <= p <= 1.0

    def test_fraud_probability_rounded_to_4dp(self):
        _arm(0.123456789)
        p = predict_module.predict(SAMPLE_TRANSACTION)["fraud_probability"]
        decimal_part = str(p).split(".")[-1]
        assert len(decimal_part) <= 4


# ─── threshold logic ──────────────────────────────────────────────────────────


class TestThresholdLogic:
    @pytest.mark.parametrize(
        "prob,threshold,expected",
        [
            (0.5, 0.28, True),  # clearly above
            (0.28, 0.28, True),  # exactly at threshold (inclusive)
            (0.27, 0.28, False),  # just below
            (0.0, 0.28, False),  # zero probability → never fraud
            (1.0, 0.28, True),  # maximum probability → always fraud
            (0.1, 0.5, False),  # default threshold, low prob
            (0.9, 0.5, True),  # default threshold, high prob
        ],
    )
    def test_boundary(self, prob, threshold, expected):
        _arm(prob, threshold)
        assert predict_module.predict(SAMPLE_TRANSACTION)["is_fraud"] is expected


# ─── model receives correct input ─────────────────────────────────────────────


class TestModelInput:
    def test_model_called_with_dataframe_of_one_row(self):
        mock = _arm(0.4)
        predict_module.predict(SAMPLE_TRANSACTION)
        df = mock.predict_proba.call_args[0][0]
        assert len(df) == 1

    def test_model_dataframe_has_correct_columns(self):
        mock = _arm(0.4)
        predict_module.predict(SAMPLE_TRANSACTION)
        df = mock.predict_proba.call_args[0][0]
        assert list(df.columns) == list(SAMPLE_TRANSACTION.keys())

    def test_model_called_exactly_once_per_predict(self):
        mock = _arm(0.4)
        predict_module.predict(SAMPLE_TRANSACTION)
        assert mock.predict_proba.call_count == 1


# ─── error handling ───────────────────────────────────────────────────────────


class TestErrorHandling:
    def test_raises_when_model_not_loaded(self):
        predict_module._model = None
        predict_module._config = {"prediction": {"threshold": 0.3}}
        with pytest.raises(RuntimeError, match="load_artifacts"):
            predict_module.predict(SAMPLE_TRANSACTION)

    def test_raises_when_config_not_loaded(self):
        predict_module._model = MagicMock()
        predict_module._config = None
        with pytest.raises(RuntimeError, match="load_artifacts"):
            predict_module.predict(SAMPLE_TRANSACTION)

    def test_raises_when_both_not_loaded(self):
        with pytest.raises(RuntimeError, match="load_artifacts"):
            predict_module.predict(SAMPLE_TRANSACTION)
