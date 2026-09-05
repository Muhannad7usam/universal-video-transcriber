# Universal Video Transcriber

Local-first video and playlist transcription for editors and technical users. It uses `yt-dlp`, safe original-language captions when they are usable, and local `faster-whisper` as the fallback. No transcription API key is required.

## Web Editor

```text
python -m uvicorn web_app.main:app --host 127.0.0.1 --port 8000
```

Paste a video or playlist link. Editors can choose the spoken language or leave **Auto Detect** enabled. The transcription-language selector is separate from the EN/Egyptian-Arabic interface switch and remembers the last browser choice.

Playlists support one video, arbitrary selected videos, a range, or the entire playlist. Results include clean and timestamped transcripts, copy controls, search, language/method/coverage labels, and live progress updates.

## CMD Edition

```text
python -m cmd_app "URL" --language ar
python -m cmd_app "PLAYLIST_URL" --video 7 --language ar
python -m cmd_app "PLAYLIST_URL" --range 5 12
python -m cmd_app "PLAYLIST_URL" --first 10
python -m cmd_app "PLAYLIST_URL" --all
```

## Performance + Accuracy Strategy

The pipeline is adaptive rather than forcing one slow path for every video:

1. Check the retention-scoped result cache. Repeating the same URL + language can return almost immediately.
2. Inspect captions and only trust a source-language track. Auto Detect never picks an arbitrary translated caption such as YouTube's alphabetically-first language.
3. Prefer JSON3/VTT caption formats and remove rolling-caption overlap/repetition.
4. If captions are missing, translated, incomplete, or unavailable, download the compressed audio stream directly instead of converting the whole source to WAV first.
5. Run `faster-whisper` with VAD, no translation, selected-language prompting, hallucination thresholds, and live segment progress.
6. Adaptive model selection uses `large-v3` on a working CUDA GPU for maximum multilingual accuracy and `large-v3-turbo` on CPU for a much better speed/accuracy balance than the previous medium/small path.
7. One heavy inference job runs per machine by default to avoid CPU/GPU contention. Deployments with more compute can override `MAX_CONCURRENT_JOBS`.

The first use of a Whisper model can take longer because its model files must be downloaded and loaded. Later runs reuse the local Hugging Face model cache.

## Languages

The Web Editor exposes the Whisper-supported language list through `/api/languages`, including Arabic, English, French, Spanish, German, Italian, Portuguese, Turkish, Russian, Urdu, Hindi, Chinese, Japanese, Korean, and more.

Use **Arabic — العربية** for primarily Arabic/Egyptian-Arabic speech, **English** for primarily English speech, or **Auto Detect** when the source language is unknown or genuinely mixed.

The system transcribes spoken content; it does not intentionally translate it.

## Progress

Single jobs and playlist groups use Server-Sent Events (SSE) for responsive progress without constant browser polling. Stages include cache lookup, caption checks, audio download, model loading, transcription, formatting, saving, and caching. Whisper segment timestamps advance the progress bar during transcription instead of leaving the UI stuck at a fixed percentage.

## Configuration

Copy `.env.example` to `.env` if you want overrides. Useful settings include:

```text
WHISPER_MODEL=auto
WHISPER_DEVICE=auto
WHISPER_COMPUTE_TYPE=auto
WHISPER_BEAM_SIZE=3
MAX_CONCURRENT_JOBS=1
TRANSCRIPTION_CACHE_ENABLED=true
RESULT_RETENTION_DAYS=10
```

## Security

Only public HTTP(S) URLs are accepted. Credentials, localhost, private/link-local/reserved addresses, and unsupported schemes are rejected. User URLs are passed to `yt-dlp` through its Python API rather than shell concatenation. Generated paths are constrained to the configured data directory. DRM/login bypass and cookies are not supported.

The Web UI uses external JavaScript event listeners, allowing a strict `script-src 'self'` Content Security Policy.

## Retention

Generated transcripts and the repeat-result cache are retained for up to 10 days. Temporary media is removed after processing. Cleanup runs periodically and can be inspected with:

```text
python -m scripts.cleanup --dry-run
```

The Whisper model cache is not part of generated user data and is not removed by result cleanup.

## Health

```text
GET /health
GET /ready
```

`/health` reports FFmpeg, yt-dlp, the transcription engine, and the adaptive runtime choice without loading a Whisper model.

## Windows

From the project folder:

```powershell
.\.venv\Scripts\Activate.ps1
$env:Path = "C:\path\to\ffmpeg\bin;$env:Path"
python -m uvicorn web_app.main:app --host 127.0.0.1 --port 8000
```

Verify FFmpeg when needed:

```powershell
python -c "import shutil; print(shutil.which('ffmpeg')); print(shutil.which('ffprobe'))"
```

## CI

GitHub Actions compiles the Python packages, installs FFmpeg/dependencies, and runs the unit tests. Live transcription is intentionally not part of CI because it depends on external media services and one-time Whisper model downloads.

## Personal → Company Migration

No personal credentials or machine-specific FFmpeg path is hard-coded. Move the repository, provide deployment environment variables, provision equivalent compute/storage, and redeploy.
