"""
Fragment-Based Drug Design
==========================

This module provides tools for fragment-based drug design (FBDD), including:
- Fragment decomposition (BRICS, RECAP)
- Fragment library generation and filtering
- Fragment growing and linking
- Scaffold hopping
- Lead optimization strategies

Author: Pharma AI Portfolio
Date: 2025
"""

from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, Crippen, Lipinski
from rdkit.Chem import BRICS, Recap
from rdkit.Chem import Fragments, GraphDescriptors
from rdkit.Chem.Scaffolds import MurckoScaffold
import pandas as pd
from typing import List, Dict, Tuple
import os


class FragmentLibraryGenerator:
    """Generate and analyze molecular fragments."""
    
    def __init__(self):
        """Initialize the fragment generator with default filters."""
        self.fragment_filters = {
            'max_mw': 300,
            'max_logp': 3,
            'max_hbd': 3,
            'max_hba': 3,
            'max_rotatable': 3,
            'max_tpsa': 60
        }
    
    def decompose_brics(self, smiles: str) -> List[str]:
        """
        Decompose molecule using BRICS method.
        
        BRICS (Breaking of Retrosynthetically Interesting Chemical Substructures)
        breaks bonds that are commonly formed in synthesis.
        
        Args:
            smiles: SMILES string of molecule
        
        Returns:
            List of fragment SMILES
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return []
        
        # Get BRICS fragments
        fragments = BRICS.BRICSDecompose(mol)
        
        # Clean up dummy atoms
        cleaned_fragments = []
        for frag in fragments:
            # Replace dummy atoms with hydrogen
            cleaned = frag.replace('[*]', '[H]')
            mol_frag = Chem.MolFromSmiles(cleaned)
            if mol_frag:
                cleaned_fragments.append(Chem.MolToSmiles(mol_frag))
        
        return list(set(cleaned_fragments))
    
    def decompose_recap(self, smiles: str) -> List[str]:
        """
        Decompose molecule using RECAP method.
        
        RECAP (Retrosynthetic Combinatorial Analysis Procedure)
        identifies retrosynthetically interesting bond breaks.
        
        Args:
            smiles: SMILES string of molecule
        
        Returns:
            List of fragment SMILES
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return []
        
        # Get RECAP tree
        recap_tree = Recap.RecapDecompose(mol)
        
        # Extract leaf fragments
        fragments = []
        for leaf in recap_tree.GetLeaves().values():
            mol_frag = leaf.mol
            if mol_frag:
                # Remove dummy atoms
                for atom in mol_frag.GetAtoms():
                    if atom.GetAtomicNum() == 0:  # Dummy atom
                        atom.SetAtomicNum(1)  # Replace with H
                fragments.append(Chem.MolToSmiles(mol_frag))
        
        return list(set(fragments))
    
    def extract_scaffold(self, smiles: str) -> str:
        """
        Extract Murcko scaffold from molecule.
        
        Args:
            smiles: SMILES string of molecule
        
        Returns:
            SMILES of scaffold
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return ""
        
        scaffold = MurckoScaffold.GetScaffoldForMol(mol)
        return Chem.MolToSmiles(scaffold)
    
    def calculate_fragment_properties(self, smiles: str) -> Dict[str, float]:
        """Calculate key properties for a fragment."""
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {}
        
        return {
            'SMILES': smiles,
            'MolecularWeight': Descriptors.MolWt(mol),
            'LogP': Crippen.MolLogP(mol),
            'HBD': Lipinski.NumHDonors(mol),
            'HBA': Lipinski.NumHAcceptors(mol),
            'TPSA': Descriptors.TPSA(mol),
            'HeavyAtoms': mol.GetNumHeavyAtoms(),
            'RotatableBonds': Lipinski.NumRotatableBonds(mol),
            'AromaticRings': Lipinski.NumAromaticRings(mol),
            'Complexity': GraphDescriptors.BertzCT(mol)
        }
    
    def is_valid_fragment(self, smiles: str) -> bool:
        """Check if fragment passes drug-like filters."""
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return False
        
        return (
            Descriptors.MolWt(mol) <= self.fragment_filters['max_mw'] and
            Crippen.MolLogP(mol) <= self.fragment_filters['max_logp'] and
            Lipinski.NumHDonors(mol) <= self.fragment_filters['max_hbd'] and
            Lipinski.NumHAcceptors(mol) <= self.fragment_filters['max_hba'] and
            Lipinski.NumRotatableBonds(mol) <= self.fragment_filters['max_rotatable'] and
            Descriptors.TPSA(mol) <= self.fragment_filters['max_tpsa']
        )
    
    def score_fragment(self, smiles: str) -> float:
        """
        Score fragment based on drug-likeness.
        
        Higher score = better fragment for drug design
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return 0.0
        
        heavy_atoms = mol.GetNumHeavyAtoms()
        if heavy_atoms == 0:
            return 0.0
        
        # Prefer aromatic fragments with moderate LogP
        logp = Crippen.MolLogP(mol)
        aromatic_rings = Lipinski.NumAromaticRings(mol)
        complexity = GraphDescriptors.BertzCT(mol)
        
        # Scoring function
        score = (aromatic_rings * 2 + 5) / heavy_atoms
        score -= abs(logp) * 0.1  # Penalize extreme LogP
        score -= complexity / 1000  # Penalize high complexity
        
        return max(0.0, score)
    
    def generate_fragment_library(self, smiles_list: List[str], 
                                 method: str = 'brics') -> pd.DataFrame:
        """
        Generate fragment library from multiple molecules.
        
        Args:
            smiles_list: List of SMILES strings
            method: 'brics' or 'recap'
        
        Returns:
            DataFrame with fragments and properties
        """
        all_fragments = set()
        
        for smiles in smiles_list:
            if method.lower() == 'brics':
                frags = self.decompose_brics(smiles)
            elif method.lower() == 'recap':
                frags = self.decompose_recap(smiles)
            else:
                raise ValueError("Method must be 'brics' or 'recap'")
            
            all_fragments.update(frags)
        
        # Parse each fragment SMILES once, then derive validity and score
        # from the already-computed properties to avoid triple re-parsing.
        results = []
        for frag in all_fragments:
            props = self.calculate_fragment_properties(frag)
            if not props:
                continue
            f = self.fragment_filters
            props['IsValid'] = (
                props['MolecularWeight'] <= f['max_mw'] and
                props['LogP'] <= f['max_logp'] and
                props['HBD'] <= f['max_hbd'] and
                props['HBA'] <= f['max_hba'] and
                props['RotatableBonds'] <= f['max_rotatable'] and
                props['TPSA'] <= f['max_tpsa']
            )
            n = props['HeavyAtoms']
            raw_score = ((props['AromaticRings'] * 2 + 5) / n if n > 0 else 0)
            raw_score -= abs(props['LogP']) * 0.1
            raw_score -= props['Complexity'] / 1000
            props['Score'] = max(0.0, raw_score)
            results.append(props)
        
        df = pd.DataFrame(results)
        
        if not df.empty:
            df = df.sort_values('Score', ascending=False)
        
        return df


