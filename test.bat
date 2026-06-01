@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    call "%~dp0update.bat"
)
".venv\Scripts\python.exe" -m pytest tests -q
