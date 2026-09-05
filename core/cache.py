import hashlib
import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

from core.config import settings
from core.output.store import result_dir
from core.security.filenames import inside


def _key(url: str, requested_language: str | None) -> str:
    raw = "\0".join(
        (
            settings.transcription_cache_version,
            url.strip(),
            requested_language or "auto",
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_path(url: str, requested_language: str | None) -> Path:
    return settings.cache_dir / _key(url, requested_language)


def restore_cached_result(url: str, requested_language: str | None, job_id: str):
    source = _cache_path(url, requested_language)
    metadata_path = source / "metadata.json"
    transcript_path = source / "transcript.txt"
    if not metadata_path.is_file() or not transcript_path.is_file():
        return None

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.result_retention_days)
        modified = datetime.fromtimestamp(source.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            shutil.rmtree(source, ignore_errors=True)
            return None

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        title = metadata.get("title") or "Untitled video"
        destination = result_dir(title, job_id)
        for name in ("transcript.txt", "transcript_timestamped.txt"):
            src = source / name
            if src.is_file():
                shutil.copy2(src, destination / name)
        metadata["job_id"] = job_id
        metadata["cache_hit"] = True
        metadata["restored_at"] = datetime.now(timezone.utc).isoformat()
        (destination / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return metadata, destination
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def cache_result(url: str, requested_language: str | None, source_dir: Path):
    if not settings.transcription_cache_enabled:
        return
    source_dir = source_dir.resolve()
    if not inside(settings.results_dir, source_dir):
        return

    destination = _cache_path(url, requested_language)
    tmp = destination.with_name(destination.name + ".tmp")
    try:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True, exist_ok=True)
        for name in ("transcript.txt", "transcript_timestamped.txt", "metadata.json"):
            src = source_dir / name
            if src.is_file():
                shutil.copy2(src, tmp / name)
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        tmp.replace(destination)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)
