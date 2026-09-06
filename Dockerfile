FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TRANSCRIPTION_PROVIDER=cloudflare \
    MAX_VIDEO_DURATION_SECONDS=0 \
    CLOUD_CHUNK_SECONDS=900 \
    CLOUD_CHUNK_OVERLAP_SECONDS=3 \
    MAX_CONCURRENT_JOBS=1 \
    YT_DLP_POT_PROVIDER_URL=http://127.0.0.1:4416

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates git nodejs npm \
    && git clone --depth 1 --branch 1.3.2 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /root/bgutil-ytdlp-pot-provider \
    && cd /root/bgutil-ytdlp-pot-provider/server \
    && npm ci \
    && npx tsc \
    && npm prune --omit=dev \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-cloud.txt ./requirements-cloud.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements-cloud.txt

COPY . .

RUN mkdir -p /app/data/temp /app/data/jobs /app/data/results /app/data/cache

EXPOSE 8080

CMD ["sh", "-c", "node /root/bgutil-ytdlp-pot-provider/server/build/main.js --host 127.0.0.1 --port 4416 & exec python -m uvicorn web_app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
