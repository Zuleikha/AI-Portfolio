"""
Unit tests for model manager functionality
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from models.model_manager import CustomModel, HuggingFaceModel, ModelManager


class TestModelManager:
    @pytest.fixture
    def temp_config(self):
        """Create temporary configuration for testing"""
        temp_dir = tempfile.mkdtemp()
        config_path = Path(temp_dir) / "test_config.yaml"

        test_config = {
            "models": {
                "available": {
                    "test_bert": {
                        "source": "huggingface",
                        "model_name": "distilbert-base-uncased",
                        "task": "classification",
                        "fine_tunable": True,
                    },
                    "test_custom": {
                        "source": "local",
                        "model_path": "models/test_model.pt",
                        "task": "classification",
                        "architecture": "lstm",
                    },
                },
                "default": "test_bert",
            }
        }

        with open(config_path, "w") as f:
            yaml.dump(test_config, f)

        yield str(config_path)

        # Cleanup
        shutil.rmtree(temp_dir)

    def test_model_manager_init(self, temp_config):
        """Test model manager initialization"""
        manager = ModelManager(temp_config)
        assert manager.config is not None
        assert len(manager.config["models"]["available"]) == 2

    def test_get_available_models(self, temp_config):
        """Test getting available models"""
        manager = ModelManager(temp_config)
        models = manager.get_available_models()
        assert "test_bert" in models
        assert "test_custom" in models

    def test_load_huggingface_model(self, temp_config):
        """Test loading Hugging Face model"""
        manager = ModelManager(temp_config)

        # This test requires internet connection and may take time
        # Skip in CI/CD if needed
        try:
            model = manager.load_model("test_bert")
            assert model is not None
            assert isinstance(model, HuggingFaceModel)
            assert model.model_name == "distilbert-base-uncased"
        except Exception as e:
            pytest.skip(f"Skipping HF model test: {e}")

    def test_load_custom_model(self, temp_config):
        """Test loading custom model"""
        manager = ModelManager(temp_config)

        # Custom models will create new instances if file doesn't exist
        model = manager.load_model("test_custom")
        assert model is not None
        assert isinstance(model, CustomModel)
        assert model.architecture == "lstm"


class TestHuggingFaceModel:
    def test_hf_model_init(self):
        """Test Hugging Face model initialization"""
        config = {
            "model_name": "distilbert-base-uncased",
            "task": "classification",
            "num_labels": 2,
        }

        model = HuggingFaceModel(config)
        assert model.model_name == "distilbert-base-uncased"
        assert model.task == "classification"


class TestCustomModel:
    def test_custom_model_init(self):
        """Test custom model initialization"""
        config = {"model_path": "models/test.pt", "architecture": "lstm", "task": "classification"}

        model = CustomModel(config)
        assert model.architecture == "lstm"
        assert model.model_path == "models/test.pt"

    def test_create_lstm_model(self):
        """Test LSTM model creation"""
        config = {"architecture": "lstm", "task": "classification"}

        model = CustomModel(config)
        model.load_model()  # This will create a new LSTM model

        assert model.model is not None
