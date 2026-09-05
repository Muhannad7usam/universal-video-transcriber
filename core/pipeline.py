import shutil
import time

from core.cache import cache_result, restore_cached_result
from core.config import settings
from core.downloader.metadata import extract_info, platform_name
from core.subtitles.engine import find_usable_caption, download_caption
from core.subtitles.normalize import normalize_segments
from core.downloader.audio import download_audio
from core.transcription.whisper_engine import transcribe_audio
from core.formatting.transcript import (
    clean_transcript,
    timestamped_transcript,
    language_label,
)
from core.output.store import save_result
from core.security.filenames import inside


def duration_tier(duration: float | int | None) -> str:
    """Human-facing duration class used only to describe processing strategy."""
    if duration is None:
        return "unknown"
    seconds = max(0.0, float(duration))
    if seconds < 15 * 60:
        return "short"
    if seconds < 60 * 60:
        return "medium"
    if seconds < 4 * 60 * 60:
        return "long"
    return "extremely_long"


def _base_language(value: str | None) -> str | None:
    if not value:
        return None
    return value.lower().replace("_", "-").split("-")[0]


def _caption_output_looks_usable(segments, clean: str, duration: float | None) -> bool:
    if not segments or not clean.strip():
        return False

    words = [w for w in clean.split() if w.strip()]
    if len(words) < 3:
        return False

    # Reject obviously incomplete caption tracks, but do not penalize naturally
    # sparse speech too aggressively.
    if duration and duration >= 120:
        minutes = duration / 60
        if len(words) / max(minutes, 1) < 4:
            return False

    texts = [s.get("text", "").strip() for s in segments if s.get("text", "").strip()]
    if len(texts) >= 8:
        unique_ratio = len(set(texts)) / len(texts)
        if unique_ratio < 0.35:
            return False

    return True


def run_job(
    job_id,
    url,
    store,
    progress=lambda p, s: None,
    requested_language: str | None = None,
):
    started = time.monotonic()
    work = settings.temp_dir / job_id
    work.mkdir(parents=True, exist_ok=True)

    try:
        progress(2, "checking_cache")
        if settings.transcription_cache_enabled:
            cached = restore_cached_result(url, requested_language, job_id)
            if cached:
                metadata, result_path = cached
                language = metadata.get("language") or "Unknown"
                method = metadata.get("method") or "cached"
                store.update(
                    job_id,
                    state="completed",
                    progress=100,
                    language=language,
                    method=method,
                    result_dir=str(result_path),
                )
                progress(100, "completed")
                return

        progress(5, "analyzing")
        info = extract_info(url, flat=False)
        title = info.get("title") or "Untitled video"
        duration = info.get("duration")
        tier = duration_tier(duration)

        # Zero means unlimited. A deployment can still opt into an explicit cap
        # without changing code, but the default product supports extremely long
        # videos and lets the chunked transcription engine bound memory use.
        if (
            duration
            and settings.max_video_duration_seconds > 0
            and duration > settings.max_video_duration_seconds
        ):
            raise ValueError("Video exceeds the configured duration limit.")

        platform = platform_name(info)
        method = None
        clean = ""
        timestamped = ""
        segments = []
        language_code = requested_language
        model = None
        device = None
        confidence = None
        chunked = False

        progress(12, "checking_captions")
        cap = find_usable_caption(info, requested_language)

        if cap:
            try:
                progress(16, "downloading_captions")
                caption_path = download_caption(
                    url,
                    work / "captions",
                    cap["language"],
                )
                if caption_path:
                    progress(22, "cleaning_captions")
                    segments = normalize_segments(caption_path)
                    clean = clean_transcript(segments)
                    language_code = requested_language or _base_language(cap["language"])

                    if _caption_output_looks_usable(segments, clean, duration):
                        method = (
                            "manual captions"
                            if cap["kind"] == "subtitles"
                            else "auto captions"
                        )
                        timestamped = timestamped_transcript(segments)
                    else:
                        clean = ""
                        timestamped = ""
                        segments = []
            except Exception:
                clean = ""
                timestamped = ""
                segments = []

        if not clean:
            method = "whisper"

            def download_progress(ratio: float):
                progress(25 + int(max(0.0, min(1.0, ratio)) * 20), "downloading_audio")

            progress(25, "downloading_audio")
            audio = download_audio(url, work / "audio", download_progress)

            progress(48, "loading_model")

            def transcription_progress(ratio: float):
                progress(52 + int(max(0.0, min(1.0, ratio)) * 32), "transcribing")

            result = transcribe_audio(
                audio,
                requested_language,
                duration=duration,
                progress_callback=transcription_progress,
            )
            language_code = result["language"] or requested_language
            segments = result["segments"]
            model = result.get("model")
            device = result.get("device")
            confidence = result.get("confidence")
            chunked = bool(result.get("chunked"))
            if not duration and result.get("duration"):
                duration = result["duration"]
                tier = duration_tier(duration)

            progress(86, "formatting")
            clean = clean_transcript(segments)
            timestamped = timestamped_transcript(segments)

            if not clean.strip():
                raise RuntimeError(
                    "Transcription completed but no usable speech was detected."
                )
        else:
            progress(86, "formatting")

        language = language_label(language_code)
        processing_seconds = round(time.monotonic() - started, 3)

        progress(92, "saving")
        result_path = save_result(
            title=title,
            url=url,
            platform=platform,
            language=language,
            requested_language=requested_language,
            method=method,
            model=model,
            device=device,
            confidence=confidence,
            processing_seconds=processing_seconds,
            duration_seconds=duration,
            duration_tier=tier,
            chunked=chunked,
            segments=segments,
            clean=clean,
            timestamped=timestamped,
            job_id=job_id,
        )

        progress(96, "caching")
        cache_result(url, requested_language, result_path)

        store.update(
            job_id,
            state="completed",
            progress=100,
            language=language,
            method=method,
            result_dir=str(result_path),
        )
        progress(100, "completed")

    except Exception as exc:
        store.update(job_id, state="failed", error=str(exc), progress=100)
        progress(100, "failed")

    finally:
        if inside(settings.temp_dir, work):
            shutil.rmtree(work, ignore_errors=True)
