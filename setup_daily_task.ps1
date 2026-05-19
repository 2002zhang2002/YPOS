param(
    [string]$TaskName = "POS_FullCustomer_History_Sync",
    [string]$RunTime = "01:30",
    [string]$WorkDir = "",
    [ValidateSet("auto", "daily", "backfill")]
    [string]$Mode = "auto"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($WorkDir)) {
    $WorkDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

if (-not (Test-Path $WorkDir)) {
    throw "WorkDir not found: $WorkDir"
}

$exePath = Join-Path $WorkDir "CustomerHistorySync_Win7.exe"
$pyScript = Join-Path $WorkDir "full_customer_history_sync.py"
$configPath = Join-Path $WorkDir "config.json"

if (-not (Test-Path $configPath)) {
    throw "config.json not found: $configPath"
}

if (Test-Path $exePath) {
    $action = New-ScheduledTaskAction -Execute $exePath -Argument "--config \"$configPath\" --mode $Mode" -WorkingDirectory $WorkDir
    $commandText = "$exePath --config $configPath --mode $Mode"
} else {
    if (-not (Test-Path $pyScript)) {
        throw "full_customer_history_sync.py not found: $pyScript"
    }

    $action = New-ScheduledTaskAction -Execute "py" -Argument "-3 \"$pyScript\" --config \"$configPath\" --mode $Mode" -WorkingDirectory $WorkDir
    $commandText = "py -3 $pyScript --config $configPath --mode $Mode"
}

$trigger = New-ScheduledTaskTrigger -Daily -At $RunTime
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 8)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "POS full customer history sync" -Force | Out-Null

Write-Host "Task created/updated: $TaskName"
Write-Host "Run time: $RunTime"
Write-Host "Mode: $Mode"
Write-Host "WorkDir: $WorkDir"
Write-Host "Command: $commandText"
Write-Host ""
Write-Host "Delete command:"
Write-Host "Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
