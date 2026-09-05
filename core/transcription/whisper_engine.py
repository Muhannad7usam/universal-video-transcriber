from functools import lru_cache
from pathlib import Path
import math
import re
import shutil

from core.config import settings


_LANGUAGE_PROMPTS = {
    "ar": "هذا تسجيل باللغة العربية وقد يتضمن اللهجة المصرية وأسماء أو كلمات إنجليزية. اكتب الكلام المنطوق كما هو بدقة، من دون ترجمة ومن دون تكرار أو اختراع كلام غير مسموع.",
    "en": "This is an English recording and may contain names or short phrases from other languages. Transcribe only the spoken words as heard, without translating or inventing text.",
}


def _cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return shutil.which("nvidia-smi") is not None


def _runtime_choice():
    device = settings.whisper_device
    if device == "auto":
        device = "cuda" if _cuda_available() else "cpu"

    model_name = settings.whisper_model
    if model_name == "auto":
        # large-v3 on GPU prioritizes maximum multilingual accuracy; turbo on
        # CPU avoids the very long latency of the full large model while still
        # being substantially stronger than small for Arabic/multilingual audio.
        model_name = "large-v3" if device == "cuda" else "large-v3-turbo"

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
        num_workers=1,
    )


def _model():
    model_name, device, compute = _runtime_choice()
    try:
        return _load_model(model_name, device, compute), (model_name, device, compute)
    except Exception:
        # A machine can expose an NVIDIA utility while the CUDA runtime needed
        # by CTranslate2 is unavailable. Fall back cleanly instead of failing the
        # whole job.
        if device == "cuda":
            fallback_model = "large-v3-turbo" if settings.whisper_model == "auto" else model_name
            return _load_model(fallback_model, "cpu", "int8"), (fallback_model, "cpu", "int8")
        raise


def runtime_info():
    model_name, device, compute = _runtime_choice()
    return {"model": model_name, "device": device, "compute_type": compute}


def _norm_token(token: str) -> str:
    return re.sub(r"[^\w]+", "", token, flags=re.UNICODE).casefold()


def _collapse_excessive_repetition(text: str) -> str:
    """Collapse only extreme immediate loops that are typical Whisper hallucinations.

    Natural emphasis is preserved: single-word repetition is allowed up to three
    times, while multi-word phrases are allowed twice. We only collapse when a
    phrase repeats far beyond that threshold.
    """
    tokens = text.split()
    if len(tokens) < 5:
        return text

    out = []
    i = 0
    while i < len(tokens):
        matched = False
        max_size = min(12, (len(tokens) - i) // 3)
        for size in range(max_size, 0, -1):
            base = [_norm_token(x) for x in tokens[i : i + size]]
            if not base or not all(base):
                continue

            count = 1
            pos = i + size
            while pos + size <= len(tokens):
                candidate = [_norm_token(x) for x in tokens[pos : pos + size]]
                if candidate != base:
                    break
                count += 1
                pos += size

            threshold = 5 if size == 1 else 3
            if count >= threshold:
                keep = 3 if size == 1 else 2
                for _ in range(keep):
                    out.extend(tokens[i : i + size])
                i = pos
                matched = True
                break

        if not matched:
            out.append(tokens[i])
            i += 1

    return " ".join(out)


def _run(
    path: Path,
    language: str | None,
    vad_filter: bool,
    duration: float | None = None,
    progress_callback=None,
):
    model, runtime = _model()
    _, device, _ = runtime

    beam_size = max(1, int(settings.whisper_beam_size))
    # CPU inference benefits dramatically from a modest beam; GPU can afford
    # the configured beam without making the editor feel stuck.
    if device == "cpu":
        beam_size = min(beam_size, 2)

    kwargs = {
        "beam_size": beam_size,
        "task": "transcribe",
        "vad_filter": vad_filter,
        "condition_on_previous_text": False,
        "temperature": 0.0,
        "compression_ratio_threshold": 2.4,
        "log_prob_threshold": -1.0,
        "no_speech_threshold": 0.6,
        # With Auto Detect, detect language per segment. This improves genuine
        # Arabic/English code-switching while condition_on_previous_text=False
        # prevents one segment's language context from contaminating the next.
        "multilingual": language is None,
        "language_detection_segments": 3 if language is None else 1,
    }

    if vad_filter:
        kwargs["vad_parameters"] = {
            "min_silence_duration_ms": settings.whisper_vad_min_silence_ms,
            "speech_pad_ms": settings.whisper_vad_speech_pad_ms,
        }

    if language:
        kwargs["language"] = language
        prompt = _LANGUAGE_PROMPTS.get(language)
        if prompt:
            kwargs["initial_prompt"] = prompt

    segments_iter, info = model.transcribe(str(path), **kwargs)
    total_duration = float(duration or getattr(info, "duration", 0.0) or 0.0)
    parsed = []
    probabilities = []

    for segment in segments_iter:
        text = _collapse_excessive_repetition((segment.text or "").strip())
        if not text:
            continue

        parsed.append(
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": text,
            }
        )

        avg_logprob = getattr(segment, "avg_logprob", None)
        if isinstance(avg_logprob, (int, float)):
            probabilities.append(max(0.0, min(1.0, math.exp(float(avg_logprob)))))

        if progress_callback and total_duration > 0:
            ratio = max(0.0, min(0.99, float(segment.end) / total_duration))
            progress_callback(ratio)

    confidence = sum(probabilities) / len(probabilities) if probabilities else None
    return (getattr(info, "language", None) or language), parsed, runtime, confidence


def transcribe_audio(
    path: Path,
    language: str | None = None,
    duration: float | None = None,
    progress_callback=None,
):
    # VAD skips pure music/silence but still scans the complete media timeline.
    detected_language, segments, runtime, confidence = _run(
        path,
        language,
        vad_filter=True,
        duration=duration,
        progress_callback=progress_callback,
    )

    # Retry without VAD only when the first pass found nothing at all. This
    # preserves coverage for unusual media without routinely doubling latency.
    if not segments:
        detected_language, segments, runtime, confidence = _run(
            path,
            language,
            vad_filter=False,
            duration=duration,
            progress_callback=progress_callback,
        )

    if not segments:
        raise RuntimeError("Whisper could not detect usable speech in this media.")

    return {
        "language": detected_language,
        "segments": segments,
        "model": runtime[0],
        "device": runtime[1],
        "confidence": confidence,
    }
