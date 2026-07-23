@echo off
setlocal
set "SOURCE=%~dp0after_effects\MSB_AutoMontage_Panel.jsx"
set "AE_ROOT=%ProgramFiles%\Adobe"

echo Recherche des installations After Effects...
set "FOUND="
for /d %%D in ("%AE_ROOT%\Adobe After Effects *") do (
    if exist "%%~fD\Support Files\Scripts\ScriptUI Panels" (
        copy /Y "%SOURCE%" "%%~fD\Support Files\Scripts\ScriptUI Panels\MSB_AutoMontage_Panel.jsx" >nul
        echo Installe dans : %%~fD
        set "FOUND=1"
    )
)

if not defined FOUND (
    echo Installation automatique impossible.
    echo Copie manuellement le fichier suivant dans Scripts\ScriptUI Panels :
    echo %SOURCE%
) else (
    echo.
    echo Redemarre After Effects puis ouvre : Fenetre ^> MSB_AutoMontage_Panel
)
pause
