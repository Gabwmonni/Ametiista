@echo off
chcp 65001 >nul
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo Coloque as gravacoes em voz\amostras antes de continuar.
echo.
echo  1 = ElevenLabs (melhor qualidade, precisa de plano pago)
echo  2 = No proprio PC (gratis, precisa de placa NVIDIA para ficar rapido)
set /p OP="Escolha 1 ou 2: "
if "%OP%"=="2" (
  pip install coqui-tts
  python -m ametista.clonar_voz --local
) else (
  python -m ametista.clonar_voz
)
pause
