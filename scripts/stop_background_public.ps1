$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runDir = Join-Path $root "data\background"
$pidFile = Join-Path $runDir "pids.json"

if (-not (Test-Path $pidFile)) {
    Write-Host "No background deployment PID file was found." -ForegroundColor Yellow
    exit 0
}

try {
    $state = Get-Content $pidFile -Raw | ConvertFrom-Json
} catch {
    throw "Could not read $pidFile"
}

foreach ($pid in @($state.cloudflared_pid, $state.uvicorn_pid)) {
    if ($pid) {
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped PID $pid ($($proc.ProcessName))"
        }
    }
}

Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
Write-Host "Background public deployment stopped." -ForegroundColor Green
