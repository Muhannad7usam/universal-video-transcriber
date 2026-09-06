from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "production"
    host: str = "0.0.0.0"
    port: int = 8000

    # Transcription provider:
    # local -> faster-whisper on the machine
    # cloudflare -> Cloudflare Workers AI Whisper through the REST API
    transcription_provider: str = "local"

    # Local adaptive quality/performance profile.
    whisper_model: str = "auto"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"
    whisper_beam_size: int = 3
    whisper_vad_min_silence_ms: int = 450
    whisper_vad_speech_pad_ms: int = 220

    # Cloudflare Workers AI credentials. Keep the token only in deployment
    # environment variables; never commit a real secret to the repository.
    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None
    cloud_chunk_seconds: int = 900
    cloud_chunk_overlap_seconds: int = 3
    cloudflare_request_timeout_seconds: int = 600
    cloudflare_inter_chunk_delay_seconds: float = 0.2

    # Long-form handling. Zero means no application-level duration cap.
    max_video_duration_seconds: int = 0
    long_video_chunk_threshold_seconds: int = 3600
    long_video_chunk_seconds: int = 1800
    long_video_chunk_overlap_seconds: int = 3

    max_playlist_items: int = 100
    max_concurrent_jobs: int = 1

    result_retention_days: int = 10
    cleanup_interval_hours: int = 24
    log_level: str = "INFO"
    data_dir: Path = Path("./data")

    transcription_cache_enabled: bool = True
    transcription_cache_version: str = "uvt-2026-09-06-cloudflare-v1"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def temp_dir(self):
        return self.data_dir / "temp"

    @property
    def jobs_dir(self):
        return self.data_dir / "jobs"

    @property
    def results_dir(self):
        return self.data_dir / "results"

    @property
    def cache_dir(self):
        return self.data_dir / "cache"


settings = Settings()
for p in (
    settings.temp_dir,
    settings.jobs_dir,
    settings.results_dir,
    settings.cache_dir,
):
    p.mkdir(parents=True, exist_ok=True)
