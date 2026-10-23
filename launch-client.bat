@echo off
:: ============================================================
:: Stress Letterbox — Windows Client Launcher
:: Double-click to start, or add to Startup folder for auto-launch.
:: ============================================================

setlocal

:: Determine script directory (project root)
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Activate venv if present (accepts either venv\ or .venv\)
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo Warning: No venv found at .venv\ or venv\. Using system Python.
    echo Run: python -m venv venv && venv\Scripts\activate && pip install -r requirements-client.txt
)

:: Launch client without a console window (pythonw)
:: Falls back to python if pythonw is not found.
where pythonw >nul 2>&1
if %errorlevel% == 0 (
    start "" pythonw client\main.py
) else (
    start "" python client\main.py
)

endlocal
