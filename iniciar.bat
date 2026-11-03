@echo off
cd /d "%~dp0"
echo Consulta tus leyes - http://127.0.0.1:8000
echo Mantenga esta ventana abierta. Para detener, Ctrl+C.
python backend\server.py
if errorlevel 1 pause
