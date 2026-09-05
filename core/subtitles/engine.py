from pathlib import Path

from core.downloader.metadata import ydl_base


def _normalize_lang(value: str | None) -> str | None:
    if not value:
        return None
    return value.lower().replace("_", "-").split("-")[0]


def find_usable_caption(info: dict, preferred_language: str | None = None):
    preferred = _normalize_lang(preferred_language)

    for key in ("subtitles", "automatic_captions"):
        tracks = info.get(key) or {}
        if not tracks:
            continue

        ordered = list(tracks.items())
        if preferred:
            ordered.sort(key=lambda pair: 0 if _normalize_lang(pair[0]) == preferred else 1)

        for lang, entries in ordered:
            if preferred and _normalize_lang(lang) != preferred:
                continue
            if not entries:
                continue
            for entry in entries:
                if entry.get("ext") in {"vtt", "srt", "ttml", "json3"}:
                    return key, lang, entry.get("ext")
            return key, lang, entries[0].get("ext", "vtt")

    return None


def download_caption(url: str, out_dir: Path, language: str | None = None):
    out_dir.mkdir(parents=True, exist_ok=True)
    langs = [language] if language else ["all"]
    opts = ydl_base() | {
        "noplaylist": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": langs,
        "subtitlesformat": "vtt",
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
