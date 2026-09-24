@echo off
chcp 65001 >nul
title Instalando a voz clonada da Ametista
cd /d "%~dp0"
echo.
echo  ===== Voz clonada no proprio PC (XTTS-v2) =====
echo  Baixa uns 4 GB (PyTorch e o modelo de voz). Com placa NVIDIA a voz sai rapida.
echo.
if not exist .venv\Scripts\python.exe (
  echo  Rode o instalar.bat primeiro.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m ametista.instalar_voz_local %*
set "CODIGO=%errorlevel%"
echo.
pause
exit /b %CODIGO%
