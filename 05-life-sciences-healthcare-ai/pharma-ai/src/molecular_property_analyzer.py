"""
Molecular Property Analyzer
============================

This module provides tools for analyzing molecular properties and drug-likeness
using RDKit. It calculates various descriptors and evaluates molecules against
pharmaceutical property rules.

Author: Pharma AI Portfolio
Date: 2025
"""

from rdkit import Chem
from rdkit.Chem import Descriptors, Crippen, Lipinski, QED, AllChem
from rdkit.Chem import rdMolDescriptors
import pandas as pd
import os


class MolecularPropertyAnalyzer:
    """Analyzer for molecular properties and drug-likeness."""

    def __init__(self):
        """Initialize the analyzer."""
        self.properties = [
            'MolecularWeight', 'LogP', 'NumHDonors', 'NumHAcceptors',
            'TPSA', 'NumRotatableBonds', 'NumHeteroatoms',
            'NumAliphaticRings', 'NumAromaticRings', 'QED'
        ]

    def smiles_to_mol(self, smiles: str):
        """Convert a SMILES string to an RDKit molecule."""
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES string: {smiles}")
        return mol

    def calculate_basic_properties(self, mol):
        """Calculate basic molecular descriptors."""
        mw = Descriptors.MolWt(mol)
        logp = Crippen.MolLogP(mol)
        h_donors = Lipinski.NumHDonors(mol)
        h_acceptors = Lipinski.NumHAcceptors(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        rot_bonds = Lipinski.NumRotatableBonds(mol)
        heteroatoms = rdMolDescriptors.CalcNumHeteroatoms(mol)
        aliphatic_rings = rdMolDescriptors.CalcNumAliphaticRings(mol)
        aromatic_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
        qed_score = QED.qed(mol)

        return {
            'MolecularWeight': mw,
            'LogP': logp,
            'NumHDonors': h_donors,
            'NumHAcceptors': h_acceptors,
            'TPSA': tpsa,
            'NumRotatableBonds': rot_bonds,
            'NumHeteroatoms': heteroatoms,
            'NumAliphaticRings': aliphatic_rings,
            'NumAromaticRings': aromatic_rings,
            'QED': qed_score,
        }

    def evaluate_lipinski(self, properties):
        """Evaluate Lipinski's Rule of Five."""
        violations = []

        if properties['MolecularWeight'] > 500:
            violations.append('Molecular weight > 500')
        if properties['LogP'] > 5:
            violations.append('LogP > 5')
        if properties['NumHDonors'] > 5:
            violations.append('H-bond donors > 5')
        if properties['NumHAcceptors'] > 10:
            violations.append('H-bond acceptors > 10')

        return {
            'LipinskiPass': len(violations) == 0,
            'LipinskiViolations': violations
        }

    def analyze_molecule(self, smiles: str):
        """Analyze a single molecule given its SMILES string."""
        mol = self.smiles_to_mol(smiles)
        basic_props = self.calculate_basic_properties(mol)
        lipinski = self.evaluate_lipinski(basic_props)

        results = {
            'SMILES': smiles,
            'BasicProperties': basic_props,
            'Lipinski': lipinski,
            'QED': basic_props['QED']
        }

        self.pretty_print_results(results)
        return results

    def pretty_print_results(self, results):
        """Nicely format and print the analysis results."""
        print(f"SMILES: {results['SMILES']}")
        print("\nBasic Properties:")
        for key, value in results['BasicProperties'].items():
            print(f"  {key:20s}: {value:.3f}" if isinstance(value, (int, float)) else f"  {key:20s}: {value}")

        print("\nLipinski's Rule of Five:")
        lipinski = results['Lipinski']
        print(f"  Passes: {lipinski['LipinskiPass']}")
        if lipinski['LipinskiViolations']:
            print("  Violations:")
            for v in lipinski['LipinskiViolations']:
                print(f"    - {v}")
        else:
            print("  No violations.")

        print(f"\nQED (Drug-likeness): {results['QED']:.3f}")
        print("-" * 60)

    def analyze_batch(self, smiles_list):
        """Analyze a batch of molecules and return a DataFrame."""
        results = []

        for smiles in smiles_list:
            try:
                analysis = self.analyze_molecule(smiles)
                flat_result = {'SMILES': smiles}
                flat_result.update(analysis['BasicProperties'])
                flat_result.update(analysis['Lipinski'])
                flat_result['QED'] = analysis['QED']
                results.append(flat_result)
            except ValueError as e:
                print(f"Error analyzing {smiles}: {e}")

        return pd.DataFrame(results)


def demo_analysis(csv_filename: str = "molecular_analysis_results.csv") -> pd.DataFrame:
    """
    Run a demo batch analysis and save results to a CSV file.

    This is the function the Jupyter notebook imports.
    It writes the CSV into the same folder as this file (src/).
    """
    analyzer = MolecularPropertyAnalyzer()

    # Same example molecules used in main()
    examples = {
        'Aspirin': 'CC(=O)Oc1ccccc1C(=O)O',
        'Ibuprofen': 'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
        'Caffeine': 'CN1C=NC2=C1C(=O)N(C(=O)N2C)C',
        'Penicillin G': 'CC1(C)SC2C(NC(=O)Cc3ccccc3)C(=O)N2C1C(=O)O'
    }

    smiles_list = list(examples.values())
    df = analyzer.analyze_batch(smiles_list)

    # Save CSV in output dir
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, csv_filename)
    df.to_csv(csv_path, index=False)

    print(f"\nCSV file saved to: {csv_path}")
    return df


def main():
    """Example usage of MolecularPropertyAnalyzer."""
    analyzer = MolecularPropertyAnalyzer()

    # Example molecules
    examples = {
        'Aspirin': 'CC(=O)Oc1ccccc1C(=O)O',
        'Ibuprofen': 'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
        'Caffeine': 'CN1C=NC2=C1C(=O)N(C(=O)N2C)C',
        'Penicillin G': 'CC1(C)SC2C(NC(=O)Cc3ccccc3)C(=O)N2C1C(=O)O'
    }

    print("Analyzing example drug molecules...\n")

    for name, smiles in examples.items():
        print(f"\n{'='*60}")
        print(f"Analyzing: {name}")
        print(f"{'='*60}")
        analyzer.analyze_molecule(smiles)

    # Batch analysis example
    print("\n\nBatch Analysis Example:")
    print("-" * 60)
    smiles_list = list(examples.values())
    df = analyzer.analyze_batch(smiles_list)
    print(df[['SMILES', 'MolecularWeight', 'LogP', 'QED', 'LipinskiPass']].to_string())


if __name__ == "__main__":
    main()
