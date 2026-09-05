from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "production"
    host: str = "0.0.0.0"
    port: int = 8000
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"
    max_playlist_items: int = 100
    max_video_duration_seconds: int = 14400
    max_concurrent_jobs: int = 2
    result_retention_days: int = 10
    cleanup_interval_hours: int = 24
    log_level: str = "INFO"
    data_dir: Path = Path("./data")
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    @property
    def temp_dir(self): return self.data_dir / "temp"
    @property
    def jobs_dir(self): return self.data_dir / "jobs"
    @property
    def results_dir(self): return self.data_dir / "results"
settings = Settings()
for p in (settings.temp_dir, settings.jobs_dir, settings.results_dir): p.mkdir(parents=True, exist_ok=True)
