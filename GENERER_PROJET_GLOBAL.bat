@echo off
setlocal
cd /d "%~dp0"
if not exist "resultats\video_index.sqlite3" (
  echo Base SQLite introuvable. Lance d'abord INDEXER_CATALOGUE.bat ou le pipeline.
  pause
  exit /b 1
)
set "EVENT_NAME=MySelfieBooth Catalogue"
set /p "EVENT_NAME=Nom du projet [MySelfieBooth Catalogue] : "
if "%EVENT_NAME%"=="" set "EVENT_NAME=MySelfieBooth Catalogue"
python generate_after_effects_project.py "resultats\video_index.sqlite3" ^
  --output "resultats\after_effects_global" ^
  --all-runs ^
  --event-name "%EVENT_NAME%" ^
  --style promo ^
  --story-arc promo ^
  --visual-dedup ^
  --caption-mode machine ^
  --machine-labels ^
  --review-comp ^
  --machine-review-comps ^
  --quality-gate warn ^
  --background-mode blur ^
  --save-project
if errorlevel 1 (
  pause
  exit /b 1
)
start "" "resultats\after_effects_global\rapport_qualite.html"
