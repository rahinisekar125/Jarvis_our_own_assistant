$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$RenderExe = Join-Path $ProjectRoot ".tools\render\cli_v2.16.0.exe"

if (-not (Test-Path $RenderExe)) {
    throw "Render CLI is not installed at $RenderExe"
}

& $RenderExe @args
