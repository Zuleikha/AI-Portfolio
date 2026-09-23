"""Dagster definitions for MLOps pipeline with complete training"""

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import torch
import yaml
from dagster import Definitions, asset


@asset
def pipeline_config() -> dict[str, Any]:
    """Load pipeline configuration"""
    with open("config/pipeline.yaml") as f:
        config_data = yaml.safe_load(f)
    return config_data


@asset
def dataset_info(pipeline_config: dict[str, Any]) -> dict[str, Any]:
    """Get information about the dataset to be used"""
    hf_config = pipeline_config["data"]["huggingface"]

    info = {
        "dataset_name": hf_config["dataset_name"],
        "sample_size": hf_config["sample_size"],
        "text_column": hf_config["text_column"],
        "label_column": hf_config["label_column"],
    }

    return info


@asset
def raw_dataset(dataset_info: dict[str, Any]) -> dict[str, Any]:
    """Load raw dataset from Hugging Face"""
    from datasets import load_dataset

    dataset_name = dataset_info["dataset_name"]
    sample_size = dataset_info["sample_size"]

    if sample_size:
        dataset = load_dataset(dataset_name, split=f"train[:{sample_size}]")
        test_dataset = load_dataset(dataset_name, split=f"test[:{sample_size // 4}]")
    else:
        full_dataset = load_dataset(dataset_name)
        dataset = full_dataset["train"]
        test_dataset = full_dataset["test"]

    train_df = dataset.to_pandas()
    test_df = test_dataset.to_pandas()

    Path("data/processed").mkdir(parents=True, exist_ok=True)
    train_df.to_parquet("data/processed/train_data.parquet")
    test_df.to_parquet("data/processed/test_data.parquet")

    return {
        "train_samples": len(train_df),
        "test_samples": len(test_df),
        "train_path": "data/processed/train_data.parquet",
        "test_path": "data/processed/test_data.parquet",
        "columns": list(train_df.columns),
    }


@asset
def processed_train_data(raw_dataset: dict[str, Any]) -> pd.DataFrame:
    """Load and preprocess training data"""
    train_df = pd.read_parquet(raw_dataset["train_path"])

    train_df = train_df.dropna()
    train_df["text_length"] = train_df["text"].str.len()
    train_df = train_df[(train_df["text_length"] >= 10) & (train_df["text_length"] <= 5000)]

    return train_df


@asset
def processed_test_data(raw_dataset: dict[str, Any]) -> pd.DataFrame:
    """Load and preprocess test data"""
    test_df = pd.read_parquet(raw_dataset["test_path"])

    test_df = test_df.dropna()
    test_df["text_length"] = test_df["text"].str.len()
    test_df = test_df[(test_df["text_length"] >= 10) & (test_df["text_length"] <= 5000)]

    return test_df


@asset
def model_config(pipeline_config: dict[str, Any]) -> dict[str, Any]:
    """Extract model configuration with proper type conversion"""
    training_config = pipeline_config["training"]

    model_config = {
        "model_name": training_config["pretrained_model"],
        "task_type": training_config["task_type"],
        "num_labels": 2,
        "max_length": int(training_config["max_length"]),
        "learning_rate": float(training_config["learning_rate"]),
        "batch_size": int(training_config["batch_size"]),
        "num_epochs": int(training_config["epochs"]),
        "warmup_steps": int(training_config["warmup_steps"]),
    }

    return model_config


@asset
def pretrained_model_setup(model_config: dict[str, Any]) -> dict[str, Any]:
    """Setup pretrained model and tokenizer"""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    model_name = model_config["model_name"]
    num_labels = model_config["num_labels"]

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=num_labels)

    Path("models/pretrained").mkdir(parents=True, exist_ok=True)
    tokenizer.save_pretrained("models/pretrained")

    model_info = {
        "model_name": model_name,
        "num_parameters": sum(p.numel() for p in model.parameters()),
        "learning_rate": model_config["learning_rate"],
        "device": "cuda" if torch.cuda.is_available() else "cpu",
    }

    return model_info


