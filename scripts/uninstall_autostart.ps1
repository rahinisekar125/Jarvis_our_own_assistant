$ErrorActionPreference = "Stop"

$TaskName = "JarvisVoiceAssistant"
$StartupCmd = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\$TaskName.cmd"
if (Test-Path $StartupCmd) {
    Remove-Item -LiteralPath $StartupCmd -Force
    Write-Host "Removed startup launcher: $StartupCmd"
} else {
    Write-Host "Startup launcher was not present: $StartupCmd"
}
