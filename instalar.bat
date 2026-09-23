@echo off
chcp 65001 >nul
title Instalando a Ametista
cd /d "%~dp0"
echo.
echo  ===== Projeto Ametista - instalacao =====
echo.
where python >nul 2>nul || (echo  Python nao encontrado. Instale o Python 3.11+ em python.org marcando "Add Python to PATH". & pause & exit /b 1)

if not exist .venv (
  echo  [1/4] Criando ambiente Python...
  python -m venv .venv || (pause & exit /b 1)
)
call .venv\Scripts\activate.bat

echo  [2/4] Instalando bibliotecas (pode levar alguns minutos)...
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q || (echo  Falha ao instalar. & pause & exit /b 1)

if not exist .env copy .env.example .env >nul

echo  [3/4] Baixando modelos de voz offline (ouvir, reconhecer quem fala, transcrever)...
python -m ametista.baixar_modelos || (pause & exit /b 1)

echo  [4/4] Ligando "Iniciar com o Windows"...
python -m ametista --autoinicio on

echo.
echo  Pronto! Agora:
echo   1. O arquivo .env vai abrir: cole sua ANTHROPIC_API_KEY e salve.
echo   2. Depois de salvar, de dois cliques em iniciar.bat
echo   3. Clique com o botao direito no icone da Ametista perto do relogio:
echo      Vozes ^> Cadastrar a minha voz
echo   4. O resto (celular, agenda, Spotify, voz clonada) esta no LEIA-ME.
echo.
start notepad .env
pause
