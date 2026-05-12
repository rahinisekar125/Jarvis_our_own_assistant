$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Starter = Join-Path $ProjectRoot "scripts\start_jarvis_voice_hidden.ps1"
$TaskName = "JarvisVoiceAssistant"

$StartupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$StartupCmd = Join-Path $StartupDir "$TaskName.cmd"
$Command = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Starter`"`r`n"

New-Item -ItemType Directory -Path $StartupDir -Force | Out-Null
Set-Content -Path $StartupCmd -Value $Command -Encoding ASCII

Write-Host "Installed startup launcher: $StartupCmd"
Write-Host "Jarvis will start automatically after you sign in to Windows."
