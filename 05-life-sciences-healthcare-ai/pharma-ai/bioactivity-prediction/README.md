# DHFR Bioactivity Prediction

Machine learning model for predicting compound bioactivity against Dihydrofolate Reductase (DHFR).

## Overview

This project demonstrates a complete ML pipeline for pharmaceutical compound screening:
- Target: DHFR enzyme (validated drug target for antibacterials and anticancer drugs)
- Task: Binary classification (active vs inactive compounds)
- Features: Molecular descriptors + Morgan fingerprints
- Model: Random Forest classifier

## Business Value

Cost savings: $1,000-5,000 per compound avoided from wet-lab screening

Speed: Screen thousands of compounds in minutes vs weeks

Hit enrichment: Prioritize most promising candidates for experimental testing

## Quick Start

Run the prediction pipeline:
```bash
python bioactivity_prediction.py
```

Expected output:
- Generated bioactivity dataset (1000 compounds)
- Trained Random Forest model
- Performance metrics (Accuracy, Precision, Recall, ROC-AUC)
- Example predictions on new compounds

## Model Performance

Typical metrics on test set:
- Accuracy: 85%
- Precision: 82%
- Recall: 79%
- F1 Score: 0.80
- ROC-AUC: 0.88

Note: These are targets for models trained on real ChEMBL data. Current demo uses simulated data for workflow demonstration.

## Project Structure
```
bioactivity-prediction/
├── bioactivity_prediction.py    # Core ML pipeline
└── README.md                     # This file
```

## Features Generated

Molecular Descriptors (9 features):
- Molecular Weight (MW)
- LogP (lipophilicity)
- Topological Polar Surface Area (TPSA)
- Hydrogen Bond Acceptors (HBA)
- Hydrogen Bond Donors (HBD)
- Rotatable Bonds
- Aromatic Rings
- Fraction sp3 carbons
- Number of heteroatoms

Morgan Fingerprints (512 bits):
- Circular fingerprints capturing substructure patterns
- Radius 2 (equivalent to ECFP4)
- Binary vector representation

## Workflow

1. Data acquisition from ChEMBL database
2. Feature engineering (descriptors + fingerprints)
3. Train/test split with stratification
4. Model training (Random Forest)
5. Evaluation with multiple metrics
6. Prediction on new compounds

## Data Source

ChEMBL Database:
- Target: DHFR (CHEMBL202)
- Activity threshold: pIC50 > 6.0 (IC50 < 1 μM)
- Current version uses simulated data for demonstration

In production:
```bash
pip install chembl_webresource_client rdkit
```

## Next Steps

1. Integrate real RDKit for molecular descriptors
2. Query live ChEMBL database
3. Deploy as REST API (FastAPI)
4. Add model versioning and monitoring
5. Integrate with docking workflow from AlphaFold pipeline

## Technical Stack

- Python 3.8+
- NumPy, Pandas
- scikit-learn (Random Forest)
- RDKit (molecular descriptors, future)
- ChEMBL API (bioactivity data, future)

## Author

Zuleikha - Transitioning from software engineering to AI-driven drug discovery

## License

MIT License