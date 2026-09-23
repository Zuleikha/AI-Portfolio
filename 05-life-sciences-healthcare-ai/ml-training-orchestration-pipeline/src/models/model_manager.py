"""
Multi-model manager for handling Hugging Face and custom models
"""

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import mlflow
import mlflow.pytorch
import mlflow.transformers
import torch
import yaml
from transformers import (
    AutoModel,
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BaseModel(ABC):
    """Abstract base class for all models"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.model = None
        self.tokenizer = None
        self.is_trained = False

    @abstractmethod
    def load_model(self):
        """Load the model"""
        pass

    @abstractmethod
    def train(self, train_data, val_data=None):
        """Train the model"""
        pass

    @abstractmethod
    def predict(self, inputs):
        """Make predictions"""
        pass

    @abstractmethod
    def save_model(self, path: str):
        """Save the model"""
        pass


class HuggingFaceModel(BaseModel):
    """Hugging Face transformer model wrapper"""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.model_name = config["model_name"]
        self.task = config.get("task", "classification")

    def load_model(self):
        """Load Hugging Face model and tokenizer"""
        try:
            logger.info(f"Loading Hugging Face model: {self.model_name}")

            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)

            # Load model based on task
            if self.task == "classification":
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    self.model_name, num_labels=self.config.get("num_labels", 2)
                )
            else:
                self.model = AutoModel.from_pretrained(self.model_name)

            logger.info(f"Successfully loaded {self.model_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to load model {self.model_name}: {e}")
            return False

    def train(self, train_data, val_data=None):
        """Fine-tune the Hugging Face model"""
        if not self.model:
            self.load_model()

        # Training arguments
        training_args = TrainingArguments(
            output_dir=f"./models/checkpoints/{self.model_name}",
            num_train_epochs=self.config.get("epochs", 3),
            per_device_train_batch_size=self.config.get("batch_size", 16),
            per_device_eval_batch_size=self.config.get("batch_size", 16),
            learning_rate=self.config.get("learning_rate", 2e-5),
            warmup_steps=self.config.get("warmup_steps", 500),
            weight_decay=0.01,
            logging_dir=f"./logs/{self.model_name}",
            logging_steps=100,
            evaluation_strategy="epoch" if val_data else "no",
            save_strategy="epoch",
            load_best_model_at_end=bool(val_data),
            metric_for_best_model="eval_loss" if val_data else None,
        )

        # Initialize trainer
        trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=train_data,
            eval_dataset=val_data,
            tokenizer=self.tokenizer,
        )

        # Start MLflow run
        with mlflow.start_run(run_name=f"{self.model_name}_training"):
            # Log parameters
            mlflow.log_params(
                {
                    "model_name": self.model_name,
                    "epochs": training_args.num_train_epochs,
                    "batch_size": training_args.per_device_train_batch_size,
                    "learning_rate": training_args.learning_rate,
                }
            )

            # Train model
            logger.info(f"Starting training for {self.model_name}")
            trainer.train()

            # Log model
            mlflow.transformers.log_model(
                transformers_model={"model": self.model, "tokenizer": self.tokenizer},
                artifact_path="model",
                registered_model_name=f"{self.model_name}_finetuned",
            )

        self.is_trained = True
        logger.info(f"Training completed for {self.model_name}")

    def predict(self, inputs):
        """Make predictions with the model"""
        if not self.model:
            self.load_model()

        # Tokenize inputs
        if isinstance(inputs, str):
            inputs = [inputs]

        encoded = self.tokenizer(
            inputs,
            padding=True,
            truncation=True,
            max_length=self.config.get("max_seq_length", 512),
            return_tensors="pt",
        )

        # Get predictions
        with torch.no_grad():
            outputs = self.model(**encoded)
            predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)

        return predictions.numpy()

    def save_model(self, path: str):
        """Save the fine-tuned model"""
        if not self.model:
            raise ValueError("No model loaded to save")

        save_path = Path(path)
        save_path.mkdir(parents=True, exist_ok=True)

        self.model.save_pretrained(save_path)
        self.tokenizer.save_pretrained(save_path)

        logger.info(f"Model saved to {save_path}")


class CustomModel(BaseModel):
    """Custom PyTorch model wrapper"""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.model_path = config.get("model_path")
        self.architecture = config.get("architecture", "lstm")

    def load_model(self):
        """Load custom PyTorch model"""
        if self.model_path and os.path.exists(self.model_path):
            try:
                self.model = torch.load(self.model_path)
                logger.info(f"Loaded custom model from {self.model_path}")
                return True
            except Exception as e:
                logger.error(f"Failed to load custom model: {e}")
                return False
        else:
            # Initialize new model based on architecture
            self.model = self._create_model()
            logger.info(f"Initialized new {self.architecture} model")
            return True

    def _create_model(self):
        """Create a new model based on architecture"""
        # Placeholder for custom model architectures
        if self.architecture == "lstm":
            return self._create_lstm_model()
        elif self.architecture == "cnn":
            return self._create_cnn_model()
        else:
            raise ValueError(f"Unknown architecture: {self.architecture}")

    def _create_lstm_model(self):
        """Create LSTM model for text classification"""
        import torch.nn as nn

        class LSTMClassifier(nn.Module):
            def __init__(self, vocab_size=10000, embed_dim=128, hidden_dim=64, num_classes=2):
                super().__init__()
                self.embedding = nn.Embedding(vocab_size, embed_dim)
                self.lstm = nn.LSTM(embed_dim, hidden_dim, batch_first=True)
                self.classifier = nn.Linear(hidden_dim, num_classes)
                self.dropout = nn.Dropout(0.3)

            def forward(self, x):
                embedded = self.embedding(x)
                lstm_out, (hidden, _) = self.lstm(embedded)
                hidden = self.dropout(hidden[-1])
                return self.classifier(hidden)

        return LSTMClassifier()

    def _create_cnn_model(self):
        """Create CNN model for text classification"""
        import torch.nn as nn

        class CNNClassifier(nn.Module):
            def __init__(self, vocab_size=10000, embed_dim=128, num_filters=100, num_classes=2):
                super().__init__()
                self.embedding = nn.Embedding(vocab_size, embed_dim)
                self.conv1 = nn.Conv1d(embed_dim, num_filters, kernel_size=3)
                self.conv2 = nn.Conv1d(embed_dim, num_filters, kernel_size=4)
                self.conv3 = nn.Conv1d(embed_dim, num_filters, kernel_size=5)
                self.dropout = nn.Dropout(0.3)
                self.classifier = nn.Linear(num_filters * 3, num_classes)

            def forward(self, x):
                embedded = self.embedding(x).transpose(1, 2)
                conv1_out = torch.relu(self.conv1(embedded))
                conv2_out = torch.relu(self.conv2(embedded))
                conv3_out = torch.relu(self.conv3(embedded))

                pooled1 = torch.max_pool1d(conv1_out, conv1_out.size(2)).squeeze(2)
                pooled2 = torch.max_pool1d(conv2_out, conv2_out.size(2)).squeeze(2)
                pooled3 = torch.max_pool1d(conv3_out, conv3_out.size(2)).squeeze(2)

                concatenated = torch.cat([pooled1, pooled2, pooled3], dim=1)
                dropped = self.dropout(concatenated)
                return self.classifier(dropped)

        return CNNClassifier()

    def train(self, train_data, val_data=None):
        """Train the custom model"""
        # Implementation for custom model training
        logger.info(f"Training custom {self.architecture} model")
        # This would contain the custom training loop
        pass

    def predict(self, inputs):
        """Make predictions with custom model"""
        if not self.model:
            self.load_model()

        # Custom prediction logic
        with torch.no_grad():
            outputs = self.model(inputs)
            predictions = torch.nn.functional.softmax(outputs, dim=-1)

        return predictions.numpy()

    def save_model(self, path: str):
        """Save the custom model"""
        if not self.model:
            raise ValueError("No model loaded to save")

        save_path = Path(path)
        save_path.mkdir(parents=True, exist_ok=True)

        torch.save(self.model, save_path / "model.pt")
        logger.info(f"Custom model saved to {save_path}")


class ModelManager:
    """Central manager for all models in the pipeline"""

    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.models = {}
        self.active_model = None

    def load_model(self, model_name: str) -> BaseModel:
        """Load a specific model by name"""
        if model_name in self.models:
            return self.models[model_name]

        model_config = self.config["models"]["available"].get(model_name)
        if not model_config:
            raise ValueError(f"Model {model_name} not found in configuration")

        # Create appropriate model instance
        if model_config["source"] == "huggingface":
            model = HuggingFaceModel(model_config)
        elif model_config["source"] == "local":
            model = CustomModel(model_config)
        else:
            raise ValueError(f"Unknown model source: {model_config['source']}")

        # Load the model
        if model.load_model():
            self.models[model_name] = model
            logger.info(f"Successfully loaded model: {model_name}")
            return model
        else:
            raise RuntimeError(f"Failed to load model: {model_name}")

    def get_available_models(self):
        """Get list of available models"""
        return list(self.config["models"]["available"].keys())

    def set_active_model(self, model_name: str):
        """Set the active model for the pipeline"""
        if model_name not in self.models:
            self.load_model(model_name)

        self.active_model = self.models[model_name]
        logger.info(f"Active model set to: {model_name}")

    def compare_models(self, model_names: list, test_data):
        """Compare performance of multiple models"""
        results = {}

        for model_name in model_names:
            if model_name not in self.models:
                self.load_model(model_name)

            model = self.models[model_name]
            # Run evaluation
            predictions = model.predict(test_data)
            # Calculate metrics (would be implemented with actual evaluation logic)
            results[model_name] = {
                "predictions": predictions,
                "model_type": model.config["source"],
                "architecture": model.config.get("architecture", "transformer"),
            }

        return results


# Example usage and testing
if __name__ == "__main__":
    # Initialize model manager
    manager = ModelManager()

    # Load and test different model types
    print("Available models:", manager.get_available_models())

    # Load a Hugging Face model
    bert_model = manager.load_model("bert_classifier")
    print(f"Loaded BERT model: {bert_model}")

    # Load a custom model
    # custom_model = manager.load_model("custom_lstm")
    # print(f"Loaded custom model: {custom_model}")

    print("Model manager initialization completed successfully!")
