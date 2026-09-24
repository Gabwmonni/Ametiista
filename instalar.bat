@echo off
chcp 65001 >nul
title Instalando a Ametista
cd /d "%~dp0"
echo.
echo  ===== Projeto Ametista 3.0 - instalacao =====
echo  (serve tambem para atualizar a 1.0 ou a 2.0: nada do que ela aprendeu se perde)
echo.

rem --- acha um Python 3.11 ou 3.12 (o "py" escolhe a versao certa quando ha varias)
set "PY="
py -3.12 -c "" >nul 2>nul && set "PY=py -3.12"
if not defined PY py -3.11 -c "" >nul 2>nul && set "PY=py -3.11"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python"
if not defined PY (
  echo  Nao achei o Python 3.11 ou 3.12.
  echo  Instale em python.org, marcando "Add Python to PATH", e rode este arquivo de novo.
  pause
  exit /b 1
)

rem --- lugar da pasta: caminho curto e fora do OneDrive (senao o Windows recusa arquivos da instalacao).
rem     Tambem traz memoria, vozes e configuracoes de uma Ametista instalada em outra pasta.
set "ARQ_DESTINO=%TEMP%\ametista_destino.txt"
if exist "%ARQ_DESTINO%" del "%ARQ_DESTINO%"
%PY% -m ametista.pasta_segura "%CD%" "%ARQ_DESTINO%"
if errorlevel 10 goto continuar_no_destino
if errorlevel 1 (
  pause
  exit /b 1
)

rem --- ambiente Python proprio da Ametista (reaproveitado na atualizacao)
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul || (
    echo  O ambiente Python antigo nao funciona mais: vou recriar.
    rmdir /s /q .venv
  )
)
if not exist .venv\Scripts\python.exe (
  echo  [1/7] Criando o ambiente Python...
  %PY% -m venv .venv || (pause & exit /b 1)
) else (
  echo  [1/7] Ambiente Python ja existe: atualizando.
)
call .venv\Scripts\activate.bat

rem --- apaga o codigo compilado da versao anterior (evita rodar pedaco velho depois de atualizar)
for /d /r "ametista" %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"

echo  [2/7] Instalando bibliotecas - pode levar alguns minutos...
python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt -q || (
  echo.
  echo  Falha ao instalar as bibliotecas. Confira a internet e rode o instalar.bat de novo.
  pause
  exit /b 1
)

echo  [3/7] Busca por significado na memoria - opcional...
python -m pip install "fastembed>=0.4" -q || echo  Nao instalou; tudo funciona, a memoria usa busca por palavras.

if not exist .env (
  copy .env.example .env >nul
  set "NOVO=1"
)

echo  [4/7] Baixando os modelos offline: ouvir, reconhecer quem fala, transcrever e memoria...
python -m ametista.baixar_modelos || (pause & exit /b 1)

echo  [5/7] Ligando "Iniciar com o Windows"...
python -m ametista --autoinicio on

echo  [6/7] Cerebro no proprio PC (Ollama) - opcional...
python -m ametista.cerebro_local --preparar

echo  [7/7] App do celular - se ja estava publicado, publica a versao nova...
python -m ametista.publicar_celular --so-atualizar

rem --- abre a Ametista ja na versao nova (a que estava aberta foi fechada no comeco da instalacao)
echo.
if not defined AMETISTA_NAO_ABRIR python -m ametista --abrir
echo.
echo  Pronto!
if defined NOVO (
  echo   1. O painel de configuracoes abre no navegador: cole a chave da Anthropic
  echo      em Cerebro e clique em Salvar.
) else (
  echo   1. Suas configuracoes, memoria e vozes cadastradas continuam as mesmas.
  echo      As novidades da 3.0 estao no LEIA-ME e no painel: botao direito no icone da Ametista.
)
echo   2. Cadastre a sua voz: botao direito no icone da Ametista ^> Vozes ^> Cadastrar a minha voz.
echo   3. Algo estranho? De dois cliques em diagnostico.bat.
echo   Ela liga sozinha com o Windows. Para abrir de novo na mao: iniciar.bat.
echo   O resto - celular, agenda, Spotify, casa, voz clonada - esta no LEIA-ME.
if defined AMETISTA_PASTA_ANTIGA echo.
if defined AMETISTA_PASTA_ANTIGA echo   A Ametista agora fica em "%CD%".
if defined AMETISTA_PASTA_ANTIGA echo   A pasta antiga nao e mais usada e pode ser apagada: "%AMETISTA_PASTA_ANTIGA%"
echo.
pause
exit /b 0

:continuar_no_destino
rem a pasta foi copiada para um lugar bom: a instalacao continua de la
set /p DESTINO=<"%ARQ_DESTINO%"
set "AMETISTA_PASTA_ANTIGA=%CD%"
cd /d "%DESTINO%"
call "%DESTINO%\instalar.bat"
exit /b %errorlevel%
