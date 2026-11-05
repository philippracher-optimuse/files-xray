@echo off
rem Builds dist\FilesXray.exe (single file, no Python needed on the target PC).
cd /d "%~dp0"
if not exist .venv (
    py -m venv .venv || python -m venv .venv
    .venv\Scripts\python -m pip install pyinstaller
)
.venv\Scripts\python -m PyInstaller --noconfirm --onefile --console --name FilesXray --add-data "index.html;." server.py
echo.
echo Fertig: dist\FilesXray.exe
pause
