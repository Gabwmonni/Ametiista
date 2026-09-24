@echo off
rem Confere cada peca da Ametista (internet, Claude, microfone, voz, memoria...) e mostra um relatorio.
chcp 65001 >nul
title Diagnostico da Ametista
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Rode o instalar.bat primeiro. & pause & exit /b 1)
call .venv\Scripts\activate.bat
python -m ametista --diagnostico
echo.
echo O relatorio tambem fica salvo em dados\diagnostico.txt
pause
