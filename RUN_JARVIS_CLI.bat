@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Run scripts\install_windows.ps1 first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m jarvis_assistant --mode cli
pause
