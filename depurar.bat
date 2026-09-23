@echo off
rem Igual ao iniciar.bat, mas com a janela de mensagens aberta (para ver erros)
chcp 65001 >nul
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m ametista
pause
