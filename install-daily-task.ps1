# install-daily-task.ps1 - Register the daily auction refresh task at 08:00.
# Usage:  powershell -ExecutionPolicy Bypass -File .\install-daily-task.ps1
# Remove: schtasks /delete /tn "OnbidDailyScrape" /f

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$scriptPath = Join-Path $root 'daily-scrape.ps1'
$taskName = 'OnbidDailyScrape'

if (-not (Test-Path $scriptPath)) {
    Write-Host "ABORT: daily-scrape.ps1 not found at $scriptPath" -ForegroundColor Red
    exit 1
}

# The TR string must be a single token to schtasks; quote the inner -File path.
$tr = "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

Write-Host "Registering '$taskName' to run daily at 08:00..." -ForegroundColor Cyan
schtasks /create /tn $taskName /tr $tr /sc DAILY /st 08:00 /f
if ($LASTEXITCODE -ne 0) {
    Write-Host "schtasks /create failed (exit $LASTEXITCODE)" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ''
Write-Host 'Verification:' -ForegroundColor Cyan
schtasks /query /tn $taskName /fo LIST | Select-Object -First 12

Write-Host ''
Write-Host "Done. Trigger now:    schtasks /run /tn $taskName" -ForegroundColor Green
Write-Host "Disable temporarily:  schtasks /change /tn $taskName /disable" -ForegroundColor DarkGray
Write-Host "Remove:               schtasks /delete /tn $taskName /f" -ForegroundColor DarkGray
Write-Host "Logs:                 .daily-scrape.log" -ForegroundColor DarkGray
