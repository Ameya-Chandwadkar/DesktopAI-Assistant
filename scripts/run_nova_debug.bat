@echo off
rem Starts NOVA with a console so errors are visible.
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m nova
pause
