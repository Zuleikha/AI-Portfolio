# CLAUDE.md — pharma-ai

## PROJECT PURPOSE

- Pharmaceutical AI portfolio demonstrating ML and computational chemistry for drug discovery against the DHFR (Dihydrofolate Reductase) target
- Covers toxicity prediction, fragment-based drug design, molecular property analysis, ligand docking preparation, protein structure prediction via AlphaFold, and a REST API for property analysis
- Live URL: https://portfolio-website-ecru-pi-95.vercel.app (portfolio site); the FastAPI app is containerised via Docker but no live Render/cloud URL was found in the repo files
- Portfolio angle: demonstrates a software engineer's transition into pharmaceutical AI/ML — production-ready modules covering the full virtual drug discovery pipeline from structure prediction to compound ranking

---

## ML PIPELINE

| Stage | Status | File(s) that own it |
|---|---|---|
| 1. Data Ingestion | Implemented (synthetic) | `bioactivity-prediction/bioactivity_prediction.py` — `BioactivityDataset.generate_sample_data()` generates synthetic DHFR bioactivity records; note for production: swap for live ChEMBL pull |
| 2. Data Validation / EDA | NOT IMPLEMENTED — gap | No dedicated EDA or schema-validation module exists; notebooks contain exploratory work but no validation code |
| 3. Feature Engineering | Implemented | `bioactivity-prediction/bioactivity_prediction.py` — `MolecularDescriptors` (9 physicochemical descriptors + 512-bit ECFP4 Morgan fingerprints); `src/ml_compound_prioritisation.py` — `MolecularFingerprinter` (2048-bit Morgan or MACCS) |
| 4. Model Training | Implemented | `src/ml_compound_prioritisation.py` — `ToxicityPredictor.train()`; `bioactivity-prediction/bioactivity_prediction.py` — `BioactivityPredictor.train()` |
| 5. Model Evaluation | Implemented | Both training modules report Accuracy, Precision, Recall, ROC-AUC, F1, and confusion matrix |
| 6. Model Registry / Versioning | Partially implemented — gap | `ToxicityPredictor.save_model()` / `load_model()` uses pickle to `output/toxicity_model.pkl`; no versioning scheme, no MLflow/DVC integration |
| 7. Serving / Inference | Implemented | `apps/api.py` — FastAPI app exposing `POST /analyze`, `POST /batch`, `GET /examples`; `Dockerfile` containerises it |
| 8. Monitoring | NOT IMPLEMENTED — gap | No logging framework, health-check metrics, or drift detection in any module |
| 9. Feedback Loop | NOT IMPLEMENTED — gap | No mechanism to ingest new labels, retrain, or update the model from production predictions |

---

## ARCHITECTURE

