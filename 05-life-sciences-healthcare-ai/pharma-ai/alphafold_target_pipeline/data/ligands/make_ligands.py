"""
Generate 3D ligand structure files for DHFR docking.

Produces one .mol file per ligand with:
  - Explicit hydrogens added
  - ETKDG conformer embedded (random seed 42 for reproducibility)
  - MMFF94 energy minimization
"""

from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

OUTPUT_DIR = Path(__file__).parent

LIGANDS = {
    "trimethoprim":  "COc1cc(Cc2cnc(N)nc2N)cc(OC)c1OC",
    "pyrimethamine": "Cc1nc(N)nc(N)c1Cc1ccc(Cl)cc1",
    "fragment_core": "Nc1nc(N)ncn1",
}


def prepare_ligand(name: str, smiles: str) -> bool:
    """Embed and minimise a single ligand; save to <name>.mol. Returns True on success."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        print(f"  ERROR: invalid SMILES for {name!r} — skipping.")
        return False

    mol = Chem.AddHs(mol)

    result = AllChem.EmbedMolecule(mol, AllChem.ETKDGv3(), randomSeed=42)
    if result != 0:
        print(f"  WARNING: 3D embedding failed for {name!r} — skipping.")
        return False

    ff_result = AllChem.MMFFOptimizeMolecule(mol)
    if ff_result == -1:
        print(f"  WARNING: MMFF94 optimisation failed for {name!r}, using unminimised geometry.")

    out_path = OUTPUT_DIR / f"{name}.mol"
    Chem.MolToMolFile(mol, str(out_path))
    print(f"  Saved {out_path.name}  ({mol.GetNumAtoms()} atoms)")
    return True


def main():
    print("Generating 3D ligand files...")
    success = sum(prepare_ligand(name, smiles) for name, smiles in LIGANDS.items())
    print(f"\nDone: {success}/{len(LIGANDS)} ligands prepared.")


if __name__ == "__main__":
    main()
