@echo off
chcp 65001 >nul
title Installation de WikiMasters Auto-Claimer
color 0b
echo ====================================================================
echo             INSTALLATION DE WIKIMASTERS AUTO-CLAIMER
echo ====================================================================
echo.
echo Ce script va preparer votre environnement en quelques secondes.
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Python n'est pas detecte sur votre ordinateur !
    echo.
    echo 1. Rendez-vous sur https://www.python.org/downloads/
    echo 2. Telechargez et lancez l'installateur Python.
    echo 3. IMPORTANT : Cochez la case "Add python.exe to PATH" !
    echo 4. Relancez ensuite ce fichier "installer.bat".
    echo.
    pause
    exit /b
)

echo [1/3] Verification et installation des modules (PySide6, Playwright)...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install PySide6 playwright >nul 2>&1
if %errorlevel% neq 0 (
    echo [AVERTISSEMENT] Erreur lors de l'installation pip, reessai...
    pip install PySide6 playwright
)

echo [2/3] Telechargement des binaires Playwright Chromium...
python -m playwright install chromium

echo [3/3] Creation du fichier de configuration de vos comptes...
if not exist config.json (
    if exist config.example.json (
        copy config.example.json config.json >nul
    ) else (
        echo {"target_url": "https://wiki-masters.com/pulls", "check_interval_seconds": 600, "random_jitter_seconds": 15, "headless": true, "chrome_executable": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "accounts": []} > config.json
    )
)

echo.
echo ====================================================================
echo   INSTALLATION TERMINEE AVEC SUCCES !
echo.
echo   Vos comptes et cookies seront 100%% independants et preserves.
echo   Vous pouvez desormais lancer le logiciel avec :
echo   ==> "lancer_interface.bat"
echo ====================================================================
echo.
pause
