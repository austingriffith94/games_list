@echo off
REM Double-click to start the Game List app. Paths come from config.json (see config.example.json).
REM Uses the "game1" conda env directly (the bare "python" on PATH is the Microsoft Store stub).
cd /d "%~dp0"

set "PY=%USERPROFILE%\miniconda3\envs\game1\python.exe"
if not exist "%PY%" (
    echo Could not find %PY%
    pause
    exit /b 1
)

"%PY%" app.py
pause
