import rasterio
from rasterio import features
from rasterio.enums import Resampling
import json
import numpy as np
import os
import sys
import time

# Installation silencieuse de tqdm si absent
try:
    from tqdm import tqdm
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])
    from tqdm import tqdm

# ================= CONFIGURATION =================
INPUT_FILE = r"C:\Users\fafou\Desktop\Semaine_web_data\Datavisualisation\_PNR_geodatavisualisation\output_terrasses\ruptures_pente.tif"
OUTPUT_GEOJSON = r"C:\Users\fafou\Desktop\Semaine_web_data\Datavisualisation\_PNR_geodatavisualisation\output_terrasses\terrasses_classees.geojson"

SEUIL_BAS = 15
SEUIL_HAUT = 45
SCALE_FACTOR = 0.25 
# =================================================

def main():
    # En-tête stylé
    print("\n" + "="*60)
    print("      🚀 VECTORISATION HAUTE PERFORMANCE - PNR VENTOUX")
    print("="*60 + "\n")
    
    if not os.path.exists(INPUT_FILE):
        print(f"❌ ERREUR: Fichier introuvable : {INPUT_FILE}")
        return

    # --- ÉTAPE 1 : LECTURE (Rapide) ---
    print("1️⃣  LECTURE ET LISSAGE DE L'IMAGE...")
    with rasterio.open(INPUT_FILE) as src:
        new_height = int(src.height * SCALE_FACTOR)
        new_width = int(src.width * SCALE_FACTOR)
        
        # On lit l'image
        data = src.read(
            1,
            out_shape=(new_height, new_width),
            resampling=Resampling.bilinear
        )
        
        transform = src.transform * src.transform.scale(
            (src.width / new_width),
            (src.height / new_height)
        )
    print(f"    ✅ Image chargée en mémoire ({new_width}x{new_height} px)\n")

    # --- ÉTAPE 2 : CLASSIFICATION (Instantané) ---
    print("2️⃣  CLASSIFICATION DES ZONES...")
    carte_classes = np.zeros_like(data, dtype=np.uint8)
    carte_classes[(data >= SEUIL_BAS) & (data < SEUIL_HAUT)] = 2
    carte_classes[(data >= SEUIL_HAUT)] = 3
    print("    ✅ Classification terminée\n")

    # --- ÉTAPE 3 : VECTORISATION (Barre de progression 1) ---
    print("3️⃣  VECTORISATION DES FORMES")
    
    # On prépare le générateur
    shapes = features.shapes(carte_classes, transform=transform)
    
    valid_features = []
    
    # On utilise tqdm sans 'total' car on ne sait pas combien il y en a, 
    # mais ça montre la vitesse et le compteur qui défile !
    with tqdm(desc="    ⚡ Calcul", unit=" poly", colour="cyan", ncols=100) as pbar:
        for geometry, class_value in shapes:
            val = int(class_value)
            
            if val == 0: continue
            
            if val == 2:
                props = {"classe": "Probable", "val": 2, "color": "#F59E0B"}
            elif val == 3:
                props = {"classe": "Terrasse", "val": 3, "color": "#7C3AED"}
                
            valid_features.append({
                "type": "Feature",
                "properties": props,
                "geometry": geometry
            })
            pbar.update(1)
            
    num_features = len(valid_features)
    print(f"    ✅ {num_features} formes détectées.\n")

    # --- ÉTAPE 4 : SAUVEGARDE STREAMING (Barre de progression 2) ---
    # C'est LA nouveauté : on écrit le fichier ligne par ligne pour avoir une barre
    print("4️⃣  ÉCRITURE DU FICHIER GEOJSON")
    
    with open(OUTPUT_GEOJSON, 'w', encoding='utf-8') as f:
        # Écriture de l'en-tête manuellement
        f.write('{"type": "FeatureCollection", ')
        f.write('"name": "Terrasses Classifiées", ')
        f.write('"crs": { "type": "name", "properties": { "name": "urn:ogc:def:crs:EPSG::2154" } }, ')
        f.write('"features": [')
        
        # Boucle d'écriture avec barre de progression
        # Cette fois on connait le total, donc la barre sera pourcentage (0% -> 100%)
        for i, feature in enumerate(tqdm(valid_features, desc="    💾 Sauvegarde", unit=" obj", colour="green", ncols=100)):
            if i > 0:
                f.write(',') # Virgule entre les objets
            json.dump(feature, f)
            
        # Fermeture du JSON
        f.write(']}')

    print("\n" + "="*60)
    print("✅ TERMINÉ ! DASHBOARD PRÊT À ÊTRE OUVERT.")
    print("="*60)

if __name__ == "__main__":
    main()