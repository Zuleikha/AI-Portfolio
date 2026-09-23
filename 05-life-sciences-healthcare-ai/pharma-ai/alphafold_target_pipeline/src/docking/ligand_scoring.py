#!/usr/bin/env python

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
from rdkit import Chem


def parse_vina_scores(pdbqt_path: Path) -> List[float]:
    """Parse Vina scores from a .pdbqt file."""
    scores: List[float] = []
    with pdbqt_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("REMARK VINA RESULT"):
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        scores.append(float(parts[3]))
                    except ValueError:
                        pass
    return scores


def guess_ligand_core_name(ligand_name: str) -> str:
    """Strip common suffixes like '_out' from docking file names."""
    if ligand_name.endswith("_out"):
        return ligand_name[:-4]
    return ligand_name


def load_ligand_heavy_atoms(ligand_core: str, ligands_dir: Path) -> int | None:
    """
    Try to load the ligand from ligands_dir using RDKit and return heavy atom count.
    Tries .sdf then .mol.
    """
    candidates = [
        ligands_dir / f"{ligand_core}.sdf",
        ligands_dir / f"{ligand_core}.mol",
    ]
    for path in candidates:
        if path.exists():
            suppl = None
            if path.suffix.lower() == ".sdf":
                suppl = Chem.SDMolSupplier(str(path), removeHs=False)
                mol = next((m for m in suppl if m is not None), None)
            else:
                mol = Chem.MolFromMolFile(str(path), removeHs=False)

            if mol is not None:
                return mol.GetNumHeavyAtoms()
    return None


def summarize_ligand_scores(
    pdbqt_files: List[Path],
    ligands_dir: Path,
) -> pd.DataFrame:
    """Build a summary DataFrame from docking outputs + RDKit heavy atoms."""
    records: List[Dict[str, Any]] = []

    for path in pdbqt_files:
        scores = parse_vina_scores(path)
        ligand_name = path.stem
        core_name = guess_ligand_core_name(ligand_name)
        heavy_atoms = load_ligand_heavy_atoms(core_name, ligands_dir)

        if scores:
            best_score = min(scores)
            worst_score = max(scores)
            mean_score = sum(scores) / len(scores)
        else:
            best_score = worst_score = mean_score = None

        if best_score is not None and heavy_atoms and heavy_atoms > 0:
            ligand_efficiency = best_score / heavy_atoms
        else:
            ligand_efficiency = None

        records.append(
            {
                "ligand_file": str(path),
                "ligand_name": ligand_name,
                "ligand_core": core_name,
                "num_poses": len(scores),
                "best_score": best_score,
                "worst_score": worst_score,
                "mean_score": mean_score,
                "heavy_atoms": heavy_atoms,
                "ligand_efficiency": ligand_efficiency,
            }
        )

    df = pd.DataFrame.from_records(records)
    if "best_score" in df.columns:
        df = df.sort_values(by="best_score", ascending=True, na_position="last")
    return df


def main():
    parser = argparse.ArgumentParser(
        description="Summarize AutoDock Vina docking scores for DHFR ligands."
    )
    parser.add_argument(
        "--docking-dir",
        type=str,
        default="alphafold_target_pipeline/output/docking",
        help="Directory containing Vina .pdbqt output files.",
    )
    parser.add_argument(
        "--ligands-dir",
        type=str,
        default="alphafold_target_pipeline/data/ligands",
        help="Directory containing ligand structure files (.sdf/.mol).",
    )
    parser.add_argument(
        "--out-csv",
        type=str,
        default="alphafold_target_pipeline/output/ligand_scoring.csv",
        help="Path to write the ligand scoring summary CSV.",
    )

    args = parser.parse_args()

    docking_dir = Path(args.docking_dir)
    ligands_dir = Path(args.ligands_dir)
    out_csv = Path(args.out_csv)

    if not docking_dir.exists():
        raise SystemExit(f"[ERROR] Docking directory not found: {docking_dir}")

    pdbqt_files = sorted(docking_dir.glob("*.pdbqt"))
    if not pdbqt_files:
        raise SystemExit(f"[ERROR] No .pdbqt files found in {docking_dir}")

    print(f"[INFO] Found {len(pdbqt_files)} docking files in {docking_dir}")
    for f in pdbqt_files:
        print(f"  - {f.name}")

    df = summarize_ligand_scores(pdbqt_files, ligands_dir)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)

    print(f"\n[INFO] Scoring summary written to: {out_csv}")
    print(df)


if __name__ == "__main__":
    main()
