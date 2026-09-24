@echo off
chcp 65001 >nul
title Clonar uma voz para a Ametista
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo.
echo  Coloque as gravacoes da voz em voz\amostras antes de continuar
echo  (audios comuns servem: ela escolhe sozinha os melhores trechos).
echo.
echo  1 = No proprio PC (gratis; rapido com placa NVIDIA) - recomendado
echo  2 = ElevenLabs (na nuvem, precisa de plano pago)
set /p OP="Escolha 1 ou 2: "
if "%OP%"=="2" (
  python -m ametista.clonar_voz
) else (
  if not exist voz_local\instalado.json (
    python -m ametista.instalar_voz_local --sem-teste || (pause & exit /b 1)
  )
  python -m ametista.clonar_voz --local
)
pause
