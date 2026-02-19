@echo off
chcp 65001 >nul 2>&1
cls
color 0A
title Telechargeur LiDAR HD

echo.
echo ================================================================================
echo                    TELECHARGEUR DE DALLES LIDAR HD - IGN
echo ================================================================================
echo.
echo Dossier de travail: %CD%
echo.

REM Verifier Python
echo [1/4] Verification de Python...
python --version 2>nul
if errorlevel 1 (
    color 0C
    echo.
    echo ERREUR: Python n'est pas installe !
    echo.
    echo Installez Python depuis: https://www.python.org/downloads/
    echo Cochez "Add Python to PATH" lors de l'installation
    echo.
    pause
    exit /b 1
)
echo       OK - Python detecte
echo.

REM Verifier dalles.txt
echo [2/4] Verification du fichier dalles.txt...
if not exist "dalles.txt" (
    color 0C
    echo.
    echo ERREUR: Le fichier dalles.txt est introuvable !
    echo.
    echo Placez dalles.txt dans: %CD%
    echo.
    pause
    exit /b 1
)
echo       OK - dalles.txt trouve
echo.

REM Verifier le script Python
echo [3/4] Verification du script Python...
if not exist "telecharger_lidar.py" (
    color 0C
    echo.
    echo ERREUR: Le fichier telecharger_lidar.py est introuvable !
    echo.
    echo Placez telecharger_lidar.py dans: %CD%
    echo.
    pause
    exit /b 1
)
echo       OK - telecharger_lidar.py trouve
echo.

REM Installer les dependances
echo [4/4] Installation des modules Python...
python -m pip install --quiet requests tqdm
if errorlevel 1 (
    echo       AVERTISSEMENT - Probleme d'installation (le script va quand meme essayer)
) else (
    echo       OK - Modules installes
)
echo.

echo ================================================================================
echo                         LANCEMENT DU TELECHARGEMENT
echo ================================================================================
echo.

REM Lancer le script
python telecharger_lidar.py

REM Le script Python gere lui-meme la pause finale
exit /b 0
