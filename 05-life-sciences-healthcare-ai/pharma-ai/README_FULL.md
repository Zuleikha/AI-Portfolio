# Pharma AI — Computational Drug Discovery

A working computational drug-discovery system built around a single validated target,
**DHFR (dihydrofolate reductase)**: predict the protein structure, locate its binding
pocket, dock known inhibitors into it, and analyse candidate compounds for
drug-likeness.

The point of the project is **systems integration across a scientific domain** —
connecting structure prediction, cavity detection, docking and cheminformatics into one
coherent workflow, and reading the results correctly. Each stage uses the standard tool
for the job (ColabFold, fpocket, AutoDock Vina, RDKit); the work is in making them
agree on a target, a coordinate frame and a set of ligands, and in knowing what the
output does and does not prove.

> **Evidence label: PERSONAL PROJECT EXPERIENCE.**
> Self-directed build work. This is **not** professional pharmaceutical, clinical or
> laboratory experience, and nothing here has been validated experimentally.

---

## Status — read this before the results

This repository contains **two kinds of work**, and they are not equally strong. They
are separated here deliberately rather than presented as one uniform "portfolio".

| Component | Status |
|---|---|
| **Structure → pocket → docking pipeline** | ✅ **Real.** Genuine AutoDock Vina runs against a real DHFR structure, producing results that are chemically coherent |
| **RDKit cheminformatics modules** | ✅ **Real.** Standard descriptors and fragmentation, correctly applied |
| **ML toxicity classifier** | ⚠️ **Demonstration only.** Trained on 20 hand-picked molecules. The metrics it prints are not meaningful |
| **ML bioactivity classifier** | ⚠️ **Demonstration only.** Runs on **synthetic data**, not real ChEMBL records. No performance claim is made |
| **Tests** | ❌ **None.** The project has no test suite |

