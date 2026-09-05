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

Paste a video or playlist link. Editors can choose the spoken/transcription language or leave **Auto Detect** enabled. The language selector is separate from the EN/Egyptian Arabic interface switch and remembers the editor's last choice in the browser.

For an explicitly selected language, the pipeline first looks for captions in that language. If matching captions are unavailable or cannot be fetched, it downloads the full selected video's audio and runs local Whisper with `task="transcribe"` and the requested language. Whisper's first pass uses full-audio mode (`vad_filter=False`) so VAD does not silently remove portions of the source.

Single videos start automatically; playlists show visual selection controls for one video, selected videos, a range, or the entire playlist. Results support clean/timestamped views, copy, search, language/method/coverage labels, and EN/Egyptian Arabic UI.

## Transcription Languages

The Web Editor exposes the Whisper-supported language list through `/api/languages`, including Arabic, English, French, Spanish, German, Italian, Portuguese, Turkish, Russian, Urdu, Hindi, Chinese, Japanese, Korean and more.

Use **Arabic — العربية** for primarily Arabic/Egyptian Arabic speech, **English** for primarily English speech, or **Auto Detect** when the spoken language is unknown or genuinely mixed.

The system transcribes; it does not translate between languages.

## Architecture

`core/` contains URL security, metadata extraction, captions, audio extraction, Whisper, formatting, output, jobs and cleanup. `cmd_app/` is the CLI. `web_app/` is the FastAPI editor. Jobs use SQLite plus a bounded thread pool; playlist items are isolated jobs.

`yt-dlp` receives the detected FFmpeg location when FFmpeg is available on the server PATH, avoiding post-processing failures caused by child-process PATH differences.

## Docker

```text
cp .env.example .env
docker compose up --build
```

The container includes FFmpeg and persists data plus the Whisper model cache through Docker volumes.

## Security

Only public HTTP(S) URLs are accepted. Credentials, localhost, private/link-local/reserved addresses and unsupported schemes are rejected. User input is passed to `yt-dlp` through its Python API, never shell concatenation. Generated paths are constrained to the configured data directory. DRM, login bypass and cookies are not supported.

The Web UI uses external/static JavaScript event listeners instead of inline handlers, so the strict `script-src 'self'` Content Security Policy can remain enabled.

The URL validation includes DNS resolution checks, but DNS rebinding cannot be completely eliminated when a third-party downloader resolves the host separately; deploy behind a network egress policy if this service is exposed publicly.

## Retention

Generated results are retained for up to 10 days. Temporary source media is removed after processing. The application runs safe cleanup daily and also exposes `python -m scripts.cleanup --dry-run` for inspection.

## Health

```text
GET /health
GET /ready
```

Healthy local output should report FFmpeg, yt-dlp and the transcription engine as available.

## CI

GitHub Actions compiles the package, installs FFmpeg and dependencies, and runs the test suite. CI does not download a Whisper model.

## Testing limitations

The included test suite covers security, preferred subtitle-language selection, formatting, jobs/cleanup, CLI parsing, Web routes and the language-list API. A full live transcription test requires network access to a supported video site plus `yt-dlp` and `faster-whisper`; local/editor validation should be used for live media.

## Windows

`scripts/package_windows.ps1` documents the optional PyInstaller build path.

For a local PowerShell session, verify:

```powershell
python -c "import shutil; print(shutil.which('ffmpeg'))"
python -c "import shutil; print(shutil.which('ffprobe'))"
```

Both should print real executable paths before starting Uvicorn.

## Personal → Company Migration

No personal credentials or infrastructure are hard-coded. Move the repository, copy `.env.example` into the deployment environment, provision equivalent compute/storage, and redeploy.
