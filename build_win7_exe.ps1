param(
    [string]$WorkDir = "",
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($WorkDir)) {
    $WorkDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

if (-not (Test-Path $WorkDir)) {
    throw "WorkDir not found: $WorkDir"
}

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $candidate = Join-Path (Split-Path -Parent $WorkDir) "tools\python38\python.exe"
    if (Test-Path $candidate) {
        $PythonExe = $candidate
    } else {
        $PythonExe = "py"
    }
}

Push-Location $WorkDir
try {
    Write-Host "Using Python: $PythonExe"
    & $PythonExe -V

    & $PythonExe -m pip install --upgrade pip setuptools wheel
    & $PythonExe -m pip install "requests==2.32.3" "pyinstaller==5.13.2"

    & $PythonExe -m PyInstaller --clean --onefile --name CustomerHistorySync_Win7 full_customer_history_sync.py

    $distDir = Join-Path $WorkDir "dist"
    $exeSrc = Join-Path $distDir "CustomerHistorySync_Win7.exe"
    if (-not (Test-Path $exeSrc)) {
        throw "EXE not generated: $exeSrc"
    }

    $outDir = Join-Path $WorkDir "dist_win7"
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null

    Copy-Item $exeSrc (Join-Path $outDir "CustomerHistorySync_Win7.exe") -Force
    Copy-Item (Join-Path $WorkDir "config.json") (Join-Path $outDir "config.json") -Force
    Copy-Item (Join-Path $WorkDir "run_once.bat") (Join-Path $outDir "run_once.bat") -Force
    Copy-Item (Join-Path $WorkDir "setup_daily_task.ps1") (Join-Path $outDir "setup_daily_task.ps1") -Force
    Copy-Item (Join-Path $WorkDir "README.md") (Join-Path $outDir "README.md") -Force

    $zipPath = Join-Path $WorkDir ("dist_win7_history_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".zip")
    if (Test-Path $zipPath) {
        Remove-Item $zipPath -Force
    }
    Compress-Archive -Path (Join-Path $outDir "*") -DestinationPath $zipPath -Force

    Write-Host "Win7 package ready: $outDir"
    Write-Host "Win7 zip ready: $zipPath"
}
finally {
    Pop-Location
}
