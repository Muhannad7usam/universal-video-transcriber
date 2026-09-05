import shutil
from core.config import settings
from core.downloader.metadata import extract_info,platform_name
from core.subtitles.engine import find_usable_caption,download_caption
from core.subtitles.normalize import normalize_segments
from core.downloader.audio import download_audio
from core.transcription.whisper_engine import transcribe_audio
from core.formatting.transcript import clean_transcript,timestamped_transcript,language_label,format_caption_text
from core.output.store import save_result
from core.security.filenames import inside
def run_job(job_id,url,store,progress=lambda p,s:None):
    work=settings.temp_dir/job_id; work.mkdir(parents=True,exist_ok=True)
    try:
        progress(5,"analyzing"); info=extract_info(url,flat=False); title=info.get("title") or "Untitled video"; duration=info.get("duration")
        if duration and duration>settings.max_video_duration_seconds: raise ValueError("Video exceeds the configured duration limit.")
        platform=platform_name(info); method="captions"; progress(15,"fetching_captions"); cap=find_usable_caption(info); clean=""; segments=[]; language=None
        if cap:
            try:
                p=download_caption(url,work/"captions")
                if p:
                    segments=normalize_segments(p); clean=format_caption_text(" ".join(s["text"] for s in segments)); language=cap[1].split("-")[0]
            except Exception: clean=""
        if not clean:
            method="whisper"; progress(25,"extracting_audio"); audio=download_audio(url,work/"audio"); progress(55,"transcribing"); result=transcribe_audio(audio); language=language_label(result["language"]); segments=result["segments"]; clean=clean_transcript(segments); timestamped=timestamped_transcript(segments)
        else:
            progress(70,"formatting"); timestamped=timestamped_transcript(segments); language=language_label(language) if language else "Unknown"
        progress(85,"formatting"); d=save_result(title=title,url=url,platform=platform,language=language,method=method,segments=segments,clean=clean,timestamped=timestamped,job_id=job_id); store.update(job_id,state="completed",progress=100,language=language,method=method,result_dir=str(d)); progress(100,"completed")
    except Exception as exc:
        store.update(job_id,state="failed",error=str(exc),progress=100); progress(100,"failed")
    finally:
        if inside(settings.temp_dir,work): shutil.rmtree(work,ignore_errors=True)
