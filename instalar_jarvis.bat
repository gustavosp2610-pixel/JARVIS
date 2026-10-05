@echo off
rem JARVIS-BAT-SEGURO
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Instalador do JARVIS
echo ==================================================
echo              Instalador do J.A.R.V.I.S.
echo ==================================================
echo.

rem ---- 1. Python ------------------------------------------------------------
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY goto instalar_python
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto instalar_python
echo [1/4] Python encontrado.
goto ambiente

:instalar_python
echo [1/4] Python 3.10 ou mais novo nao encontrado. Instalando o Python 3.12...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto python_manual
echo.
echo Python instalado! FECHE esta janela e de dois cliques em instalar_jarvis.bat de novo.
pause
exit /b 0

:python_manual
echo.
echo Nao consegui instalar o Python sozinho.
echo Vou abrir o site: baixe o Python, e na instalacao MARQUE a opcao "Add python.exe to PATH".
echo Depois de instalar, de dois cliques em instalar_jarvis.bat de novo.
start "" https://www.python.org/downloads/
pause
exit /b 1

rem ---- 2. Ambiente e bibliotecas ---------------------------------------------
:ambiente
echo [2/4] Preparando o ambiente do JARVIS...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" goto erro_ambiente
set "VPY=%~dp0.venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip --quiet

echo [3/4] Instalando as bibliotecas. Pode levar alguns minutos...
"%VPY%" -m pip install --prefer-binary -r requirements.txt --disable-pip-version-check
if not errorlevel 1 goto opcionais
echo.
echo Algumas bibliotecas falharam. Instalando uma por uma e pulando as que nao funcionarem...
set "FALHOU="
for /f "usebackq eol=# tokens=*" %%L in ("requirements.txt") do (
  "%VPY%" -m pip install --prefer-binary "%%L" --disable-pip-version-check --quiet || (echo   Aviso: nao consegui instalar "%%L" & set "FALHOU=1")
)
"%VPY%" -c "import google.genai, edge_tts, dotenv, rich" >nul 2>&1
if errorlevel 1 goto erro_bibliotecas
if defined FALHOU echo O essencial foi instalado. As funcoes das bibliotecas acima podem nao funcionar.

:opcionais
"%VPY%" -m pip install --prefer-binary -r requirements-opcional.txt --quiet >nul 2>&1
if errorlevel 1 echo Aviso: o modo de voz pelo terminal nao foi instalado. A tela do JARVIS funciona normalmente.

rem ---- 3. Configuracao -------------------------------------------------------
echo [4/4] Configurando...
"%VPY%" -m jarvis --configurar

rem ---- 4. Atalho na Area de Trabalho ----------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\JARVIS.lnk'); $s.TargetPath = '%~dp0iniciar_jarvis.bat'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%SystemRoot%\System32\shell32.dll,43'; $s.Save()" >nul 2>&1
if errorlevel 1 (echo Nao consegui criar o atalho. Use o arquivo iniciar_jarvis.bat desta pasta.) else (echo Atalho JARVIS criado na Area de Trabalho.)

echo.
echo ==================================================
echo   Instalacao concluida!
echo ==================================================
choice /c SN /m "Ligar o JARVIS agora"
if errorlevel 2 exit /b 0
start "" "%~dp0iniciar_jarvis.bat"
exit /b 0

:erro_ambiente
echo.
echo Nao consegui criar o ambiente do Python. Tente rodar este instalador de novo.
pause
exit /b 1

:erro_bibliotecas
echo.
echo Nao consegui instalar as bibliotecas. Verifique a internet e rode o instalador de novo.
pause
exit /b 1
