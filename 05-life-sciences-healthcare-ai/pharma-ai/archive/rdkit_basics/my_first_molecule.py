from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

smiles = "CC(=O)Oc1ccccc1C(=O)O"  # aspirin
mol = Chem.MolFromSmiles(smiles)

print("Molecule created:", mol is not None)
print("Atoms (heavy):", mol.GetNumAtoms())
print("Bonds:", mol.GetNumBonds())
print("Formula:", rdMolDescriptors.CalcMolFormula(mol))
              