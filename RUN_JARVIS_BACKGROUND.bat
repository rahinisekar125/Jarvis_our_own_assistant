@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "scripts\start_jarvis_voice_hidden.ps1"
echo Jarvis voice assistant started in the background.
