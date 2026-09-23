"""
ML-Based Compound Prioritization
=================================

Predicts molecular toxicity using Random Forest with Morgan fingerprints,
then ranks compounds by predicted safety score.

Fingerprint options: 'morgan' (ECFP4, 2048-bit default) or 'maccs' (166-bit).
"""

import os
import pickle

import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem import AllChem, MACCSkeys
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    roc_auc_score, confusion_matrix,
)
from sklearn.model_selection import train_test_split


class MolecularFingerprinter:
    """Generate Morgan or MACCS fingerprint vectors from SMILES strings."""

    def __init__(self, fingerprint_type: str = "morgan", radius: int = 2, n_bits: int = 2048):
        if fingerprint_type not in ("morgan", "maccs"):
            raise ValueError(f"Unknown fingerprint type: {fingerprint_type!r}. Use 'morgan' or 'maccs'.")
        self.fingerprint_type = fingerprint_type
        self.radius = radius
        self.n_bits = n_bits

    def smiles_to_fingerprint(self, smiles: str) -> np.ndarray | None:
        """Return a fingerprint array for a SMILES string, or None if invalid."""
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        if self.fingerprint_type == "morgan":
            fp = AllChem.GetMorganFingerprintAsBitVect(mol, self.radius, nBits=self.n_bits)
        else:
            fp = MACCSkeys.GenMACCSKeys(mol)

        return np.array(fp)

    def batch_fingerprints(
        self, smiles_list: list[str]
    ) -> tuple[np.ndarray, list[int]]:
        """
        Generate fingerprints for a list of SMILES.

        Returns:
            fingerprints: 2-D array of shape (n_valid, n_bits).
            valid_indices: original indices of SMILES that produced a valid fingerprint.
        """
        fingerprints, valid_indices = [], []
        for i, smiles in enumerate(smiles_list):
            fp = self.smiles_to_fingerprint(smiles)
            if fp is not None:
                fingerprints.append(fp)
                valid_indices.append(i)

        return np.array(fingerprints), valid_indices


