$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Missing virtual environment at $Python. Run scripts/install_windows.ps1 first."
}

Push-Location $ProjectRoot
try {
    & $Python -m jarvis_assistant --doctor
    & $Python -m unittest discover -s tests -q
} finally {
    Pop-Location
}
