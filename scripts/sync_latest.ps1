$ErrorActionPreference = "Stop"

if (-not (Test-Path ".\requirements.txt")) {
    throw "Run this script from the Universal Video Transcriber project root."
}

$base = "https://raw.githubusercontent.com/Muhannad7usam/universal-video-transcriber/main"
$files = @(
    ".env.example",
    "core/cache.py",
    "core/config.py",
    "core/downloader/audio.py",
    "core/downloader/metadata.py",
    "core/output/store.py",
    "core/pipeline.py",
    "core/security/filenames.py",
    "core/subtitles/engine.py",
    "core/subtitles/normalize.py",
    "core/transcription/whisper_engine.py",
    "scripts/cleanup.py",
    "scripts/start_network_public.ps1",
    "scripts/start_background_public.ps1",
    "scripts/stop_background_public.ps1",
    "scripts/enable_lan_firewall.ps1",
    "web_app/main.py",
    "web_app/static/app.js",
    "web_app/templates/index.html",
    "tests/test_core.py",
    "tests/test_web.py",
    "cmd_app/__init__.py",
    "cmd_app/__main__.py",
    "cmd_app/commands.py",
    "README.md"
)

foreach ($relative in $files) {
    $destination = Join-Path (Get-Location) $relative
    $parent = Split-Path $destination -Parent
    if ($parent -and -not (Test-Path $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }

    $url = "$base/$($relative -replace '\\','/')"
    $temp = "$destination.download"
    Invoke-WebRequest -Uri $url -OutFile $temp -UseBasicParsing
    Move-Item -Force $temp $destination
    Write-Host "Updated $relative"
}

Write-Host ""
Write-Host "Running Python syntax check..."
python -m compileall -q core cmd_app web_app scripts
if ($LASTEXITCODE -ne 0) {
    throw "Python syntax check failed."
}

Write-Host "Update complete. Restart Uvicorn so the new code is loaded."
