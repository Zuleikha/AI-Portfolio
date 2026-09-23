"""
DHFR Bioactivity Prediction Pipeline
======================================

Predicts whether compounds are active against Dihydrofolate Reductase (DHFR).
Uses real RDKit molecular descriptors + Morgan fingerprints with a
Random Forest classifier.

Data note: the dataset here is synthetic — a pool of validated drug-like
SMILES sampled with activity labels to simulate a ChEMBL-style dataset.
Swap `BioactivityDataset.generate_sample_data()` for a real ChEMBL pull
(using chembl_webresource_client) to run against production data.
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple

from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, Crippen, Lipinski, rdMolDescriptors


# ---------------------------------------------------------------------------
# Real SMILES pool — validated drug-like structures used for the synthetic
# dataset.  Actives are known DHFR inhibitors; inactives are common drugs
# with unrelated targets.
# ---------------------------------------------------------------------------

_ACTIVE_SMILES = [
    "COc1cc(Cc2cnc(N)nc2N)cc(OC)c1OC",          # Trimethoprim
    "Cc1nc(N)nc(N)c1Cc1ccc(Cl)cc1",              # Pyrimethamine
    "Nc1nc(N)c(Cc2ccc(F)cc2)cn1",                # 4-F-phenyl aminopyrimidine
    "Nc1nc(N)c(Cc2cccc(OC)c2)cn1",               # 3-OMe phenyl variant
    "COc1cc(Cc2cnc(N)nc2N)ccc1OC",               # 3,4-dimethoxy variant
    "Nc1nc2ccccc2c(N)n1",                         # 2,4-diaminoquinazoline core
    "Nc1nc(Cl)nc(N)c1Cc1ccccc1",                  # 5-Cl variant
    "Nc1nc(N)c(Cc2ccc(C)cc2)cn1",                # 4-Me phenyl variant
    "Nc1nc(N)c(Cc2cc(F)ccc2OC)cn1",              # 2-OMe-5-F phenyl variant
    "COc1ccc(Cc2cnc(N)nc2N)cc1",                  # 4-OMe phenyl aminopyrimidine
]

_INACTIVE_SMILES = [
    "CC(=O)Oc1ccccc1C(=O)O",                     # Aspirin
    "CC(C)Cc1ccc(cc1)C(C)C(=O)O",                # Ibuprofen
    "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",             # Caffeine
    "CC(=O)Nc1ccc(O)cc1",                         # Paracetamol
    "CC1(C)SC2C(NC(=O)Cc3ccccc3)C(=O)N2C1C(=O)O",  # Penicillin G
    "c1ccc(cc1)O",                                # Phenol
    "CC(=O)O",                                    # Acetic acid
    "C1CCNCC1",                                   # Piperidine
    "c1ccncc1",                                   # Pyridine
    "C1CCCCC1",                                   # Cyclohexane
]


class MolecularDescriptors:
    """
    Generate physicochemical descriptors and Morgan fingerprints using RDKit.

    Descriptor vector (9 features):
        MolWt, LogP, TPSA, HBA, HBD, RotBonds, AromaticRings, FracCSP3, Heteroatoms

    Fingerprint:
        Morgan / ECFP4 (radius 2), configurable bit length.
    """

    @staticmethod
    def calculate_descriptors(smiles: str) -> np.ndarray:
        """Return a 9-element physicochemical descriptor vector, or zeros on failure."""
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return np.zeros(9, dtype=np.float32)

        return np.array([
            Descriptors.MolWt(mol),
            Crippen.MolLogP(mol),
            rdMolDescriptors.CalcTPSA(mol),
            float(Lipinski.NumHAcceptors(mol)),
            float(Lipinski.NumHDonors(mol)),
            float(Lipinski.NumRotatableBonds(mol)),
            float(rdMolDescriptors.CalcNumAromaticRings(mol)),
            rdMolDescriptors.CalcFractionCSP3(mol),
            float(rdMolDescriptors.CalcNumHeteroatoms(mol)),
        ], dtype=np.float32)

    @staticmethod
    def calculate_fingerprint(smiles: str, n_bits: int = 512) -> np.ndarray:
        """Return an ECFP4 Morgan fingerprint bit vector, or zeros on failure."""
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return np.zeros(n_bits, dtype=np.int8)

        fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=n_bits)
        return np.array(fp, dtype=np.int8)


class BioactivityDataset:
    """
    Synthetic DHFR bioactivity dataset built from validated drug-like SMILES.

    Actives: known DHFR inhibitor scaffolds (diaminopyrimidines, quinazolines).
    Inactives: common drugs with unrelated targets.

    In production, replace `generate_sample_data` with a live ChEMBL query:
        from chembl_webresource_client.new_client import new_client
        activity = new_client.activity
        records = activity.filter(target_chembl_id='CHEMBL202', standard_type='IC50')
    """

    TARGET_NAME = "DHFR (Dihydrofolate Reductase)"
    TARGET_CHEMBL_ID = "CHEMBL202"

    def __init__(self):
        self.data: pd.DataFrame | None = None

    def generate_sample_data(self, n_samples: int = 1000) -> pd.DataFrame:
        """Sample from validated SMILES pools to build a synthetic dataset."""
        print(f"Generating {n_samples} synthetic bioactivity records...")

        rng = np.random.default_rng(42)
        records = []

        for i in range(n_samples):
            is_active = rng.random() < 0.3
            if is_active:
                smiles = _ACTIVE_SMILES[i % len(_ACTIVE_SMILES)]
                pic50 = 6.0 + rng.random() * 3.0
                activity = "active"
            else:
                smiles = _INACTIVE_SMILES[i % len(_INACTIVE_SMILES)]
                pic50 = 3.0 + rng.random() * 2.0
                activity = "inactive"

            records.append({
                "compound_id": f"CHEMBL{1_000_000 + i}",
                "smiles": smiles,
                "pIC50": pic50,
                "IC50_nM": 10 ** (9 - pic50),
                "activity_class": activity,
                "assay_type": "B" if rng.random() > 0.2 else "F",
            })

        self.data = pd.DataFrame(records)
        active_count = (self.data.activity_class == "active").sum()
        inactive_count = (self.data.activity_class == "inactive").sum()
        print(f"  Active:   {active_count}")
        print(f"  Inactive: {inactive_count}")
        return self.data

    def prepare_classification_data(
        self,
    ) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
        """Build feature matrix and label vector for binary classification."""
        binary = self.data[
            self.data.activity_class.isin(["active", "inactive"])
        ].copy()
        binary["label"] = (binary.activity_class == "active").astype(int)

        print(f"\nBinary classification — {len(binary)} samples  "
              f"({binary.label.sum()} active, {(~binary.label.astype(bool)).sum()} inactive)")

        md = MolecularDescriptors()
        descriptors, fingerprints = [], []
        for smiles in binary.smiles:
            descriptors.append(md.calculate_descriptors(smiles))
            fingerprints.append(md.calculate_fingerprint(smiles, n_bits=512))

        X = np.hstack([np.array(descriptors), np.array(fingerprints)])
        y = binary.label.values
        print(f"Feature matrix: {X.shape}")
        return X, y, binary


class BioactivityPredictor:
    """Random Forest classifier for binary DHFR bioactivity prediction."""

    def __init__(self, model_type: str = "random_forest"):
        self.model_type = model_type
        self.model = None
        self.scaler = None
        self.metrics: Dict = {}

    def train(self, X_train: np.ndarray, y_train: np.ndarray) -> "BioactivityPredictor":
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.preprocessing import StandardScaler

        print(f"\nTraining {self.model_type} classifier...")
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X_train)
        self.model = RandomForestClassifier(
            n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
        )
        self.model.fit(X_scaled, y_train)
        print("Training complete.")
        return self

    def evaluate(self, X_test: np.ndarray, y_test: np.ndarray) -> Dict:
        from sklearn.metrics import (
            accuracy_score, precision_score, recall_score,
            f1_score, roc_auc_score, confusion_matrix,
        )

        X_scaled = self.scaler.transform(X_test)
        y_pred = self.model.predict(X_scaled)
        y_proba = self.model.predict_proba(X_scaled)[:, 1]

        self.metrics = {
            "accuracy":  accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred),
            "recall":    recall_score(y_test, y_pred),
            "f1":        f1_score(y_test, y_pred),
            "roc_auc":   roc_auc_score(y_test, y_proba),
            "confusion_matrix": confusion_matrix(y_test, y_pred),
        }

        print("\n=== Model Performance ===")
        for key in ("accuracy", "precision", "recall", "f1", "roc_auc"):
            print(f"  {key.capitalize():<10}: {self.metrics[key]:.3f}")
        return self.metrics

    def predict(
        self, smiles_list: List[str]
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Predict activity for new SMILES strings."""
        md = MolecularDescriptors()
        features = [
            np.hstack([md.calculate_descriptors(s), md.calculate_fingerprint(s, n_bits=512)])
            for s in smiles_list
        ]
        X = self.scaler.transform(np.array(features))
        return self.model.predict(X), self.model.predict_proba(X)


