"""
Tests for the FastAPI serving layer.

The sentiment model and the Dagster materialisation are both mocked, so these
tests are fast and need no trained model bundle, no dataset download and no GPU.
"""

import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Add the project root to the path so `from src.api import app` resolves.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import api
from src.api import app

client = TestClient(app)

SAMPLE_REQUEST = {"texts": ["This movie was absolutely fantastic!"]}
CANNED_PREDICTIONS = [
    {
        "text": "This movie was absolutely fantastic!",
        "predicted_class": 1,
        "prediction": "positive",
        "probabilities": {"negative": 0.02, "positive": 0.98},
    }
]


@pytest.fixture
def loaded_model():
    """Pretend a model is loaded and stub out the heavyweight predict() call."""
    api.model_service.model_loaded = True
    with patch.object(api.model_service, "predict", return_value=CANNED_PREDICTIONS):
        yield
    api.model_service.model_loaded = False


# ── Liveness ──────────────────────────────────────────────────────────────────


def test_root_reports_model_state():
    response = client.get("/")
    assert response.status_code == 200
    assert "model_loaded" in response.json()


def test_health_is_reachable_without_a_model():
    """Health must not depend on a trained bundle, or orchestration can't schedule."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["model_loaded"] is False


def test_metrics_exposes_prometheus_counters():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "predict_requests_total" in response.text


# ── Prediction ────────────────────────────────────────────────────────────────


def test_predict_returns_predictions_when_model_loaded(loaded_model):
    response = client.post("/predict", json=SAMPLE_REQUEST)
    assert response.status_code == 200
    body = response.json()
    assert body["predictions"] == CANNED_PREDICTIONS
    assert "device" in body["model_info"]


def test_predict_returns_503_when_no_model_loaded():
    """The bundle is a build artefact, so an untrained deployment is a real state."""
    api.model_service.model_loaded = False
    response = client.post("/predict", json=SAMPLE_REQUEST)
    assert response.status_code == 503
    assert "train a model first" in response.json()["detail"].lower()


def test_predict_surfaces_inference_failure_as_500(loaded_model):
    with patch.object(api.model_service, "predict", side_effect=RuntimeError("bad tensor")):
        response = client.post("/predict", json=SAMPLE_REQUEST)
    assert response.status_code == 500


def test_predict_rejects_a_malformed_body():
    response = client.post("/predict", json={"not_texts": []})
    assert response.status_code == 422


# ── Training ──────────────────────────────────────────────────────────────────


def test_train_returns_a_run_id_immediately():
    """Training is long-running, so /train must hand back a handle, not block."""
    with patch.object(api, "_run_pipeline"):
        response = client.post("/train", json={"sample_size": 10, "epochs": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["poll"] == f"/train/status/{body['run_id']}"


def test_train_status_returns_the_queued_run():
    with patch.object(api, "_run_pipeline"):
        run_id = client.post("/train", json={"sample_size": 10}).json()["run_id"]

    response = client.get(f"/train/status/{run_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["config"]["sample_size"] == 10


def test_train_status_404s_for_an_unknown_run():
    response = client.get("/train/status/not-a-real-run-id")
    assert response.status_code == 404
