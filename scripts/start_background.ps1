param(
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
$Runtime = Join-Path $Root "runtime"
New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
$InfoPath = Join-Path $Runtime "server.json"

function Get-RunningInfo {
    if (-not (Test-Path -LiteralPath $InfoPath)) { return $null }
    try {
        $info = Get-Content -LiteralPath $InfoPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $info.port) { return $null }
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$($info.port)/api/health" -TimeoutSec 2
        if ($health.ok -and $health.app -eq "CATL-CFBC") { return $info }
    } catch {
        return $null
    }
    return $null
}

$running = Get-RunningInfo
if (-not $running) {
    $python = (Get-Command python -ErrorAction Stop).Source
    $outLog = Join-Path $Runtime "server.stdout.log"
    $errLog = Join-Path $Runtime "server.stderr.log"
    Start-Process -FilePath $python -ArgumentList "app.py" -WorkingDirectory $Root `
        -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog | Out-Null

    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 400
        $running = Get-RunningInfo
        if ($running) { break }
    }
}

if (-not $running) {
    Write-Host "Start failed. Check runtime\server.stderr.log" -ForegroundColor Red
    $errLog = Join-Path $Runtime "server.stderr.log"
    if (Test-Path -LiteralPath $errLog) {
        Get-Content -LiteralPath $errLog -Tail 20
    }
    exit 1
}

Write-Host ""
Write-Host "CATL-CFBC is running" -ForegroundColor Green
foreach ($url in $running.urls) {
    Write-Host "  $url"
}
Write-Host ""
Write-Host "Port : $($running.port)"
Write-Host "Data : $($running.db)"
Write-Host "Stop : scripts\stop_background.ps1"
Write-Host ""

if ($OpenBrowser) {
    Start-Process $running.urls[0] | Out-Null
}
