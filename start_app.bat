@echo off
REM Double-click to start the Game List app. Paths come from config.json (see config.example.json).
cd /d "%~dp0"
python app.py
pause
