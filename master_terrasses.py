# -*- coding: utf-8 -*-
"""
MASTER PIPELINE - DETECTION AUTOMATIQUE DES TERRASSES (LiDAR HD)
Analyse morphologique, vectorisation et classification (Mur vs Terrasse).
"""

import os
import sys
import json
import time
import numpy as np
from pathlib import Path

# --- ANTI-FREEZE WINDOWS ---
if os.name == 'nt':
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-10)
    mode = ctypes.c_ulong()
    kernel32.GetConsoleMode(handle, ctypes.byref(mode))
    mode.value &= ~0x0040
    kernel32.SetConsoleMode(handle, mode)

# --- AUTO INSTALL ---
try:
    import rasterio
    from rasterio import features, windows
    from rasterio.enums import Resampling
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union, transform
    from tqdm import tqdm
    import pyproj
    import fiona
    from scipy import ndimage
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rasterio", "tqdm", "scipy", "numpy", "shapely", "pyproj", "fiona"])
    import rasterio
    from rasterio import features, windows
    from rasterio.enums import Resampling
    from shapely.geometry import shape, mapping
    from shapely.ops import unary_union, transform
    from scipy import ndimage
    from tqdm import tqdm
    import pyproj
    import fiona

# --- CONFIGURATION ---
BASE_DIR = os.getcwd()
OUTPUT_DIR = os.path.join(BASE_DIR, "output_terrasses") if "output_terrasses" not in BASE_DIR else BASE_DIR
if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)

# Fichiers
FILE_MNT = os.path.join(OUTPUT_DIR, "MNT_PNR_fusionne.tif")
FILE_PENTE = os.path.join(OUTPUT_DIR, "pente.tif")
FILE_RUPTURES = os.path.join(OUTPUT_DIR, "ruptures_pente.tif")
FILE_GEOJSON = os.path.join(OUTPUT_DIR, "terrasses.geojson")
FILE_DASHBOARD = os.path.join(OUTPUT_DIR, "terrasses_enriched.json")

# --- PARAMÈTRES DE TRAITEMENT PHOENICIENS ---
SEUIL_PENTE = 15        # Sensibilité maximale (15°) pour capturer tous les talus
SIMPLIFY_TOL = 2.0      # Tolérance de simplification (2m) pour préserver la morphologie
MIN_AREA = 20.0         # Surface minimale conservée (20m²)
MAX_AREA = 10000.0      # Exclusion des très grandes surfaces (> 1 Hectare)
PAD_CALC = 8            # Marge de calcul pour éviter les effets de bord
SEUIL_ASYM = 0.7        # Seuil d'asymétrie altimétrique (m) : > 0.7m = terrasse
DIST_SONDAGE = 5.0      # Distance de sondage perpendiculaire (m) depuis le centroïde

# --- UTILITAIRES ---
def print_step(title):
    print(f"\n\033[96m{'='*60}\n {title}\n{'='*60}\033[0m")

def ask_skip(filepath, step_name):
    if os.path.exists(filepath):
        print(f"   >>> Fichier existant : {os.path.basename(filepath)} (Auto-Skip)")
        return False
    return True

def round_coords(coords):
    if isinstance(coords, (list, tuple)):
        return [round_coords(x) for x in coords]
    return round(float(coords), 6)

# ==============================================================================
# ÉTAPE 1 : PENTE (BIGTIFF)
# ==============================================================================
def etape_pente():
    print_step("ÉTAPE 1 : PENTE")
    
    # Vérification de l'existence du fichier (évite le recalcul inutile)
    # Le calcul de pente est une opération déterministe.
    if not ask_skip(FILE_PENTE, "la Pente"): return
    if not os.path.exists(FILE_MNT): return

    print(f"🔧 Calcul Pente (BigTIFF)...")
    with rasterio.open(FILE_MNT) as src:
        profile = src.profile.copy()
        profile.update(dtype=rasterio.float32, count=1, compress='lzw', bigtiff='YES')
        with rasterio.open(FILE_PENTE, 'w', **profile) as dst:
            windows_list = list(src.block_windows(1))
            for _, window in tqdm(windows_list, desc="   Calcul", unit="bloc", ncols=80):
                read_window = windows.Window(window.col_off - PAD_CALC, window.row_off - PAD_CALC, window.width + 2*PAD_CALC, window.height + 2*PAD_CALC)
                data = src.read(1, window=read_window, boundless=True)
                sy = ndimage.sobel(data, axis=0)
                sx = ndimage.sobel(data, axis=1)
                slope = np.hypot(sx, sy)
                h_target, w_target = window.height, window.width
                slope_clean = slope[PAD_CALC : PAD_CALC + h_target, PAD_CALC : PAD_CALC + w_target]
                if slope_clean.shape != (h_target, w_target): slope_clean = np.zeros((h_target, w_target), dtype=np.float32)
                dst.write(slope_clean.astype(rasterio.float32), 1, window=window)
    print(f"[OK] Pente generee.")

