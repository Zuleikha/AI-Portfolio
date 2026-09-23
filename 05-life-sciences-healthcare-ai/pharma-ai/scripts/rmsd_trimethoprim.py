"""
Compute the heavy-atom RMSD between the crystal/reference trimethoprim pose
and a re-docked pose, as a docking validation metric.

Usage:
    python scripts/rmsd_trimethoprim.py

A well-reproduced pose typically has RMSD < 2 Å.
"""

from pathlib import Path

from rdkit import Chem
from rdkit.Chem import rdMolAlign

REPO_ROOT = Path(__file__).resolve().parent.parent
REF_MOL  = REPO_ROOT / "alphafold_target_pipeline" / "data" / "ligands" / "trimethoprim.mol"
DOCK_SDF = REPO_ROOT / "alphafold_target_pipeline" / "output" / "docking" / "trimethoprim_docked_redock.sdf"


def compute_rmsd(ref_path: Path, docked_path: Path) -> float:
    """Return the heavy-atom RMSD between reference and re-docked poses."""
    ref = Chem.MolFromMolFile(str(ref_path), removeHs=True)
    dock_raw = Chem.MolFromMolFile(str(docked_path), removeHs=False, sanitize=False)

    if ref is None or dock_raw is None:
        raise ValueError(f"Failed to load one or both molecules.\n  ref: {ref_path}\n  docked: {docked_path}")

    dock = Chem.RemoveHs(dock_raw)

    print(f"Reference atoms:  {ref.GetNumAtoms()}")
    print(f"Docked atoms:     {dock.GetNumAtoms()}")

    if ref.GetNumAtoms() != dock.GetNumAtoms():
        raise ValueError(
            f"Atom count mismatch ({ref.GetNumAtoms()} vs {dock.GetNumAtoms()}) "
            "— cannot compute RMSD safely."
        )

    atom_map = list(zip(range(ref.GetNumAtoms()), range(ref.GetNumAtoms())))
    return rdMolAlign.AlignMol(dock, ref, atomMap=atom_map)


def main():
    rmsd = compute_rmsd(REF_MOL, DOCK_SDF)
    print(f"Trimethoprim redocking RMSD: {rmsd:.3f} Å")
    if rmsd < 2.0:
        print("Result: PASS — pose reproduced within 2 Å threshold.")
    else:
        print("Result: FAIL — RMSD exceeds 2 Å threshold.")


if __name__ == "__main__":
    main()
