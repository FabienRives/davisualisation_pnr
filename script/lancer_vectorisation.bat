@echo off
chcp 65001 >nul
cls
:: Couleur Vert Matrix
color 0A
title TRAITEMENT TERRASSES - RUNNING...

echo.
echo Lancement du processus de vectorisation...
echo.

:: Lance le script Python
python vectoriser_classes.py

:: Petite pause SEULEMENT à la fin pour que tu puisses voir le résultat "TERMINÉ"
echo.
pause