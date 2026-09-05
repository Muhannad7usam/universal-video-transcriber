from pathlib import Path

from core.downloader.metadata import ydl_base


def _normalize_lang(value: str | None) -> str | None:
    if not value:
        return None
    return value.lower().replace("_", "-").split("-")[0]


def _pick_entry(entries):
    if not entries:
        return None
    preferred_exts = ("json3", "vtt", "srt", "ttml")
    for ext in preferred_exts:
        for entry in entries:
            if entry.get("ext") == ext:
                return entry
    return entries[0]


def _track_candidates(info: dict, key: str, preferred_language: str | None):
    tracks = info.get(key) or {}
    if not tracks:
        return []

    preferred = _normalize_lang(preferred_language)
    source_language = _normalize_lang(info.get("language"))

    if preferred:
        # The selector describes the spoken source language. If the extractor
        # confidently reports a different source language, a caption track in
        # the requested language is almost certainly a translation, so skip it
        # and let Whisper transcribe the actual audio instead.
        if source_language and source_language != preferred:
            return []
        return [
            (lang, entries)
            for lang, entries in tracks.items()
            if _normalize_lang(lang) == preferred
        ]

    # Auto Detect should never pick an arbitrary translated YouTube caption
    # (for example the alphabetically-first "ab" track). Prefer the extractor's
    # original language, then explicitly original tracks, then a sole manual
    # subtitle. If none is safe, Whisper should detect the spoken language.
    if source_language:
        exact = [
            (lang, entries)
            for lang, entries in tracks.items()
            if _normalize_lang(lang) == source_language
        ]
        if exact:
            return exact

    originals = [
        (lang, entries)
        for lang, entries in tracks.items()
        if str(lang).lower().endswith("-orig")
    ]
    if originals:
        return originals

    if key == "subtitles" and len(tracks) == 1:
        return list(tracks.items())

    return []


def find_usable_caption(info: dict, preferred_language: str | None = None):
    for key in ("subtitles", "automatic_captions"):
        for lang, entries in _track_candidates(info, key, preferred_language):
            entry = _pick_entry(entries)
            if entry:
                return {
                    "kind": key,
                    "language": lang,
                    "ext": entry.get("ext", "vtt"),
                }
    return None


def download_caption(url: str, out_dir: Path, language: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    opts = ydl_base() | {
        "noplaylist": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [language],
        # json3 is usually cleaner for YouTube rolling captions; fall back to
        # VTT/other formats transparently on sites that do not expose json3.
        "subtitlesformat": "json3/vtt/srt/ttml/best",
        "outtmpl": str(out_dir / "caption.%(ext)s"),
    }

    from yt_dlp import YoutubeDL

    with YoutubeDL(opts) as ydl:
        ydl.download([url])

    files = [
        p
        for p in out_dir.glob("caption.*")
        if p.suffix.lower() in {".vtt", ".srt", ".ttml", ".xml", ".json3", ".json"}
    ]
    return files[0] if files else None
