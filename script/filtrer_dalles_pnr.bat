@echo off
chcp 65001 >nul 2>&1
cls
color 0B
title Filtrage des Dalles LiDAR selon Emprise PNR

echo.
echo ================================================================================
echo              FILTRAGE DES DALLES LIDAR SELON EMPRISE PNR
echo ================================================================================
echo.
echo Ce script va :
echo   1. Analyser les dalles LiDAR dans le dossier dalles_lidar
echo   2. Identifier celles qui intersectent l'emprise du PNR
echo   3. Deplacer uniquement ces dalles dans dalles_lidar_pnr
echo.
echo ================================================================================
echo.
pause

echo.
echo [1/3] Verification de Python...
python --version 2>nul
if errorlevel 1 (
    color 0C
    echo.
    echo ERREUR: Python n'est pas installe !
    echo.
    pause
    exit /b 1
)
echo       OK
echo.

echo [2/3] Verification des fichiers...
if not exist "emprise_pnr.gpkg" (
    color 0C
    echo.
    echo ERREUR: Le fichier emprise_pnr.gpkg est introuvable !
    echo.
    echo Il doit etre dans: %CD%
    echo.
    pause
    exit /b 1
)
echo       OK - emprise_pnr.gpkg trouve
echo.

if not exist "dalles_lidar" (
    color 0C
    echo.
    echo ERREUR: Le dossier dalles_lidar est introuvable !
    echo.
    pause
    exit /b 1
)
echo       OK - dossier dalles_lidar trouve
echo.

if not exist "filtrer_dalles_pnr.py" (
    color 0C
    echo.
    echo ERREUR: Le fichier filtrer_dalles_pnr.py est introuvable !
    echo.
    pause
    exit /b 1
)
echo       OK - script Python trouve
echo.

echo [3/3] Installation des modules Python (peut prendre quelques minutes)...
echo       Installation de geopandas et shapely...
python -m pip install --quiet geopandas shapely 2>nul
if errorlevel 1 (
    echo       AVERTISSEMENT - Le script va essayer de les installer automatiquement
)
echo       OK
echo.

echo ================================================================================
echo                         LANCEMENT DE L'ANALYSE
echo ================================================================================
echo.

python filtrer_dalles_pnr.py

exit /b 0
