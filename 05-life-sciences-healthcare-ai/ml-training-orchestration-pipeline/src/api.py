"""FastAPI service for MLOps pipeline."""

import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import torch
import yaml
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
PREDICT_REQUESTS = Counter("predict_requests_total", "Total /predict calls")
PREDICT_ERRORS = Counter("predict_errors_total", "Total /predict errors")
TRAIN_REQUESTS = Counter("train_requests_total", "Total /train calls")
PREDICT_LATENCY = Histogram("predict_latency_seconds", "Prediction latency")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class PredictionRequest(BaseModel):
    texts: list[str]
    return_probabilities: bool = False


class PredictionResponse(BaseModel):
    predictions: list[dict[str, Any]]
    model_info: dict[str, str]


class TrainingRequest(BaseModel):
    dataset_name: str = "SetFit/ade_corpus_v2_classification"
    sample_size: int = 100
    epochs: int = 1
    batch_size: int = 16


# ---------------------------------------------------------------------------
# Model service
# ---------------------------------------------------------------------------
class ModelService:
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_loaded = False

    def load_model(self, model_path: str = "models/trained_model") -> bool:
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            if not Path(model_path).exists():
                logger.warning(f"Model not found at {model_path}")
                return False

            self.tokenizer = AutoTokenizer.from_pretrained(model_path)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
            self.model.to(self.device)
            self.model.eval()
            self.model_loaded = True
            logger.info(f"Model loaded from {model_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False

    def predict(self, texts: list[str], return_probabilities: bool = False) -> list[dict[str, Any]]:
        if not self.model_loaded:
            raise ValueError("Model not loaded")

        predictions = []
        with torch.no_grad():
            for text in texts:
                inputs = self.tokenizer(
                    text, return_tensors="pt", truncation=True, padding=True, max_length=512
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
                outputs = self.model(**inputs)
                logits = outputs.logits
                predicted_class = torch.argmax(logits, dim=-1).item()

                result = {
                    "text": text[:100] + "..." if len(text) > 100 else text,
                    "predicted_class": predicted_class,
                    "prediction": "positive" if predicted_class == 1 else "negative",
                }

                if return_probabilities:
                    probs = torch.softmax(logits, dim=-1).cpu().numpy()[0]
                    result["probabilities"] = {
                        "negative": float(probs[0]),
                        "positive": float(probs[1]),
                    }

                predictions.append(result)

        return predictions


model_service = ModelService()

# ---------------------------------------------------------------------------
# Background training state  (in-memory; resets on restart)
# ---------------------------------------------------------------------------
train_runs: dict[str, dict[str, Any]] = {}


def _run_pipeline(run_id: str, config_path: Path, request: TrainingRequest) -> None:
    """Blocking training work executed in a background thread."""
    try:
        train_runs[run_id]["status"] = "running"
        train_runs[run_id]["started_at"] = datetime.now().isoformat()

        from dagster import materialize

        from src.dagster_definitions import all_assets

        with open(config_path) as f:
            config = yaml.safe_load(f)

        config["data"]["huggingface"]["sample_size"] = request.sample_size
        config["training"]["epochs"] = request.epochs
        config["training"]["batch_size"] = request.batch_size

        with open(config_path, "w") as f:
            yaml.dump(config, f)

        logger.info(f"[{run_id}] Starting training with {request.sample_size} samples…")
        result = materialize(all_assets)

        if result.success:
            model_service.load_model()
            train_runs[run_id]["status"] = "success"
            train_runs[run_id]["finished_at"] = datetime.now().isoformat()
            logger.info(f"[{run_id}] Training complete.")
        else:
            train_runs[run_id]["status"] = "failed"
            train_runs[run_id]["error"] = "Dagster materialisation returned failure"
            train_runs[run_id]["finished_at"] = datetime.now().isoformat()

    except Exception as e:
        logger.error(f"[{run_id}] Training failed: {e}")
        train_runs[run_id]["status"] = "failed"
        train_runs[run_id]["error"] = str(e)
        train_runs[run_id]["finished_at"] = datetime.now().isoformat()


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MLOps Pipeline API…")
    if Path("models/trained_model").exists():
        model_service.load_model()
    else:
        logger.warning("No trained model found. Use /train to train a model first.")
    yield


app = FastAPI(
    title="MLOps Pipeline API",
    description="Production API for the MLOps training pipeline",
    version="2.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/")
async def root():
    return {
        "message": "MLOps Pipeline API",
        "version": "2.0.0",
        "model_loaded": model_service.model_loaded,
        "device": str(model_service.device),
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "model_loaded": model_service.model_loaded,
        "device": str(model_service.device),
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    PREDICT_REQUESTS.inc()
    if not model_service.model_loaded:
        PREDICT_ERRORS.inc()
        raise HTTPException(
            status_code=503,
            detail="Model not loaded. Train a model first using /train.",
        )
    try:
        with PREDICT_LATENCY.time():
            predictions = model_service.predict(request.texts, request.return_probabilities)
        return PredictionResponse(
            predictions=predictions,
            model_info={"device": str(model_service.device), "model_path": "models/trained_model"},
        )
    except Exception as e:
        PREDICT_ERRORS.inc()
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/train")
async def train_model(request: TrainingRequest, background_tasks: BackgroundTasks):
    """Kick off async training. Returns immediately with a run_id."""
    TRAIN_REQUESTS.inc()
    run_id = str(uuid.uuid4())
    train_runs[run_id] = {
        "run_id": run_id,
        "status": "queued",
        "queued_at": datetime.now().isoformat(),
        "config": {
            "dataset_name": request.dataset_name,
            "sample_size": request.sample_size,
            "epochs": request.epochs,
            "batch_size": request.batch_size,
        },
    }
    config_path = Path("config/pipeline.yaml")
    background_tasks.add_task(_run_pipeline, run_id, config_path, request)
    return {"run_id": run_id, "status": "queued", "poll": f"/train/status/{run_id}"}


@app.get("/train/status/{run_id}")
async def train_status(run_id: str):
    """Check the status of a training run."""
    if run_id not in train_runs:
        raise HTTPException(status_code=404, detail=f"run_id {run_id!r} not found.")
    return train_runs[run_id]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
