"""Configuration management for MLOps pipeline."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PipelineSettings(BaseSettings):
    """Environment-backed settings — validated at import time."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    mlflow_tracking_uri: str = Field(default="./mlruns")
    huggingface_token: str | None = Field(default=None)
    model_dir: str = Field(default="models")
    data_dir: str = Field(default="data")
    pipeline_config_path: str = Field(default="config/pipeline.yaml")


settings = PipelineSettings()


def load_pipeline_config(path: str | None = None) -> dict[str, Any]:
    """Load YAML pipeline config (hyperparams, dataset settings)."""
    config_path = Path(path or settings.pipeline_config_path)
    with open(config_path) as f:
        return yaml.safe_load(f)
