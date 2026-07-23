@echo off
setlocal
cd /d "%~dp0"

set "DATABASE=%~1"
if "%DATABASE%"=="" set "DATABASE=resultats\video_index.sqlite3"

set "EVENT_NAME=MySelfieBooth"
set /p "EVENT_NAME=Nom de l'evenement [MySelfieBooth] : "
if "%EVENT_NAME%"=="" set "EVENT_NAME=MySelfieBooth"

set "STYLE=balanced"
set /p "STYLE=Style balanced / dynamic / emotion / promo [balanced] : "
if "%STYLE%"=="" set "STYLE=balanced"

set "TRANSITION=fade"
set /p "TRANSITION=Transition none / fade / flash [fade] : "
if "%TRANSITION%"=="" set "TRANSITION=fade"

set "LABEL_ARG=--no-machine-labels"
if /I "%STYLE%"=="promo" set "LABEL_ARG=--machine-labels"

set "CAPTION_MODE=none"
set /p "CAPTION_MODE=Texte none / machine / description / both [none] : "
if "%CAPTION_MODE%"=="" set "CAPTION_MODE=none"

set "PROXY_ARG=--no-proxies"
set /p "CREATE_PROXIES=Creer des proxies locaux pour accelerer After Effects ? o/N : "
if /I "%CREATE_PROXIES%"=="o" set "PROXY_ARG=--proxies"
if /I "%CREATE_PROXIES%"=="oui" set "PROXY_ARG=--proxies"

python generate_after_effects_project.py "%DATABASE%" ^
  --output "resultats\after_effects" ^
  --event-name "%EVENT_NAME%" ^
  --style "%STYLE%" ^
  --transition-style "%TRANSITION%" ^
  --auto-motion ^
  --story-arc rising ^
  --visual-dedup ^
  --caption-mode "%CAPTION_MODE%" ^
  %PROXY_ARG% ^
  %LABEL_ARG% ^
  --review-comp ^
  --music-volume-db -8 ^
  --source-volume-db -2 ^
  --duck-music-db -12 ^
  --background-mode blur ^
  --save-project ^
  --queue-render

pause