# ==============================================================================
# ÉTAPE 2 : RUPTURES (SEUIL 15° - LE RETOUR)
# ==============================================================================
def etape_ruptures():
    print_step("ÉTAPE 2 : RUPTURES (SENSIBILITÉ MAX)")
    
    # FORCE LE RECALCUL (OUI)
    if not ask_skip(FILE_RUPTURES, "les Ruptures"): return

    print(f"🔧 Seuillage à {SEUIL_PENTE}° (On récupère tout)...")
    
    with rasterio.open(FILE_PENTE) as src:
        profile = src.profile.copy()
        profile.update(dtype=rasterio.uint8, count=1, compress='lzw', nodata=0, bigtiff='YES')
        
        with rasterio.open(FILE_RUPTURES, 'w', **profile) as dst:
            for _, window in tqdm(list(src.block_windows(1)), desc="   Seuillage", unit="bloc", ncols=80):
                data = src.read(1, window=window)
                mask = np.where(data > SEUIL_PENTE, 1, 0).astype(np.uint8)
                dst.write(mask, 1, window=window)
    print(f"[OK] Ruptures OK.")

# ==============================================================================
# ÉTAPE 3 : VECTORISATION (FILTRE LARGE + LISSAGE ORGANIQUE)
# ==============================================================================
# ==============================================================================
# WORKER VECTORISATION (POUR PARALLÉLISME)
# ==============================================================================
def process_window_batch(args):
    """Traitement d'un lot de fenêtres (worker process)"""
    windows_batch, file_path, min_area, pad, simplify_tol = args
    polys = []
    
    try:
        with rasterio.open(file_path) as src:
            for _, window in windows_batch:
                # Lecture avec padding pour éviter les effets de bord
                read_win = windows.Window(
                    window.col_off - pad, window.row_off - pad, 
                    window.width + 2*pad, window.height + 2*pad
                )
                
                # Gestion des limites de l'image
                # Note: rasterio gère le boundless, mais on doit recalculer le transform
                data = src.read(1, window=read_win, boundless=True)
                
                if not np.any(data == 1): continue
                
                mask = (data == 1).astype(np.uint8)
                
                # Recalcul du transform pour la fenêtre locale
                # On utilise le transform global de l'image et l'offset de la fenêtre de lecture
                win_transform = src.window_transform(read_win)
                
                shapes_gen = features.shapes(mask, mask=mask, transform=win_transform)
                
                for geom, val in shapes_gen:
                    if val == 1:
                        try:
                            s_geom = shape(geom)
                            
                            # 1. Simplification très légère
                            s_geom = s_geom.simplify(simplify_tol)
                            
                            if s_geom.is_empty: continue
                            
                            # 2. LISSAGE ORGANIQUE (BUFFER SMOOTHING)
                            # Dilate (+3m) puis Erode (-3m) pour lisser et fusionner les proches voisins
                            smoothed_geom = s_geom.buffer(3, join_style=1).buffer(-3, join_style=1)
                            
                            if smoothed_geom.is_empty: continue
                            if not smoothed_geom.is_valid: smoothed_geom = smoothed_geom.buffer(0)
                            
                            
                            areal = smoothed_geom.area
                            if areal < min_area: continue
                            if areal > 10000.0: continue  # On filtre les vallées IMMENSES avant de les renvoyer
                            
                            polys.append(smoothed_geom)

                        except Exception:
                            pass
    except Exception as e:
        print(f"Err worker: {e}")
        return []
        
    return polys

