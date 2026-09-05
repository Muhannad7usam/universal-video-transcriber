from collections import Counter
from functools import lru_cache
from pathlib import Path
import math
import re
import shutil
import subprocess

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
        # large-v3 on GPU prioritizes multilingual accuracy; turbo on CPU keeps
        # very long jobs practical while remaining substantially stronger than
        # small for Arabic and mixed-language recordings.
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
        # by CTranslate2 is unavailable. Fall back cleanly instead of failing.
        if device == "cuda":
            fallback_model = (
                "large-v3-turbo" if settings.whisper_model == "auto" else model_name
            )
            return _load_model(fallback_model, "cpu", "int8"), (
                fallback_model,
                "cpu",
                "int8",
            )
        raise


def runtime_info():
    model_name, device, compute = _runtime_choice()
    return {"model": model_name, "device": device, "compute_type": compute}


def _norm_token(token: str) -> str:
    return re.sub(r"[^\w]+", "", token, flags=re.UNICODE).casefold()


def _collapse_excessive_repetition(text: str) -> str:
    """Collapse only extreme immediate loops typical of ASR hallucinations."""
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
        # Auto Detect performs language detection throughout the file, which is
        # important for genuine Arabic/English code-switching.
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


def _probe_duration(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        value = float((proc.stdout or "").strip())
        return value if value > 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _extract_chunk(source: Path, destination: Path, start: float, length: float):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for long-form chunk processing.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-ss",
            f"{max(0.0, start):.3f}",
            "-i",
            str(source),
            "-t",
            f"{max(0.1, length):.3f}",
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "flac",
            "-compression_level",
            "3",
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not destination.is_file():
        detail = (proc.stderr or "").strip().splitlines()
        suffix = f" ({detail[-1]})" if detail else ""
        raise RuntimeError(f"Could not prepare a long-video audio chunk{suffix}")


def _history_words(segments, limit: int = 180):
    words = []
    for segment in reversed(segments):
        current = [_norm_token(x) for x in segment.get("text", "").split()]
        current = [x for x in current if x]
        words[0:0] = current
        if len(words) >= limit:
            return words[-limit:]
    return words


def _trim_prefix_overlap(text: str, history) -> str:
    raw = text.split()
    pairs = [(i, _norm_token(token)) for i, token in enumerate(raw)]
    pairs = [(i, token) for i, token in pairs if token]
    current = [token for _, token in pairs]
    if not history or not current:
        return text

    max_overlap = min(len(history), len(current), 80)
    overlap = 0
    for size in range(max_overlap, 2, -1):
        if history[-size:] == current[:size]:
            overlap = size
            break
    if not overlap:
        return text

    cutoff = pairs[overlap - 1][0] + 1
    return " ".join(raw[cutoff:]).strip()


def _merge_chunk_segments(existing, incoming, offset: float, boundary: float, overlap: float):
    """Merge an overlapped chunk without duplicating words at its boundary."""
    history = _history_words(existing)
    result = list(existing)

    for segment in incoming:
        start = float(segment.get("start", 0.0)) + offset
        end = float(segment.get("end", 0.0)) + offset
        text = (segment.get("text") or "").strip()
        if not text:
            continue

        # The previous chunk already owns segments ending fully before the new
        # nominal boundary. The small overlap exists only to preserve context.
        if boundary > 0 and end <= boundary + 0.05:
            continue

        if boundary > 0 and start <= boundary + overlap + 8:
            text = _trim_prefix_overlap(text, history)
            if not text:
                continue

        if result:
            previous = result[-1]
            if (
                _norm_token(text) == _norm_token(previous.get("text", ""))
                and start <= float(previous.get("end", 0.0)) + 1.0
            ):
                continue

        item = {"start": max(0.0, start), "end": max(start, end), "text": text}
        result.append(item)
        history.extend(_norm_token(x) for x in text.split() if _norm_token(x))
        history = history[-180:]

    return result


def _transcribe_chunked(
    path: Path,
    language: str | None,
    total_duration: float,
    vad_filter: bool,
    progress_callback=None,
):
    chunk_seconds = max(300, int(settings.long_video_chunk_seconds))
    overlap = max(0, int(settings.long_video_chunk_overlap_seconds))
    overlap = min(overlap, max(0, chunk_seconds // 10))

    chunk_dir = path.parent / "_uvt_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    merged = []
    language_votes = Counter()
    weighted_confidence = 0.0
    confidence_weight = 0
    runtime = None
    index = 0
    nominal_start = 0.0

    try:
        while nominal_start < total_duration - 0.05:
            extraction_start = max(0.0, nominal_start - (overlap if index else 0))
            nominal_end = min(total_duration, nominal_start + chunk_seconds)
            extraction_length = nominal_end - extraction_start
            if extraction_length <= 0:
                break

            chunk_path = chunk_dir / f"chunk-{index:05d}.flac"
            _extract_chunk(path, chunk_path, extraction_start, extraction_length)

            def chunk_progress(local_ratio: float):
                if not progress_callback:
                    return
                global_position = extraction_start + (
                    max(0.0, min(1.0, local_ratio)) * extraction_length
                )
                progress_callback(max(0.0, min(0.99, global_position / total_duration)))

            detected, local_segments, runtime, confidence = _run(
                chunk_path,
                language,
                vad_filter=vad_filter,
                duration=extraction_length,
                progress_callback=chunk_progress,
            )

            if detected:
                language_votes[detected] += max(1, len(local_segments))
            if confidence is not None and local_segments:
                weighted_confidence += confidence * len(local_segments)
                confidence_weight += len(local_segments)

            merged = _merge_chunk_segments(
                merged,
                local_segments,
                offset=extraction_start,
                boundary=nominal_start,
                overlap=overlap,
            )

            chunk_path.unlink(missing_ok=True)
            nominal_start += chunk_seconds
            index += 1

        if progress_callback:
            progress_callback(0.99)
    finally:
        shutil.rmtree(chunk_dir, ignore_errors=True)

    detected_language = language
    if not detected_language and language_votes:
        detected_language = language_votes.most_common(1)[0][0]
    confidence = (
        weighted_confidence / confidence_weight if confidence_weight else None
    )
    return detected_language, merged, runtime, confidence


def transcribe_audio(
    path: Path,
    language: str | None = None,
    duration: float | None = None,
    progress_callback=None,
):
    total_duration = float(duration or 0.0) or _probe_duration(path) or 0.0
    threshold = max(0, int(settings.long_video_chunk_threshold_seconds))
    use_chunks = bool(total_duration and threshold and total_duration >= threshold)

    if use_chunks:
        detected_language, segments, runtime, confidence = _transcribe_chunked(
            path,
            language,
            total_duration,
            vad_filter=True,
            progress_callback=progress_callback,
        )
        # Retry without VAD only if the entire recording produced no speech.
        # Do not reset visible progress backwards during this rare fallback.
        if not segments:
            detected_language, segments, runtime, confidence = _transcribe_chunked(
                path,
                language,
                total_duration,
                vad_filter=False,
                progress_callback=None,
            )
    else:
        detected_language, segments, runtime, confidence = _run(
            path,
            language,
            vad_filter=True,
            duration=total_duration or duration,
            progress_callback=progress_callback,
        )
        if not segments:
            detected_language, segments, runtime, confidence = _run(
                path,
                language,
                vad_filter=False,
                duration=total_duration or duration,
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
        "duration": total_duration or duration,
        "chunked": use_chunks,
    }
