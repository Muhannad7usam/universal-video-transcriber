from pathlib import Path
from core.downloader.metadata import ydl_base
def find_usable_caption(info:dict):
    for key in ("subtitles","automatic_captions"):
        tracks=info.get(key) or {}
        for lang,entries in tracks.items():
            if not entries: continue
            for e in entries:
                if e.get("ext") in {"vtt","srt","ttml","json3"}: return key,lang,e.get("ext")
            return key,lang,entries[0].get("ext","vtt")
    return None
def download_caption(url:str,out_dir:Path):
    out_dir.mkdir(parents=True,exist_ok=True); opts=ydl_base() | {"noplaylist":True,"skip_download":True,"writesubtitles":True,"writeautomaticsub":True,"subtitleslangs":["all"],"subtitlesformat":"vtt","outtmpl":str(out_dir/"caption.%(ext)s")}
    from yt_dlp import YoutubeDL
    with YoutubeDL(opts) as ydl: ydl.download([url])
    files=[p for p in out_dir.glob("caption.*") if p.suffix.lower() in {".vtt",".srt",".ttml",".xml",".json3",".json"}]; return files[0] if files else None
