@echo off
rem Construit "Dashboard LMU.exe" (dossier dist\). Nécessite Python 3 uniquement pour la construction.
cd /d "%~dp0"
py -3 -m pip install -r app\requirements.txt || python -m pip install -r app\requirements.txt
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name "Dashboard LMU" ^
  --paths bridge --add-data "web;web" app\lmu_dashboard_app.py
echo.
echo Termine : dist\Dashboard LMU.exe
pause
