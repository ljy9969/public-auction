# daily-scrape.ps1 - Daily auction data refresh (scrape + backfills + Discord notify).
# Registered to run at 08:00 daily via Task Scheduler (see install-daily-task.ps1).
# Strictly ASCII English - PowerShell 5.1 cp949 fallback safe.
# Logs to .daily-scrape.log.

$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$log = Join-Path $root '.daily-scrape.log'

# CRITICAL: Task Scheduler launches scripts from C:\Windows\System32 by default.
# Without cd to $root, `python -m scraper.run` cannot find the scraper package.
Set-Location $root

function Write-Log($msg) {
    $line = "{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $msg
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding UTF8
}

function Run-Step($label, $args) {
    Write-Log $label
    $stepOut = & $python @args 2>&1
    $stepOut | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding UTF8 }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "  WARN: exit $LASTEXITCODE (step continues, see lines above)"
        return $false
    }
    return $true
}

Write-Log '=== Daily refresh start ==='
Write-Log "CWD: $(Get-Location)"

if (-not (Test-Path $python)) {
    Write-Log "ABORT: python venv not found at $python"
    exit 1
}

$sw = [System.Diagnostics.Stopwatch]::StartNew()

Run-Step '[1/5] Scrape listings (max-pages 10)' @('-m', 'scraper.run', '--max-pages', '10') | Out-Null
Run-Step '[2/5] Backfill building registry + Kakao geo + ODsay transit' @('-m', 'scripts.backfill_all') | Out-Null
Run-Step '[3/5] Backfill MOLIT real-estate prices / rental yield' @('-m', 'scripts.backfill_realprice') | Out-Null
Run-Step '[4/5] Backfill rights analysis + price prediction' @('-m', 'scripts.backfill_analysis') | Out-Null

$sw.Stop()
$dur = '{0}m {1}s' -f $sw.Elapsed.Minutes, $sw.Elapsed.Seconds
Run-Step "[5/5] Discord notify (duration $dur)" @('-m', 'scripts.notify_discord', $dur) | Out-Null
Run-Step '[bonus] D-day reminder push (7-day horizon)' @('-m', 'scripts.notify_dday', '--days', '7') | Out-Null

Write-Log "=== Daily refresh done ($dur) ==="
