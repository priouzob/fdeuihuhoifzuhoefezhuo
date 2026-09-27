@echo off
chcp 65001 >nul
cd /d "%~dp0"
title WikiMasters Auto-Claimer

:: 1. Verifier si Python est installe
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ====================================================================
    echo [ERREUR] Python n'est pas installe ou pas dans votre PATH !
    echo.
    echo 1. Rendez-vous sur : https://www.python.org/downloads/
    echo 2. Cochez bien la case "Add python.exe to PATH" lors de l'installation.
    echo ====================================================================
    pause
    exit /b
)

:: 2. Verifier si PySide6 est bien installe
python -c "import PySide6" >nul 2>&1
if %errorlevel% neq 0 (
    echo ====================================================================
    echo Les composants necessaires [PySide6] ne sont pas encore installes.
    echo Lancement automatique de l'installation : installer.bat...
    echo ====================================================================
    call "%~dp0installer.bat"
)

:: 3. Verifier la presence de config.json
if not exist "%~dp0config.json" (
    if exist "%~dp0config.example.json" (
        copy "%~dp0config.example.json" "%~dp0config.json" >nul
    )
)

:: 4. Mise a jour automatique silencieuse via GitHub
python "%~dp0updater.py" --silent >nul 2>&1

:: 5. Lancement de l'interface graphique
where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw "%~dp0gui.py"
) else (
    start "" python "%~dp0gui.py"
)
exit
