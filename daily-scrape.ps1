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

function Append-Output($items) {
    if ($items) {
        $items | ForEach-Object { Add-Content -Path $log -Value $_ -Encoding UTF8 }
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "  WARN: exit $LASTEXITCODE (step continues, see lines above)"
    }
}

Write-Log '=== Daily refresh start ==='
Write-Log "CWD: $(Get-Location)"

if (-not (Test-Path $python)) {
    Write-Log "ABORT: python venv not found at $python"
    exit 1
}

$sw = [System.Diagnostics.Stopwatch]::StartNew()

# Steps inlined intentionally — helper function with array param triggers PowerShell
# array-unwind semantics that dropped all but the first arg (see git history of this file).

Write-Log '[0/5] Discord notify (start)'
Append-Output (& $python -m scripts.notify_discord --start 2>&1)

Write-Log '[1/5] Scrape onbid (max-pages 10) + court (apply, all 수도권 sweep)'
Append-Output (& $python -m scraper.run --max-pages 10 2>&1)
Append-Output (& $python -m scraper_court.run --apply --max-pages 10 2>&1)

Write-Log '[2/5] Backfill building registry + Kakao geo + ODsay transit'
Append-Output (& $python -m scripts.backfill_all 2>&1)

Write-Log '[3/5] Backfill MOLIT real-estate prices / rental yield'
Append-Output (& $python -m scripts.backfill_realprice 2>&1)

Write-Log '[4/5] Backfill rights analysis + price prediction'
Append-Output (& $python -m scripts.backfill_analysis 2>&1)

Write-Log '[4.5/5] Sweep filters — drop drift rows (stricter criteria.yaml)'
Append-Output (& $python -m scripts.sweep_filters --apply --delete 2>&1)

$sw.Stop()
$dur = '{0}m {1}s' -f $sw.Elapsed.Minutes, $sw.Elapsed.Seconds

Write-Log "[5/5] Discord notify (duration $dur)"
Append-Output (& $python -m scripts.notify_discord $dur 2>&1)

Write-Log '[bonus] D-day reminder push (7-day horizon)'
Append-Output (& $python -m scripts.notify_dday --days 7 2>&1)

Write-Log "=== Daily refresh done ($dur) ==="
