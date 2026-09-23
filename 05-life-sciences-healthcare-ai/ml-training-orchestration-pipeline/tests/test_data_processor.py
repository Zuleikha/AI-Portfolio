"""
Unit tests for data processing functionality
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest
import yaml

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from data.data_processor import DataManager, TextDataProcessor


class TestTextDataProcessor:
    @pytest.fixture
    def sample_data(self):
        """Create sample data for testing"""
        return pd.DataFrame(
            {
                "text": [
                    "This is a positive example",
                    "This is a negative example",
                    "Another positive case",
                    "Another negative case",
                    "More positive text",
                    "More negative text",
                ],
                "label": ["positive", "negative", "positive", "negative", "positive", "negative"],
            }
        )

    @pytest.fixture
    def temp_data_file(self, sample_data):
        """Create temporary data file"""
        # delete=False (not a context manager) so the handle is released before
        # pandas writes to the path - Windows will not allow both at once.
        temp_file = tempfile.NamedTemporaryFile(  # noqa: SIM115
            mode="w", suffix=".csv", delete=False
        )
        temp_file.close()  # release the handle so Windows can unlink it on teardown
        sample_data.to_csv(temp_file.name, index=False)
        yield temp_file.name
        os.unlink(temp_file.name)

    def test_load_data(self, temp_data_file):
        """Test data loading functionality"""
        processor = TextDataProcessor({})

        success = processor.load_data(temp_data_file)
        assert success is True
        assert processor.data is not None
        assert len(processor.data) == 6
        assert "text" in processor.data.columns
        assert "label" in processor.data.columns

    def test_validate_data(self, temp_data_file):
        """Test data validation"""
        processor = TextDataProcessor({})
        processor.load_data(temp_data_file)

        validation_results = processor.validate_data()
        assert validation_results["has_text_column"] is True
        assert validation_results["has_label_column"] is True
        assert validation_results["no_null_text"] is True
        assert validation_results["no_null_labels"] is True

    def test_preprocess_for_transformers(self, temp_data_file):
        """Test preprocessing for Hugging Face models"""
        processor = TextDataProcessor({})
        processor.load_data(temp_data_file)
        processor.preprocess("huggingface")

        assert processor.processed_data is not None
        # Check if it's a Hugging Face dataset
        assert hasattr(processor.processed_data, "column_names")

    def test_preprocess_for_custom(self, temp_data_file):
        """Test preprocessing for custom models"""
        processor = TextDataProcessor({})
        processor.load_data(temp_data_file)
        processor.preprocess("custom")

        assert processor.processed_data is not None
        assert "sequences" in processor.processed_data
        assert "labels" in processor.processed_data
        assert "vocab" in processor.processed_data


class TestDataManager:
    @pytest.fixture
    def temp_config(self):
        """Create temporary configuration"""
        temp_dir = tempfile.mkdtemp()
        config_path = Path(temp_dir) / "test_config.yaml"

        test_config = {
            "data": {
                "raw_path": "data/raw",
                "processed_path": "data/processed",
                "test_size": 0.2,
                "random_state": 42,
            }
        }

        with open(config_path, "w") as f:
            yaml.dump(test_config, f)

        yield str(config_path)
        shutil.rmtree(temp_dir)

    def test_data_manager_init(self, temp_config):
        """Test data manager initialization"""
        manager = DataManager(temp_config)
        assert manager.config is not None
        assert manager.processor is None
