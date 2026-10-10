@echo off
title Dashboard LMU
cd /d "%~dp0bridge"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 lmu_bridge.py %*
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3 est introuvable. Installe-le depuis https://www.python.org/downloads/
    echo en cochant "Add python.exe to PATH", puis relance start.bat.
    pause
    exit /b 1
  )
  python lmu_bridge.py %*
)
pause
