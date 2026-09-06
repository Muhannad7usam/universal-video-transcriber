param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found at $python"
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    $ffmpegRoot = Join-Path $env:USERPROFILE "Downloads\ffmpeg"
    if (Test-Path $ffmpegRoot) {
        $ffmpegExe = Get-ChildItem $ffmpegRoot -Filter ffmpeg.exe -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($ffmpegExe) {
            $env:Path = "$($ffmpegExe.Directory.FullName);$env:Path"
        }
    }
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "FFmpeg was not found."
}
if (-not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    throw "ffprobe was not found."
}

$env:APP_ENV = "production"
$env:HOST = "0.0.0.0"
$env:PORT = "$Port"
$env:WHISPER_MODEL = "auto"
$env:WHISPER_DEVICE = "auto"
$env:WHISPER_COMPUTE_TYPE = "auto"
$env:MAX_VIDEO_DURATION_SECONDS = "0"
$env:LONG_VIDEO_CHUNK_THRESHOLD_SECONDS = "3600"
$env:LONG_VIDEO_CHUNK_SECONDS = "1800"
$env:LONG_VIDEO_CHUNK_OVERLAP_SECONDS = "3"
$env:MAX_CONCURRENT_JOBS = "1"
$env:RESULT_RETENTION_DAYS = "10"
$env:CLEANUP_INTERVAL_HOURS = "24"
$env:TRANSCRIPTION_CACHE_ENABLED = "true"

$runDir = Join-Path $root "data\background"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$serverOut = Join-Path $runDir "uvicorn.out.log"
$serverErr = Join-Path $runDir "uvicorn.err.log"
$cloudOut = Join-Path $runDir "cloudflared.out.log"
$cloudErr = Join-Path $runDir "cloudflared.err.log"
$pidFile = Join-Path $runDir "pids.json"
$urlFile = Join-Path $runDir "public_url.txt"

Remove-Item $serverOut,$serverErr,$cloudOut,$cloudErr,$urlFile -Force -ErrorAction SilentlyContinue

if (Test-Path $pidFile) {
    try {
        $old = Get-Content $pidFile -Raw | ConvertFrom-Json
        $alive = @()
        foreach ($processId in @($old.uvicorn_pid, $old.cloudflared_pid)) {
            if ($processId) {
                $p = Get-Process -Id $processId -ErrorAction SilentlyContinue
                if ($p) { $alive += $processId }
            }
        }
        if ($alive.Count -gt 0) {
            throw "Background deployment is already running. Run scripts\stop_background_public.ps1 first."
        }
    } catch {
        if ($_.Exception.Message -like "Background deployment is already running*") { throw }
    }
}

$serverArgs = @(
    "-m", "uvicorn", "web_app.main:app",
    "--host", "0.0.0.0",
    "--port", "$Port",
    "--proxy-headers",
    "--forwarded-allow-ips", "127.0.0.1"
)
$serverStart = @{
    FilePath = $python
    ArgumentList = $serverArgs
    WorkingDirectory = $root
    WindowStyle = "Hidden"
    RedirectStandardOutput = $serverOut
    RedirectStandardError = $serverErr
    PassThru = $true
}
$server = Start-Process @serverStart

$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    if ($server.HasExited) {
        throw "Uvicorn exited during startup. Check $serverErr"
    }
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/ready" -TimeoutSec 2
        if ($health.status -eq "ok") {
            $ready = $true
            break
        }
    } catch {}
}
if (-not $ready) {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    throw "Application did not become ready on port $Port."
}

$cloudflared = $null
$cloudCommand = Get-Command cloudflared -ErrorAction SilentlyContinue
if ($cloudCommand) { $cloudflared = $cloudCommand.Source }
if (-not $cloudflared) {
    $candidate = Join-Path $env:USERPROFILE "Downloads\cloudflared.exe"
    if (Test-Path $candidate) { $cloudflared = $candidate }
}
if (-not $cloudflared) {
    $toolDir = Join-Path $root ".tools"
    New-Item -ItemType Directory -Force -Path $toolDir | Out-Null
    $cloudflared = Join-Path $toolDir "cloudflared.exe"
    Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $cloudflared -UseBasicParsing
}

$cloudArgs = @("tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$Port")
$cloudStart = @{
    FilePath = $cloudflared
    ArgumentList = $cloudArgs
    WorkingDirectory = $root
    WindowStyle = "Hidden"
    RedirectStandardOutput = $cloudOut
    RedirectStandardError = $cloudErr
    PassThru = $true
}
$cloud = Start-Process @cloudStart

$url = $null
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    if ($cloud.HasExited) {
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
        throw "cloudflared exited during startup. Check $cloudErr"
    }

    $combined = ""
    if (Test-Path $cloudOut) { $combined += (Get-Content $cloudOut -Raw -ErrorAction SilentlyContinue) }
    if (Test-Path $cloudErr) { $combined += "`n" + (Get-Content $cloudErr -Raw -ErrorAction SilentlyContinue) }
    $match = [regex]::Match($combined, 'https://[a-z0-9-]+\.trycloudflare\.com')
    if ($match.Success) {
        $url = $match.Value
        break
    }
}

@{
    uvicorn_pid = $server.Id
    cloudflared_pid = $cloud.Id
    port = $Port
    started_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content $pidFile -Encoding UTF8

if ($url) {
    $url | Set-Content $urlFile -Encoding UTF8
    Write-Host ""
    Write-Host "Background public deployment is running." -ForegroundColor Green
    Write-Host "Public: $url" -ForegroundColor Green
    Write-Host "Local:  http://127.0.0.1:$Port" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "You can now close this PowerShell window. The background processes will keep running while Windows stays on." -ForegroundColor Yellow
    Write-Host "Saved URL: $urlFile" -ForegroundColor DarkGray
    Write-Host "Stop later with: powershell -ExecutionPolicy Bypass -File .\scripts\stop_background_public.ps1" -ForegroundColor DarkGray
} else {
    Write-Host "Background processes started, but the Quick Tunnel URL was not detected yet." -ForegroundColor Yellow
    Write-Host "Check: $cloudErr" -ForegroundColor DarkGray
}
