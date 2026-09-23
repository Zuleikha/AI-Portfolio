"""
Model evaluation pipeline for MLOps system
Handles evaluation for both Hugging Face and custom models with comprehensive metrics
"""

import json
import logging
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import mlflow
import mlflow.pytorch
import numpy as np
import pandas as pd
import seaborn as sns
import torch
import yaml
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

try:
    # Works when imported with `src/` on sys.path (e.g. the test suite).
    from data.data_processor import DataManager
    from models.model_manager import BaseModel, ModelManager
except ImportError:
    # Works when imported as part of the `src` package (e.g. `src.evaluation.evaluator`).
    from src.data.data_processor import DataManager
    from src.models.model_manager import BaseModel, ModelManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModelEvaluator:
    """Comprehensive model evaluation system"""

    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.model_manager = ModelManager(config_path)
        self.data_manager = DataManager(config_path)
        self.evaluation_results = {}

    def evaluate_model(
        self, model_name: str, test_data_path: str, save_results: bool = True
    ) -> dict[str, Any]:
        """Comprehensive evaluation of a single model"""

        logger.info(f"Starting evaluation for model: {model_name}")

        # Load model
        model = self.model_manager.load_model(model_name)
        model_config = self.config["models"]["available"][model_name]

        # Process test data
        model_type = "huggingface" if model_config["source"] == "huggingface" else "custom"
        data_splits = self.data_manager.process_data(test_data_path, model_type)

        # Get test data
        if model_config["source"] == "huggingface":
            test_data = data_splits["test"]
            predictions, true_labels = self._evaluate_hf_model(model, test_data)
        else:
            test_data = data_splits["test"]
            predictions, true_labels = self._evaluate_custom_model(model, test_data)

        # Calculate comprehensive metrics
        metrics = self._calculate_metrics(predictions, true_labels)

        # Generate evaluation report
        report = self._generate_evaluation_report(model_name, metrics, predictions, true_labels)

        # Store results
        self.evaluation_results[model_name] = {
            "metrics": metrics,
            "predictions": predictions,
            "true_labels": true_labels,
            "report": report,
        }

        # Save results if requested
        if save_results:
            self._save_evaluation_results(model_name, report)

        # Log to MLflow
        with mlflow.start_run(run_name=f"{model_name}_evaluation"):
            for metric_name, value in metrics.items():
                if isinstance(value, (int, float)):
                    mlflow.log_metric(metric_name, value)

            mlflow.log_text(json.dumps(report, indent=2), "evaluation_report.json")

        logger.info(f"Evaluation completed for {model_name}")
        return report

    def _evaluate_hf_model(self, model: BaseModel, test_data) -> tuple[np.ndarray, np.ndarray]:
        """Evaluate Hugging Face model"""
        from transformers import AutoTokenizer

        # Tokenize test data
        tokenizer = AutoTokenizer.from_pretrained(model.model_name)

        def tokenize_function(examples):
            return tokenizer(
                examples["text"],
                truncation=True,
                padding=True,
                max_length=self.config["training"]["max_seq_length"],
            )

        tokenized_test = test_data.map(tokenize_function, batched=True)

        # Get predictions
        predictions = []
        true_labels = []

        model.model.eval()
        device = next(model.model.parameters()).device

        for i in range(len(tokenized_test)):
            inputs = {
                "input_ids": torch.tensor([tokenized_test[i]["input_ids"]]).to(device),
                "attention_mask": torch.tensor([tokenized_test[i]["attention_mask"]]).to(device),
            }

            with torch.no_grad():
                outputs = model.model(**inputs)
                logits = outputs.logits
                predicted_class = torch.argmax(logits, dim=-1).item()

                predictions.append(predicted_class)
                true_labels.append(tokenized_test[i]["labels"])

        return np.array(predictions), np.array(true_labels)

    def _evaluate_custom_model(self, model: BaseModel, test_data) -> tuple[np.ndarray, np.ndarray]:
        """Evaluate custom PyTorch model"""
        # Get data loader for test data
        test_dataloaders = self.data_manager.get_data_loaders(batch_size=32)
        test_loader = test_dataloaders["test"]

        model.model.eval()
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.model.to(device)

        predictions = []
        true_labels = []

        with torch.no_grad():
            for batch in test_loader:
                input_ids = batch["input_ids"].to(device)
                labels = batch["labels"].to(device)

                outputs = model.model(input_ids)
                predicted_classes = torch.argmax(outputs, dim=-1)

                predictions.extend(predicted_classes.cpu().numpy())
                true_labels.extend(labels.cpu().numpy())

        return np.array(predictions), np.array(true_labels)

    def _calculate_metrics(
        self, predictions: np.ndarray, true_labels: np.ndarray
    ) -> dict[str, float]:
        """Calculate comprehensive evaluation metrics"""

        metrics = {}

        # Basic classification metrics
        metrics["accuracy"] = accuracy_score(true_labels, predictions)
        metrics["precision_macro"] = precision_score(true_labels, predictions, average="macro")
        metrics["precision_micro"] = precision_score(true_labels, predictions, average="micro")
        metrics["recall_macro"] = recall_score(true_labels, predictions, average="macro")
        metrics["recall_micro"] = recall_score(true_labels, predictions, average="micro")
        metrics["f1_macro"] = f1_score(true_labels, predictions, average="macro")
        metrics["f1_micro"] = f1_score(true_labels, predictions, average="micro")

        # Per-class metrics
        unique_labels = np.unique(true_labels)
        for label in unique_labels:
            label_name = f"class_{label}"
            metrics[f"{label_name}_precision"] = (
                precision_score(true_labels, predictions, labels=[label], average=None)[0]
                if label in predictions
                else 0.0
            )
            metrics[f"{label_name}_recall"] = (
                recall_score(true_labels, predictions, labels=[label], average=None)[0]
                if label in predictions
                else 0.0
            )
            metrics[f"{label_name}_f1"] = (
                f1_score(true_labels, predictions, labels=[label], average=None)[0]
                if label in predictions
                else 0.0
            )

        # Confusion matrix statistics
        cm = confusion_matrix(true_labels, predictions)
        metrics["confusion_matrix"] = cm.tolist()

        # Additional metrics for binary classification
        if len(unique_labels) == 2:
            try:
                metrics["roc_auc"] = roc_auc_score(true_labels, predictions)
                metrics["average_precision"] = average_precision_score(true_labels, predictions)
            except ValueError:
                # Handle cases where only one class is present
                metrics["roc_auc"] = 0.0
                metrics["average_precision"] = 0.0

        return metrics

    def _generate_evaluation_report(
        self,
        model_name: str,
        metrics: dict[str, float],
        predictions: np.ndarray,
        true_labels: np.ndarray,
    ) -> dict[str, Any]:
        """Generate comprehensive evaluation report"""

        report = {
            "model_name": model_name,
            "evaluation_timestamp": pd.Timestamp.now().isoformat(),
            "dataset_size": len(true_labels),
            "num_classes": len(np.unique(true_labels)),
            "class_distribution": {
                f"class_{label}": int(count)
                for label, count in zip(*np.unique(true_labels, return_counts=True), strict=True)
            },
            "metrics": metrics,
            "classification_report": classification_report(
                true_labels, predictions, output_dict=True
            ),
            "model_config": self.config["models"]["available"][model_name],
        }

        return report

    def _save_evaluation_results(self, model_name: str, report: dict[str, Any]):
        """Save evaluation results to file"""
        results_dir = Path("evaluation_results")
        results_dir.mkdir(exist_ok=True)

        # Save detailed report
        report_path = results_dir / f"{model_name}_evaluation_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        # Save visualizations
        self._create_evaluation_visualizations(model_name, report)

        logger.info(f"Evaluation results saved to {results_dir}")

    def _create_evaluation_visualizations(self, model_name: str, report: dict[str, Any]):
        """Create evaluation visualizations"""
        results_dir = Path("evaluation_results")

        # Confusion matrix heatmap
        cm = np.array(report["metrics"]["confusion_matrix"])
        plt.figure(figsize=(8, 6))
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues")
        plt.title(f"Confusion Matrix - {model_name}")
        plt.ylabel("True Label")
        plt.xlabel("Predicted Label")
        plt.savefig(
            results_dir / f"{model_name}_confusion_matrix.png", dpi=300, bbox_inches="tight"
        )
        plt.close()

        # Metrics bar plot
        key_metrics = ["accuracy", "precision_macro", "recall_macro", "f1_macro"]
        metric_values = [report["metrics"].get(metric, 0) for metric in key_metrics]

        plt.figure(figsize=(10, 6))
        bars = plt.bar(key_metrics, metric_values)
        plt.title(f"Key Metrics - {model_name}")
        plt.ylabel("Score")
        plt.ylim(0, 1)

        # Add value labels on bars
        for bar, value in zip(bars, metric_values, strict=True):
            plt.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.01,
                f"{value:.3f}",
                ha="center",
                va="bottom",
            )

        plt.tight_layout()
        plt.savefig(results_dir / f"{model_name}_metrics.png", dpi=300, bbox_inches="tight")
        plt.close()

    def compare_models(self, model_names: list[str], test_data_path: str) -> dict[str, Any]:
        """Compare multiple models on the same test dataset"""

        logger.info(f"Comparing models: {model_names}")

        comparison_results = {}

        # Evaluate each model
        for model_name in model_names:
            try:
                result = self.evaluate_model(model_name, test_data_path, save_results=False)
                comparison_results[model_name] = result
            except Exception as e:
                logger.error(f"Failed to evaluate {model_name}: {e}")
                comparison_results[model_name] = {"error": str(e)}

        # Create comparison report
        comparison_report = self._create_comparison_report(comparison_results)

        # Save comparison results
        self._save_comparison_results(comparison_report)

        return comparison_report

    def _create_comparison_report(self, results: dict[str, Any]) -> dict[str, Any]:
        """Create model comparison report"""

        comparison_metrics = ["accuracy", "precision_macro", "recall_macro", "f1_macro"]

        comparison_data = {}
        for metric in comparison_metrics:
            comparison_data[metric] = {}
            for model_name, result in results.items():
                if "error" not in result:
                    comparison_data[metric][model_name] = result["metrics"].get(metric, 0)

        # Find best model for each metric
        best_models = {}
        for metric in comparison_metrics:
            if comparison_data[metric]:
                best_model = max(comparison_data[metric], key=comparison_data[metric].get)
                best_models[metric] = {
                    "model": best_model,
                    "score": comparison_data[metric][best_model],
                }

        comparison_report = {
            "comparison_timestamp": pd.Timestamp.now().isoformat(),
            "models_compared": list(results.keys()),
            "comparison_metrics": comparison_data,
            "best_models_by_metric": best_models,
            "detailed_results": results,
        }

        return comparison_report

    def _save_comparison_results(self, comparison_report: dict[str, Any]):
        """Save model comparison results"""
        results_dir = Path("evaluation_results")
        results_dir.mkdir(exist_ok=True)

        # Save comparison report
        comparison_path = results_dir / "model_comparison_report.json"
        with open(comparison_path, "w") as f:
            json.dump(comparison_report, f, indent=2, default=str)

        # Create comparison visualization
        self._create_comparison_visualization(comparison_report)

        logger.info(f"Comparison results saved to {results_dir}")

    def _create_comparison_visualization(self, comparison_report: dict[str, Any]):
        """Create model comparison visualization"""
        results_dir = Path("evaluation_results")

        metrics_data = comparison_report["comparison_metrics"]

        # Create comparison bar plot
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle("Model Performance Comparison", fontsize=16)

        metrics = ["accuracy", "precision_macro", "recall_macro", "f1_macro"]
        positions = [(0, 0), (0, 1), (1, 0), (1, 1)]

        for metric, (row, col) in zip(metrics, positions, strict=True):
            ax = axes[row, col]

            if metric in metrics_data and metrics_data[metric]:
                models = list(metrics_data[metric].keys())
                scores = list(metrics_data[metric].values())

                bars = ax.bar(models, scores)
                ax.set_title(f"{metric.replace('_', ' ').title()}")
                ax.set_ylabel("Score")
                ax.set_ylim(0, 1)

                # Add value labels
                for bar, score in zip(bars, scores, strict=True):
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.01,
                        f"{score:.3f}",
                        ha="center",
                        va="bottom",
                    )

                # Rotate x-axis labels if needed
                if len(models) > 3:
                    ax.tick_params(axis="x", rotation=45)

        plt.tight_layout()
        plt.savefig(results_dir / "model_comparison.png", dpi=300, bbox_inches="tight")
        plt.close()


# Example usage and testing
if __name__ == "__main__":
    # Initialize evaluator
    evaluator = ModelEvaluator()

    print("Model evaluator initialized successfully!")
    print("Available evaluation methods:")
    print("- evaluate_model(): Comprehensive single model evaluation")
    print("- compare_models(): Multi-model comparison")
