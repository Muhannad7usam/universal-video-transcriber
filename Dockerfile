FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TRANSCRIPTION_PROVIDER=cloudflare \
    MAX_VIDEO_DURATION_SECONDS=0 \
    CLOUD_CHUNK_SECONDS=900 \
    CLOUD_CHUNK_OVERLAP_SECONDS=3 \
    MAX_CONCURRENT_JOBS=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-cloud.txt ./requirements-cloud.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements-cloud.txt

COPY . .

RUN mkdir -p /app/data/temp /app/data/jobs /app/data/results /app/data/cache

EXPOSE 8080

CMD ["sh", "-c", "python -m uvicorn web_app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
