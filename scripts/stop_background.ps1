$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $Root "runtime"
$InfoPath = Join-Path $Runtime "server.json"

if (-not (Test-Path -LiteralPath $InfoPath)) {
    Write-Host "No running instance file found." -ForegroundColor Yellow
    exit 0
}

try {
    $info = Get-Content -LiteralPath $InfoPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Host "Runtime file is damaged: $InfoPath" -ForegroundColor Red
    exit 1
}

$process = Get-Process -Id $info.pid -ErrorAction SilentlyContinue
if (-not $process) {
    Write-Host "Process $($info.pid) is not running. Cleaning runtime files." -ForegroundColor Yellow
    Remove-Item -LiteralPath $InfoPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $Runtime "port.txt") -Force -ErrorAction SilentlyContinue
    exit 0
}

if ($process.ProcessName -notlike "python*") {
    Write-Host "PID $($info.pid) is '$($process.ProcessName)', not python. Refusing to kill it." -ForegroundColor Red
    exit 1
}

Stop-Process -Id $info.pid -Force
Start-Sleep -Milliseconds 500
Remove-Item -LiteralPath $InfoPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $Runtime "port.txt") -Force -ErrorAction SilentlyContinue
Write-Host "CATL-CFBC stopped (PID $($info.pid))." -ForegroundColor Green
