"""
Shared fixtures for the fraud detection test suite.
"""

from unittest.mock import MagicMock

import numpy as np
import pytest

FEATURE_NAMES = [f"V{i}" for i in range(1, 29)] + ["log_amount", "hour_of_day"]


@pytest.fixture
def sample_transaction():
    return {name: 0.0 for name in FEATURE_NAMES}


@pytest.fixture
def mock_xgb_model():
    m = MagicMock()
    m.predict_proba.return_value = np.array([[0.7, 0.3]])
    return m
