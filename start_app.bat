@echo off
REM Double-click to start the Game List app. Edit the covers path below if yours is elsewhere.
cd /d "%~dp0"
python app.py --covers "D:\Pictures\Game List Covers"
pause
