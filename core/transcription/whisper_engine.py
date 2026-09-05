from functools import lru_cache
from pathlib import Path
import shutil

from core.config import settings


_LANGUAGE_PROMPTS = {
    "ar": "هذا تسجيل باللغة العربية، وقد يتضمن اللهجة المصرية وكلمات أو أسماء باللغة الإنجليزية. اكتب الكلام المنطوق كما هو دون ترجمة.",
    "en": "This is an English recording and may contain names or short phrases from other languages. Transcribe the spoken words as they are without translating.",
}


def _runtime_choice():
    device = settings.whisper_device
    if device == "auto":
        device = "cuda" if shutil.which("nvidia-smi") else "cpu"

    model_name = settings.whisper_model
    if model_name == "auto":
        model_name = "large-v3" if device == "cuda" else "medium"

    compute = settings.whisper_compute_type
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"

    return model_name, device, compute


@lru_cache(maxsize=2)
def _load_model(model_name: str, device: str, compute: str):
    from faster_whisper import WhisperModel

    return WhisperModel(
        model_name,
        device=device,
        compute_type=compute,
    )


def _model():
    return _load_model(*_runtime_choice())


def _run(path: Path, language: str | None, vad_filter: bool):
    kwargs = {
        "beam_size": 5,
        "task": "transcribe",
        "vad_filter": vad_filter,
        "condition_on_previous_text": False,
        "temperature": 0.0,
        "compression_ratio_threshold": 2.4,
        "log_prob_threshold": -1.0,
        "no_speech_threshold": 0.6,
    }

    if language:
        kwargs["language"] = language
        prompt = _LANGUAGE_PROMPTS.get(language)
        if prompt:
            kwargs["initial_prompt"] = prompt

    segments, info = _model().transcribe(str(path), **kwargs)

    parsed = [
        {
            "start": float(s.start),
            "end": float(s.end),
            "text": s.text.strip(),
        }
        for s in segments
        if s.text and s.text.strip()
    ]

    return info.language or language, parsed


def transcribe_audio(path: Path, language: str | None = None):
    # First pass uses VAD to suppress music/silence hallucinations while still
    # processing the full source timeline for spoken content.
    detected_language, segments = _run(path, language, vad_filter=True)

    # Some unusual media (especially singing or heavily mixed audio) can be
    # filtered too aggressively. Retry the entire audio without VAD if needed.
    if not segments:
        detected_language, segments = _run(path, language, vad_filter=False)

    if not segments:
        raise RuntimeError("Whisper could not detect usable speech in this media.")

    return {
        "language": detected_language,
        "segments": segments,
        "model": _runtime_choice()[0],
    }
