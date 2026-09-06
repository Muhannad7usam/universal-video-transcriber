import shutil
from pathlib import Path

from core.security.urls import validate_media_url


def ydl_base():
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "restrictfilenames": False,
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
        "concurrent_fragment_downloads": 4,
        "nocheckcertificate": False,
        # Cloud/datacenter IPs are frequently challenged by YouTube. Use the
        # mweb client and explicitly point yt-dlp's PO-token plugin at the
        # BgUtils HTTP provider running inside this same container.
        "extractor_args": {
            "youtube": {
                "player_client": ["mweb"],
            },
            "youtubepot-bgutilhttp": {
                "base_url": ["http://127.0.0.1:4416"],
            },
        },
    }

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        opts["ffmpeg_location"] = str(Path(ffmpeg).parent)

    return opts


def extract_info(url: str, *, flat=False, playlist_end: int | None = None):
    validate_media_url(url)
    opts = ydl_base() | {"extract_flat": flat}
    if playlist_end is not None:
        opts["playlistend"] = max(1, int(playlist_end))
    from yt_dlp import YoutubeDL
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def platform_name(info: dict) -> str:
    return info.get("extractor_key") or info.get("extractor") or "Unknown"


def is_playlist(info: dict) -> bool:
    return info.get("_type") == "playlist" or bool(info.get("entries")) and not info.get("duration")


def playlist_items(url: str, max_items: int):
    # Tell yt-dlp the upper bound up front so very large playlists do not spend
    # time enumerating hundreds/thousands of entries that the UI will discard.
    info = extract_info(url, flat=True, playlist_end=max_items)
    if not is_playlist(info):
        raise ValueError("URL is not a playlist.")

    out = []
    for idx, item in enumerate(info.get("entries") or [], 1):
        if idx > max_items:
            break
        if not item:
            continue
        out.append(
            {
                "index": idx,
                "id": item.get("id"),
                "url": item.get("webpage_url") or item.get("url"),
                "title": item.get("title") or f"Video {idx}",
                "duration": item.get("duration"),
                "thumbnail": item.get("thumbnail"),
                "platform": platform_name(item),
            }
        )

    return {
        "title": info.get("title") or "Playlist",
        "url": url,
        "count": len(out),
        "items": out,
    }