class LeadOptimizer:
    """Tools for lead optimization in drug design."""
    
    def __init__(self):
        """Initialize lead optimizer."""
        self.generator = FragmentLibraryGenerator()
    
    def analyze_lead(self, smiles: str) -> Dict:
        """
        Analyze a lead compound for optimization opportunities.
        
        Args:
            smiles: SMILES of lead compound
        
        Returns:
            Dictionary with analysis results
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {}
        
        # Calculate properties
        mw = Descriptors.MolWt(mol)
        logp = Crippen.MolLogP(mol)
        hbd = Lipinski.NumHDonors(mol)
        hba = Lipinski.NumHAcceptors(mol)
        tpsa = Descriptors.TPSA(mol)
        rotatable = Lipinski.NumRotatableBonds(mol)
        
        # Get scaffold
        scaffold = self.generator.extract_scaffold(smiles)
        
        # Get fragments
        brics_frags = self.generator.decompose_brics(smiles)
        
        # Check Lipinski violations
        violations = []
        if mw > 500:
            violations.append('MW > 500')
        if logp > 5:
            violations.append('LogP > 5')
        if hbd > 5:
            violations.append('HBD > 5')
        if hba > 10:
            violations.append('HBA > 10')
        
        # Optimization suggestions
        suggestions = []
        if logp > 3:
            suggestions.append('Reduce lipophilicity (add polar groups)')
        if mw > 400:
            suggestions.append('Reduce molecular weight (remove non-essential groups)')
        if rotatable > 10:
            suggestions.append('Reduce flexibility (rigidify structure)')
        if tpsa < 40:
            suggestions.append('Increase TPSA for better solubility')
        
        return {
            'smiles': smiles,
            'scaffold': scaffold,
            'fragments': brics_frags,
            'properties': {
                'MW': mw,
                'LogP': logp,
                'HBD': hbd,
                'HBA': hba,
                'TPSA': tpsa,
                'Rotatable': rotatable
            },
            'lipinski_violations': violations,
            'optimization_suggestions': suggestions
        }
    
    def suggest_modifications(self, smiles: str) -> List[str]:
        """
        Suggest simple structural modifications for lead optimization.
        
        Args:
            smiles: SMILES of lead compound
        
        Returns:
            List of modification suggestions
        """
        analysis = self.analyze_lead(smiles)
        
        modifications = []
        
        if 'LogP > 5' in analysis['lipinski_violations']:
            modifications.append('Add hydroxyl or amine groups to reduce LogP')
        
        if 'MW > 500' in analysis['lipinski_violations']:
            modifications.append('Remove peripheral alkyl chains or bulky groups')
        
        if analysis['properties']['TPSA'] < 40:
            modifications.append('Add polar groups (OH, NH2, COOH) to increase TPSA')
        
        if analysis['properties']['Rotatable'] > 10:
            modifications.append('Replace flexible chains with rings')
        
        if not analysis['lipinski_violations']:
            modifications.append('Lead compound already drug-like - focus on potency')
        
        return modifications


def demo_fragment_based_design():
    """Demonstrate fragment-based drug design workflow."""
    
    print("=" * 70)
    print("FRAGMENT-BASED DRUG DESIGN DEMONSTRATION")
    print("=" * 70)
    
    # Example drug molecules for fragmentation
    example_drugs = {
        'Ibuprofen': 'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
        'Aspirin': 'CC(=O)Oc1ccccc1C(=O)O',
        'Caffeine': 'CN1C=NC2=C1C(=O)N(C(=O)N2C)C',
        'Paracetamol': 'CC(=O)Nc1ccc(O)cc1'
    }
    
    print("\n[1] Generating Fragment Library using BRICS...")
    print("-" * 70)
    
    generator = FragmentLibraryGenerator()
    smiles_list = list(example_drugs.values())
    
    fragment_library = generator.generate_fragment_library(smiles_list, method='brics')
    
    print(f"\nTotal fragments generated: {len(fragment_library)}")
    print(f"Valid drug-like fragments: {fragment_library['IsValid'].sum()}")
    
    # Show top fragments
    print("\nTop 5 Scored Fragments:")
    print(fragment_library[['SMILES', 'MolecularWeight', 'LogP', 'Score', 'IsValid']].head())
    
    # Analyze a lead compound
    print("\n" + "=" * 70)
    print("[2] Lead Compound Analysis")
    print("-" * 70)
    
    lead_compound = 'CC(C)Cc1ccc(cc1)C(C)C(=O)O'  # Ibuprofen
    
    optimizer = LeadOptimizer()
    analysis = optimizer.analyze_lead(lead_compound)
    
    print(f"\nLead Compound: {analysis['smiles']}")
    print(f"Scaffold: {analysis['scaffold']}")
    
    print("\nProperties:")
    for prop, value in analysis['properties'].items():
        print(f"  {prop}: {value:.2f}")
    
    print(f"\nLipinski Violations: {len(analysis['lipinski_violations'])}")
    if analysis['lipinski_violations']:
        for violation in analysis['lipinski_violations']:
            print(f"  - {violation}")
    else:
        print("  None - compound is drug-like!")
    
    print("\nOptimization Suggestions:")
    modifications = optimizer.suggest_modifications(lead_compound)
    for i, suggestion in enumerate(modifications, 1):
        print(f"  {i}. {suggestion}")
    
    print(f"\nFragments identified: {len(analysis['fragments'])}")
    for i, frag in enumerate(analysis['fragments'][:5], 1):
        print(f"  {i}. {frag}")
    
    # Save fragment library
    print("\n" + "=" * 70)
    print("[3] Saving Fragment Library...")
    print("-" * 70)
    
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'fragment_library.csv')
    fragment_library.to_csv(output_path, index=False)
    print(f"\nFragment library saved to: {output_path}")
    
    print("\n" + "=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)
    
    return fragment_library, analysis


def main():
    """Run the demonstration."""
    fragment_library, analysis = demo_fragment_based_design()
    
    print("\nSummary:")
    print(f"  Total fragments: {len(fragment_library)}")
    print(f"  Valid fragments: {fragment_library['IsValid'].sum()}")
    print(f"  Average fragment MW: {fragment_library['MolecularWeight'].mean():.1f}")
    print(f"  Lead optimization suggestions: {len(analysis['lipinski_violations']) + 1}")


if __name__ == "__main__":
    main()