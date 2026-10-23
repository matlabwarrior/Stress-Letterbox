@echo off
:: ============================================================
:: Stress Letterbox — Windows Server Launcher
:: For development / manual start only.
:: For production on Windows, use NSSM to run as a service.
:: See docs\deployment.md for details.
:: ============================================================

setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if not exist "config.yaml" (
    echo ERROR: config.yaml not found.
    echo Run: copy config.yaml.example config.yaml
    echo Then edit config.yaml with your settings.
    pause
    exit /b 1
)

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo Warning: No venv found at .venv\ or venv\. Using system Python.
)

echo Starting Stress Letterbox server...
echo Admin dashboard: http://localhost:5000/admin
echo Press Ctrl+C to stop.
echo.

python server\app.py

endlocal
