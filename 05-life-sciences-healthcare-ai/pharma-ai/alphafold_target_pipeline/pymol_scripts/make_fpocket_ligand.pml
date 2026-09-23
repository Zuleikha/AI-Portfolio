load data/protein/dhfr.pdb, dhfr
load data/protein/dhfr_out/pockets/pocket14_atm.pdb, pocket14
load output/docking/trimethoprim_out.pdbqt, ligand

hide everything
show cartoon, dhfr
color grey70, dhfr

show spheres, pocket14
color green, pocket14
set sphere_scale, 0.25, pocket14

show sticks, ligand
color yellow, ligand

set transparency, 0.35

zoom ligand, 20
ray 2400,1800
png images/structures/protein/dhfr_fpocket_ligand_overlay.png, dpi=300
