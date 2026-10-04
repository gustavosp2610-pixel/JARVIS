@echo off
rem Clique duas vezes neste arquivo para ligar o JARVIS.
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
python -m jarvis
pause