**No accuracy figure is quoted anywhere in this README**, because neither ML component
is trained on data that would make one meaningful. See
[What the ML components do and do not show](#what-the-ml-components-do-and-do-not-show).

---

## The genuine result: docking known DHFR inhibitors

This is the part worth reading. A DHFR structure was predicted, its binding pocket
identified with fpocket, and three ligands docked into that pocket with AutoDock Vina —
9 poses each.

| Ligand | Best score (kcal/mol) | Mean of 9 poses | Heavy atoms | Ligand efficiency |
|---|---|---|---|---|
| **Trimethoprim** *(known DHFR inhibitor)* | **−7.832** | −7.334 | 20 | −0.392 |
| **Pyrimethamine** *(known DHFR inhibitor)* | **−7.438** | −6.876 | 17 | −0.438 |
| Fragment core | −4.808 | −4.653 | 8 | **−0.601** |

Raw output is in `alphafold_target_pipeline/output/` — docked poses as `.pdbqt`
(`REMARK VINA RESULT` lines carry the per-pose scores) and the summary in
`ligand_scoring.csv`.

### Why this result is the interesting one

The numbers behave the way the chemistry says they should, which is the check that
separates a working pipeline from one that merely runs:

- **The two real drugs outscore the fragment on raw affinity.** Trimethoprim and
  pyrimethamine are actual clinical DHFR inhibitors; a small fragment is not. Recovering
  that ordering is a sanity check on the structure, the pocket and the docking setup all
  at once.
- **The fragment wins on ligand efficiency** (−0.601 vs −0.392 per heavy atom). This is
  the expected fragment-based drug design pattern: fragments bind weakly but *efficiently*,
  which is precisely why they make good starting points for growing a lead.

Reading both columns together — rather than ranking on affinity alone — is the
substantive part. A pipeline that only reported best score would rank the fragment last
and miss the point of fragment-based design.

**Honest limits:** docking scores are approximations from a scoring function, not
binding free energies. A single target, three ligands and no experimental validation
make this a *worked example of the method*, not evidence about these compounds.

---

## Pipeline

```
DHFR sequence
     │
     ▼
ColabFold / AlphaFold ──► ranked structures (DHFR_rank1..5.pdb)
     │
     ▼
fpocket ──────────────► binding-site cavities (20 candidate pockets)
     │
     ▼
Ligand preparation ────► 3D embed, conformers, Gasteiger charges, .pdbqt
     │
     ▼
AutoDock Vina ─────────► 9 poses per ligand + affinity scores
     │
     ▼
Pose analysis ─────────► ligand efficiency, PyMOL/VMD visualisation
```

The predicted structure used for docking carries 1,509 atom records; five ranked models
were generated and the top-ranked one taken forward.

---

## Cheminformatics modules

Four standalone RDKit modules in `src/`. Each runs as a demo from the command line.

| Module | What it does |
|---|---|
| `molecular_property_analyzer.py` | Lipinski Rule of Five, QED druglikeness, TPSA, LogP, HBD/HBA, rotatable bonds, ring counts. Batch CSV export |
| `fragment_based_drug_design.py` | BRICS and RECAP fragmentation, Murcko scaffold extraction, fragment library filtering, Lipinski violation reporting |
| `molecular_docking_prep.py` | 3D structure generation, multi-conformer embedding with MMFF94/UFF minimisation, Gasteiger partial charges, PDB/SDF export |
| `ml_compound_prioritisation.py` | Morgan (ECFP4) / MACCS fingerprints feeding a Random Forest toxicity classifier — **demonstration only, see below** |

```python
from src.molecular_property_analyzer import MolecularPropertyAnalyzer

analyzer = MolecularPropertyAnalyzer()
results = analyzer.analyze_molecule('CC(=O)Oc1ccccc1C(=O)O')   # Aspirin
print(f"QED Score: {results['QED']:.3f}")
print(f"Passes Lipinski: {results['Lipinski']['LipinskiPass']}")
```

These are straightforward applications of well-documented RDKit APIs. They are included
because the docking workflow needs them, not as a claim of novelty.

---

## What the ML components do and do not show

Both ML modules are **teaching scaffolding**: they demonstrate the shape of a
cheminformatics ML pipeline — fingerprints in, classifier out, ranked compounds — on
data that cannot support a performance claim. They are kept because the structure is
correct and reusable. **No accuracy number from either is quoted as a result.**

### Toxicity classifier — `src/ml_compound_prioritisation.py`

Trained on **20 hand-picked molecules** (10 labelled toxic, 10 safe). With an 80/20
split that leaves a **four-compound test set**, so the metrics it prints fluctuate
wildly between meaningless extremes and should be ignored entirely.

To make it mean anything, swap the hardcoded list for a real toxicity dataset —
**Tox21** or **ToxCast** — which is what the function's own docstring says.

> **Data defect found and fixed (2026-09-23).** The same molecule appeared in both
> classes: `CC(=O)NC1=CC=C(C=C1)O` (labelled toxic, commented "Acetaminophen precursor")
> and `CC(=O)Nc1ccc(O)cc1` (labelled safe, "Paracetamol") are two spellings of
> **acetaminophen** — confirmed by RDKit canonicalisation, both resolving to
> `CC(=O)Nc1ccc(O)cc1`. One tenth of the training set was a direct contradiction.
>
> The toxic-list entry has been replaced with **4-aminophenol** (`Nc1ccc(O)cc1`), the
> actual acetaminophen precursor the comment intended, which is genuinely nephrotoxic.
> A guard, `assert_no_label_conflicts()`, now canonicalises every SMILES at load time
> and **raises** if one structure carries two labels — the defect was invisible by eye
> and silently poisons training, so it is checked rather than trusted.

### Bioactivity classifier — `bioactivity-prediction/`

**This module uses synthetic data, not ChEMBL data.** The dataset is generated by
cycling 20 hand-written SMILES (10 DHFR-inhibitor-like scaffolds, 10 unrelated drugs)
into 1,000 rows. Because labels are fixed per molecule and the split is random, **every
test molecule also appears in training** — so any score it reports measures memorisation
of duplicates, not generalisation. No figure from it is quoted.

The DHFR target id (`CHEMBL202`) and the query needed for a real pull are written into
the module's docstring; replacing `generate_sample_data()` with a live
`chembl_webresource_client` query is the intended next step and the only thing that
would make the module's output a result.

---

## Technical stack

| Layer | Choice |
|---|---|
| Cheminformatics | RDKit |
| Structure prediction | ColabFold / AlphaFold |
| Cavity detection | fpocket |
| Docking | AutoDock Vina |
| Visualisation | PyMOL, VMD, py3Dmol |
| ML | scikit-learn (Random Forest) |
| Data | pandas, NumPy |
| Structural I/O | BioPython |
| Packaging | conda (`environment.yml`), Docker |

**Techniques:** Morgan (ECFP4) and MACCS fingerprints · molecular descriptors · QED ·
Lipinski Rule of Five · BRICS/RECAP decomposition · Murcko scaffolds · MMFF94/UFF
conformer generation · protein–ligand docking · ligand efficiency analysis.

---

## Why DHFR

Dihydrofolate reductase is used as the worked target throughout because it is a
**clinically validated** one:

- Established therapeutics exist against it — methotrexate, trimethoprim, pyrimethamine
- Well-characterised structure and mechanism, so docking output can be sanity-checked
- Relevant across oncology and infectious disease

Using a target with known inhibitors is deliberate: it means the pipeline's output can
be checked against something, rather than producing numbers with nothing to compare them to.

---

## Running it

**Requirements:** Python 3.10+, conda recommended. RDKit is the one non-trivial
dependency.

```bash
conda env create -f environment.yml
conda activate pharma-ai-env

python src/molecular_property_analyzer.py
python src/fragment_based_drug_design.py
python src/molecular_docking_prep.py
python src/ml_compound_prioritisation.py      # demonstration data — see above
```

Notebooks in `notebooks/` and `alphafold_target_pipeline/notebooks/` walk through the
structure analysis and ligand scoring steps.

Reproducing the docking stage additionally requires **AutoDock Vina** and **fpocket**,
which are not Python packages and are not installed by the conda environment. The
docked poses and scores are committed so the analysis can be read without re-running them.

---

## Known limits

Stated plainly, because several of these were previously described inaccurately.

| Area | Limit |
|---|---|
| **Tests** | 🔴 **There are none.** No test suite exists anywhere in the project. The cheminformatics modules are pure functions of SMILES and would be cheap to test against known values — this is the first thing that should be added |
| **ML on real data** | 🔴 Neither classifier is trained on a real dataset. Tox21/ToxCast and a live ChEMBL pull are the fix |
| **Docking scope** | One target, three ligands, no redocking statistics against a crystal pose, no experimental validation |
| **Scoring functions** | Vina scores approximate binding affinity; they are not free energies and should not be read as potency predictions |
| **Dependency pinning** | `requirements.txt` is unpinned; `environment.yml` pins only Python |
| **CI** | None |
| **Secrets** | Ensure `.env` is git-ignored before publishing anywhere — it is not covered by this project's own ignore rules |

---

## What this demonstrates

- **Systems thinking across an unfamiliar domain** — decomposing drug discovery into
  stages, then choosing and connecting the right tool for each
- **Architecture** — a pipeline where each stage produces a durable, inspectable
  artefact (structure, pocket, prepared ligand, docked pose, score table)
- **Connecting heterogeneous technologies** — Python tooling, command-line scientific
  binaries, structural file formats (PDB, PDBQT, SDF, MOL) and visualisation
- **Applied AI/ML experimentation** — fingerprint-based classification, and the
  judgement to state when an experiment's data does not support a conclusion
- **Reading results critically** — interpreting affinity against ligand efficiency
  rather than ranking on one number

Programming is the supporting capability here, not the subject.

---

## License

MIT — see [LICENSE](LICENSE).
