$ErrorActionPreference = "Continue"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ProjectRootText = $ProjectRoot.Path.ToLowerInvariant()
$Stopped = New-Object System.Collections.Generic.List[int]

function Get-JarvisProcesses {
    Get-CimInstance Win32_Process |
        Where-Object {
            $commandLine = [string]$_.CommandLine
            $name = [string]$_.Name
            if (-not $commandLine) {
                return $false
            }

            $lowerCommand = $commandLine.ToLowerInvariant()
            $isPython = $name -like "python*.exe"
            $isProjectProcess = $lowerCommand.Contains($ProjectRootText)
            $isJarvisProcess = $lowerCommand.Contains("jarvis_assistant")

            return $isPython -and $isProjectProcess -and $isJarvisProcess
        }
}

for ($pass = 1; $pass -le 3; $pass++) {
    $processes = @(Get-JarvisProcesses | Sort-Object ParentProcessId -Descending)
    if ($processes.Count -eq 0) {
        break
    }

    foreach ($process in $processes) {
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
            if (-not $Stopped.Contains([int]$process.ProcessId)) {
                $Stopped.Add([int]$process.ProcessId) | Out-Null
            }
        } catch {
            # Process may have already exited between discovery and Stop-Process.
        }
    }

    Start-Sleep -Milliseconds 400
}

$Remaining = @(Get-JarvisProcesses)
if ($Remaining.Count -gt 0) {
    Write-Host "Some Jarvis processes are still running:"
    $Remaining | Select-Object ProcessId, Name, CommandLine | Format-Table -AutoSize
    exit 1
}

if ($Stopped.Count -eq 0) {
    Write-Host "Jarvis was already stopped."
} else {
    Write-Host "Jarvis stopped. Processes killed: $($Stopped -join ', ')"
}
