@echo off
chcp 65001 >nul 2>&1
cls
color 0A
title Pipeline Optimisé - Terrasses Dashboard

echo.
echo ================================================================================
echo              PIPELINE OPTIMISE - TERRASSES DASHBOARD HIGHCHARTS
echo ================================================================================
echo.
echo Ce pipeline part des fichiers intermediaires existants :
echo   - MNT_PNR_fusionne.tif
echo   - pente.tif
echo   - ruptures_pente.tif
echo.
echo Et genere :
echo   - terrasses_heatmap.tif
echo   - terrasses.geojson
echo   - terrasses_enriched.json
echo   - Dashboard Highcharts pret !
echo.
echo ================================================================================
pause

echo.
echo [Verification] Python...
python --version 2>nul
if errorlevel 1 (
    echo ERREUR: Python n'est pas installe
    pause
    exit /b 1
)
echo OK
echo.

echo [Verification] Fichiers intermediaires...
set "DOSSIER=C:\Users\fafou\Desktop\Semaine_web_data\Datavisualisation\_PNR_geodatavisualisation\output_terrasses"

if not exist "%DOSSIER%\ruptures_pente.tif" (
    echo ERREUR: Le fichier ruptures_pente.tif est introuvable
    echo.
    echo Chemin attendu: %DOSSIER%\ruptures_pente.tif
    echo.
    pause
    exit /b 1
)
echo OK
echo.

echo [Installation] Modules Python...
python -m pip install --quiet rasterio scipy tqdm numpy 2>nul
echo OK
echo.

echo ================================================================================
echo                         LANCEMENT DU PIPELINE
echo ================================================================================
echo.

python pipeline_optimise.py

echo.
echo ================================================================================
echo                              TERMINE
echo ================================================================================
echo.

if exist "%DOSSIER%\terrasses_enriched.json" (
    echo.
    echo SUCCESS ! Fichiers generes :
    echo   - terrasses_heatmap.tif
    echo   - terrasses.geojson
    echo   - terrasses_enriched.json
    echo.
    echo Vous pouvez maintenant ouvrir :
    echo   dashboard_datavisualisation.html
    echo.
    echo Via un serveur HTTP :
    echo   cd "%DOSSIER%"
    echo   python -m http.server 8000
    echo.
    echo Puis ouvrir : http://localhost:8000/dashboard_datavisualisation.html
    echo.
) else (
    echo.
    echo ATTENTION : Les fichiers n'ont pas ete generes
    echo.
)

pause
