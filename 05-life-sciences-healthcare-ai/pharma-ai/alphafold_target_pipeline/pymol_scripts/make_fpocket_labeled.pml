load data/protein/dhfr.pdb, dhfr
load data/protein/dhfr_out/pockets/pocket14_atm.pdb, pocket14

hide everything
show cartoon, dhfr
color grey70, dhfr

show spheres, pocket14
color green, pocket14
set sphere_scale, 0.25, pocket14

label pocket14 and name CA, "Pocket 14"
set label_color, white
set label_size, 14

set transparency, 0.3
zoom pocket14, 15

ray 2400,1800
png images/structures/protein/dhfr_fpocket_labeled.png, dpi=300
