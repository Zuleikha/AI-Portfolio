load data/protein/dhfr.pdb, dhfr
load data/protein/dhfr_out/pockets/pocket14_atm.pdb, pocket14

hide everything
show cartoon, dhfr
color grey70, dhfr

show spheres, pocket14
color green, pocket14
set sphere_scale, 0.25, pocket14

set transparency, 0.3

zoom pocket14, 15
ray 2400,1800
png images/structures/protein/dhfr_fpocket_clean.png, dpi=300
