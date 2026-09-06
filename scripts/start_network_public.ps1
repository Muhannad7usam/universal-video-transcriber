param(
    [int]$Port = 8000,
    [switch]$LanOnly
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found at $python. Create it first with: python -m venv .venv"
}

# Find FFmpeg from PATH first, then from the user's Downloads\ffmpeg folder.
$ffmpegCommand = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpegCommand) {
    $ffmpegRoot = Join-Path $env:USERPROFILE "Downloads\ffmpeg"
    if (Test-Path $ffmpegRoot) {
        $ffmpegExe = Get-ChildItem $ffmpegRoot -Filter ffmpeg.exe -File -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($ffmpegExe) {
            $env:Path = "$($ffmpegExe.Directory.FullName);$env:Path"
        }
    }
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "FFmpeg was not found. Add its bin folder to PATH before starting the app."
}
if (-not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    throw "ffprobe was not found beside FFmpeg."
}

# Production/local-machine defaults. 0 = no application-level video duration cap.
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

Write-Host "Starting Universal Video Transcriber..." -ForegroundColor Cyan
$server = Start-Process \
    -FilePath $python \
    -ArgumentList @(
        "-m", "uvicorn", "web_app.main:app",
        "--host", "0.0.0.0",
        "--port", "$Port",
        "--proxy-headers",
        "--forwarded-allow-ips", "127.0.0.1"
    ) \
    -WorkingDirectory $root \
    -PassThru

try {
    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        if ($server.HasExited) {
            throw "Uvicorn stopped before becoming ready."
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/ready" -TimeoutSec 2
            if ($health.status -eq "ok") {
                $ready = $true
                break
            }
        } catch {
            # Keep waiting while the server starts.
        }
    }

    if (-not $ready) {
        throw "The application did not become ready on port $Port."
    }

    Write-Host ""
    Write-Host "Local:   http://127.0.0.1:$Port" -ForegroundColor Green

    try {
        $lan = Get-NetIPConfiguration |
            Where-Object { $_.IPv4DefaultGateway -and $_.IPv4Address } |
            ForEach-Object { $_.IPv4Address.IPAddress } |
            Where-Object { $_ -and $_ -notlike "169.254.*" } |
            Select-Object -First 1
        if ($lan) {
            Write-Host "LAN:     http://$lan`:$Port" -ForegroundColor Green
            Write-Host "If another LAN device cannot connect, run scripts\enable_lan_firewall.ps1 once as Administrator." -ForegroundColor DarkGray
        }
    } catch {
        Write-Host "LAN address could not be detected automatically." -ForegroundColor DarkGray
    }

    Write-Host ""
    Write-Host "Long-form mode: short + medium + long + extremely long videos" -ForegroundColor Green
    Write-Host "Duration cap: none | chunking starts at 1 hour | chunks: 30 min + 3 sec overlap" -ForegroundColor DarkGray

    if ($LanOnly) {
        Write-Host "LAN-only mode is active. Press Ctrl+C to stop." -ForegroundColor Yellow
        Wait-Process -Id $server.Id
        return
    }

    # Find or download cloudflared.
    $cloudflared = $null
    $cloudCommand = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cloudCommand) {
        $cloudflared = $cloudCommand.Source
    }

    if (-not $cloudflared) {
        $downloadCandidate = Join-Path $env:USERPROFILE "Downloads\cloudflared.exe"
        if (Test-Path $downloadCandidate) {
            $cloudflared = $downloadCandidate
        }
    }

    if (-not $cloudflared) {
        $toolDir = Join-Path $root ".tools"
        New-Item -ItemType Directory -Force -Path $toolDir | Out-Null
        $cloudflared = Join-Path $toolDir "cloudflared.exe"
        Write-Host "Downloading cloudflared..." -ForegroundColor Cyan
        Invoke-WebRequest \
            -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" \
            -OutFile $cloudflared \
            -UseBasicParsing
    }

    Write-Host ""
    Write-Host "Starting free public Cloudflare Quick Tunnel..." -ForegroundColor Cyan
    Write-Host "The public https://*.trycloudflare.com URL will appear below." -ForegroundColor Yellow
    Write-Host "Keep this window open. Press Ctrl+C to stop the public deployment." -ForegroundColor DarkGray
    Write-Host ""

    & $cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$Port"
}
finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    }
}
