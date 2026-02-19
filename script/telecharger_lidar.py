#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Téléchargeur de dalles LiDAR HD avec barre de progression
"""
import os
import sys
import requests
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import time

# Essayer d'importer tqdm pour la barre de progression
try:
    from tqdm import tqdm
    TQDM_DISPONIBLE = True
except ImportError:
    TQDM_DISPONIBLE = False
    print("Module 'tqdm' non trouvé - Installation automatique...")
    import subprocess
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])
        from tqdm import tqdm
        TQDM_DISPONIBLE = True
        print("Module 'tqdm' installé avec succès!\n")
    except:
        print("Impossible d'installer 'tqdm' - Continuation sans barre de progression\n")

def extraire_nom_fichier(url):
    """Extrait le nom de fichier depuis l'URL"""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if 'FILENAME' in params:
        return params['FILENAME'][0]
    if 'BBOX' in params:
        bbox = params['BBOX'][0].replace(',', '_')
        return f"dalle_{bbox}.tif"
    return None

def telecharger_dalle(url, dossier_sortie):
    """Télécharge une dalle LiDAR"""
    try:
        nom_fichier = extraire_nom_fichier(url)
        if not nom_fichier:
            return False, None, "Nom invalide"
        
        chemin_complet = os.path.join(dossier_sortie, nom_fichier)
        
        # Si le fichier existe déjà
        if os.path.exists(chemin_complet):
            taille = os.path.getsize(chemin_complet) / (1024 * 1024)
            return True, 0, f"Déjà présent ({taille:.1f} MB)"
        
        # Téléchargement
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        
        # Sauvegarde
        with open(chemin_complet, 'wb') as f:
            f.write(response.content)
        
        taille = os.path.getsize(chemin_complet) / (1024 * 1024)
        return True, taille, f"Téléchargé ({taille:.1f} MB)"
        
    except requests.exceptions.RequestException as e:
        return False, None, f"Erreur réseau"
    except Exception as e:
        return False, None, f"Erreur: {str(e)[:30]}"

def main():
    print("\n" + "=" * 80)
    print(" " * 20 + "TÉLÉCHARGEUR DE DALLES LIDAR HD - IGN")
    print("=" * 80 + "\n")
    
    # Lire les URLs
    fichier_urls = "dalles.txt"
    
    if not os.path.exists(fichier_urls):
        print(f"❌ ERREUR: Le fichier '{fichier_urls}' n'existe pas!")
        print(f"\nDossier actuel: {os.getcwd()}\n")
        return 1
    
    try:
        with open(fichier_urls, 'r', encoding='utf-8') as f:
            urls = [ligne.strip() for ligne in f if ligne.strip()]
    except Exception as e:
        print(f"❌ ERREUR lors de la lecture du fichier: {e}\n")
        return 1
    
    print(f"📊 Nombre de dalles à télécharger: {len(urls)}")
    
    # Créer le dossier de sortie
    dossier_sortie = "dalles_lidar"
    try:
        Path(dossier_sortie).mkdir(exist_ok=True)
        print(f"📁 Dossier de destination: {os.path.abspath(dossier_sortie)}")
    except Exception as e:
        print(f"❌ ERREUR: Impossible de créer le dossier: {e}\n")
        return 1
    
    print("\n" + "=" * 80)
    print("🚀 DÉMARRAGE DU TÉLÉCHARGEMENT")
    print("=" * 80)
    print("\n⚠️  Appuyez sur Ctrl+C pour interrompre\n")
    
    # Téléchargement
    reussies = 0
    echouees = 0
    taille_totale = 0
    debut = time.time()
    
    if TQDM_DISPONIBLE:
        # Avec barre de progression
        with tqdm(total=len(urls), 
                  desc="📥 Téléchargement", 
                  unit="dalle",
                  bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]') as pbar:
            
            for url in urls:
                succes, taille, message = telecharger_dalle(url, dossier_sortie)
                
                if succes:
                    reussies += 1
                    if taille:
                        taille_totale += taille
                    pbar.set_postfix_str(f"✅ {message}")
                else:
                    echouees += 1
                    pbar.set_postfix_str(f"❌ {message}")
                
                pbar.update(1)
                time.sleep(0.3)  # Pause pour le serveur
    else:
        # Sans barre de progression
        for i, url in enumerate(urls, 1):
            succes, taille, message = telecharger_dalle(url, dossier_sortie)
            
            if succes:
                reussies += 1
                if taille:
                    taille_totale += taille
                print(f"[{i}/{len(urls)}] ✅ {message}")
            else:
                echouees += 1
                print(f"[{i}/{len(urls)}] ❌ {message}")
            
            time.sleep(0.3)
    
    duree = time.time() - debut
    
    # Résumé final
    print("\n" + "=" * 80)
    print(" " * 30 + "📊 RÉSUMÉ DU TÉLÉCHARGEMENT")
    print("=" * 80)
    print(f"\n✅ Dalles téléchargées avec succès: {reussies}/{len(urls)}")
    print(f"❌ Dalles en erreur: {echouees}/{len(urls)}")
    print(f"💾 Taille totale téléchargée: {taille_totale:.1f} MB ({taille_totale/1024:.2f} GB)")
    print(f"⏱️  Durée totale: {duree/60:.1f} minutes ({duree/3600:.2f} heures)")
    
    if taille_totale > 0 and duree > 0:
        vitesse = taille_totale / duree
        print(f"⚡ Vitesse moyenne: {vitesse:.2f} MB/s")
    
    print(f"\n📁 Emplacement des fichiers:")
    print(f"   {os.path.abspath(dossier_sortie)}")
    print("\n" + "=" * 80)
    
    if echouees > 0:
        print("\n⚠️  Certains téléchargements ont échoué.")
        print("   Relancez le script pour télécharger les dalles manquantes.\n")
    
    return 0

if __name__ == "__main__":
    try:
        code_retour = main()
        print("\n" + "=" * 80)
        input("\n✅ Appuyez sur Entrée pour fermer cette fenêtre...")
        sys.exit(code_retour)
        
    except KeyboardInterrupt:
        print("\n\n" + "=" * 80)
        print("⚠️  TÉLÉCHARGEMENT INTERROMPU par l'utilisateur (Ctrl+C)")
        print("=" * 80)
        print("\nVous pouvez relancer le script pour reprendre.")
        print("Les dalles déjà téléchargées ne seront pas re-téléchargées.\n")
        input("Appuyez sur Entrée pour fermer cette fenêtre...")
        sys.exit(1)
        
    except Exception as e:
        print("\n\n" + "=" * 80)
        print("❌ ERREUR INATTENDUE")
        print("=" * 80)
        print(f"\nType: {type(e).__name__}")
        print(f"Message: {e}\n")
        input("Appuyez sur Entrée pour fermer cette fenêtre...")
        sys.exit(1)
