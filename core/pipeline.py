import shutil

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
    format_caption_text,
)
from core.output.store import save_result
from core.security.filenames import inside


def run_job(job_id, url, store, progress=lambda p, s: None, requested_language: str | None = None):
    work = settings.temp_dir / job_id
    work.mkdir(parents=True, exist_ok=True)

    try:
        progress(5, "analyzing")
        info = extract_info(url, flat=False)
        title = info.get("title") or "Untitled video"
        duration = info.get("duration")

        if duration and duration > settings.max_video_duration_seconds:
            raise ValueError("Video exceeds the configured duration limit.")

        platform = platform_name(info)
        method = "captions"
        progress(15, "fetching_captions")

        cap = find_usable_caption(info, requested_language)
        clean = ""
        segments = []
        language_code = None

        if cap:
            try:
                caption_path = download_caption(
                    url,
                    work / "captions",
                    requested_language or cap[1],
                )
                if caption_path:
                    segments = normalize_segments(caption_path)
                    clean = format_caption_text(
                        " ".join(segment["text"] for segment in segments)
                    )
                    language_code = requested_language or cap[1].split("-")[0]
            except Exception:
                clean = ""

        if not clean:
            method = "whisper"
            progress(25, "extracting_audio")
            audio = download_audio(url, work / "audio")
            progress(55, "transcribing")

            result = transcribe_audio(audio, requested_language)
            language_code = result["language"] or requested_language
            segments = result["segments"]
            clean = clean_transcript(segments)
            timestamped = timestamped_transcript(segments)

            if not clean.strip():
                raise RuntimeError(
                    "Transcription completed but no usable speech was detected."
                )
        else:
            progress(70, "formatting")
            timestamped = timestamped_transcript(segments)

        language = language_label(language_code)
        progress(85, "formatting")

        result_dir = save_result(
            title=title,
            url=url,
            platform=platform,
            language=language,
            method=method,
            segments=segments,
            clean=clean,
            timestamped=timestamped,
            job_id=job_id,
        )

        store.update(
            job_id,
            state="completed",
            progress=100,
            language=language,
            method=method,
            result_dir=str(result_dir),
        )
        progress(100, "completed")

    except Exception as exc:
        store.update(job_id, state="failed", error=str(exc), progress=100)
        progress(100, "failed")

    finally:
        if inside(settings.temp_dir, work):
            shutil.rmtree(work, ignore_errors=True)
