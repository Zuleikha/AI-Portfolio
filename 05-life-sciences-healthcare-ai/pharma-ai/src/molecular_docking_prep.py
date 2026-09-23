"""
Molecular Docking Preparation
==============================

This module provides tools for preparing molecules for molecular docking studies.
It includes methods for 3D structure generation, energy minimization, protonation,
and file format conversion.

Molecular docking is a computational technique used to predict the binding mode
and affinity of small molecules (ligands) to protein targets.

Author: Pharma AI Portfolio
Date: 2025
"""

from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors, Lipinski
from rdkit.Chem import rdMolTransforms, rdDistGeom
from rdkit.Chem import rdPartialCharges
from typing import Optional, List, Tuple
import os


class MolecularDockingPrep:
    """
    Tools for preparing ligands for molecular docking.

    This class provides methods for:
    - 3D conformation generation
    - Energy minimization
    - Protonation state assignment
    - File format conversion (PDB, MOL2, SDF)
    - Multiple conformer generation
    """

    def __init__(self, ph: float = 7.4):
        """
        Initialize MolecularDockingPrep.

        Args:
            ph: pH for protonation state (default: 7.4, physiological pH)
        """
        self.ph = ph
        self.ff = "MMFF94"  # Force field for minimization

    def prepare_ligand(self, smiles: str,
                      add_hydrogens: bool = True,
                      generate_3d: bool = True,
                      minimize: bool = True) -> Optional[Chem.Mol]:
        """
        Prepare a ligand molecule for docking.

        Args:
            smiles: SMILES string of molecule
            add_hydrogens: Add explicit hydrogens
            generate_3d: Generate 3D coordinates
            minimize: Perform energy minimization

        Returns:
            Prepared RDKit molecule object or None
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            print(f"Error: Invalid SMILES string: {smiles}")
            return None

        # Add hydrogens
        if add_hydrogens:
            mol = Chem.AddHs(mol)

        # Generate 3D coordinates
        if generate_3d:
            result = AllChem.EmbedMolecule(mol, randomSeed=42)
            if result != 0:
                print("Warning: 3D embedding failed, trying with random coordinates")
                AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=42)

        # Energy minimization
        if minimize and generate_3d:
            self.minimize_energy(mol)

        return mol

    def minimize_energy(self, mol: Chem.Mol,
                       max_iterations: int = 200,
                       force_field: str = "MMFF94") -> Tuple[int, float]:
        """
        Minimize the energy of a molecule using force field.

        Args:
            mol: RDKit molecule object with 3D coordinates
            max_iterations: Maximum number of minimization iterations
            force_field: Force field to use ('MMFF94' or 'UFF')

        Returns:
            Tuple of (convergence_flag, final_energy)
        """
        if mol.GetNumConformers() == 0:
            print("Warning: No conformers found. Generate 3D coordinates first.")
            return -1, 0.0

        if force_field.upper() == "MMFF94":
            # MMFF94 force field
            props = AllChem.MMFFGetMoleculeProperties(mol)
            if props is None:
                print("Warning: MMFF94 not applicable, falling back to UFF")
                return self.minimize_energy(mol, max_iterations, "UFF")

            ff = AllChem.MMFFGetMoleculeForceField(mol, props)
            ff.Initialize()
            convergence = ff.Minimize(maxIts=max_iterations)
            energy = ff.CalcEnergy()
        else:
            # UFF force field
            ff = AllChem.UFFGetMoleculeForceField(mol)
            convergence = ff.Minimize(maxIts=max_iterations)
            energy = ff.CalcEnergy()

        return convergence, energy

    def generate_conformers(self, mol: Chem.Mol,
                           num_conformers: int = 10,
                           minimize: bool = True,
                           rms_threshold: float = 0.5) -> int:
        """
        Generate multiple conformers for a molecule.

        Args:
            mol: RDKit molecule object
            num_conformers: Number of conformers to generate
            minimize: Minimize each conformer
            rms_threshold: RMS threshold for conformer pruning

        Returns:
            Number of conformers generated
        """
        # Ensure hydrogens are added
        if mol.GetNumAtoms() == mol.GetNumHeavyAtoms():
            mol = Chem.AddHs(mol)

        # Generate conformers
        conf_ids = AllChem.EmbedMultipleConfs(
            mol,
            numConfs=num_conformers,
            randomSeed=42,
            pruneRmsThresh=rms_threshold,
            useRandomCoords=True
        )

        if len(conf_ids) == 0:
            print("Warning: No conformers generated")
            return 0

        # Minimize conformers
        if minimize:
            for conf_id in conf_ids:
                props = AllChem.MMFFGetMoleculeProperties(mol)
                if props is not None:
                    ff = AllChem.MMFFGetMoleculeForceField(
                        mol, props, confId=conf_id
                    )
                    ff.Minimize()
                else:
                    ff = AllChem.UFFGetMoleculeForceField(mol, confId=conf_id)
                    ff.Minimize()

        return len(conf_ids)

    def calculate_conformer_energies(self, mol: Chem.Mol) -> List[float]:
        """
        Calculate energies for all conformers.

        Args:
            mol: RDKit molecule object with conformers

        Returns:
            List of energies for each conformer
        """
        energies = []

        for conf in mol.GetConformers():
            props = AllChem.MMFFGetMoleculeProperties(mol)
            if props is not None:
                ff = AllChem.MMFFGetMoleculeForceField(
                    mol, props, confId=conf.GetId()
                )
                energy = ff.CalcEnergy()
            else:
                ff = AllChem.UFFGetMoleculeForceField(mol, confId=conf.GetId())
                energy = ff.CalcEnergy()

            energies.append(energy)

        return energies

    def assign_partial_charges(self, mol: Chem.Mol,
                              method: str = "gasteiger") -> Chem.Mol:
        """
        Assign partial charges to atoms.

        Args:
            mol: RDKit molecule object
            method: Charge calculation method ('gasteiger' or 'mmff')

        Returns:
            Molecule with assigned charges
        """
        if method.lower() == "gasteiger":
            rdPartialCharges.ComputeGasteigerCharges(mol)
        elif method.lower() == "mmff":
            props = AllChem.MMFFGetMoleculeProperties(mol)
            if props is not None:
                # MMFF charges are computed during force field setup
                AllChem.MMFFGetMoleculeForceField(mol, props)
        else:
            print(f"Unknown charge method: {method}")

        return mol

    def get_lowest_energy_conformer(self, mol: Chem.Mol) -> int:
        """
        Get the ID of the lowest energy conformer.

        Args:
            mol: RDKit molecule object with conformers

        Returns:
            Conformer ID with lowest energy
        """
        energies = self.calculate_conformer_energies(mol)
        if not energies:
            return -1

        min_energy_idx = energies.index(min(energies))
        return mol.GetConformers()[min_energy_idx].GetId()

    def write_pdb_file(self, mol: Chem.Mol,
                      filename: str,
                      conf_id: int = -1) -> bool:
        """
        Write molecule to PDB file.

        Args:
            mol: RDKit molecule object
            filename: Output filename
            conf_id: Conformer ID (-1 for first conformer)

        Returns:
            True if successful
        """
        try:
            writer = Chem.PDBWriter(filename)
            writer.write(mol, confId=conf_id)
            writer.close()
            return True
        except Exception as e:
            print(f"Error writing PDB file: {e}")
            return False

    def write_sdf_file(self, mol: Chem.Mol,
                      filename: str,
                      conf_id: int = -1) -> bool:
        """
        Write molecule to SDF file.

        Args:
            mol: RDKit molecule object
            filename: Output filename
            conf_id: Conformer ID (-1 for first conformer)

        Returns:
            True if successful
        """
        try:
            writer = Chem.SDWriter(filename)
            writer.write(mol, confId=conf_id)
            writer.close()
            return True
        except Exception as e:
            print(f"Error writing SDF file: {e}")
            return False

    def write_mol2_file(self, mol: Chem.Mol,
                       filename: str,
                       conf_id: int = -1) -> bool:
        """
        MOL2 export is not supported by RDKit's built-in writers.

        Use Open Babel for this format::

            obabel input.sdf -O output.mol2

        Or install the Python bindings::

            conda install -c conda-forge openbabel

        Returns:
            False — always, to signal that no file was written.
        """
        print(f"MOL2 export skipped for {filename!r}: "
              "RDKit does not write MOL2. Use Open Babel instead.")
        return False

    def prepare_and_save(self, smiles: str,
                        output_prefix: str,
                        formats: List[str] = ['pdb', 'sdf']) -> dict:
        """
        Prepare a molecule and save in multiple formats.

        Args:
            smiles: SMILES string
            output_prefix: Prefix for output files
            formats: List of formats to save ('pdb', 'sdf', 'mol2')

        Returns:
            Dictionary with preparation statistics
        """
        # Prepare molecule
        mol = self.prepare_ligand(smiles)
        if mol is None:
            return {'success': False, 'error': 'Failed to prepare molecule'}

        # Generate conformers
        num_conformers = self.generate_conformers(mol, num_conformers=10)

        # Get lowest energy conformer
        lowest_conf_id = self.get_lowest_energy_conformer(mol)

        # Calculate energies
        energies = self.calculate_conformer_energies(mol)

        # Assign charges
        self.assign_partial_charges(mol)

        # Save in requested formats
        saved_files = []
        for fmt in formats:
            filename = f"{output_prefix}.{fmt}"

            if fmt == 'pdb':
                if self.write_pdb_file(mol, filename, conf_id=lowest_conf_id):
                    saved_files.append(filename)
            elif fmt == 'sdf':
                if self.write_sdf_file(mol, filename, conf_id=lowest_conf_id):
                    saved_files.append(filename)
            elif fmt == 'mol2':
                if self.write_mol2_file(mol, filename, conf_id=lowest_conf_id):
                    saved_files.append(filename)

        return {
            'success': True,
            'num_conformers': num_conformers,
            'lowest_energy_conf': lowest_conf_id,
            'min_energy': min(energies) if energies else None,
            'saved_files': saved_files
        }


def main():
    """Example usage of MolecularDockingPrep."""
    prep = MolecularDockingPrep()

    print("="*70)
    print("MOLECULAR DOCKING PREPARATION")
    print("="*70)

    # Example molecules
    examples = {
        'Aspirin': 'CC(=O)Oc1ccccc1C(=O)O',
        'Ibuprofen': 'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
        'Caffeine': 'CN1C=NC2=C1C(=O)N(C(=O)N2C)C'
    }

    for name, smiles in examples.items():
        print(f"\n{'='*70}")
        print(f"Preparing: {name}")
        print(f"SMILES: {smiles}")
        print(f"{'='*70}")

        # Prepare ligand
        mol = prep.prepare_ligand(smiles)
        if mol is None:
            continue

        print(f"[OK] 3D structure generated")
        print(f"[OK] Hydrogens added: {mol.GetNumAtoms()} total atoms")

        # Generate conformers
        num_conf = prep.generate_conformers(mol, num_conformers=10)
        print(f"[OK] Generated {num_conf} conformers")

        # Calculate energies
        energies = prep.calculate_conformer_energies(mol)
        if energies:
            print(f"[OK] Energy range: {min(energies):.2f} to {max(energies):.2f} kcal/mol")
            lowest_conf = prep.get_lowest_energy_conformer(mol)
            print(f"[OK] Lowest energy conformer: {lowest_conf}")

        # Assign charges
        prep.assign_partial_charges(mol)
        print(f"[OK] Partial charges assigned")

        # Save files
        output_prefix = name.lower().replace(' ', '_')
        result = prep.prepare_and_save(smiles, output_prefix, formats=['pdb', 'sdf'])

        if result['success']:
            print(f"\n[>>] Files saved:")
            for filename in result['saved_files']:
                print(f"   - {filename}")

    print(f"\n{'='*70}")
    print("Preparation complete!")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()