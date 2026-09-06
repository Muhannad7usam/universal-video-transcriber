import base64
import os
import shutil
from pathlib import Path

from core.security.urls import validate_media_url


_COOKIE_PATH = Path("/tmp/uvt-youtube-cookies.txt")


def _youtube_cookiefile() -> str | None:
    """Materialize optional YouTube cookies from a secret environment variable.

    The public repository never stores account cookies. Cloud hosts can provide
    a Mozilla/Netscape cookies.txt file as base64 in YOUTUBE_COOKIES_B64. The
    decoded file is written only inside the ephemeral container with mode 0600.
    """
    encoded = os.getenv("YOUTUBE_COOKIES_B64", "").strip()
    if not encoded:
        return None

    try:
        raw = base64.b64decode(encoded, validate=True)
        text = raw.decode("utf-8-sig")
    except Exception as exc:
        raise RuntimeError("YOUTUBE_COOKIES_B64 is not valid base64 UTF-8 data.") from exc

    # yt-dlp expects Mozilla/Netscape cookie-file format and LF newlines on Linux.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    first_line = text.split("\n", 1)[0].strip()
    if first_line not in {"# Netscape HTTP Cookie File", "# HTTP Cookie File"}:
        raise RuntimeError(
            "YOUTUBE_COOKIES_B64 must contain a Mozilla/Netscape cookies.txt file."
        )

    if not _COOKIE_PATH.exists() or _COOKIE_PATH.read_text(encoding="utf-8") != text:
        _COOKIE_PATH.write_text(text, encoding="utf-8", newline="\n")
        os.chmod(_COOKIE_PATH, 0o600)

    return str(_COOKIE_PATH)


def ydl_base():
    cookiefile = _youtube_cookiefile()

    # Anonymous cloud traffic first tries the PO-token path. When YouTube has
    # flagged the hosting provider's egress IP, optional account cookies are a
    # separate fallback. Logged-in sessions use the normal/default clients
    # first because some mweb combinations can still be rejected with cookies.
    if cookiefile:
        youtube_args = {
            "player_client": ["default", "web_embedded", "mweb"],
            "pot_trace": ["true"],
        }
        youtubetab_args = {}
    else:
        youtube_args = {
            "player_client": ["mweb", "android_vr", "web_embedded", "tv"],
            "player_skip": ["webpage", "configs"],
            "pot_trace": ["true"],
        }
        youtubetab_args = {"skip": ["webpage"]}

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
        "source_address": "0.0.0.0",
        "extractor_args": {
            "youtube": youtube_args,
            "youtubetab": youtubetab_args,
            "youtubepot-bgutilhttp": {
                "base_url": ["http://127.0.0.1:4416"],
            },
        },
    }

    if cookiefile:
        opts["cookiefile"] = cookiefile

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
