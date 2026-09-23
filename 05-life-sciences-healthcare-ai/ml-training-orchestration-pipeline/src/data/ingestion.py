"""Data ingestion pipeline"""

from pathlib import Path

import pandas as pd
from dagster import Config, asset


class DataIngestionConfig(Config):
    """Configuration for data ingestion"""

    source_path: str
    target_path: str
    file_format: str = "csv"


@asset
def raw_data(config: DataIngestionConfig) -> pd.DataFrame:
    """Ingest raw data from source"""
    source_path = Path(config.source_path)

    if config.file_format == "csv":
        data = pd.read_csv(source_path)
    elif config.file_format == "parquet":
        data = pd.read_parquet(source_path)
    else:
        raise ValueError(f"Unsupported file format: {config.file_format}")

    # Save to target path
    target_path = Path(config.target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    data.to_parquet(target_path)

    return data
