"""
Training pipeline for MLOps system
Handles training for both Hugging Face and custom models
"""

import logging
from typing import Any

import mlflow
import mlflow.pytorch
import torch
import torch.nn as nn
import yaml
from torch.optim import AdamW
from transformers import AutoTokenizer, Trainer, TrainingArguments

from ..data.data_processor import DataManager
from ..models.model_manager import BaseModel, ModelManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MLOpsTrainer:
    """Main training orchestrator for the MLOps pipeline"""

    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.model_manager = ModelManager(config_path)
        self.data_manager = DataManager(config_path)

        # Initialize MLflow
        mlflow.set_tracking_uri(self.config.get("mlflow_tracking_uri", "mlruns"))
        mlflow.set_experiment(self.config["project"]["name"])

    def train_model(
        self, model_name: str, data_path: str, hyperopt: bool = False
    ) -> dict[str, Any]:
        """Train a specific model with the data pipeline"""

        logger.info(f"Starting training for model: {model_name}")

        # Load model
        model = self.model_manager.load_model(model_name)
        model_config = self.config["models"]["available"][model_name]

        # Process data according to model type
        model_type = "huggingface" if model_config["source"] == "huggingface" else "custom"
        data_splits = self.data_manager.process_data(data_path, model_type)

        if hyperopt and self.config["training"]["hyperopt"]["enabled"]:
            return self._hyperparameter_optimization(model, model_name, data_splits)
        else:
            return self._standard_training(model, model_name, data_splits)

    def _standard_training(self, model: BaseModel, model_name: str, data_splits) -> dict[str, Any]:
        """Standard training without hyperparameter optimization"""

        with mlflow.start_run(run_name=f"{model_name}_standard_training"):
            # Log configuration
            mlflow.log_params(
                {
                    "model_name": model_name,
                    "model_source": model.config["source"],
                    "batch_size": self.config["training"]["batch_size"],
                    "learning_rate": self.config["training"]["learning_rate"],
                    "epochs": self.config["training"]["epochs"],
                }
            )

            # Train model
            if model.config["source"] == "huggingface":
                metrics = self._train_hf_model(model, data_splits)
            else:
                metrics = self._train_custom_model(model, data_splits)

            # Log metrics
            for metric_name, value in metrics.items():
                mlflow.log_metric(metric_name, value)

            # Save model
            model_path = f"models/{model_name}_trained"
            model.save_model(model_path)

            # Log model to MLflow
            mlflow.log_artifacts(model_path)

            logger.info(f"Training completed for {model_name}")
            return metrics

    def _train_hf_model(self, model: BaseModel, data_splits) -> dict[str, float]:
        """Train Hugging Face model"""

        # Tokenize datasets
        tokenizer = AutoTokenizer.from_pretrained(model.model_name)

        def tokenize_function(examples):
            return tokenizer(
                examples["text"],
                truncation=True,
                padding=True,
                max_length=self.config["training"]["max_seq_length"],
            )

        tokenized_datasets = data_splits.map(tokenize_function, batched=True)

        # Training arguments
        training_args = TrainingArguments(
            output_dir=f"./models/checkpoints/{model.model_name}",
            num_train_epochs=self.config["training"]["epochs"],
            per_device_train_batch_size=self.config["training"]["batch_size"],
            per_device_eval_batch_size=self.config["training"]["batch_size"],
            learning_rate=self.config["training"]["learning_rate"],
            warmup_steps=self.config["training"]["warmup_steps"],
            logging_dir=f"./logs/{model.model_name}",
            logging_steps=100,
            evaluation_strategy="epoch",
            save_strategy="epoch",
            load_best_model_at_end=True,
            metric_for_best_model="eval_loss",
            greater_is_better=False,
            report_to=["mlflow"],
        )

        # Initialize trainer
        trainer = Trainer(
            model=model.model,
            args=training_args,
            train_dataset=tokenized_datasets["train"],
            eval_dataset=tokenized_datasets["validation"],
            tokenizer=tokenizer,
        )

        # Train
        trainer.train()

        # Evaluate
        eval_results = trainer.evaluate(tokenized_datasets["test"])

        return {
            "final_train_loss": trainer.state.log_history[-2]["train_loss"],
            "final_eval_loss": eval_results["eval_loss"],
            "eval_runtime": eval_results["eval_runtime"],
        }

    def _train_custom_model(self, model: BaseModel, data_splits) -> dict[str, float]:
        """Train custom PyTorch model"""

        # Get data loaders
        dataloaders = self.data_manager.get_data_loaders(
            batch_size=self.config["training"]["batch_size"]
        )

        # Setup training components
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.model.to(device)

        optimizer = AdamW(model.model.parameters(), lr=self.config["training"]["learning_rate"])

        criterion = nn.CrossEntropyLoss()

        # Training loop
        best_val_loss = float("inf")
        train_losses = []
        val_losses = []

        for epoch in range(self.config["training"]["epochs"]):
            # Training phase
            model.model.train()
            epoch_train_loss = 0.0

            for batch in dataloaders["train"]:
                optimizer.zero_grad()

                input_ids = batch["input_ids"].to(device)
                labels = batch["labels"].to(device)

                outputs = model.model(input_ids)
                loss = criterion(outputs, labels)

                loss.backward()
                optimizer.step()

                epoch_train_loss += loss.item()

            avg_train_loss = epoch_train_loss / len(dataloaders["train"])
            train_losses.append(avg_train_loss)

            # Validation phase
            model.model.eval()
            epoch_val_loss = 0.0

            with torch.no_grad():
                for batch in dataloaders["validation"]:
                    input_ids = batch["input_ids"].to(device)
                    labels = batch["labels"].to(device)

                    outputs = model.model(input_ids)
                    loss = criterion(outputs, labels)

                    epoch_val_loss += loss.item()

            avg_val_loss = epoch_val_loss / len(dataloaders["validation"])
            val_losses.append(avg_val_loss)

            # Log metrics
            mlflow.log_metrics({"train_loss": avg_train_loss, "val_loss": avg_val_loss}, step=epoch)

            # Save best model
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                torch.save(
                    model.model.state_dict(), f"models/{model.config['architecture']}_best.pt"
                )

            logger.info(
                f"Epoch {epoch + 1}/{self.config['training']['epochs']} - "
                f"Train Loss: {avg_train_loss:.4f}, Val Loss: {avg_val_loss:.4f}"
            )

        return {
            "final_train_loss": train_losses[-1],
            "final_val_loss": val_losses[-1],
            "best_val_loss": best_val_loss,
        }

    def _hyperparameter_optimization(
        self, model: BaseModel, model_name: str, data_splits
    ) -> dict[str, Any]:
        """Grid-search hyperparameter optimization tracked via MLflow."""

        logger.info(f"Starting hyperparameter optimization for {model_name}")

        grid = (
            self.config["training"]
            .get("hyperopt", {})
            .get(
                "grid",
                {
                    "learning_rate": [1e-5, 3e-5, 1e-4],
                    "batch_size": [16, 32],
                    "epochs": [3],
                },
            )
        )

        best_score = float("inf")
        best_params: dict[str, Any] = {}

        from itertools import product

        keys = list(grid.keys())
        for combo in product(*[grid[k] for k in keys]):
            params = dict(zip(keys, combo, strict=True))
            original = self.config["training"].copy()
            self.config["training"].update(params)

            try:
                with mlflow.start_run(run_name=f"{model_name}_trial", nested=True):
                    mlflow.log_params(params)
                    if model.config["source"] == "huggingface":
                        metrics = self._train_hf_model(model, data_splits)
                        score = metrics["final_eval_loss"]
                    else:
                        metrics = self._train_custom_model(model, data_splits)
                        score = metrics["final_val_loss"]
                    mlflow.log_metric("trial_score", score)

                if score < best_score:
                    best_score = score
                    best_params = params

            except Exception as e:
                logger.error(f"Trial {params} failed: {e}")
            finally:
                self.config["training"] = original

        logger.info(f"Best hyperparameters: {best_params} (score={best_score:.4f})")

        self.config["training"].update(best_params)
        final_metrics = self._standard_training(model, f"{model_name}_optimized", data_splits)

        return {"best_params": best_params, "best_score": best_score, **final_metrics}

    def compare_models(self, model_names: list[str], data_path: str) -> dict[str, dict]:
        """Compare multiple models on the same dataset"""

        logger.info(f"Comparing models: {model_names}")

        results = {}

        with mlflow.start_run(run_name="model_comparison"):
            for model_name in model_names:
                logger.info(f"Training model for comparison: {model_name}")

                model_metrics = self.train_model(model_name, data_path, hyperopt=False)

                results[model_name] = model_metrics

                # Log comparison metrics
                mlflow.log_metrics(
                    {
                        f"{model_name}_final_loss": model_metrics.get(
                            "final_val_loss", model_metrics.get("final_eval_loss", 0)
                        )
                    }
                )

        # Log comparison results
        logger.info("Model comparison results:")
        for model_name, metrics in results.items():
            logger.info(f"  {model_name}: {metrics}")

        return results


# Example usage
if __name__ == "__main__":
    # Initialize trainer
    trainer = MLOpsTrainer()

    # Train single model
    try:
        results = trainer.train_model(
            model_name="bert_classifier", data_path="data/sample_data.csv", hyperopt=False
        )
        print(f"Training results: {results}")

    except Exception as e:
        print(f"Training failed: {e}")
