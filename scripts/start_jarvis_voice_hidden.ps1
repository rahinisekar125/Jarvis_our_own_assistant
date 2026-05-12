$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Pythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $Pythonw)) {
    throw "Missing virtual environment pythonw.exe at $Pythonw"
}

try {
    $OllamaReady = $false
    try {
        $Response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 2
        $OllamaReady = $Response.StatusCode -eq 200
    } catch {
        $OllamaReady = $false
    }

    if (-not $OllamaReady) {
        $Ollama = Get-Command "ollama.exe" -ErrorAction SilentlyContinue
        if ($Ollama) {
            Start-Process `
                -FilePath $Ollama.Source `
                -ArgumentList @("serve") `
                -WindowStyle Hidden
            Start-Sleep -Seconds 2
        }
    }
} catch {
    # Jarvis can still run in fallback mode if Ollama cannot be started.
}

$Existing = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq "pythonw.exe" -and
        $_.CommandLine -like "*jarvis_assistant*" -and
        (
            $_.CommandLine -like "*voice-supervisor*" -or
            $_.CommandLine -like "*--mode*voice*"
        )
    }

if ($Existing) {
    exit 0
}

Start-Process `
    -FilePath $Pythonw `
    -ArgumentList @("-m", "jarvis_assistant", "--mode", "voice-supervisor") `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden
