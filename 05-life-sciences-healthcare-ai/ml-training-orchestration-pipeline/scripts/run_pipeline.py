"""
MLOps Pipeline Launcher
Runs the complete ML pipeline: data prep → training → evaluation → serving.
"""

import argparse
import logging
import pickle
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class MLOpsPipelineLauncher:
    """Orchestrates the MLOps pipeline stages."""

    def __init__(self):
        self.project_root = Path(__file__).parent
        self.processes: list = []

    def check_dependencies(self) -> bool:
        """Verify essential packages are available."""
        logger.info("Checking dependencies...")
        missing = []
        for package in ["pandas", "sklearn"]:
            try:
                __import__(package)
            except ImportError:
                missing.append(package)

        if missing:
            logger.error(f"Missing packages: {missing}")
            return False

        logger.info("Dependencies OK")
        return True

    def setup_environment(self):
        """Create required directories and copy .env template if needed."""
        logger.info("Setting up environment...")
        for directory in [
            "data/raw",
            "data/processed",
            "models",
            "logs",
            "mlruns",
            "evaluation_results",
            "monitoring_results",
        ]:
            (self.project_root / directory).mkdir(parents=True, exist_ok=True)

        env_file = self.project_root / ".env"
        template = self.project_root / ".env.example"
        if not env_file.exists() and template.exists():
            import shutil

            shutil.copy(template, env_file)
            logger.info("Created .env from template — configure API keys before running.")

        logger.info("Environment ready")

    def create_sample_data(self) -> str:
        """Generate a labelled sentiment dataset for pipeline smoke-testing."""
        import pandas as pd

        logger.info("Generating sample data...")
        positive = [
            "This is a great product, I love it!",
            "Amazing service and fast delivery",
            "Excellent value for money",
            "Outstanding quality and design",
            "Perfect for my needs, highly recommended",
        ]
        negative = [
            "Terrible quality, would not recommend",
            "Poor customer support experience",
            "Waste of money, very disappointed",
            "Not worth the price, overrated",
            "Broke after one day of use",
        ]
        texts = (positive + negative) * 10
        labels = (["positive"] * 5 + ["negative"] * 5) * 10

        data_path = self.project_root / "data" / "sample_data.csv"
        pd.DataFrame({"text": texts, "label": labels}).to_csv(data_path, index=False)
        logger.info(f"Sample data saved to {data_path} ({len(texts)} rows)")
        return str(data_path)

    def run_training(self, data_path: str) -> bool:
        """Train a TF-IDF + Logistic Regression classifier and persist the artefacts."""
        logger.info("Starting model training...")
        try:
            import pandas as pd
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.model_selection import train_test_split

            data = pd.read_csv(data_path)
            logger.info(f"Loaded {len(data)} training samples")

            vectorizer = TfidfVectorizer(max_features=1000, stop_words="english")
            X = vectorizer.fit_transform(data["text"])
            y = (data["label"] == "positive").astype(int)

            X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

            model = LogisticRegression(max_iter=1000)
            model.fit(X_train, y_train)

            val_accuracy = model.score(X_val, y_val) * 100
            logger.info(f"Validation accuracy: {val_accuracy:.1f}%")

            models_dir = self.project_root / "models"
            with open(models_dir / "model.pkl", "wb") as f:
                pickle.dump(model, f)
            with open(models_dir / "vectorizer.pkl", "wb") as f:
                pickle.dump(vectorizer, f)

            logger.info("Model artefacts saved to models/")
            return True

        except Exception as e:
            logger.error(f"Training failed: {e}")
            return False

    def run_evaluation(self, data_path: str) -> bool:
        """Evaluate the saved model and log standard classification metrics."""
        logger.info("Starting model evaluation...")
        try:
            import pandas as pd
            from sklearn.metrics import (
                accuracy_score,
                f1_score,
                precision_score,
                recall_score,
            )

            models_dir = self.project_root / "models"
            model_path = models_dir / "model.pkl"
            vectorizer_path = models_dir / "vectorizer.pkl"

            if not model_path.exists():
                logger.error("No trained model found — run training first.")
                return False

            with open(model_path, "rb") as f:
                model = pickle.load(f)
            with open(vectorizer_path, "rb") as f:
                vectorizer = pickle.load(f)

            data = pd.read_csv(data_path)
            X = vectorizer.transform(data["text"])
            y_true = (data["label"] == "positive").astype(int)
            y_pred = model.predict(X)

            logger.info("Evaluation results:")
            logger.info(f"  Accuracy:  {accuracy_score(y_true, y_pred) * 100:.1f}%")
            logger.info(f"  Precision: {precision_score(y_true, y_pred) * 100:.1f}%")
            logger.info(f"  Recall:    {recall_score(y_true, y_pred) * 100:.1f}%")
            logger.info(f"  F1 Score:  {f1_score(y_true, y_pred) * 100:.1f}%")
            return True

        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return False

    def start_api_server(self) -> bool:
        """Launch the FastAPI prediction server as a background process."""
        logger.info("Starting API server...")
        try:
            import fastapi  # noqa: F401

            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "src.api:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8000",
                ],
                cwd=self.project_root,
            )
            self.processes.append(process)
            logger.info("API server started — http://localhost:8000/docs")
            return True
        except ImportError:
            logger.warning("FastAPI not installed — skipping API server")
            return False
        except Exception as e:
            logger.error(f"Failed to start API server: {e}")
            return False

    def start_mlflow_ui(self) -> bool:
        """Launch the MLflow experiment-tracking UI as a background process."""
        logger.info("Starting MLflow UI...")
        try:
            import mlflow  # noqa: F401

            process = subprocess.Popen(
                [sys.executable, "-m", "mlflow", "ui", "--host", "0.0.0.0", "--port", "5000"],
                cwd=self.project_root,
            )
            self.processes.append(process)
            logger.info("MLflow UI available — http://localhost:5000")
            return True
        except ImportError:
            logger.warning("MLflow not installed — skipping UI")
            return False
        except Exception as e:
            logger.error(f"Failed to start MLflow: {e}")
            return False

    def run_tests(self) -> bool:
        """Execute the test suite via pytest."""
        logger.info("Running test suite...")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            cwd=self.project_root,
        )
        if result.returncode == 0:
            logger.info("All tests passed")
        else:
            logger.warning("Some tests failed:\n%s", result.stdout[-2000:])
        return result.returncode == 0

    def cleanup(self):
        """Terminate any background processes launched during the pipeline."""
        logger.info("Cleaning up...")
        for process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            except Exception:
                pass

    def run_full_pipeline(self) -> bool:
        """Execute the full pipeline end-to-end."""
        logger.info("Starting MLOps pipeline...")
        try:
            if not self.check_dependencies():
                return False

            self.setup_environment()
            data_path = self.create_sample_data()

            if not self.run_training(data_path):
                logger.error("Pipeline failed at training stage")
                return False

            if not self.run_evaluation(data_path):
                logger.error("Pipeline failed at evaluation stage")
                return False

            self.start_mlflow_ui()
            self.start_api_server()

            logger.info("=" * 60)
            logger.info("MLOps pipeline complete")
            logger.info("  Data:       processed")
            logger.info("  Training:   complete")
            logger.info("  Evaluation: complete")
            logger.info("  Services:   started")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            return False
        finally:
            self.cleanup()


def main():
    parser = argparse.ArgumentParser(description="MLOps Pipeline Launcher")
    parser.add_argument(
        "--mode",
        choices=["full", "train", "eval", "api", "test"],
        default="full",
        help="Pipeline stage to run",
    )
    parser.add_argument("--data", help="Path to data CSV (optional)")
    args = parser.parse_args()

    launcher = MLOpsPipelineLauncher()

    try:
        if args.mode == "full":
            success = launcher.run_full_pipeline()
        elif args.mode == "train":
            launcher.setup_environment()
            data_path = args.data or launcher.create_sample_data()
            success = launcher.run_training(data_path)
        elif args.mode == "eval":
            data_path = args.data or launcher.create_sample_data()
            success = launcher.run_evaluation(data_path)
        elif args.mode == "api":
            launcher.setup_environment()
            success = launcher.start_api_server()
        elif args.mode == "test":
            success = launcher.run_tests()

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        launcher.cleanup()


if __name__ == "__main__":
    main()
