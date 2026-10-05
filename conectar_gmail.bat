@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Conectar o Gmail ao JARVIS
if not exist ".venv\Scripts\python.exe" goto sem_instalacao
".venv\Scripts\python.exe" -m jarvis --gmail
echo.
echo Se conectou, feche o JARVIS e abra de novo pelo atalho para usar o Gmail.
pause
exit /b 0

:sem_instalacao
echo O JARVIS ainda nao foi instalado nesta pasta. Rode o instalar_jarvis.bat primeiro.
pause
