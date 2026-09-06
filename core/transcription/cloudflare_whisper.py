import base64
import os
import shutil
import subprocess
import time
from pathlib import Path

import requests

from core.config import settings
from core.subtitles.normalize import parse_vtt_srt_segments


_MODEL = "@cf/openai/whisper-large-v3-turbo"

_LANGUAGE_PROMPTS = {
    "ar": (
        "هذا تسجيل باللغة العربية وقد يتضمن اللهجة المصرية وأسماء أو كلمات إنجليزية. "
        "اكتب الكلام المنطوق كما هو بدقة، من دون ترجمة ومن دون اختراع كلام غير مسموع."
    ),
    "en": (
        "This is an English recording and may contain names or short phrases from "
        "other languages. Transcribe only the spoken words as heard, without translating."
    ),
}


def _credentials():
    account_id = (settings.cloudflare_account_id or "").strip()
    api_token = (settings.cloudflare_api_token or "").strip()
    if not account_id or not api_token:
        raise RuntimeError(
            "Cloudflare Workers AI is not configured. Set CLOUDFLARE_ACCOUNT_ID "
            "and CLOUDFLARE_API_TOKEN in the deployment environment."
        )
    return account_id, api_token


def runtime_info():
    return {
        "provider": "cloudflare",
        "model": _MODEL,
        "device": "cloudflare-workers-ai",
        "compute_type": "managed",
        "chunk_seconds": settings.cloud_chunk_seconds,
        "chunk_overlap_seconds": settings.cloud_chunk_overlap_seconds,
    }


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


def _extract_mp3_chunk(source: Path, destination: Path, start: float, length: float):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for cloud transcription chunking.")

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
            "libmp3lame",
            "-b:a",
            "64k",
            str(destination),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not destination.is_file():
        detail = (proc.stderr or "").strip().splitlines()
        suffix = f" ({detail[-1]})" if detail else ""
        raise RuntimeError(f"Could not prepare audio chunk{suffix}")


def _cloudflare_request(chunk_path: Path, language: str | None):
    account_id, api_token = _credentials()
    endpoint = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{account_id}/ai/run/{_MODEL}"
    )

    audio_b64 = base64.b64encode(chunk_path.read_bytes()).decode("ascii")
    payload = {
        "audio": audio_b64,
        "task": "transcribe",
        "vad_filter": True,
        "beam_size": 3,
        "condition_on_previous_text": False,
        "no_speech_threshold": 0.6,
        "compression_ratio_threshold": 2.4,
        "log_prob_threshold": -1.0,
    }
    if language:
        payload["language"] = language
        prompt = _LANGUAGE_PROMPTS.get(language)
        if prompt:
            payload["initial_prompt"] = prompt

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=(20, max(120, int(settings.cloudflare_request_timeout_seconds))),
    )

    if response.status_code == 429:
        raise RuntimeError(
            "Cloudflare Workers AI rate/free-quota limit was reached. "
            "Wait for the free allocation to reset and run the job again."
        )
    if response.status_code == 403:
        raise RuntimeError(
            "Cloudflare Workers AI rejected the request. Verify the API token, "
            "account ID, model access, and free-plan availability."
        )
    if not response.ok:
        body = response.text[:500]
        raise RuntimeError(
            f"Cloudflare Workers AI request failed ({response.status_code}): {body}"
        )

    data = response.json()
    if not data.get("success", False):
        raise RuntimeError(f"Cloudflare Workers AI returned an error: {data.get('errors')}")

    result = data.get("result") or {}
    text = (result.get("text") or "").strip()
    vtt = result.get("vtt") or ""

    segments = parse_vtt_srt_segments(vtt) if vtt.strip() else []
    if not segments and text:
        segments = [{"start": 0.0, "end": 0.0, "text": text}]

    detected_language = None
    info = result.get("transcription_info") or {}
    if isinstance(info, dict):
        detected_language = info.get("language")

    return detected_language or language, segments


def _norm_word(token: str) -> str:
    import re

    return re.sub(r"[^\w]+", "", token, flags=re.UNICODE).casefold()


def _history_words(segments, limit: int = 160):
    words = []
    for segment in reversed(segments):
        current = [_norm_word(x) for x in segment.get("text", "").split()]
        current = [x for x in current if x]
        words[0:0] = current
        if len(words) >= limit:
            break
    return words[-limit:]


def _trim_prefix_overlap(text: str, history) -> str:
    raw = text.split()
    pairs = [(i, _norm_word(token)) for i, token in enumerate(raw)]
    pairs = [(i, token) for i, token in pairs if token]
    current = [token for _, token in pairs]
    if not history or not current:
        return text

    max_overlap = min(len(history), len(current), 60)
    for size in range(max_overlap, 2, -1):
        if history[-size:] == current[:size]:
            cutoff = pairs[size - 1][0] + 1
            return " ".join(raw[cutoff:]).strip()
    return text


def _merge(existing, incoming, offset: float, boundary: float, overlap: float):
    result = list(existing)
    history = _history_words(existing)

    for segment in incoming:
        start = float(segment.get("start", 0.0) or 0.0) + offset
        end = float(segment.get("end", 0.0) or 0.0) + offset
        text = (segment.get("text") or "").strip()
        if not text:
            continue

        if boundary > 0 and end <= boundary + 0.05:
            continue

        if boundary > 0 and start <= boundary + overlap + 8:
            text = _trim_prefix_overlap(text, history)
            if not text:
                continue

        result.append(
            {
                "start": max(0.0, start),
                "end": max(start, end),
                "text": text,
            }
        )
        history.extend(_norm_word(x) for x in text.split() if _norm_word(x))
        history = history[-160:]

    return result


def transcribe_audio(
    path: Path,
    language: str | None = None,
    duration: float | None = None,
    progress_callback=None,
):
    total_duration = float(duration or 0.0) or _probe_duration(path) or 0.0
    if total_duration <= 0:
        raise RuntimeError("Could not determine the audio duration for cloud transcription.")

    chunk_seconds = max(60, int(settings.cloud_chunk_seconds))
    overlap = max(0, int(settings.cloud_chunk_overlap_seconds))
    overlap = min(overlap, max(0, chunk_seconds // 10))

    chunk_dir = path.parent / "_cloudflare_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    merged = []
    detected_language = language
    index = 0
    nominal_start = 0.0

    try:
        while nominal_start < total_duration - 0.05:
            extraction_start = max(0.0, nominal_start - (overlap if index else 0))
            nominal_end = min(total_duration, nominal_start + chunk_seconds)
            extraction_length = nominal_end - extraction_start
            chunk_path = chunk_dir / f"chunk-{index:05d}.mp3"

            _extract_mp3_chunk(path, chunk_path, extraction_start, extraction_length)

            local_language, local_segments = _cloudflare_request(chunk_path, language)
            if local_language and not detected_language:
                detected_language = local_language

            merged = _merge(
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
                progress_callback(min(0.99, nominal_start / total_duration))

            # Small pause avoids needless bursts while remaining far below the
            # published Workers AI ASR rate limit.
            time.sleep(max(0.0, float(settings.cloudflare_inter_chunk_delay_seconds)))
    finally:
        shutil.rmtree(chunk_dir, ignore_errors=True)

    if not merged:
        raise RuntimeError("Cloudflare Whisper returned no usable speech.")

    if progress_callback:
        progress_callback(0.99)

    return {
        "language": detected_language or language,
        "segments": merged,
        "model": _MODEL,
        "device": "cloudflare-workers-ai",
        "confidence": None,
        "duration": total_duration,
        "chunked": total_duration > chunk_seconds,
    }
