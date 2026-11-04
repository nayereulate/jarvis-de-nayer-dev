@echo off
cd /d "%~dp0"
title Instalar Jarvis
echo === Instalando Jarvis ===
where python >nul 2>nul
if errorlevel 1 (
  echo Necesitas Python 3.13: https://www.python.org/downloads/  ^(marca "Add python.exe to PATH"^)
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creando el entorno de Python...
  python -m venv .venv || (echo No pude crear el entorno & pause & exit /b 1)
)
echo Instalando dependencias ^(puede tardar varios minutos; ocupa unos 4 GB^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo Fallo la instalacion de dependencias & pause & exit /b 1)
".venv\Scripts\python.exe" -m jarvis.instalar
pause
