from functools import lru_cache
from pathlib import Path

from core.config import settings


@lru_cache(maxsize=1)
def _model():
    from faster_whisper import WhisperModel
    import shutil

    device = settings.whisper_device
    compute = settings.whisper_compute_type

    if device == "auto":
        device = "cuda" if shutil.which("nvidia-smi") else "cpu"

    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"

    return WhisperModel(
        settings.whisper_model,
        device=device,
        compute_type=compute,
    )


def _run(path: Path, language: str | None, vad_filter: bool):
    kwargs = {
        "beam_size": 5,
        "task": "transcribe",
        "vad_filter": vad_filter,
        "condition_on_previous_text": True,
    }
    if language:
        kwargs["language"] = language

    segments, info = _model().transcribe(str(path), **kwargs)
    parsed = [
        {"start": s.start, "end": s.end, "text": s.text.strip()}
        for s in segments
        if s.text and s.text.strip()
    ]
    return info.language or language, parsed


def transcribe_audio(path: Path, language: str | None = None):
    # Full-audio mode: do not let VAD skip parts of the source on the first pass.
    detected_language, segments = _run(path, language, vad_filter=False)

    # A conservative fallback for unusual media where the full pass yielded nothing.
    if not segments:
        detected_language, segments = _run(path, language, vad_filter=True)

    if not segments:
        raise RuntimeError("Whisper could not detect usable speech in this media.")

    return {
        "language": detected_language,
        "segments": segments,
    }
