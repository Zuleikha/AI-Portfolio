# visualize_molecules.py

from rdkit import Chem
from rdkit.Chem import Draw  # ✅ import before using Draw
from rdkit import RDLogger

# (optional) turn off RDKit warnings
RDLogger.DisableLog('rdApp.*')

# Create molecules
aspirin   = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
caffeine  = Chem.MolFromSmiles("CN1C=NC2=C1C(=O)N(C(=O)N2C)C")
ibuprofen = Chem.MolFromSmiles("CC(C)Cc1ccc(cc1)C(C)C(=O)O")

# Draw a single molecule (aspirin)
img = Draw.MolToImage(aspirin, size=(300, 300))
img.save("aspirin.png")
print("Saved aspirin.png!")

# Draw multiple molecules in a grid
molecules = [aspirin, caffeine, ibuprofen]
labels = ["Aspirin", "Caffeine", "Ibuprofen"]

grid = Draw.MolsToGridImage(
    molecules, molsPerRow=3, subImgSize=(300, 300), legends=labels
)
grid.save("three_drugs.png")
print("Saved three_drugs.png!")
