$ErrorActionPreference = "Stop"

function Get-PythonCommand {
    $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pythonLauncher) {
        return @("py", "-3.11")
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $pythonPath = $python.Source
        if ($pythonPath -match "\\(msys64|cygwin64|Git)\\") {
            throw "PowerShell is using a Unix-style Python at $pythonPath. Install Python 3.11+ for Windows from python.org or use the py launcher, then rerun this script."
        }
        return @("python")
    }

    throw "Python was not found. Install Python 3.11+ for Windows from python.org, then reopen PowerShell."
}

if ((Test-Path ".venv") -and -not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Found .venv, but it is not a Windows virtual environment. Delete .venv, install Python 3.11+ for Windows from python.org, then rerun this script."
}

$PythonCommand = Get-PythonCommand

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if ($PythonCommand.Length -gt 1) {
        & $PythonCommand[0] $PythonCommand[1..($PythonCommand.Length - 1)] -m venv .venv
    } else {
        & $PythonCommand[0] -m venv .venv
    }
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Virtual environment creation failed. Make sure PowerShell is using Python for Windows, not MSYS2/Git Bash Python."
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

$ModelDir = "models\vosk-model-small-en-us-0.15"
$ModelZip = "models\vosk-model-small-en-us-0.15.zip"
$ModelUrl = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
if (-not (Test-Path $ModelDir)) {
    New-Item -ItemType Directory -Force -Path "models" | Out-Null
    if (-not (Test-Path $ModelZip)) {
        Write-Host "Downloading Vosk wake-word model..."
        Invoke-WebRequest -Uri $ModelUrl -OutFile $ModelZip
    }
    Write-Host "Extracting Vosk wake-word model..."
    Expand-Archive -LiteralPath $ModelZip -DestinationPath "models" -Force
}

Write-Host "Installed. Edit .env, then run scripts/validate_deployment.ps1, scripts/run_cli.ps1, or scripts/run_voice.ps1."
