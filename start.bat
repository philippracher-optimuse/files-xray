@echo off
rem FilesXray - double-click to start. Close this window to stop the tool.
title FilesXray
cd /d "%~dp0"

rem Use "py" (Python launcher) if available, otherwise "python".
where py >nul 2>nul
if %errorlevel%==0 (
    py server.py
    goto end
)
where python >nul 2>nul
if %errorlevel%==0 (
    python server.py
    goto end
)

echo.
echo Python wurde nicht gefunden.
echo Bitte Python installieren: https://www.python.org/downloads/
echo (bei der Installation "Add python.exe to PATH" anhaken), danach erneut starten.
echo.

:end
pause
