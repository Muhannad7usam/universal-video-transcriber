from pathlib import Path

from core.downloader.metadata import ydl_base


def download_audio(url: str, out_dir: Path, progress_callback=None) -> Path:
    """Download the best compressed audio stream without an unnecessary WAV pass.

    faster-whisper decodes common media containers through PyAV directly, so
    keeping the source compressed saves download time, disk I/O and FFmpeg
    re-encoding time. FFmpeg remains available as a general runtime dependency.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    def hook(data):
        if not progress_callback or data.get("status") != "downloading":
            return
        downloaded = data.get("downloaded_bytes") or 0
        total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
        if total:
            progress_callback(max(0.0, min(1.0, downloaded / total)))

    opts = ydl_base() | {
        "noplaylist": True,
        "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
        "outtmpl": str(out_dir / "source.%(ext)s"),
        "keepvideo": False,
        "progress_hooks": [hook],
    }

    from yt_dlp import YoutubeDL

    with YoutubeDL(opts) as ydl:
        ydl.download([url])

    matches = [
        p for p in out_dir.glob("source.*")
        if p.is_file() and not p.name.endswith((".part", ".ytdl"))
    ]
    if not matches:
        raise RuntimeError("Audio download produced no usable file.")

    # yt-dlp creates only one selected audio file for the formats above. If a
    # site leaves more than one candidate, prefer the largest completed file.
    return max(matches, key=lambda p: p.stat().st_size)
