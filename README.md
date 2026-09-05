# Universal Video Transcriber

Local-first transcription for editors and technical users. Uses `yt-dlp`, available captions when usable, and local `faster-whisper` as the fallback. No transcription API key is required.

## CMD Edition

```text
transcribe "URL"
transcribe "PLAYLIST_URL" --video 7
transcribe "PLAYLIST_URL" --range 5 12
transcribe "PLAYLIST_URL" --first 10
transcribe "PLAYLIST_URL" --all
```

## Web Editor Edition

```text
uvicorn web_app.main:app --host 0.0.0.0 --port 8000
```

Paste a video or playlist link. Single videos start automatically; playlists show visual selection controls. Results support clean/timestamped views, copy, search, and EN/Egyptian Arabic UI.

## Architecture

`core/` contains URL security, metadata extraction, captions, audio extraction, Whisper, formatting, output, jobs and cleanup. `cmd_app/` is the CLI. `web_app/` is the FastAPI editor. Jobs use SQLite plus a bounded thread pool; playlist items are isolated jobs.

## Docker

```text
cp .env.example .env
docker compose up --build
```

The container includes FFmpeg and persists data plus the Whisper model cache through Docker volumes.

## Security

Only public HTTP(S) URLs are accepted. Credentials, localhost, private/link-local/reserved addresses and unsupported schemes are rejected. User input is passed to `yt-dlp` through its Python API, never shell concatenation. Generated paths are constrained to the configured data directory. DRM, login bypass and cookies are not supported.

The URL validation includes DNS resolution checks, but DNS rebinding cannot be completely eliminated when a third-party downloader resolves the host separately; deploy behind a network egress policy if this service is exposed publicly.

## Retention

Generated results are retained for up to 10 days. Temporary source media is removed after processing. The application runs safe cleanup daily and also exposes `python -m scripts.cleanup --dry-run` for inspection.

## CI

GitHub Actions compiles the package, installs FFmpeg and dependencies, and runs the test suite. CI does not download a Whisper model.

## Testing limitations

The included test suite covers security, subtitle normalization, formatting, jobs/cleanup, CLI parsing and web routes. A full live transcription test requires network access to a supported video site plus `yt-dlp` and `faster-whisper`; those external dependencies were not available in the development sandbox, so no live transcription result is claimed.

## Windows

`scripts/package_windows.ps1` documents the optional PyInstaller build path.

## Personal → Company Migration

No personal credentials or infrastructure are hard-coded. Move the repository, copy `.env.example` into the deployment environment, provision equivalent compute/storage, and redeploy.
