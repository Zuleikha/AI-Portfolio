"""
Data drift detection for MLOps pipeline
Monitors for changes in data distribution that might affect model performance
"""

import json
import logging
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from scipy import stats
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DriftDetector:
    """Comprehensive drift detection system"""

    def __init__(self, config_path: str = "config/config.yaml"):
        try:
            with open(config_path) as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}. Using default settings.")
            self.config = self._default_config()

        # Data storage for drift detection
        self.reference_data = None
        self.current_data = deque(maxlen=1000)  # Store recent data
        self.vectorizer = TfidfVectorizer(max_features=1000, stop_words="english")
        self.pca = PCA(n_components=50)

        # Drift detection thresholds
        self.drift_threshold = self.config.get("monitoring", {}).get("drift_threshold", 0.05)
        self.min_samples = self.config.get("monitoring", {}).get("min_samples", 100)

        # Drift history
        self.drift_history = []

        logger.info("Drift detector initialized")

    def _default_config(self):
        """Default configuration when config file is not available"""
        return {"monitoring": {"drift_threshold": 0.05, "min_samples": 100}}

    def set_reference_data(self, texts: list[str], labels: list[int] | None = None):
        """Set reference data for drift detection"""

        logger.info(f"Setting reference data with {len(texts)} samples")

        # Vectorize text data
        text_vectors = self.vectorizer.fit_transform(texts)

        # Apply PCA for dimensionality reduction
        text_features = self.pca.fit_transform(text_vectors.toarray())

        self.reference_data = {
            "features": text_features,
            "labels": labels,
            "statistics": {
                "mean": np.mean(text_features, axis=0),
                "std": np.std(text_features, axis=0),
                "size": len(texts),
            },
        }

        logger.info("Reference data set successfully")

    def add_current_data(self, text: str, prediction: int | None = None):
        """Add new data point to current data stream"""

        try:
            # Vectorize the text
            text_vector = self.vectorizer.transform([text])
            text_features = self.pca.transform(text_vector.toarray())[0]

            data_point = {
                "features": text_features,
                "prediction": prediction,
                "timestamp": datetime.now(),
            }

            self.current_data.append(data_point)

        except Exception as e:
            logger.error(f"Failed to add data point: {e}")

    def check_text_drift(self, text: str) -> bool:
        """Check if a single text sample shows drift"""

        if self.reference_data is None:
            logger.warning("No reference data set for drift detection")
            return False

        try:
            # Add to current data
            self.add_current_data(text)

            # Check if we have enough samples for drift detection
            if len(self.current_data) < self.min_samples:
                return False

            # Extract recent features
            recent_features = np.array(
                [point["features"] for point in list(self.current_data)[-self.min_samples :]]
            )

            # Perform drift detection
            drift_detected = self._detect_feature_drift(recent_features)

            if drift_detected:
                self._log_drift_detection(
                    "text_drift", {"sample_text": text[:100]}
                )  # Log first 100 chars

            return drift_detected

        except Exception as e:
            logger.error(f"Drift detection failed: {e}")
            return False

    def _detect_feature_drift(self, current_features: np.ndarray) -> bool:
        """Detect drift using statistical tests"""

        reference_features = self.reference_data["features"]

        # Kolmogorov-Smirnov test for each feature
        drift_scores = []

        for i in range(min(reference_features.shape[1], current_features.shape[1])):
            ref_feature = reference_features[:, i]
            curr_feature = current_features[:, i]

            # KS test
            ks_statistic, p_value = stats.ks_2samp(ref_feature, curr_feature)

            drift_scores.append(
                {
                    "feature_idx": i,
                    "ks_statistic": ks_statistic,
                    "p_value": p_value,
                    "drift_detected": p_value < self.drift_threshold,
                }
            )

        # Check if any feature shows significant drift
        num_drifted_features = sum(1 for score in drift_scores if score["drift_detected"])
        drift_ratio = num_drifted_features / len(drift_scores)

        # Consider drift detected if more than 10% of features show drift
        overall_drift = drift_ratio > 0.1

        if overall_drift:
            logger.warning(
                f"Drift detected: {num_drifted_features}/{len(drift_scores)} features show drift"
            )

        return overall_drift

    def check_prediction_drift(self) -> dict[str, Any]:
        """Check for drift in prediction distribution"""

        if len(self.current_data) < self.min_samples:
            return {"drift_detected": False, "reason": "Insufficient data"}

        # Extract recent predictions
        recent_predictions = [
            point["prediction"] for point in self.current_data if point["prediction"] is not None
        ]

        if len(recent_predictions) < self.min_samples:
            return {"drift_detected": False, "reason": "Insufficient prediction data"}

        # Get reference predictions if available
        if self.reference_data is None or self.reference_data["labels"] is None:
            return {"drift_detected": False, "reason": "No reference predictions"}

        reference_predictions = self.reference_data["labels"]

        # Calculate prediction distributions
        ref_unique, ref_counts = np.unique(reference_predictions, return_counts=True)
        curr_unique, curr_counts = np.unique(recent_predictions, return_counts=True)

        # Align distributions
        all_classes = sorted(set(ref_unique) | set(curr_unique))
        ref_dist = np.array(
            [
                ref_counts[list(ref_unique).index(cls)] if cls in ref_unique else 0
                for cls in all_classes
            ]
        )
        curr_dist = np.array(
            [
                curr_counts[list(curr_unique).index(cls)] if cls in curr_unique else 0
                for cls in all_classes
            ]
        )

        # Normalize to probabilities
        ref_dist = ref_dist / ref_dist.sum()
        curr_dist = curr_dist / curr_dist.sum()

        # Chi-square test
        chi2_stat, p_value = stats.chisquare(
            curr_dist * len(recent_predictions), ref_dist * len(recent_predictions)
        )

        drift_detected = p_value < self.drift_threshold

        result = {
            "drift_detected": drift_detected,
            "p_value": float(p_value),
            "chi2_statistic": float(chi2_stat),
            "reference_distribution": ref_dist.tolist(),
            "current_distribution": curr_dist.tolist(),
            "classes": all_classes,
        }

        if drift_detected:
            self._log_drift_detection("prediction_drift", result)

        return result

    def check_performance_drift(self, accuracy_threshold: float = 0.05) -> dict[str, Any]:
        """Check for performance degradation"""

        # This is a simplified implementation
        # In practice, you'd track accuracy over time and compare with historical performance

        result = {
            "drift_detected": False,
            "reason": "Performance drift detection not fully implemented",
            "accuracy_threshold": accuracy_threshold,
        }

        return result

    def _log_drift_detection(self, drift_type: str, details: dict[str, Any]):
        """Log drift detection event"""

        drift_event = {
            "timestamp": datetime.now().isoformat(),
            "drift_type": drift_type,
            "details": details,
            "threshold": self.drift_threshold,
        }

        self.drift_history.append(drift_event)

        # Save to file
        self._save_drift_history()

        logger.warning(f"Drift detected: {drift_type}")

    def _save_drift_history(self):
        """Save drift history to file"""

        try:
            drift_dir = Path("monitoring_results")
            drift_dir.mkdir(exist_ok=True)

            drift_file = drift_dir / "drift_history.json"
            with open(drift_file, "w") as f:
                json.dump(self.drift_history, f, indent=2, default=str)

        except Exception as e:
            logger.error(f"Failed to save drift history: {e}")

    def get_drift_report(self) -> dict[str, Any]:
        """Generate comprehensive drift report"""

        report = {
            "report_timestamp": datetime.now().isoformat(),
            "reference_data_size": self.reference_data["statistics"]["size"]
            if self.reference_data
            else 0,
            "current_data_size": len(self.current_data),
            "drift_threshold": self.drift_threshold,
            "total_drift_events": len(self.drift_history),
            "recent_drift_events": [
                event
                for event in self.drift_history
                if datetime.fromisoformat(event["timestamp"]) > datetime.now() - timedelta(days=7)
            ],
            "drift_history": self.drift_history[-10:],  # Last 10 events
        }

        # Add current drift status
        if len(self.current_data) >= self.min_samples:
            report["current_prediction_drift"] = self.check_prediction_drift()
            report["current_performance_drift"] = self.check_performance_drift()

        return report

    def reset_current_data(self):
        """Reset current data buffer"""
        self.current_data.clear()
        logger.info("Current data buffer reset")

    def update_thresholds(
        self, drift_threshold: float | None = None, min_samples: int | None = None
    ):
        """Update drift detection thresholds"""

        if drift_threshold is not None:
            self.drift_threshold = drift_threshold
            logger.info(f"Drift threshold updated to {drift_threshold}")

        if min_samples is not None:
            self.min_samples = min_samples
            self.current_data = deque(self.current_data, maxlen=max(1000, min_samples * 2))
            logger.info(f"Minimum samples updated to {min_samples}")


# Example usage
if __name__ == "__main__":
    # Initialize drift detector
    detector = DriftDetector()

    # Simulate reference data
    reference_texts = [
        "This is a positive example",
        "This is a negative example",
        "Another positive case",
        "Another negative case",
    ] * 25  # Create 100 samples

    reference_labels = [0, 1, 0, 1] * 25

    # Set reference data
    detector.set_reference_data(reference_texts, reference_labels)

    # Simulate new data with drift
    new_texts = [
        "Completely different text pattern",
        "Very unusual content here",
        "Strange new vocabulary",
    ]

    for text in new_texts:
        drift_detected = detector.check_text_drift(text)
        print(f"Text: '{text[:50]}...' - Drift detected: {drift_detected}")

    # Generate drift report
    report = detector.get_drift_report()
    print(f"\nDrift Report: {json.dumps(report, indent=2, default=str)}")