class ToxicityPredictor:
    """Random Forest model for predicting binary molecular toxicity."""

    def __init__(
        self,
        fingerprint_type: str = "morgan",
        radius: int = 2,
        n_bits: int = 2048,
    ):
        self.fingerprinter = MolecularFingerprinter(fingerprint_type, radius, n_bits)
        self.model = RandomForestClassifier(
            n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
        )
        self.is_trained = False

    def train(self, smiles_list: list[str], labels: list[int]) -> dict:
        """
        Train the toxicity model.

        Args:
            smiles_list: SMILES strings for all compounds.
            labels: Binary labels aligned with smiles_list (1 = toxic, 0 = safe).

        Returns:
            Dict of evaluation metrics (accuracy, precision, recall, roc_auc).
        """
        X, valid_indices = self.fingerprinter.batch_fingerprints(smiles_list)
        y = np.array([labels[i] for i in valid_indices])

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        print("Training Random Forest model...")
        self.model.fit(X_train, y_train)
        self.is_trained = True

        y_pred = self.model.predict(X_test)
        y_proba = self.model.predict_proba(X_test)[:, 1]

        metrics = {
            "accuracy":  accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred),
            "recall":    recall_score(y_test, y_pred),
            "roc_auc":   roc_auc_score(y_test, y_proba),
            "confusion_matrix": confusion_matrix(y_test, y_pred),
            "n_train": len(X_train),
            "n_test":  len(X_test),
        }

        print(f"\nTraining set: {metrics['n_train']} compounds")
        print(f"Test set:     {metrics['n_test']} compounds")
        print(f"\nPerformance metrics:")
        print(f"  Accuracy:  {metrics['accuracy']:.3f}")
        print(f"  Precision: {metrics['precision']:.3f}")
        print(f"  Recall:    {metrics['recall']:.3f}")
        print(f"  ROC-AUC:   {metrics['roc_auc']:.3f}")

        return metrics

    def predict(self, smiles_list: list[str]) -> pd.DataFrame:
        """
        Predict toxicity for new compounds.

        Returns:
            DataFrame with SMILES, Predicted_Toxic, Toxicity_Probability, Safety_Score,
            sorted safest-first.
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before making predictions.")

        X, valid_indices = self.fingerprinter.batch_fingerprints(smiles_list)
        valid_smiles = [smiles_list[i] for i in valid_indices]

        predictions = self.model.predict(X)
        probabilities = self.model.predict_proba(X)[:, 1]

        return pd.DataFrame({
            "SMILES": valid_smiles,
            "Predicted_Toxic": predictions.astype(bool),
            "Toxicity_Probability": probabilities,
            "Safety_Score": 1 - probabilities,
        }).sort_values("Safety_Score", ascending=False).reset_index(drop=True)

    def rank_compounds(self, smiles_list: list[str]) -> pd.DataFrame:
        """Predict and rank compounds by safety, printing a summary table."""
        results = self.predict(smiles_list)
        results.insert(0, "Rank", range(1, len(results) + 1))

        print("\nCompound Ranking (safest first):")
        print("=" * 70)
        for _, row in results.iterrows():
            status = "TOXIC" if row["Predicted_Toxic"] else "SAFE "
            print(f"  Rank {row['Rank']:2.0f} | {status} | "
                  f"Safety: {row['Safety_Score']:.3f} | {row['SMILES']}")

        return results

    def save_model(self, filepath: str = "toxicity_model.pkl"):
        """Persist the trained model and fingerprinter to disk."""
        if not self.is_trained:
            raise ValueError("No trained model to save.")
        with open(filepath, "wb") as f:
            pickle.dump({"model": self.model, "fingerprinter": self.fingerprinter}, f)
        print(f"Model saved to: {filepath}")

    @classmethod
    def load_model(cls, filepath: str = "toxicity_model.pkl") -> "ToxicityPredictor":
        """Load a saved model from disk."""
        with open(filepath, "rb") as f:
            data = pickle.load(f)
        predictor = cls()
        predictor.model = data["model"]
        predictor.fingerprinter = data["fingerprinter"]
        predictor.is_trained = True
        print(f"Model loaded from: {filepath}")
        return predictor


def generate_synthetic_training_data() -> tuple[list[str], list[int]]:
    """
    Build a small demonstration training set from known compounds.

    Toxic compounds: known electrophiles, reactive species, problematic structures.
    Safe compounds: approved drugs and natural products.

    For production use, replace with Tox21 or ToxCast datasets.
    """
    toxic = [
        "C1=CC=C(C=C1)N(=O)=O",              # Nitrobenzene
        "C1=CC=C2C(=C1)C(=O)C3=CC=CC=C3C2=O",  # Anthraquinone
        "C1=CC=C(C=C1)Cl",                   # Chlorobenzene
        # Was "CC(=O)NC1=CC=C(C=C1)O", commented "Acetaminophen precursor" — but that
        # SMILES *is* acetaminophen, which also appears in the safe list below. The
        # same molecule was therefore labelled both toxic and safe. Replaced with the
        # actual precursor, 4-aminophenol, which is genuinely nephrotoxic.
        "Nc1ccc(O)cc1",                      # 4-Aminophenol (acetaminophen precursor)
        "C1=CC=C(C=C1)CCCl",                 # 3-chloropropylbenzene
        "O=C1C=CC(=O)C=C1",                  # Benzoquinone
        "C1=CC=C(C=C1)N=NC2=CC=CC=C2",       # Azobenzene
        "CC(C)(C)OOC(C)(C)C",                # Di-tert-butyl peroxide
        "C1CCOC1",                            # THF (high-dose toxicity)
        "BrCCBr",                             # 1,2-dibromoethane
    ]
    safe = [
        "CC(=O)Oc1ccccc1C(=O)O",             # Aspirin
        "CC(C)Cc1ccc(cc1)C(C)C(=O)O",        # Ibuprofen
        "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",      # Caffeine
        "CC(C)NCC(COc1ccccc1)O",              # Propranolol
        "CN(C)CCOC(c1ccccc1)c2ccccc2",        # Diphenhydramine
        "CC(C)(C)NCC(c1ccc(c(c1)CO)O)O",      # Salbutamol
        "CC1(C)SC2C(NC(=O)Cc3ccccc3)C(=O)N2C1C(=O)O",  # Penicillin G
        "COc1ccc2c(c1)c(=O)c(cn2C)C(=O)O",   # Nalidixic acid
        "Cc1ccc(cc1)S(=O)(=O)N",              # Toluenesulfonamide
        "CC(=O)Nc1ccc(O)cc1",                 # Paracetamol
    ]

    smiles = toxic + safe
    labels = [1] * len(toxic) + [0] * len(safe)
    assert_no_label_conflicts(smiles, labels)
    return smiles, labels


def assert_no_label_conflicts(smiles: list[str], labels: list[int]) -> None:
    """Fail loudly if the same molecule carries two different labels.

    Two SMILES strings can spell the same molecule — ``CC(=O)NC1=CC=C(C=C1)O`` and
    ``CC(=O)Nc1ccc(O)cc1`` are both acetaminophen. A contradiction like that is
    invisible by eye and silently poisons training, so it is checked rather than
    trusted. Comparison is on the RDKit canonical SMILES, which is what makes two
    spellings of one structure comparable.
    """
    by_structure: dict[str, set[int]] = {}
    for smi, label in zip(smiles, labels):
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            raise ValueError(f"Unparseable SMILES in training data: {smi!r}")
        by_structure.setdefault(Chem.MolToSmiles(mol), set()).add(label)

    conflicts = {c: sorted(lbls) for c, lbls in by_structure.items() if len(lbls) > 1}
    if conflicts:
        detail = "; ".join(f"{c} labelled {lbls}" for c, lbls in conflicts.items())
        raise ValueError(f"Same molecule given conflicting labels: {detail}")


def demo_toxicity_prediction():
    """Run the complete ML toxicity prediction workflow."""
    print("=" * 70)
    print("ML-BASED COMPOUND PRIORITIZATION — TOXICITY PREDICTION")
    print("=" * 70)

    smiles_list, labels = generate_synthetic_training_data()
    print(f"\n[1] Training data: {len(smiles_list)} compounds "
          f"({sum(labels)} toxic, {len(labels) - sum(labels)} safe)")

    predictor = ToxicityPredictor(fingerprint_type="morgan", radius=2, n_bits=2048)
    metrics = predictor.train(smiles_list, labels)

    test_compounds = [
        "CC(C)Cc1ccc(cc1)C(C)C(=O)O",    # Ibuprofen — safe
        "C1=CC=C(C=C1)N(=O)=O",           # Nitrobenzene — toxic
        "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",  # Caffeine — safe
        "O=C1C=CC(=O)C=C1",               # Benzoquinone — toxic
        "CC(=O)Oc1ccccc1C(=O)O",          # Aspirin — safe
    ]
    print("\n[2] Ranking test compounds by safety:")
    results = predictor.rank_compounds(test_compounds)

    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(output_dir, exist_ok=True)
    model_path = os.path.join(output_dir, "toxicity_model.pkl")
    predictor.save_model(model_path)

    return predictor, results


def main():
    predictor, results = demo_toxicity_prediction()
    print(f"\nSummary: {len(results)} ranked | "
          f"{(~results['Predicted_Toxic']).sum()} safe | "
          f"{results['Predicted_Toxic'].sum()} toxic | "
          f"avg safety {results['Safety_Score'].mean():.3f}")


if __name__ == "__main__":
    main()
