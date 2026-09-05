from functools import lru_cache
from pathlib import Path
from core.config import settings
@lru_cache(maxsize=1)
def _model():
    from faster_whisper import WhisperModel
    import shutil
    device=settings.whisper_device; compute=settings.whisper_compute_type
    if device=="auto": device="cuda" if shutil.which("nvidia-smi") else "cpu"
    if compute=="auto": compute="float16" if device=="cuda" else "int8"
    return WhisperModel(settings.whisper_model,device=device,compute_type=compute)
def transcribe_audio(path:Path):
    segments,info=_model().transcribe(str(path),beam_size=5,vad_filter=True)
    return {"language":info.language,"segments":[{"start":s.start,"end":s.end,"text":s.text} for s in segments]}
