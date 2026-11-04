@echo off
cd /d "%~dp0"
title Jarvis
echo Jarvis: http://127.0.0.1:8765
rem Al arrancar con Windows (iniciar.bat auto) no se abre el navegador.
if /i not "%~1"=="auto" start "" http://127.0.0.1:8765
".venv\Scripts\python.exe" -m uvicorn jarvis.server:app --host 127.0.0.1 --port 8765
pause
