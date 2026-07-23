@echo off
setlocal
cd /d "%~dp0"
if exist "CONFIGURATION_MSB.bat" call "CONFIGURATION_MSB.bat"
if not defined MSB_MONTAGE_ROOT set "MSB_MONTAGE_ROOT=P:\Montage-EVENT\ALL_MONTAGE"
if not defined MSB_EXCLUDE_FOLDERS set "MSB_EXCLUDE_FOLDERS=cache;temp;tmp;proxy;proxies;previews;miniatures;resultats"
if not defined MSB_PROBE_WORKERS set "MSB_PROBE_WORKERS=6"

if not exist "%MSB_MONTAGE_ROOT%" (
  echo ERREUR : %MSB_MONTAGE_ROOT% est introuvable.
  pause
  exit /b 1
)

python nas_video_ai_analyzer.py "%MSB_MONTAGE_ROOT%" ^
  --output "resultats" ^
  --inventory-only ^
  --probe-workers %MSB_PROBE_WORKERS% ^
  --exclude-folders "%MSB_EXCLUDE_FOLDERS%"
if errorlevel 1 (
  pause
  exit /b 1
)
start "" "resultats\catalogue_dashboard.html"
