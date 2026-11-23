@echo off
rem Publishes a new FilesXray version: uploads the code to GitHub and
rem starts the automatic build. GitHub then puts FilesXray.exe on the release page.
title FilesXray - neue Version veroeffentlichen
cd /d "%~dp0"

rem Stop if there are changes that are not committed yet.
for /f %%s in ('git status --porcelain') do (
    echo Es gibt noch Aenderungen, die nicht committet sind:
    git status --short
    echo Bitte zuerst committen, dann erneut starten.
    goto end
)

set LAST=keine
for /f %%v in ('git describe --tags --abbrev^=0 2^>nul') do set LAST=%%v
echo Letzte Version: %LAST%
echo Schema: v1.0.1 = Fehlerbehebung, v1.1.0 = neue Funktion, v2.0.0 = grosse Aenderung
echo.
set VER=
set /p VER=Neue Version (z. B. v1.1.0): 
if "%VER%"=="" goto end
if /i not "%VER:~0,1%"=="v" (
    echo Die Version muss mit v beginnen, z. B. v1.1.0
    goto end
)
set NOTES=
set /p NOTES=Was ist neu? (ein Satz, erscheint auf der Download-Seite): 
if "%NOTES%"=="" set NOTES=Neue Version %VER%

echo.
echo Lade Code hoch ...
git push origin main || goto fail
git tag -a %VER% -m "%NOTES%" || goto fail
git push origin %VER% || goto fail

echo.
echo Fertig. GitHub baut jetzt FilesXray.exe (dauert ca. 3-5 Minuten).
echo Danach liegt sie hier zum Download:
echo   https://github.com/philippracher-optimuse/files-xray/releases/latest
echo Der Fortschritt oeffnet sich im Browser.
start "" "https://github.com/philippracher-optimuse/files-xray/actions"
goto end

:fail
echo.
echo Etwas ist schiefgegangen (siehe Meldung oben). Nichts wurde veroeffentlicht,
echo falls der Fehler vor "git push origin %VER%" kam.

:end
echo.
pause
