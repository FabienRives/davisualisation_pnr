#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour filtrer et déplacer les dalles LiDAR qui intersectent l'emprise du PNR
"""
import os
import sys
import shutil
from pathlib import Path

# Installation automatique des dépendances si nécessaire
try:
    import geopandas as gpd
    from shapely.geometry import box
except ImportError:
    print("Installation des modules nécessaires (geopandas, shapely)...")
    print("Cela peut prendre quelques minutes...\n")
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "geopandas", "shapely"])
        import geopandas as gpd
        from shapely.geometry import box
        print("✅ Modules installés avec succès!\n")
    except Exception as e:
        print(f"❌ Erreur lors de l'installation des modules: {e}")
        print("\nInstallez manuellement avec: pip install geopandas shapely")
        input("\nAppuyez sur Entrée pour fermer...")
        sys.exit(1)

try:
    from tqdm import tqdm
    TQDM_DISPONIBLE = True
except ImportError:
    TQDM_DISPONIBLE = False

def extraire_bbox_du_nom(nom_fichier):
    """
    Extrait les coordonnées BBOX depuis le nom du fichier LiDAR
    Exemple: LHD_FXX_0865_6363_MNT_O_0M50_LAMB93_IGN69.tif
    Format attendu: LHD_FXX_XMIN_YMIN_...
    """
    try:
        parties = nom_fichier.replace('.tif', '').split('_')
        
        # Le nom contient les coordonnées en kilomètres
        # Format: LHD_FXX_0865_6363 -> X=865000, Y=6363000
        x_km = int(parties[2])
        y_km = int(parties[3])
        
        # Convertir en mètres et créer la BBOX (dalle de 1km x 1km)
        xmin = x_km * 1000
        ymin = y_km * 1000
        xmax = xmin + 1000
        ymax = ymin + 1000
        
        return box(xmin, ymin, xmax, ymax)
    except Exception as e:
        print(f"⚠️  Impossible d'extraire BBOX de {nom_fichier}: {e}")
        return None

def main():
    print("\n" + "=" * 80)
    print(" " * 15 + "FILTRE DES DALLES LIDAR SELON EMPRISE PNR")
    print("=" * 80 + "\n")
    
    # Chemins
    emprise_path = r"C:\Users\fafou\Desktop\Semaine_web_data\Datavisualisation\_PNR_geodatavisualisation\LIDAR\emprise_pnr.gpkg"
    dalles_source = r"C:\Users\fafou\Desktop\Semaine_web_data\Datavisualisation\_PNR_geodatavisualisation\LIDAR\dalles_lidar"
    dalles_dest = r"C:\Users\fafou\Desktop\Semaine_web_data\Datavisualisation\_PNR_geodatavisualisation\LIDAR\dalles_lidar_pnr"
    
    # Si on est sur Linux/Mac (pour les tests), utiliser les chemins relatifs
    if not os.path.exists(emprise_path):
        emprise_path = "emprise_pnr.gpkg"
        dalles_source = "dalles_lidar"
        dalles_dest = "dalles_lidar_pnr"
    
    print(f"📁 Dossier source: {dalles_source}")
    print(f"📁 Dossier destination: {dalles_dest}")
    print(f"🗺️  Emprise PNR: {emprise_path}\n")
    
    # Vérifier que l'emprise existe
    if not os.path.exists(emprise_path):
        print(f"❌ ERREUR: Le fichier emprise_pnr.gpkg n'existe pas!")
        print(f"   Cherché dans: {os.path.abspath(emprise_path)}")
        return 1
    
    # Vérifier que le dossier source existe
    if not os.path.exists(dalles_source):
        print(f"❌ ERREUR: Le dossier {dalles_source} n'existe pas!")
        return 1
    
    # Charger l'emprise PNR
    print("📥 Chargement de l'emprise PNR...")
    try:
        emprise_gdf = gpd.read_file(emprise_path)
        
        # Vérifier le système de coordonnées
        print(f"   Système de coordonnées: {emprise_gdf.crs}")
        
        # S'assurer qu'on est en Lambert 93 (EPSG:2154)
        if emprise_gdf.crs is None:
            print("   ⚠️  Aucun CRS défini, on suppose Lambert 93 (EPSG:2154)")
            emprise_gdf.set_crs("EPSG:2154", inplace=True)
        elif emprise_gdf.crs.to_epsg() != 2154:
            print(f"   🔄 Reprojection de {emprise_gdf.crs} vers EPSG:2154...")
            emprise_gdf = emprise_gdf.to_crs("EPSG:2154")
        
        # Unifier les géométries en une seule
        emprise_union = emprise_gdf.unary_union
        
        # Afficher les limites de l'emprise
        bounds = emprise_gdf.total_bounds
        print(f"   Limites de l'emprise:")
        print(f"     X: {bounds[0]:.0f} à {bounds[2]:.0f} m")
        print(f"     Y: {bounds[1]:.0f} à {bounds[3]:.0f} m")
        print(f"   ✅ Emprise chargée avec succès!\n")
        
    except Exception as e:
        print(f"❌ ERREUR lors du chargement de l'emprise: {e}")
        return 1
    
    # Lister les dalles .tif
    print("📋 Analyse des dalles LiDAR...")
    fichiers_tif = [f for f in os.listdir(dalles_source) if f.endswith('.tif')]
    print(f"   Nombre total de dalles trouvées: {len(fichiers_tif)}\n")
    
    if len(fichiers_tif) == 0:
        print("⚠️  Aucune dalle .tif trouvée dans le dossier source!")
        return 1
    
    # Créer le dossier de destination
    Path(dalles_dest).mkdir(exist_ok=True)
    print(f"✅ Dossier de destination créé: {os.path.abspath(dalles_dest)}\n")
    
    # Analyser chaque dalle
    print("🔍 Analyse des intersections avec l'emprise PNR...\n")
    
    dalles_a_deplacer = []
    dalles_hors_emprise = []
    dalles_erreur = []
    
    iterateur = tqdm(fichiers_tif, desc="Analyse", unit="dalle") if TQDM_DISPONIBLE else fichiers_tif
    
    for fichier in iterateur:
        bbox = extraire_bbox_du_nom(fichier)
        
        if bbox is None:
            dalles_erreur.append(fichier)
            continue
        
        # Vérifier l'intersection
        if bbox.intersects(emprise_union):
            dalles_a_deplacer.append(fichier)
        else:
            dalles_hors_emprise.append(fichier)
    
    # Afficher le résumé de l'analyse
    print("\n" + "=" * 80)
    print(" " * 25 + "📊 RÉSULTAT DE L'ANALYSE")
    print("=" * 80)
    print(f"\n✅ Dalles qui intersectent l'emprise PNR: {len(dalles_a_deplacer)}")
    print(f"❌ Dalles hors emprise PNR: {len(dalles_hors_emprise)}")
    print(f"⚠️  Dalles avec erreur d'analyse: {len(dalles_erreur)}")
    print(f"\n📦 Total analysé: {len(fichiers_tif)} dalles")
    
    if len(dalles_erreur) > 0:
        print(f"\n⚠️  Dalles avec erreur:")
        for dalle in dalles_erreur[:10]:
            print(f"   - {dalle}")
        if len(dalles_erreur) > 10:
            print(f"   ... et {len(dalles_erreur) - 10} autres")
    
    # Demander confirmation pour le déplacement
    if len(dalles_a_deplacer) == 0:
        print("\n⚠️  Aucune dalle à déplacer!")
        return 0
    
    print("\n" + "=" * 80)
    print(f"📦 {len(dalles_a_deplacer)} dalles vont être DÉPLACÉES vers:")
    print(f"   {os.path.abspath(dalles_dest)}")
    print("=" * 80)
    
    try:
        reponse = input("\n▶️  Voulez-vous continuer ? (o/n) : ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n❌ Opération annulée")
        return 0
    
    if reponse not in ['o', 'oui', 'y', 'yes']:
        print("❌ Opération annulée")
        return 0
    
    # Déplacer les dalles
    print("\n📦 Déplacement des dalles en cours...\n")
    
    deplacees = 0
    erreurs_deplacement = 0
    
    iterateur = tqdm(dalles_a_deplacer, desc="Déplacement", unit="dalle") if TQDM_DISPONIBLE else dalles_a_deplacer
    
    for fichier in iterateur:
        source = os.path.join(dalles_source, fichier)
        dest = os.path.join(dalles_dest, fichier)
        
        try:
            shutil.move(source, dest)
            deplacees += 1
        except Exception as e:
            erreurs_deplacement += 1
            if not TQDM_DISPONIBLE:
                print(f"❌ Erreur avec {fichier}: {e}")
    
    # Résumé final
    print("\n" + "=" * 80)
    print(" " * 30 + "✅ OPÉRATION TERMINÉE")
    print("=" * 80)
    print(f"\n📦 Dalles déplacées avec succès: {deplacees}")
    print(f"❌ Erreurs lors du déplacement: {erreurs_deplacement}")
    print(f"\n📁 Les dalles sont maintenant dans:")
    print(f"   {os.path.abspath(dalles_dest)}")
    print(f"\n📁 Il reste {len(dalles_hors_emprise)} dalles hors emprise dans:")
    print(f"   {os.path.abspath(dalles_source)}")
    print("\n" + "=" * 80)
    
    return 0

if __name__ == "__main__":
    try:
        code_retour = main()
        print("\n" + "=" * 80)
        input("\n✅ Appuyez sur Entrée pour fermer cette fenêtre...")
        sys.exit(code_retour)
        
    except KeyboardInterrupt:
        print("\n\n" + "=" * 80)
        print("⚠️  OPÉRATION INTERROMPUE par l'utilisateur (Ctrl+C)")
        print("=" * 80)
        input("\nAppuyez sur Entrée pour fermer cette fenêtre...")
        sys.exit(1)
        
    except Exception as e:
        print("\n\n" + "=" * 80)
        print("❌ ERREUR INATTENDUE")
        print("=" * 80)
        print(f"\nType: {type(e).__name__}")
        print(f"Message: {e}\n")
        import traceback
        traceback.print_exc()
        input("\nAppuyez sur Entrée pour fermer cette fenêtre...")
        sys.exit(1)
