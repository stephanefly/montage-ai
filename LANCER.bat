@echo off
setlocal
cd /d "%~dp0"

set "SOURCE=P:\Montage-EVENT\ALL_MONTAGE"

if not exist "%SOURCE%" (
    echo ERREUR : %SOURCE% est introuvable.
    echo Verifie que le lecteur P: est connecte.
    pause
    exit /b 1
)

where python >nul 2>nul || (
    echo ERREUR : Python est introuvable.
    pause
    exit /b 1
)

where ffmpeg >nul 2>nul || (
    echo ERREUR : FFmpeg est introuvable.
    pause
    exit /b 1
)

set "NB=50"
set /p "NB=Nombre de videos a analyser maintenant [50] : "
if "%NB%"=="" set "NB=50"

set "NOM=MySelfieBooth"
set /p "NOM=Nom du projet After Effects [MySelfieBooth] : "
if "%NOM%"=="" set "NOM=MySelfieBooth"

python main.py "%SOURCE%" --output resultats --max-videos %NB% --event-name "%NOM%" --references machine_references

if errorlevel 1 (
    echo.
    echo Une erreur est survenue. La progression SQLite est conservee.
    pause
    exit /b 1
)

start "" "%~dp0resultats"
echo.
echo Dans After Effects : Fichier ^> Scripts ^> Executer un fichier de script
echo Puis ouvre : resultats\MSB_Creer_Projet_After_Effects.jsx
pause
