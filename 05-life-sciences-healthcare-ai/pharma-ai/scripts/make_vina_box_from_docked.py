"""
Compute AutoDock Vina search-box parameters from a docked ligand pose.

Usage:
    python scripts/make_vina_box_from_docked.py

Reads the docked trimethoprim SDF, calculates the bounding box of the ligand,
and prints center / size values ready to paste into a Vina config file.
"""

from pathlib import Path

from rdkit import Chem

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKED_SDF = REPO_ROOT / "alphafold_target_pipeline" / "output" / "docking" / "trimethoprim_docked.sdf"


def ligand_bounding_box(mol_path: Path) -> dict:
    """Return Vina box parameters derived from the ligand's heavy-atom positions."""
    mol = Chem.MolFromMolFile(str(mol_path), removeHs=False)
    if mol is None:
        raise ValueError(f"Could not load molecule from {mol_path}")

    conf = mol.GetConformer()
    positions = [conf.GetAtomPosition(i) for i in range(mol.GetNumAtoms())]
    xs = [p.x for p in positions]
    ys = [p.y for p in positions]
    zs = [p.z for p in positions]

    # Center on ligand centroid; add 10 Å padding on each side.
    center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
    size   = (max(xs) - min(xs) + 10.0, max(ys) - min(ys) + 10.0, max(zs) - min(zs) + 10.0)

    return {"center": center, "size": size}


def main():
    params = ligand_bounding_box(DOCKED_SDF)
    cx, cy, cz = params["center"]
    sx, sy, sz = params["size"]

    print(f"center_x = {cx:.3f}")
    print(f"center_y = {cy:.3f}")
    print(f"center_z = {cz:.3f}")
    print(f"size_x   = {sx:.3f}")
    print(f"size_y   = {sy:.3f}")
    print(f"size_z   = {sz:.3f}")


if __name__ == "__main__":
    main()
