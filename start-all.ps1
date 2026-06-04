# start-all.ps1 - Scrape + backfill, then launch backend + frontend + Cloudflare Tunnel (background, hidden).
# Usage:  powershell -ExecutionPolicy Bypass -File .\start-all.ps1
#         powershell -ExecutionPolicy Bypass -File .\start-all.ps1 -SkipScrape   (skip data collection)
# Stop:   powershell -ExecutionPolicy Bypass -File .\stop-all.ps1
# Logs:   .backend.log  .frontend.log  .cloudflared.log  (in this folder)

param([switch]$SkipScrape)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$cloudflared = Join-Path $env:USERPROFILE 'cloudflared.exe'
$pidFile = Join-Path $root '.run-pids.txt'
$cfLog = Join-Path $root '.cloudflared.log'

Write-Host ''
Write-Host '=== Onbid Auction - start all (background) ===' -ForegroundColor Cyan

# 0) Scrape listings + backfill (building registry + ODsay). Runs in foreground (a few minutes).
if (-not $SkipScrape) {
    if (-not (Test-Path $python)) {
        Write-Host "python venv not found at $python" -ForegroundColor Red
        return
    }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    Write-Host '[0/3] Scraping listings (this takes a few minutes)...' -ForegroundColor Cyan
    & $python -m scraper.run --max-pages 10
    Write-Host '[0/3] Backfilling court property photos (image_url IS NULL only)...' -ForegroundColor Cyan
    & $python -m scripts.backfill_court_photos
    Write-Host '[0/3] Backfilling building registry + ODsay transit...' -ForegroundColor Cyan
    & $python -m scripts.backfill_all
    Write-Host '[0/3] Backfilling MOLIT real estate prices / rental yield...' -ForegroundColor Cyan
    & $python -m scripts.backfill_realprice
    Write-Host '[0/3] Backfilling rights analysis + price prediction...' -ForegroundColor Cyan
    & $python -m scripts.backfill_analysis
    $sw.Stop()
    $dur = '{0}m {1}s' -f $sw.Elapsed.Minutes, $sw.Elapsed.Seconds
    Write-Host "[0/3] Scrape + backfill done ($dur) - sending Discord notification" -ForegroundColor Cyan
    & $python -m scripts.notify_discord $dur
} else {
    Write-Host '[0/3] Skipping scrape (-SkipScrape)' -ForegroundColor DarkGray
}

$pids = @()

# 1) Backend (FastAPI :8000) - hidden, logs to .backend.log
Write-Host '[1/3] Backend  (FastAPI :8000)' -ForegroundColor Cyan
$pids += (Start-Process powershell -WindowStyle Hidden -PassThru -ArgumentList `
    '-Command', "cd '$root'; .\.venv\Scripts\uvicorn.exe api.main:app --port 8000 *> '$root\.backend.log'").Id

# 2) Frontend (Vite :5173) - hidden, logs to .frontend.log
Write-Host '[2/3] Frontend (Vite :5173)' -ForegroundColor Cyan
$pids += (Start-Process powershell -WindowStyle Hidden -PassThru -ArgumentList `
    '-Command', "cd '$root\web'; npm run dev *> '$root\.frontend.log'").Id

Start-Sleep -Seconds 5

# 3) Cloudflare Tunnel - hidden, logs to .cloudflared.log
if (-not (Test-Path $cloudflared)) {
    Write-Host "cloudflared not found at $cloudflared" -ForegroundColor Red
    Write-Host 'Download: https://github.com/cloudflare/cloudflared/releases/latest' -ForegroundColor Yellow
    $pids | Set-Content $pidFile
    return
}
Write-Host '[3/3] Cloudflare Tunnel' -ForegroundColor Cyan
if (Test-Path $cfLog) { Remove-Item $cfLog -Force }
$pids += (Start-Process powershell -WindowStyle Hidden -PassThru -ArgumentList `
    '-Command', "& '$cloudflared' tunnel --url http://localhost:5173 *> '$cfLog'").Id

# Save PIDs for stop-all.ps1
$pids | Set-Content $pidFile

# Poll the log for the public URL (up to 30s)
Write-Host ''
Write-Host 'Waiting for tunnel URL...' -ForegroundColor Yellow
$url = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $cfLog) {
        $m = Select-String -Path $cfLog -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value; break }
    }
}

Write-Host ''
if ($url) {
    Write-Host '========================================================' -ForegroundColor Green
    Write-Host '  PUBLIC URL:' -ForegroundColor Green
    Write-Host "  $url" -ForegroundColor White
    Write-Host '========================================================' -ForegroundColor Green
    try { Set-Clipboard -Value $url; Write-Host '(copied to clipboard)' -ForegroundColor DarkGray } catch {}
    Write-Host ''
    Write-Host 'NOTE: register this host in NCP console for Naver Maps' -ForegroundColor Yellow
    Write-Host '      (AI-NAVER API > Maps App > Web service URL).' -ForegroundColor Yellow
} else {
    Write-Host 'Could not auto-detect URL. Check .cloudflared.log' -ForegroundColor Red
}
Write-Host ''
Write-Host "All 3 services running in background. PIDs saved to .run-pids.txt" -ForegroundColor DarkGray
Write-Host "Stop with:  powershell -ExecutionPolicy Bypass -File .\stop-all.ps1" -ForegroundColor DarkGray
