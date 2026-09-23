load data/protein/dhfr.pdb, dhfr

hide everything
show cartoon, dhfr
color grey70, dhfr

select active_site, resi 27+31+32+94+115
show sticks, active_site
color red, active_site

show surface, dhfr
set transparency, 0.35

zoom active_site, 15

ray 2400,1800
png images/structures/protein/dhfr_active_site_clean.png, dpi=300
