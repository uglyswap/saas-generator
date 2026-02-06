@echo off
chcp 65001 >nul
title SaaS Generator

echo.
echo ==========================================
echo   SaaS Generator - Demarrage
echo ==========================================
echo.

cd /d "%~dp0"

echo Verification de Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou pas dans le PATH
    echo Installez Python depuis : https://www.python.org/downloads/
    pause
    exit /b 1
)
echo Python detecte.
echo.

echo Verification des dependances...
python -c "import flask, flask_sqlalchemy, flask_login, flask_wtf, bcrypt, cryptography" >nul 2>&1
if errorlevel 1 (
    echo Installation des dependances...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERREUR] Erreur lors de l'installation des dependances
        pause
        exit /b 1
    )
)
echo Dependances OK.
echo.

REM Create .env from .env.example if it doesn't exist
if not exist ".env" (
    echo Creation du fichier .env depuis .env.example...
    copy .env.example .env >nul
    echo [INFO] Editez le fichier .env pour configurer SECRET_KEY
    echo.
)

REM Run migration if database doesn't exist
if not exist "instance\saas_generator.db" (
    if not exist "saas_generator.db" (
        if exist "templates.json" (
            echo Migration des donnees existantes...
            python migrate.py
            echo.
        )
    )
)

echo Demarrage de l'application...
echo.
echo Application accessible sur : http://localhost:5000
echo.
echo Appuyez sur Ctrl+C pour arreter
echo ==========================================
echo.

python run.py

if errorlevel 1 (
    echo.
    echo [ERREUR] L'application s'est arretee avec une erreur
    echo Consultez app.log pour plus de details
    pause
)
