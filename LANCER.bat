@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "SOURCE=P:\Montage-EVENT\ALL_MONTAGE"
set "OUTPUT=resultats"

where python >nul 2>nul || (
    echo ERREUR : Python est introuvable.
    pause
    exit /b 1
)

where ffmpeg >nul 2>nul || (
    echo ERREUR : FFmpeg est introuvable.
    echo Ferme et relance ce terminal apres l'installation de FFmpeg.
    pause
    exit /b 1
)

where ffprobe >nul 2>nul || (
    echo ERREUR : FFprobe est introuvable.
    pause
    exit /b 1
)

where ollama >nul 2>nul || (
    echo ERREUR : Ollama est introuvable.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo          MONTAGE AI - MYSELFIEBOOTH
echo ==========================================
echo.
echo 1 - Analyser depuis SQLite sans rescanner le NAS
echo 2 - Indexer un petit lot puis analyser
echo 3 - Indexer tout le NAS puis analyser
echo 4 - Indexer uniquement
echo 5 - Regenerer les exports et le Top 10
echo.

set "CHOIX=1"
set /p "CHOIX=Choix [1] : "
if "%CHOIX%"=="" set "CHOIX=1"

set "NOM=MySelfieBooth"
set /p "NOM=Nom du projet After Effects [MySelfieBooth] : "
if "%NOM%"=="" set "NOM=MySelfieBooth"

if "%CHOIX%"=="5" goto EXPORTS

if not exist "%SOURCE%" (
    echo ERREUR : %SOURCE% est introuvable.
    echo Verifie que le lecteur P: est connecte.
    pause
    exit /b 1
)

set "NB=50"
set /p "NB=Nombre de videos a analyser maintenant [50] : "
if "%NB%"=="" set "NB=50"

if "%CHOIX%"=="1" goto ANALYSE_SQLITE
if "%CHOIX%"=="2" goto PETIT_LOT
if "%CHOIX%"=="3" goto INDEX_COMPLET
if "%CHOIX%"=="4" goto INDEX_SEUL

echo Choix invalide.
pause
exit /b 1

:ANALYSE_SQLITE
python main.py "%SOURCE%" --output "%OUTPUT%" --skip-index --max-videos %NB% --event-name "%NOM%" --references machine_references
if errorlevel 1 goto ERREUR
goto SUCCES

:PETIT_LOT
set "INDEX_NB=100"
set /p "INDEX_NB=Nombre de fichiers a parcourir pendant l'indexation [100] : "
if "%INDEX_NB%"=="" set "INDEX_NB=100"
python main.py "%SOURCE%" --output "%OUTPUT%" --max-index %INDEX_NB% --max-videos %NB% --event-name "%NOM%" --references machine_references
if errorlevel 1 goto ERREUR
goto SUCCES

:INDEX_COMPLET
python main.py "%SOURCE%" --output "%OUTPUT%" --max-videos %NB% --event-name "%NOM%" --references machine_references
if errorlevel 1 goto ERREUR
goto SUCCES

:INDEX_SEUL
set "INDEX_NB=0"
set /p "INDEX_NB=Nombre de fichiers a parcourir [0 = tous] : "
if "%INDEX_NB%"=="" set "INDEX_NB=0"
python main.py "%SOURCE%" --output "%OUTPUT%" --index-only --max-index %INDEX_NB%
if errorlevel 1 goto ERREUR
goto SUCCES

:EXPORTS
python main.py --output "%OUTPUT%" --export-only --top-machine Photobooth --top-limit 10 --event-name "%NOM%"
if errorlevel 1 goto ERREUR
goto SUCCES

:ERREUR
echo.
echo Une erreur est survenue. La progression SQLite est conservee.
pause
exit /b 1

:SUCCES
if exist "%~dp0%OUTPUT%" start "" "%~dp0%OUTPUT%"
echo.
echo Dans After Effects : Fichier ^> Scripts ^> Executer un fichier de script
echo Puis ouvre : %OUTPUT%\MSB_Creer_Projet_After_Effects.jsx
pause
