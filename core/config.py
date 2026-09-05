from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "production"
    host: str = "0.0.0.0"
    port: int = 8000

    # Adaptive quality/performance profile. The editor never needs to see these.
    # auto => CUDA: large-v3 for maximum accuracy; CPU: large-v3-turbo for a
    # much better speed/quality balance than medium while remaining multilingual.
    whisper_model: str = "auto"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"
    whisper_beam_size: int = 3
    whisper_vad_min_silence_ms: int = 450
    whisper_vad_speech_pad_ms: int = 220

    # Long-form handling. Short/medium videos run directly for minimum latency;
    # long/extremely-long videos are processed in bounded-memory chunks.
    # Set MAX_VIDEO_DURATION_SECONDS to 0 for no application-level duration cap.
    max_video_duration_seconds: int = 0
    long_video_chunk_threshold_seconds: int = 3600
    long_video_chunk_seconds: int = 1800
    long_video_chunk_overlap_seconds: int = 3

    max_playlist_items: int = 100

    # One heavy Whisper job at a time avoids CPU/GPU contention and usually
    # finishes each individual transcript faster. Override in deployment if the
    # machine has enough resources for parallel inference.
    max_concurrent_jobs: int = 1

    result_retention_days: int = 10
    cleanup_interval_hours: int = 24
    log_level: str = "INFO"
    data_dir: Path = Path("./data")

    # Repeated URL + language requests can be restored instantly. Bump the
    # version whenever transcription semantics change materially.
    transcription_cache_enabled: bool = True
    transcription_cache_version: str = "uvt-2026-09-05-longform-v1"

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
