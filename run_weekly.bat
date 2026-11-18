@echo off
cd /d "%~dp0"

set PYTHON=%~dp0.venv\Scripts\python.exe

if not exist "%PYTHON%" (
    echo ERREUR : environnement virtuel introuvable dans .venv
    exit /b 1
)

echo ===== VEILLE CONCURRENTIELLE =====
"%PYTHON%" scripts\research.py || exit /b 1

echo ===== ANALYSE DES CONCURRENTS =====
"%PYTHON%" scripts\analyze.py || exit /b 1

echo ===== MESURE DE VISIBILITE IA =====
"%PYTHON%" scripts\visibility.py || exit /b 1

echo ===== COMPARAISON DES RESULTATS =====
"%PYTHON%" scripts\compare.py || exit /b 1

echo ===== GENERATION DES RECOMMANDATIONS =====
"%PYTHON%" scripts\recommendations.py || exit /b 1

echo ===== EXECUTION TERMINEE =====

