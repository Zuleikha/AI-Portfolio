# Computational Drug Discovery (DHFR)

> Part of [ai-portfolio](../../README.md) · Personal project · **Life Sciences / Healthcare AI**

**In one line:** a computer-based drug discovery workflow for one drug target: predict the protein's shape, find its binding pocket, and test how known drugs fit.

## Why it matters

The work is in connecting standard scientific tools so they agree on one target, and in reading the results correctly.

## Key results

| | |
|---|---|
| Tools | ColabFold / AlphaFold, fpocket, AutoDock Vina, RDKit |
| Docking (kcal/mol, lower is stronger) | Trimethoprim −7.8 · Pyrimethamine −7.4 · small fragment −4.8 |
| Sanity check | The two real drugs beat the fragment, as the chemistry predicts |
| Ligand efficiency | The fragment wins (−0.60 vs −0.39), the classic fragment-based pattern |

## The key decision

Results are split into "real" and "demonstration only", so nothing is overstated.

## Honest limits

- No automated tests yet
- The two ML classifiers are demonstrations on tiny or synthetic data
- One target, three ligands, no lab validation
- A personal project, not professional pharmaceutical experience

## Run it

```bash
conda env create -f environment.yml
conda activate pharma-ai-env
python src/molecular_property_analyzer.py
```

Re-running the docking also needs AutoDock Vina and fpocket, installed separately.

---

📄 **Full technical README:** [README_FULL.md](README_FULL.md) (docking results, component status, known limits)

🕘 **Development history:** first published here; there is no separate public repository.
