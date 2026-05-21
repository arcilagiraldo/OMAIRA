@echo off
title OMAIRA v4 — Sistema de Gestión Inteligente de Riesgos
color 0A
echo.
echo  ================================================
echo   OMAIRA v4 — Iniciando...
echo   Observacion, Monitoreo, Analisis e Inteligencia
echo   de Riesgos y Amenazas
echo  ================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python no esta instalado.
    echo.
    echo  Instala Python desde: https://www.python.org/downloads/
    echo  Marca la casilla "Add Python to PATH" al instalar.
    echo.
    pause
    exit /b 1
)

echo  [OK] Python encontrado
echo  [..] Iniciando OMAIRA...
echo.

cd /d "%~dp0"
python servidor.py

pause