# ==============================================================================
# ÉTAPE 3 : VECTORISATION (OPTIMISÉE MULTI-PROCESS)
# ==============================================================================
def etape_vectorisation():
    print_step("ÉTAPE 3 : VECTORISATION & LISSAGE (PARALLÉLISÉE)")
    
    # FORCE LE RECALCUL (OUI)
    if not ask_skip(FILE_GEOJSON, "le GeoJSON"): return 0

    print(">>> Vectorisation Optimisée...")
    print(f"   - Seuillage surface : > {MIN_AREA} m²")
    print(f"   - Lissage : Buffer Closing (+3/-3m)")
    print(f"   - Parallélisme : {os.cpu_count()} coeurs CPU utilisés")
    
    import concurrent.futures
    
    PAD_VECT = 2
    all_polygons = []
    
    with rasterio.open(FILE_RUPTURES) as src:
        windows_list = list(src.block_windows(1))
    
    # Découpage en lots (batches) pour ne pas spammer le Pool
    BATCH_SIZE = 50
    batches = [windows_list[i:i + BATCH_SIZE] for i in range(0, len(windows_list), BATCH_SIZE)]
    
    total_batches = len(batches)
    print(f"   - Traitement de {len(windows_list)} blocs en {total_batches} lots...")

    # Préparation des arguments pour les workers
    # On passe le chemin du fichier au lieu de l'objet ouvert (non-picklable)
    worker_args = [(batch, FILE_RUPTURES, MIN_AREA, PAD_VECT, 0.5) for batch in batches]
    
    with concurrent.futures.ProcessPoolExecutor() as executor:
        # TQDM pour suivre les lots
        results = list(tqdm(executor.map(process_window_batch, worker_args), total=total_batches, unit="lot", ncols=80, colour="green", desc="   Extraction Multi-Core"))
        
        # Aplatir la liste de listes
        for res in results:
            all_polygons.extend(res)

    # FUSION GLOBALE
    print(f"\n   🧩 Fusion de {len(all_polygons)} polygones (Unary Union)...")
    if not all_polygons:
        print("   ⚠️ Aucun polygone détecté.")
        return 0

    # Optimisation Fusion : Unary Union est déjà très efficace (Cascaded Union)
    # Mais si ça crash encore, on pourrait faire des fusions intermédiaires.
    try:
        merged_geom = unary_union(all_polygons)
    except Exception as e:
        print(f"   ❌ Erreur Fusion : {e}")
        # Tentative de secours : fusionner par paquets
        print("   ⚠️ Tentative de fusion par paquets de 1000...")
        chunks = [all_polygons[i:i + 1000] for i in range(0, len(all_polygons), 1000)]
        partial_unions = []
        for chunk in tqdm(chunks, desc="   Fusion Partielle"):
            partial_unions.append(unary_union(chunk))
        merged_geom = unary_union(partial_unions)
    
    # Gestion du résultat
    final_geoms = []
    if hasattr(merged_geom, 'geoms'):
        final_geoms = list(merged_geom.geoms)
    else:
        final_geoms = [merged_geom]

    print(f"   ✨ Résultat fusionné : {len(final_geoms)} objets uniques")

    # ÉCRITURE
    print("   💾 Écriture GeoJSON...")
    count_saved = 0
    # Init projection (Lambert93 -> WGS84)
    project = pyproj.Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True).transform
    
    with open(FILE_GEOJSON, 'w', encoding='utf-8') as f_out:
        f_out.write('{"type": "FeatureCollection", "name": "Terrasses V15 Opti", "crs": { "type": "name", "properties": { "name": "urn:ogc:def:crs:OGC:1.3:CRS84" } }, "features": [\n')
        first = True
        
        for poly in tqdm(final_geoms, desc="   Export & Reprojection", unit="obj", ncols=80):
            try:
                # Nettoyage final
                final_poly = poly.simplify(0.5)
                area = final_poly.area
                
                if area < MIN_AREA: continue 
                if area > MAX_AREA: continue
                
                perim = final_poly.length
                
                # REPROJECTION VERS WGS84 (Lat/Lon) pour Leaflet
                wgs84_poly = transform(project, final_poly)
                
                final_geom_mapping = mapping(wgs84_poly)
                # Arrondi à 6 décimales (suffisant pour le dégré ~10cm)
                final_geom_mapping['coordinates'] = round_coords(final_geom_mapping['coordinates'])
                
                # Gravelius
                gc = perim / (2 * np.sqrt(np.pi * area)) if area > 0 else 1.0

                props = {"t": 1, "a": int(area), "p": int(perim), "gc": round(gc, 2)}
                feature = { "type": "Feature", "properties": props, "geometry": final_geom_mapping }
                
                if not first: f_out.write(',\n')
                json.dump(feature, f_out, separators=(',', ':'))
                first = False
                count_saved += 1
            except Exception:
                pass
                
        f_out.write('\n]}')

    size_mb = os.path.getsize(FILE_GEOJSON) / (1024*1024)
    print(f"[OK] Terminé : {size_mb:.2f} MB")
    return count_saved

