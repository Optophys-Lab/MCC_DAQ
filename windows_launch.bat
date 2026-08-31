@echo off
REM Double-click launcher for MCC_DAQ on the rig PC -- runs this repo's own
REM .venv, not whatever Python happens to be on PATH. %~dp0 resolves to this
REM script's own folder regardless of where the repo lives or where the
REM shortcut is placed, so a Desktop shortcut to this file still works.
setlocal
set "REPO=%~dp0"
set "PYTHON=%REPO%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Virtual environment not found at "%PYTHON%".
    echo Run: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt mcculw
    pause
    exit /b 1
)

cd /d "%REPO%"
"%PYTHON%" GUI_my.py
if errorlevel 1 (
    echo.
    echo MCC DAQ GUI exited with an error - see above.
    pause
)
