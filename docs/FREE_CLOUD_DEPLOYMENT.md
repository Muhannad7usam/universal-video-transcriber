# Free Cloud Deployment (No Credit Card)

This branch keeps the existing FastAPI web editor and moves Whisper inference to Cloudflare Workers AI so the app can run on a very small Back4app container.

## Architecture

Back4app Container -> yt-dlp/FFmpeg -> 15-minute MP3 audio chunks -> Cloudflare Workers AI whisper-large-v3-turbo -> merged transcript.

The laptop is not part of the runtime after deployment.

## Required environment variables

- TRANSCRIPTION_PROVIDER=cloudflare
- CLOUDFLARE_ACCOUNT_ID=<Cloudflare account ID>
- CLOUDFLARE_API_TOKEN=<Workers AI API token>
- MAX_VIDEO_DURATION_SECONDS=0
- CLOUD_CHUNK_SECONDS=900
- CLOUD_CHUNK_OVERLAP_SECONDS=3
- MAX_CONCURRENT_JOBS=1

Never commit a real Cloudflare token.

## Back4app

Deploy the `cloud-free-deploy` branch. The root directory is `/` and the Dockerfile is in the repository root. Enable auto-deploy only after the first successful deployment.

## Health check

Open `/ready`. A healthy cloud deployment reports:

- ffmpeg: true
- ffprobe: true
- yt_dlp: true
- transcription_engine: true
- transcription_provider: cloudflare

## Free-tier limits

Cloudflare Workers AI currently includes 10,000 free Neurons per day. `@cf/openai/whisper-large-v3-turbo` uses 46.63 Neurons per audio minute, so the theoretical maximum if every request uses Whisper is about 214 minutes of audio per UTC day. Videos that can use valid source captions do not need Whisper inference.

Back4app's free container is intended for testing/learning and currently provides 0.25 shared CPU, 256 MB RAM, and 100 GB transfer. Keep one background transcription job at a time.

## Long videos

The cloud path processes audio sequentially in 15-minute chunks with a 3-second overlap. Chunks are transcoded to mono 16 kHz 64 kbps MP3 to keep memory and request sizes small, sent one at a time, merged back onto the original timeline, and deleted immediately.

There is no application-level duration cap, but free Cloudflare AI quota, Back4app resources, source availability, and temporary disk space remain practical limits.