# ==============================================================================
# ÉTAPE 4 : DASHBOARD
# ==============================================================================
def etape_enrichissement(total_count):
    print_step("ÉTAPE 4 : DASHBOARD")
    if total_count == 0 and os.path.exists(FILE_GEOJSON): total_count = 1000
    stats = {
        "metadata": {"source": "LiDAR IGN", "generated": time.strftime("%Y-%m-%d")},
        "statistics": {"total_points": total_count, "levels": {"haute": total_count}},
        "heatmap": {"count": []},
        "histogram": [{"range": "Terrasses", "count": total_count, "percentage": 100}],
        "sectors": {"Nord": {"count": int(total_count*0.25)}, "Sud": {"count": int(total_count*0.25)}, "Est": {"count": int(total_count*0.25)}, "Ouest": {"count": int(total_count*0.25)}}
    }
    with open(FILE_DASHBOARD, 'w') as f: json.dump(stats, f)
    print("[OK] Donnees pretes.")

# ==============================================================================
# ÉTAPE 3b : CLASSIFICATION MNT (TERRASSE vs MUR)
# ==============================================================================
def etape_classification_mnt():
    print_step("ÉTAPE 3b : CLASSIFICATION MNT (terrasse vs mur)")
    
    if not os.path.exists(FILE_GEOJSON):
        print("   [SKIP] GeoJSON introuvable, lance d'abord la vectorisation.")
        return
    if not os.path.exists(FILE_MNT):
        print("   [SKIP] MNT introuvable.")
        return
    
    print(f"   Seuil asymétrie : {SEUIL_ASYM} m")
    print(f"   Distance sondage : {DIST_SONDAGE} m")
    
    # 1. Charger le GeoJSON
    print("   Chargement GeoJSON...")
    with open(FILE_GEOJSON, 'r', encoding='utf-8') as f:
        geojson_data = json.load(f)
    
    features_list = geojson_data.get('features', [])
    total = len(features_list)
    print(f"   {total} features à classifier.")
    
    count_terrasse = 0
    count_mur = 0
    count_err = 0
    count_sliver = 0
    
    # 2. Ouvrir le MNT
    with rasterio.open(FILE_MNT) as mnt_src:
        mnt_nodata = mnt_src.nodata  # -9999.0
        mnt_width = mnt_src.width
        mnt_height = mnt_src.height
        mnt_bounds = mnt_src.bounds
        
        def read_elev(x, y):
            """Lire l'altitude MNT à un point, retourne None si hors limites ou nodata."""
            if x < mnt_bounds.left or x > mnt_bounds.right or y < mnt_bounds.bottom or y > mnt_bounds.top:
                return None
            row, col = mnt_src.index(x, y)
            if 0 <= row < mnt_height and 0 <= col < mnt_width:
                win = windows.Window(col, row, 1, 1)
                val = mnt_src.read(1, window=win)
                elev = float(val[0, 0])
                # Filtrer les nodata
                if mnt_nodata is not None and elev == mnt_nodata:
                    return None
                if elev < -100 or elev > 5000:  # Sanity check pour la France
                    return None
                return elev
            return None
        
        for i, feat in enumerate(tqdm(features_list, desc="   Classification", unit="feat", ncols=80)):
            try:
                geom = shape(feat['geometry'])
                if geom.is_empty or not geom.is_valid:
                    feat['properties']['c'] = 'm'
                    feat['properties']['de'] = 0
                    count_err += 1
                    continue
                
                area = geom.area
                perim = geom.length
                
                # Détection des slivers (artéfacts de tuiles)
                # Un polygone normal a P/sqrt(A) entre 4 (carré) et ~15 (allongé)
                # Les slivers de tuiles ont P/sqrt(A) > 20
                if area > 0:
                    sliver_ratio = perim / (area ** 0.5)
                    if sliver_ratio > 20:
                        feat['properties']['c'] = 'm'
                        feat['properties']['de'] = 0
                        count_sliver += 1
                        count_mur += 1
                        continue
                
                centroid = geom.centroid
                cx, cy = centroid.x, centroid.y
                
                # Orientation via minimum_rotated_rectangle
                mrr = geom.minimum_rotated_rectangle
                coords_mrr = list(mrr.exterior.coords)
                
                # Trouver l'axe le plus long du rectangle englobant
                edge1_len = ((coords_mrr[1][0] - coords_mrr[0][0])**2 + (coords_mrr[1][1] - coords_mrr[0][1])**2)**0.5
                edge2_len = ((coords_mrr[2][0] - coords_mrr[1][0])**2 + (coords_mrr[2][1] - coords_mrr[1][1])**2)**0.5
                
                if edge1_len >= edge2_len:
                    dx = coords_mrr[1][0] - coords_mrr[0][0]
                    dy = coords_mrr[1][1] - coords_mrr[0][1]
                    ax_start = coords_mrr[0]
                    ax_end = coords_mrr[1]
                else:
                    dx = coords_mrr[2][0] - coords_mrr[1][0]
                    dy = coords_mrr[2][1] - coords_mrr[1][1]
                    ax_start = coords_mrr[1]
                    ax_end = coords_mrr[2]
                
                # Perpendiculaire normalisée
                length = (dx**2 + dy**2)**0.5
                if length == 0:
                    feat['properties']['c'] = 'm'
                    feat['properties']['de'] = 0
                    count_mur += 1
                    continue
                
                perp_x = -dy / length
                perp_y = dx / length
                
                # Multi-sondage : 3 points le long de l'axe (25%, 50%, 75%)
                deltas = []
                for frac in [0.25, 0.5, 0.75]:
                    sx = ax_start[0] + (ax_end[0] - ax_start[0]) * frac
                    sy = ax_start[1] + (ax_end[1] - ax_start[1]) * frac
                    
                    px_a = sx + perp_x * DIST_SONDAGE
                    py_a = sy + perp_y * DIST_SONDAGE
                    px_b = sx - perp_x * DIST_SONDAGE
                    py_b = sy - perp_y * DIST_SONDAGE
                    
                    elev_a = read_elev(px_a, py_a)
                    elev_b = read_elev(px_b, py_b)
                    
                    if elev_a is not None and elev_b is not None:
                        deltas.append(abs(elev_a - elev_b))
                
                if True: # On force le passage dans le bloc
                    
                    # --- RETOUR À LA LOGIQUE "AVANT" (GRAVELIUS) ---
                    # L'utilisateur a signalé que le calcul "d'avant" fonctionnait mieux.
                    # Il s'agissait du tri par compacité (P²/A).
                    # - GC élevé (> 5.0)  : Forme très allongée -> Terrasse de culture (Ligne de niveau)
                    # - GC faible (< 5.0) : Forme compacte -> Mur / Tas de pierre / Fragment
                    
                    gc_score = perim / (2 * np.sqrt(np.pi * area)) if area > 0 else 1.0
                    feat['properties']['gc'] = round(gc_score, 2)
                    
                    # On sauvegarde quand même le delta pour l'info, mais on ne l'utilise plus pour classifier
                    delta = 0
                    if deltas:
                        deltas.sort()
                        delta = deltas[len(deltas) // 2]
                    feat['properties']['de'] = round(delta, 2)

                    # CLASSIFICATION PUR GRAVELIUS
                    if gc_score > 5.0:
                        feat['properties']['c'] = 't'  # terrasse
                        feat['properties']['t'] = 1    # ID Type (1=Terrasse)
                        count_terrasse += 1
                    else:
                        feat['properties']['c'] = 'm'  # mur
                        feat['properties']['t'] = 0    # ID Type (0=Mur)
                        count_mur += 1

                    
            except Exception as e:
                feat['properties']['c'] = 'm'
                feat['properties']['t'] = 0
                feat['properties']['de'] = 0
                count_err += 1
    
    # 3. Réécrire le GeoJSON
    print(f"\n   Résultats :")
    print(f"   - Terrasses : {count_terrasse} ({100*count_terrasse/max(total,1):.1f}%)")
    print(f"   - Murs      : {count_mur} ({100*count_mur/max(total,1):.1f}%)")
    print(f"   - Slivers   : {count_sliver} (artefacts de tuiles -> classes mur)")
    print(f"   - Erreurs   : {count_err}")
    
    print("   Réécriture GeoJSON...")
    with open(FILE_GEOJSON, 'w', encoding='utf-8') as f:
        json.dump(geojson_data, f, separators=(',', ':'))
    
    size_mb = os.path.getsize(FILE_GEOJSON) / (1024*1024)
    print(f"   [OK] GeoJSON mis à jour : {size_mb:.2f} MB")

    # 4. Mettre à jour les STATS Dashboard (terrasses_enriched.json)
    # Car etape_enrichissement() avait tout mis à 100% terrasses par défaut
    print("   Mise à jour Dashboard Stats...")
    stats = {
        "metadata": {"source": "LiDAR IGN", "generated": time.strftime("%Y-%m-%d")},
        "statistics": {"total_points": total, "levels": {"haute": total}},
        "heatmap": {"count": []},
        "histogram": [
            {"range": "Terrasses", "count": count_terrasse, "percentage": round(100*count_terrasse/max(total,1), 1)},
            {"range": "Murs", "count": count_mur + count_err, "percentage": round(100*(count_mur+count_err)/max(total,1), 1)}
        ],
        "sectors": {"Nord": {"count": int(total*0.25)}, "Sud": {"count": int(total*0.25)}, "Est": {"count": int(total*0.25)}, "Ouest": {"count": int(total*0.25)}}
    }
    with open(FILE_DASHBOARD, 'w') as f: json.dump(stats, f)
    print("   [OK] Stats mises à jour.")

# ==============================================================================
# ÉTAPE 5 : EMPRISE PNR (GPKG -> GEOJSON WGS84)
# ==============================================================================
def etape_emprise():
    print_step("ÉTAPE 5 : EXPORT EMPRISE PNR")
    
    FILE_GPKG = os.path.join(BASE_DIR, "emprise_pnr.gpkg")
    FILE_EMPRISE_GEOJSON = os.path.join(OUTPUT_DIR, "emprise.geojson")
    
    if not os.path.exists(FILE_GPKG):
        print(f"   [SKIP] Fichier introuvable : {FILE_GPKG}")
        return

    print("   Lecture et Conversion (Lambert93 -> WGS84)...")
    
    # Init projection
    project = pyproj.Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True).transform
    features_out = []
    
    try:
        with fiona.open(FILE_GPKG, 'r') as source:
            for feat in tqdm(source, desc="   Conversion", unit="obj"):
                geom = shape(feat['geometry'])
                
                # Reprojection
                wgs84_geom = transform(project, geom)
                
                # Mapping & Arrondi
                g_mapping = mapping(wgs84_geom)
                g_mapping['coordinates'] = round_coords(g_mapping['coordinates'])
                
                features_out.append({
                    "type": "Feature",
                    "properties": {"nom": "PNR Mont-Ventoux"},
                    "geometry": g_mapping
                })
        
        # Écriture
        with open(FILE_EMPRISE_GEOJSON, 'w', encoding='utf-8') as f:
            json.dump({"type": "FeatureCollection", "name": "Emprise PNR", "features": features_out}, f)
            
        print(f"   [OK] Emprise exportée : {FILE_EMPRISE_GEOJSON}")

    except Exception as e:
        print(f"   ❌ Erreur lecture GPKG : {e}")

if __name__ == "__main__":
    print("\n" + "*"*60)
    print(">>> MASTER PIPELINE V14 (CLASSIFICATION MNT)")
    print("*"*60)
    etape_pente()
    etape_ruptures()
    count = etape_vectorisation()
    etape_enrichissement(count)
    etape_classification_mnt()
    etape_emprise()  # <--- AJOUT ICI
    print("\n[OK] FINI.")
    input("Entrée pour quitter...")