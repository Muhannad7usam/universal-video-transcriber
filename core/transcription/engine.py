from core.config import settings


def _provider() -> str:
    return (settings.transcription_provider or "local").strip().lower()


def runtime_info():
    if _provider() == "cloudflare":
        from core.transcription.cloudflare_whisper import runtime_info as cloud_runtime_info

        return cloud_runtime_info()

    from core.transcription.whisper_engine import runtime_info as local_runtime_info

    return local_runtime_info()


def transcribe_audio(path, language=None, duration=None, progress_callback=None):
    if _provider() == "cloudflare":
        from core.transcription.cloudflare_whisper import transcribe_audio as cloud_transcribe

        return cloud_transcribe(
            path,
            language=language,
            duration=duration,
            progress_callback=progress_callback,
        )

    from core.transcription.whisper_engine import transcribe_audio as local_transcribe

    return local_transcribe(
        path,
        language=language,
        duration=duration,
        progress_callback=progress_callback,
    )
