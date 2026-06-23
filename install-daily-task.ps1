# install-daily-task.ps1 - Register BidScope daily refresh at 08:00 KST.
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\install-daily-task.ps1
#   powershell -ExecutionPolicy Bypass -File .\install-daily-task.ps1 -Uninstall
#
# Improvements over the old schtasks-based version:
#  - WakeToRun + StartWhenAvailable: PC sleeping at 08:00? wakes it; PC was off?
#    runs as soon as it's available. The old schtasks /sc DAILY /st 08:00 silently
#    skipped if the PC wasn't awake at the trigger moment.
#  - DontStopIfGoingOnBatteries / AllowStartIfOnBatteries: laptop-safe.
#  - ExecutionTimeLimit 2h: kills runaway jobs (typical refresh = 5-15 min).
#  - Runs as current user, Interactive Limited level — no admin elevation needed,
#    .venv / Kakao key / ODsay key all in scope.
#
# Verify after install:
#   schtasks /Query /TN "OnbidDailyScrape" /V /FO LIST
# Or via PowerShell:
#   Get-ScheduledTaskInfo -TaskName "OnbidDailyScrape"

param([switch]$Uninstall)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$daily = Join-Path $root 'daily-scrape.ps1'
$taskName = 'OnbidDailyScrape'

if ($Uninstall) {
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Removed: $taskName" -ForegroundColor Yellow
    } else {
        Write-Host "Not found: $taskName" -ForegroundColor DarkGray
    }
    return
}

if (-not (Test-Path $daily)) {
    Write-Host "ABORT: $daily not found" -ForegroundColor Red
    exit 1
}

# Always reinstall — picks up the latest options if this script changes.
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing task to reinstall with latest settings" -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-ExecutionPolicy Bypass -NonInteractive -WindowStyle Hidden -File `"$daily`"" `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -Daily -At 8:00am

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "BidScope daily refresh — onbid + court scrape + 5종 backfill + Discord notify. Re-run install-daily-task.ps1 to update." | Out-Null

$next = (Get-ScheduledTaskInfo -TaskName $taskName).NextRunTime

Write-Host ""
Write-Host "Installed: $taskName" -ForegroundColor Green
Write-Host "  Daily at 08:00 KST (WakeToRun + StartWhenAvailable)"
Write-Host "  Runs: $daily"
Write-Host "  As user: $env:USERNAME (Interactive, Limited)"
Write-Host "  Next scheduled: $next"
Write-Host ""
Write-Host "Verify:    schtasks /Query /TN `"$taskName`" /V /FO LIST" -ForegroundColor DarkGray
Write-Host "Run now:   schtasks /Run /TN `"$taskName`"" -ForegroundColor DarkGray
Write-Host "Uninstall: .\install-daily-task.ps1 -Uninstall" -ForegroundColor DarkGray
Write-Host "Logs:      .daily-scrape.log" -ForegroundColor DarkGray
