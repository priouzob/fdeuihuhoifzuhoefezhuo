@echo off
chcp 65001 >nul
title Installation de WikiMasters Auto-Claimer
color 0b
echo ====================================================================
echo             INSTALLATION DE WIKIMASTERS AUTO-CLAIMER
echo ====================================================================
echo.
echo Ce script va préparer votre environnement automatiquement.
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Python n'est pas détecté sur votre ordinateur !
    echo.
    echo 1. Rendez-vous sur : https://www.python.org/downloads/
    echo 2. Téléchargez et lancez l'installateur Python.
    echo 3. IMPORTANT : Cochez impérativement la case :
    echo    "Add python.exe to PATH" tout en bas de la première fenêtre !
    echo 4. Relancez ensuite ce fichier "installer.bat".
    echo.
    pause
    exit /b
)

echo [1/3] Initialisation du fichier de configuration...
if not exist config.json (
    if exist config.example.json (
        copy config.example.json config.json >nul
    ) else (
        echo {"target_url": "https://wiki-masters.com/pulls", "check_interval_seconds": 600, "random_jitter_seconds": 15, "headless": true, "chrome_executable": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "accounts": []} > config.json
    )
)
echo      Fichier de configuration prêt.
echo.

echo [2/3] Installation des modules (PySide6, Playwright)...
echo      Téléchargement en cours (environ 100 Mo, veuillez patienter sans fermer)...
echo.
python -m pip install --upgrade pip
python -m pip install PySide6 playwright
if %errorlevel% neq 0 (
    echo.
    echo [AVERTISSEMENT] Nouvelle tentative d'installation...
    pip install PySide6 playwright
)

echo.
echo [3/3] Téléchargement des composants Chromium Playwright...
python -m playwright install chromium

echo.
echo ====================================================================
echo   INSTALLATION TERMINÉE AVEC SUCCÈS !
echo.
echo   Vos comptes et cookies seront 100%% indépendants et sécurisés.
echo   Vous pouvez dès maintenant lancer le logiciel avec :
echo   ==^> "lancer_interface.bat"
echo ====================================================================
echo.
pause