def main():
    """Complete bioactivity prediction pipeline."""
    from sklearn.model_selection import train_test_split

    print("=" * 60)
    print("DHFR Bioactivity Prediction Pipeline")
    print("=" * 60)

    dataset = BioactivityDataset()
    dataset.generate_sample_data(n_samples=1000)
    X, y, _ = dataset.prepare_classification_data()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"\nTrain: {len(X_train)} | Test: {len(X_test)}")

    predictor = BioactivityPredictor()
    predictor.train(X_train, y_train)
    predictor.evaluate(X_test, y_test)

    # Demonstrate prediction on held-out known inhibitors
    print("\n=== Example Predictions ===")
    test_smiles = [
        "COc1cc(Cc2cnc(N)nc2N)cc(OC)c1OC",  # Trimethoprim — expect ACTIVE
        "Cc1nc(N)nc(N)c1Cc1ccc(Cl)cc1",       # Pyrimethamine — expect ACTIVE
        "CC(=O)Oc1ccccc1C(=O)O",              # Aspirin — expect INACTIVE
    ]
    predictions, probabilities = predictor.predict(test_smiles)
    for smiles, pred, prob in zip(test_smiles, predictions, probabilities):
        label = "ACTIVE" if pred == 1 else "INACTIVE"
        print(f"  {smiles[:40]:<40}  {label}  (conf: {prob[pred]:.2%})")

    print("\n" + "=" * 60)
    print("Pipeline complete.")
    print("=" * 60)

    return predictor, dataset, predictor.metrics


if __name__ == "__main__":
    predictor, dataset, metrics = main()
