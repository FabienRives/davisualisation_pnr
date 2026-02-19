@echo off
chcp 65001 >nul
cls
color 0A
title TRAITEMENT COMPLET - PNR VENTOUX

echo.
echo ====================================================
echo    LANCEMENT DU PIPELINE COMPLET
echo ====================================================
echo.
echo Ce script va verifier chaque etape et generer
echo les fichiers pour le Dashboard Highcharts.
echo.

python master_terrasses.py

echo.
pause