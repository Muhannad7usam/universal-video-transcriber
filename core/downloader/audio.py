from pathlib import Path
from core.downloader.metadata import ydl_base
def download_audio(url:str,out_dir:Path)->Path:
    out_dir.mkdir(parents=True,exist_ok=True)
    opts=ydl_base() | {"noplaylist":True,"format":"bestaudio/best","outtmpl":str(out_dir/"source.%(ext)s"),"postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"wav","preferredquality":"192"}],"keepvideo":False}
    from yt_dlp import YoutubeDL
    with YoutubeDL(opts) as ydl: ydl.download([url])
    wav=out_dir/"source.wav"
    if not wav.exists():
        matches=list(out_dir.glob("source.*"))
        if not matches: raise RuntimeError("Audio extraction produced no file.")
        return matches[0]
    return wav
