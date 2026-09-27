@echo off
chcp 65001 >nul
cd /d "%~dp0"
title WikiMasters Auto-Claimer (Mode Diagnostic)
echo ====================================================================
echo             WIKIMASTERS AUTO-CLAIMER -- MODE DIAGNOSTIC
echo ====================================================================
echo.
echo Verification de Python...
python --version
echo.
echo Verification des modules...
python -c "import PySide6; print('PySide6: OK'); import playwright; print('Playwright: OK')"
echo.
echo Lancement de l'interface en mode console (ne fermez pas cette fenetre)...
python "%~dp0gui.py"
echo.
echo ====================================================================
echo Le programme s'est arrete.
echo ====================================================================
pause
