"""
Data processing pipeline for MLOps system
Handles data ingestion, validation, and preprocessing for multiple model types
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd
import torch
import yaml
from datasets import Dataset as HFDataset
from datasets import DatasetDict
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from torch.utils.data import DataLoader, Dataset

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BaseDataProcessor(ABC):
    """Abstract base class for data processors"""

    def __init__(self, config: dict):
        self.config = config
        self.data = None
        self.processed_data = None

    @abstractmethod
    def load_data(self, data_path: str):
        """Load raw data"""
        pass

    @abstractmethod
    def validate_data(self):
        """Validate data quality"""
        pass

    @abstractmethod
    def preprocess(self):
        """Preprocess data for model training"""
        pass

    @abstractmethod
    def split_data(self) -> tuple:
        """Split data into train/validation/test sets"""
        pass


class TextDataProcessor(BaseDataProcessor):
    """Data processor for text classification tasks"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.tokenizer = None
        self.label_encoder = LabelEncoder()

    def load_data(self, data_path: str):
        """Load text data from various formats"""
        data_path = Path(data_path)

        try:
            if data_path.suffix == ".csv":
                self.data = pd.read_csv(data_path)
            elif data_path.suffix == ".json":
                self.data = pd.read_json(data_path)
            elif data_path.suffix == ".parquet":
                self.data = pd.read_parquet(data_path)
            else:
                raise ValueError(f"Unsupported file format: {data_path.suffix}")

            logger.info(f"Loaded data with shape: {self.data.shape}")
            return True

        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            return False

    def validate_data(self) -> dict[str, bool]:
        """Validate data using pandas assertions."""
        if self.data is None:
            raise ValueError("No data loaded for validation")

        results: dict[str, bool] = {}

        results["has_text_column"] = "text" in self.data.columns
        results["has_label_column"] = "label" in self.data.columns
        results["no_null_text"] = (
            bool(self.data["text"].notna().all()) if results["has_text_column"] else False
        )
        results["no_null_labels"] = (
            bool(self.data["label"].notna().all()) if results["has_label_column"] else False
        )

        if results["has_text_column"]:
            lengths = self.data["text"].astype(str).str.len()
            results["min_text_length"] = bool((lengths >= 1).all() and (lengths <= 10000).all())

        if results["has_label_column"]:
            unique_labels = self.data["label"].nunique()
            results["valid_label_count"] = 1 < unique_labels <= 100

        logger.info(f"Data validation completed: {results}")
        return results

    def preprocess(self, model_type: str = "huggingface"):
        """Preprocess text data based on model type"""
        if self.data is None:
            raise ValueError("No data loaded for preprocessing")

        logger.info(f"Preprocessing data for model type: {model_type}")

        # Basic text cleaning
        self.data["text"] = self.data["text"].astype(str)
        self.data["text"] = self.data["text"].str.strip()

        # Encode labels
        self.data["label_encoded"] = self.label_encoder.fit_transform(self.data["label"])

        if model_type == "huggingface":
            self.processed_data = self._preprocess_for_transformers()
        elif model_type == "custom":
            self.processed_data = self._preprocess_for_custom_models()
        else:
            raise ValueError(f"Unknown model type: {model_type}")

        logger.info("Data preprocessing completed")

    def _preprocess_for_transformers(self) -> DatasetDict:
        """Preprocess data for Hugging Face transformers"""
        # Convert to Hugging Face dataset format
        dataset = HFDataset.from_pandas(
            self.data[["text", "label_encoded"]].rename(columns={"label_encoded": "labels"})
        )

        return dataset

    def _preprocess_for_custom_models(self) -> dict:
        """Preprocess data for custom PyTorch models"""
        # Create vocabulary for custom models
        vocab = self._build_vocabulary()

        # Convert text to sequences of token IDs
        sequences = [self._text_to_sequence(text, vocab) for text in self.data["text"]]

        return {
            "sequences": sequences,
            "labels": self.data["label_encoded"].tolist(),
            "vocab": vocab,
            "max_length": max(len(seq) for seq in sequences),
        }

    def _build_vocabulary(self, min_freq: int = 2) -> dict[str, int]:
        """Build vocabulary for custom models"""
        word_freq = {}

        for text in self.data["text"]:
            words = text.lower().split()
            for word in words:
                word_freq[word] = word_freq.get(word, 0) + 1

        # Create vocabulary with frequent words
        vocab = {"<PAD>": 0, "<UNK>": 1}
        idx = 2

        for word, freq in word_freq.items():
            if freq >= min_freq:
                vocab[word] = idx
                idx += 1

        logger.info(f"Built vocabulary with {len(vocab)} tokens")
        return vocab

    def _text_to_sequence(self, text: str, vocab: dict[str, int]) -> list[int]:
        """Convert text to sequence of token IDs"""
        words = text.lower().split()
        return [vocab.get(word, vocab["<UNK>"]) for word in words]

    def split_data(self, test_size: float = 0.2, val_size: float = 0.1) -> tuple:
        """Split data into train/validation/test sets"""
        if self.processed_data is None:
            raise ValueError("No processed data available for splitting")

        # Split based on data type
        if isinstance(self.processed_data, HFDataset):
            return self._split_hf_dataset(test_size, val_size)
        elif isinstance(self.processed_data, dict):
            return self._split_custom_dataset(test_size, val_size)
        else:
            raise ValueError("Unknown processed data format")

    def _split_hf_dataset(self, test_size: float, val_size: float) -> DatasetDict:
        """Split Hugging Face dataset"""
        # First split: separate test set
        train_val = self.processed_data.train_test_split(test_size=test_size, seed=42)

        # Second split: separate validation from training
        train_split = train_val["train"].train_test_split(
            test_size=val_size / (1 - test_size), seed=42
        )

        return DatasetDict(
            {
                "train": train_split["train"],
                "validation": train_split["test"],
                "test": train_val["test"],
            }
        )

    def _split_custom_dataset(self, test_size: float, val_size: float) -> tuple:
        """Split custom dataset"""
        sequences = self.processed_data["sequences"]
        labels = self.processed_data["labels"]

        # First split: separate test set
        X_train_val, X_test, y_train_val, y_test = train_test_split(
            sequences, labels, test_size=test_size, random_state=42, stratify=labels
        )

        # Second split: separate validation from training
        X_train, X_val, y_train, y_val = train_test_split(
            X_train_val,
            y_train_val,
            test_size=val_size / (1 - test_size),
            random_state=42,
            stratify=y_train_val,
        )

        return {
            "train": {"sequences": X_train, "labels": y_train},
            "validation": {"sequences": X_val, "labels": y_val},
            "test": {"sequences": X_test, "labels": y_test},
            "vocab": self.processed_data["vocab"],
            "max_length": self.processed_data["max_length"],
        }


