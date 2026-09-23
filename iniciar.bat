@echo off
cd /d "%~dp0"
if not exist .venv (echo Rode o instalar.bat primeiro. & pause & exit /b 1)
start "" ".venv\Scripts\pythonw.exe" "%~dp0ametista.pyw"
