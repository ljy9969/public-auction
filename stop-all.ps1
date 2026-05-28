# stop-all.ps1 - Stop the background services started by start-all.ps1
# Usage:  powershell -ExecutionPolicy Bypass -File .\stop-all.ps1

$root = $PSScriptRoot
$pidFile = Join-Path $root '.run-pids.txt'

if (-not (Test-Path $pidFile)) {
    Write-Host 'No .run-pids.txt found - nothing to stop.' -ForegroundColor Yellow
    return
}

Write-Host 'Stopping background services...' -ForegroundColor Cyan
Get-Content $pidFile | ForEach-Object {
    $procId = $_.Trim()
    if ($procId) {
        # /T kills the whole process tree (powershell wrapper + node/uvicorn/cloudflared children)
        taskkill /PID $procId /T /F 2>$null | Out-Null
        Write-Host "  killed PID $procId (and children)" -ForegroundColor DarkGray
    }
}
Remove-Item $pidFile -Force
Write-Host 'Done.' -ForegroundColor Green
