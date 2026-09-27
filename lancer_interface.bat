@echo off
cd /d "%~dp0"
python updater.py --silent >nul 2>&1
start "" pythonw "%~dp0gui.py"
exit
