# daily-scrape.ps1 - Daily auction data refresh (scrape + backfills + Discord notify).
# Registered to run at 08:00 daily via Task Scheduler (see install-daily-task.ps1).
# Strictly ASCII English - PowerShell 5.1 cp949 fallback safe.
# Logs to .daily-scrape.log.

$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$log = Join-Path $root '.daily-scrape.log'

function Write-Log($msg) {
    $line = "{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $msg
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding UTF8
}

Write-Log '=== Daily refresh start ==='

if (-not (Test-Path $python)) {
    Write-Log "ABORT: python venv not found at $python"
    exit 1
}

$sw = [System.Diagnostics.Stopwatch]::StartNew()

Write-Log '[1/5] Scrape listings (max-pages 10)'
& $python -m scraper.run --max-pages 10 *>&1 | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding UTF8 }

Write-Log '[2/5] Backfill building registry + Kakao geo + ODsay transit'
& $python -m scripts.backfill_all *>&1 | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding UTF8 }

Write-Log '[3/5] Backfill MOLIT real-estate prices / rental yield'
& $python -m scripts.backfill_realprice *>&1 | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding UTF8 }

Write-Log '[4/5] Backfill rights analysis + price prediction'
& $python -m scripts.backfill_analysis *>&1 | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding UTF8 }

$sw.Stop()
$dur = '{0}m {1}s' -f $sw.Elapsed.Minutes, $sw.Elapsed.Seconds
Write-Log "[5/5] Discord notify (duration $dur)"
& $python -m scripts.notify_discord $dur *>&1 | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding UTF8 }

# D-day push: upcoming bids in 7 days
Write-Log '[bonus] D-day reminder push (7-day horizon)'
& $python -m scripts.notify_dday --days 7 *>&1 | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding UTF8 }

Write-Log "=== Daily refresh done ($dur) ==="