```
pharma-ai/
├── apps/
│   └── api.py                          # FastAPI REST API — molecular property analysis endpoint
├── alphafold_target_pipeline/          # AlphaFold + AutoDock Vina sub-project for DHFR
│   ├── data/
│   │   ├── protein_sequence.fasta      # DHFR amino acid sequence for ColabFold
│   │   ├── ligands/                    # Ligand files (MOL, SDF, PDBQT) for docking
│   │   └── protein/                    # DHFR PDB/PDBQT structures + fpocket output
│   ├── images/
│   │   └── structures/                 # PyMOL/py3Dmol rendered PNG visualisations
│   ├── notebooks/
│   │   ├── 01_run_alphafold_colab.ipynb   # Run ColabFold; generates 5 ranked PDB models
│   │   ├── 02_structure_analysis.ipynb    # Structure visualisation with py3Dmol/PyMOL
│   │   └── 03_ligand_scoring.ipynb        # Ligand scoring and docking analysis
│   ├── output/
│   │   ├── structures/                 # AlphaFold PDB outputs (DHFR_rank1-5.pdb)
│   │   ├── docking/                    # AutoDock Vina docking outputs (PDBQT, SDF)
│   │   └── vina/                       # Vina pocket-specific docking results
│   ├── pymol_scripts/                  # PyMOL .pml scripts for pocket visualisation
│   ├── src/docking/
│   │   └── ligand_scoring.py           # Ligand pose scoring utilities
│   └── README.md                       # AlphaFold pipeline documentation
├── archive/rdkit_basics/               # Early learning scripts — not production code
├── bioactivity-prediction/
│   ├── bioactivity_prediction.py       # DHFR bioactivity ML pipeline (full train/eval/predict)
│   └── README.md                       # Sub-project documentation
├── docs/roadmaps/
│   └── pharma_roadmap.html             # Visual pipeline roadmap (HTML)
├── images/                             # Top-level molecule images (aspirin, drugs)
├── notebooks/
│   ├── drug_analysis_demo.ipynb        # Drug property analysis demo
│   ├── drug_discovery_workflow.ipynb   # End-to-end workflow notebook
│   ├── fragment_based_drug_design.ipynb
│   ├── Molecular Docking Preparation.ipynb
│   └── molecular_property_analysis.ipynb
├── output/                             # Generated outputs from src modules
│   ├── toxicity_model.pkl              # Saved Random Forest toxicity model (pickle)
│   ├── fragment_library.csv            # BRICS/RECAP fragment library output
│   ├── molecular_analysis_results.csv  # Batch property analysis CSV
│   └── *.png                           # Visualisation outputs
├── scripts/
│   ├── make_vina_box_from_docked.py    # Utility to compute Vina box from docked pose
│   └── rmsd_trimethoprim.py            # RMSD calculation for redocking validation
├── src/
│   ├── ml_compound_prioritisation.py   # ToxicityPredictor — RF model + Morgan fingerprints
│   ├── fragment_based_drug_design.py   # FragmentLibraryGenerator + LeadOptimizer (BRICS/RECAP)
│   ├── molecular_property_analyzer.py  # MolecularPropertyAnalyzer — Lipinski, QED, descriptors
│   └── molecular_docking_prep.py       # MolecularDockingPrep — 3D gen, conformers, charges
├── aspirin.pdb / aspirin.sdf           # Top-level molecule files generated by docking prep
├── caffeine.pdb / caffeine.sdf         # Top-level molecule files
├── ibuprofen.pdb / ibuprofen.sdf       # Top-level molecule files
├── Dockerfile                          # Container for FastAPI app (python:3.9-slim)
├── environment.yml                     # Conda environment (Python 3.10, rdkit, openbabel)
├── requirements.txt                    # pip dependencies for Docker/API
├── FUTURE_WORK.md                      # Roadmap: Phases 7-12 (pose analysis, ADMET, MD, etc.)
├── LEARNING_PATH.md                    # Personal learning notes
├── start_pharma_env.bat                # Windows batch script to activate conda environment
└── README.md                           # Main portfolio documentation
```

---

## BUNDLE CONTRACT

No formal model bundle exists. The only persisted model artifact is:

- `output/toxicity_model.pkl` — pickle file containing `{"model": RandomForestClassifier, "fingerprinter": MolecularFingerprinter}`

What breaks if missing:

| File | What breaks |
|---|---|
| `output/toxicity_model.pkl` | `ToxicityPredictor.load_model()` raises `FileNotFoundError`; the API does not load this model (the API uses `MolecularPropertyAnalyzer` only, not the toxicity model), so the API itself is unaffected |

Gap: There is no bundle spec, no versioned model registry, no manifest listing expected files. The pickle approach is fragile — sklearn version changes can break deserialization. Flag this as a gap for production readiness.

---

## CODING STANDARDS

- Type hints required on all functions
- Docstrings required on all functions
- No hardcoded values — all thresholds, paths, and config must come from function parameters or config files, not inline literals
- No `print()` in production code — use `logging`; note that the current codebase uses `print()` extensively and must be refactored before any production deployment
- All config from files, not inline code — database paths, model paths, and API settings must be externalised

---

