@echo off
setlocal EnableExtensions
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

where ollama >nul 2>nul || (
    echo ERREUR : Ollama est introuvable.
    pause
    exit /b 1
)

echo Test de Montage AI sur 5 videos.
echo.

if exist "resultats\video_index.sqlite3" (
    echo Base SQLite detectee : aucun rescan du NAS.
    python main.py "%SOURCE%" --output resultats --skip-index --max-videos 5 --candidates 3 --top-moments 2 --top-machine Photobooth --top-limit 10
) else (
    echo Premiere utilisation : indexation limitee a 5 fichiers.
    python main.py "%SOURCE%" --output resultats --max-index 5 --max-videos 5 --candidates 3 --top-moments 2 --top-machine Photobooth --top-limit 10
)

if errorlevel 1 (
    echo.
    echo Le test a rencontre une erreur. Consulte les messages ci-dessus.
    pause
    exit /b 1
)

start "" "%~dp0resultats"
echo.
echo Test termine. Consulte resultats\moments.csv et resultats\top_10_photobooth.csv
pause
