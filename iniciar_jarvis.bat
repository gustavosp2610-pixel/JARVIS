@echo off
rem JARVIS-BAT-SEGURO: este arquivo pode ser trocado pela atualizacao automatica enquanto roda.
chcp 65001 >nul
cd /d "%~dp0"
title J.A.R.V.I.S.
if not exist ".venv\Scripts\python.exe" goto sem_instalacao
if not exist ".env" ".venv\Scripts\python.exe" -m jarvis --configurar
".venv\Scripts\python.exe" -m jarvis & pause & exit /b 0

:sem_instalacao
echo O JARVIS ainda nao foi instalado. Abrindo o instalador...
call "%~dp0instalar_jarvis.bat"
