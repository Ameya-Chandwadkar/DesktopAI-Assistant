@echo off
rem Starts NOVA without a console window. If nothing appears, use run_nova_debug.bat and check the log
rem file in %APPDATA%\NOVA\logs.
cd /d "%~dp0.."
if not exist ".venv\Scripts\pythonw.exe" (
    echo NOVA is not set up yet. Run: powershell -ExecutionPolicy Bypass -File scripts\setup_lenovo.ps1
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m nova
