@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    call "%~dp0update.bat"
    if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m pytest tests/test_examples.py -q
exit /b %ERRORLEVEL%