@asset
def training_datasets(
    processed_train_data: pd.DataFrame,
    processed_test_data: pd.DataFrame,
    model_config: dict[str, Any],
) -> dict[str, Any]:
    """Prepare datasets for training"""
    from datasets import Dataset
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained("models/pretrained")

    def tokenize_function(examples):
        return tokenizer(
            examples["text"], truncation=True, padding=True, max_length=model_config["max_length"]
        )

    train_dataset = Dataset.from_pandas(processed_train_data[["text", "label"]])
    train_dataset = train_dataset.map(tokenize_function, batched=True)

    val_dataset = Dataset.from_pandas(processed_test_data[["text", "label"]])
    val_dataset = val_dataset.map(tokenize_function, batched=True)

    Path("data/processed/tokenized").mkdir(parents=True, exist_ok=True)
    train_dataset.save_to_disk("data/processed/tokenized/train")
    val_dataset.save_to_disk("data/processed/tokenized/validation")

    return {
        "train_dataset_path": "data/processed/tokenized/train",
        "val_dataset_path": "data/processed/tokenized/validation",
        "train_size": len(train_dataset),
        "val_size": len(val_dataset),
    }


@asset
def trained_model(
    training_datasets: dict[str, Any],
    model_config: dict[str, Any],
    pretrained_model_setup: dict[str, Any],
    dataset_info: dict[str, Any],
) -> dict[str, Any]:
    """Train the model"""
    import numpy as np
    from datasets import load_from_disk
    from sklearn.metrics import accuracy_score, precision_recall_fscore_support
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        DataCollatorWithPadding,
        Trainer,
        TrainingArguments,
    )

    tokenizer = AutoTokenizer.from_pretrained("models/pretrained")
    model = AutoModelForSequenceClassification.from_pretrained(
        model_config["model_name"], num_labels=model_config["num_labels"]
    )

    train_dataset = load_from_disk(training_datasets["train_dataset_path"])
    val_dataset = load_from_disk(training_datasets["val_dataset_path"])

    def compute_metrics(eval_pred):
        predictions, labels = eval_pred
        predictions = np.argmax(predictions, axis=1)

        precision, recall, f1, _ = precision_recall_fscore_support(
            labels, predictions, average="weighted"
        )
        accuracy = accuracy_score(labels, predictions)

        return {"accuracy": accuracy, "f1": f1, "precision": precision, "recall": recall}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"models/training_output_{timestamp}"

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=model_config["num_epochs"],
        per_device_train_batch_size=model_config["batch_size"],
        per_device_eval_batch_size=model_config["batch_size"],
        warmup_steps=model_config["warmup_steps"],
        weight_decay=0.01,
        logging_dir=f"{output_dir}/logs",
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        learning_rate=model_config["learning_rate"],
        report_to=[],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        processing_class=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer=tokenizer),
        compute_metrics=compute_metrics,
    )

    train_result = trainer.train()
    eval_result = trainer.evaluate()

    final_model_path = "models/trained_model"
    Path(final_model_path).mkdir(parents=True, exist_ok=True)
    trainer.save_model(final_model_path)

    training_summary = {
        "model_path": final_model_path,
        "training_output_dir": output_dir,
        "train_runtime": train_result.metrics.get("train_runtime", 0),
        "eval_accuracy": eval_result.get("eval_accuracy", 0),
        "eval_f1": eval_result.get("eval_f1", 0),
        "eval_precision": eval_result.get("eval_precision", 0),
        "eval_recall": eval_result.get("eval_recall", 0),
        "eval_loss": eval_result.get("eval_loss", 0),
        "training_timestamp": timestamp,
    }

    with open(f"{final_model_path}/training_summary.yaml", "w") as f:
        yaml.dump(training_summary, f)

    import json

    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    eval_results = {
        "model": model_config["model_name"],
        # Read from the resolved config, not hardcoded — a results file that names
        # a dataset the run did not use is worse than one that names none.
        "dataset": dataset_info["dataset_name"],
        "train_samples": training_datasets["train_size"],
        "test_samples": training_datasets["val_size"],
        "epochs": model_config["num_epochs"],
        "accuracy": round(eval_result.get("eval_accuracy", 0), 4),
        "f1_weighted": round(eval_result.get("eval_f1", 0), 4),
        "precision_weighted": round(eval_result.get("eval_precision", 0), 4),
        "recall_weighted": round(eval_result.get("eval_recall", 0), 4),
        "eval_loss": round(eval_result.get("eval_loss", 0), 4),
        "training_timestamp": timestamp,
    }
    with open("docs/eval_results.json", "w") as f:
        json.dump(eval_results, f, indent=2)

    return training_summary


all_assets = [
    pipeline_config,
    dataset_info,
    raw_dataset,
    processed_train_data,
    processed_test_data,
    model_config,
    pretrained_model_setup,
    training_datasets,
    trained_model,
]

defs = Definitions(assets=all_assets)