class CustomTextDataset(Dataset):
    """PyTorch Dataset for custom models"""

    def __init__(self, sequences: list[list[int]], labels: list[int], max_length: int = 512):
        self.sequences = sequences
        self.labels = labels
        self.max_length = max_length

    def __len__(self):
        return len(self.sequences)

    def __getitem__(self, idx):
        sequence = self.sequences[idx]
        label = self.labels[idx]

        # Pad or truncate sequence
        if len(sequence) < self.max_length:
            sequence = sequence + [0] * (self.max_length - len(sequence))
        else:
            sequence = sequence[: self.max_length]

        return {
            "input_ids": torch.tensor(sequence, dtype=torch.long),
            "labels": torch.tensor(label, dtype=torch.long),
        }


class DataManager:
    """Central manager for data processing pipeline"""

    def __init__(self, config_path: str = "config/config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.processor = None
        self.splits = None

    def process_data(self, data_path: str, model_type: str = "huggingface"):
        """End-to-end data processing pipeline"""
        logger.info("Starting data processing pipeline")

        # Initialize appropriate processor
        self.processor = TextDataProcessor(self.config["data"])

        # Load and validate data
        if not self.processor.load_data(data_path):
            raise RuntimeError("Failed to load data")

        validation_results = self.processor.validate_data()
        if not all(validation_results.values()):
            logger.warning(f"Data validation issues: {validation_results}")

        # Preprocess data
        self.processor.preprocess(model_type)

        # Split data
        self.splits = self.processor.split_data()

        logger.info("Data processing pipeline completed successfully")
        return self.splits

    def get_data_loaders(self, batch_size: int = 32) -> dict[str, DataLoader]:
        """Create PyTorch DataLoaders for custom models"""
        if self.splits is None:
            raise ValueError("No data splits available")

        if isinstance(self.splits, dict) and "vocab" in self.splits:
            # Custom model format
            dataloaders = {}
            for split in ["train", "validation", "test"]:
                dataset = CustomTextDataset(
                    self.splits[split]["sequences"],
                    self.splits[split]["labels"],
                    self.splits["max_length"],
                )
                dataloaders[split] = DataLoader(
                    dataset, batch_size=batch_size, shuffle=(split == "train")
                )
            return dataloaders
        else:
            raise ValueError("Data splits not in custom model format")

    def get_hf_datasets(self) -> DatasetDict:
        """Get Hugging Face dataset splits"""
        if isinstance(self.splits, DatasetDict):
            return self.splits
        else:
            raise ValueError("Data splits not in Hugging Face format")


# Example usage and testing
if __name__ == "__main__":
    # Initialize data manager
    data_manager = DataManager()

    # Create sample data for testing
    sample_data = pd.DataFrame(
        {
            "text": [
                "This is a positive example",
                "This is a negative example",
                "Another positive case",
                "Another negative case",
            ],
            "label": ["positive", "negative", "positive", "negative"],
        }
    )

    # Save sample data
    sample_data.to_csv("data/sample_data.csv", index=False)

    # Test data processing
    try:
        splits = data_manager.process_data("data/sample_data.csv", model_type="huggingface")
        print("Data processing successful!")
        print(f"Data splits: {type(splits)}")

    except Exception as e:
        print(f"Data processing failed: {e}")