## PRODUCTION FILES

These files are the live production entry points:

| File | Role |
|---|---|
| `apps/api.py` | FastAPI application — the only live HTTP interface |
| `src/molecular_property_analyzer.py` | Imported directly by the API at startup |
| `Dockerfile` | Defines the container build and CMD |
| `requirements.txt` | Controls all dependencies installed in the Docker image |

These files must never be refactored without explicit instruction.

---

## TESTING

No test suite exists anywhere in this project. There is no `tests/` directory and no `test_*.py` files.

This is a significant gap. Before any further production work:

1. Create `tests/` at the project root
2. Write unit tests for at least: `MolecularPropertyAnalyzer`, `ToxicityPredictor`, `FragmentLibraryGenerator`, and all API endpoints
3. pytest must pass before any commit.

---

## DECISIONS MADE

`DECISIONS.md` does not exist in this project. This is a gap — architectural and design decisions are not formally recorded.

Key decisions inferred from code and `FUTURE_WORK.md`:

- **Target selected: DHFR** — Dihydrofolate Reductase chosen because it is a clinically validated, well-characterised target with known inhibitors (trimethoprim, pyrimethamine, methotrexate), making it ideal for demonstrating structure-based drug discovery
- **Random Forest over deep learning** — RF used for toxicity and bioactivity prediction because the training dataset is small (synthetic, ~20 labelled compounds for toxicity); deep learning would overfit
- **Synthetic training data** — `generate_synthetic_training_data()` and `BioactivityDataset.generate_sample_data()` use hardcoded SMILES pools rather than live ChEMBL data; this is documented as a known limitation with a clear swap path
- **Morgan fingerprints (ECFP4)** — 2048-bit for toxicity, 512-bit for bioactivity; chosen for their proven performance in molecular ML tasks
- **FastAPI over Flask** — FastAPI chosen for automatic OpenAPI docs, Pydantic validation, and async support
- **Pickle for model persistence** — simple approach; flagged in FUTURE_WORK.md as needing replacement with a proper model registry
- **No MOL2 export** — explicitly documented in `molecular_docking_prep.py`: RDKit does not write MOL2; use Open Babel instead

---

## WHAT NOT TO DO

1. **Do not run `src/ml_compound_prioritisation.py` or `bioactivity_prediction.py` expecting production-quality results** — training data is synthetic (hardcoded SMILES lists). These are demonstration pipelines. Always label outputs clearly as demo/synthetic.

2. **Do not add new dependencies to `requirements.txt` without also updating `environment.yml`** — the two files serve different environments (Docker vs Conda) and must stay in sync.

3. **Do not use pickle (`output/toxicity_model.pkl`) across different scikit-learn versions** — pickle is not stable across sklearn major versions. Never commit a model pickle trained locally and expect it to load in a different environment without testing.

4. **Do not place `.pdb`, `.sdf`, or `.pdbqt` files at the project root** — molecule files (aspirin, caffeine, ibuprofen) have leaked to the root. All molecular data belongs under `alphafold_target_pipeline/data/` or `output/`.

5. **Do not refactor `apps/api.py` or `src/molecular_property_analyzer.py` without explicit instruction** — these are the live production entry points; changes cascade directly to the Docker image and any deployed container.

6. **Do not assume the AlphaFold pipeline can be run locally** — `alphafold_target_pipeline/notebooks/01_run_alphafold_colab.ipynb` runs on Google Colab (ColabFold). It requires GPU resources and an internet connection to the ColabFold server; it is not executable in a local Python environment without significant setup.

---

## SESSION END CHECKLIST

- [ ] pytest passes
- [ ] git add (specific files — never `git add .` to avoid committing `.pkl`, `.pdb`, `.sdf`, or molecule files unintentionally)
- [ ] git commit with descriptive message
- [ ] git push
- [ ] Check deployment logs if production files changed (`apps/api.py`, `src/molecular_property_analyzer.py`, `Dockerfile`, `requirements.txt`)
