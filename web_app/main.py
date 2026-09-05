import asyncio
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from core.config import settings
from core.downloader.metadata import extract_info, is_playlist, playlist_items
from core.jobs import JobStore
from core.pipeline import run_job
from core.security.filenames import inside
from core.security.urls import validate_media_url
from scripts.cleanup import cleanup

store = JobStore(settings.jobs_dir / "jobs.db")
executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_jobs)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app = FastAPI(title="Universal Video Transcriber", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
_rate = {}
_RATE_WINDOW = 600
_RATE_LIMIT = 30

class LinkIn(BaseModel):
    url: str = Field(min_length=8, max_length=4096)

class PlaylistJobsIn(BaseModel):
    group_id: str | None = None
    items: list[int] = Field(min_length=1, max_length=100)
    playlist_url: str = Field(min_length=8, max_length=4096)

def _rate_check(request: Request):
    now = time.monotonic()
    key = request.client.host if request.client else "unknown"
    hits = [t for t in _rate.get(key, []) if now - t < _RATE_WINDOW]
    if len(hits) >= _RATE_LIMIT:
        raise HTTPException(429, "Too many requests. Please try again later.")
    hits.append(now)
    _rate[key] = hits

def submit(url, title, group_id=None, item_index=None):
    jid = str(uuid.uuid4())
    store.create(jid, url, title, group_id, item_index)
    executor.submit(run_job, jid, url, store, lambda p, s: store.update(jid, progress=p, state=s))
    return jid

@app.middleware("http")
async def security_headers(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > 65536:
        return JSONResponse({"detail": "Request body too large."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' https: data:; style-src 'self'; script-src 'self'; connect-src 'self'"
    return response

@asynccontextmanager
async def lifespan(app):
    async def cleaner():
        while True:
            await asyncio.sleep(max(1, settings.cleanup_interval_hours * 3600))
            await asyncio.to_thread(cleanup, False)
    task = asyncio.create_task(cleaner())
    try:
        yield
    finally:
        task.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
app.router.lifespan_context = lifespan

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/health")
async def health():
    import shutil
    try:
        import yt_dlp
        y = True
    except Exception:
        y = False
    try:
        import faster_whisper
        w = True
    except Exception:
        w = False
    return {"status": "ok", "ffmpeg": shutil.which("ffmpeg") is not None, "yt_dlp": y, "transcription_engine": w}

@app.get("/ready")
async def ready():
    h = await health()
    return h if all(h[k] for k in ("ffmpeg", "yt_dlp", "transcription_engine")) else JSONResponse(h, status_code=503)

@app.post("/api/analyze")
async def analyze(payload: LinkIn, request: Request):
    _rate_check(request)
    try:
        url = validate_media_url(payload.url)
        info = extract_info(url, flat=True)
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    if is_playlist(info):
        try:
            return {"type": "playlist", **playlist_items(url, settings.max_playlist_items)}
        except Exception as e:
            raise HTTPException(400, str(e)) from e
    return {"type": "video", "job_id": submit(url, info.get("title") or "Untitled video"), "title": info.get("title"), "thumbnail": info.get("thumbnail"), "duration": info.get("duration"), "platform": info.get("extractor_key") or info.get("extractor") or "Unknown", "url": url}

@app.post("/api/playlist/jobs")
async def playlist_jobs(payload: PlaylistJobsIn, request: Request):
    _rate_check(request)
    try:
        url = validate_media_url(payload.playlist_url)
        meta = playlist_items(url, settings.max_playlist_items)
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    selected = {x["index"]: x for x in meta["items"]}
    if any(i not in selected for i in payload.items):
        raise HTTPException(400, "One or more selected videos are invalid.")
    gid = payload.group_id or str(uuid.uuid4())
    jobs = [submit(selected[i]["url"], selected[i]["title"], gid, i) for i in payload.items]
    return {"group_id": gid, "job_ids": jobs, "items": [store.get(j) for j in jobs]}

@app.get("/api/jobs/{job_id}")
async def job(job_id: str):
    j = store.get(job_id)
    if not j: raise HTTPException(404, "Job not found")
    return j

@app.get("/api/groups/{group_id}")
async def group(group_id: str):
    return {"group_id": group_id, "jobs": store.group(group_id)}

@app.get("/api/results/{job_id}")
async def result(job_id: str):
    j = store.get(job_id)
    if not j or j["state"] != "completed": raise HTTPException(404, "Result not found")
    d = Path(j["result_dir"]).resolve()
    if not inside(settings.results_dir, d): raise HTTPException(403, "Invalid result path")
    p = d / "transcript.txt"
    if not p.is_file(): raise HTTPException(404, "Transcript not found")
    return {"title": j["title"], "language": j["language"], "method": j["method"], "url": j["url"], "transcript": p.read_text(encoding="utf-8"), "timestamped": (d / "transcript_timestamped.txt").read_text(encoding="utf-8") if (d / "transcript_timestamped.txt").exists() else ""}

@app.get("/api/jobs/{job_id}/events")
async def events(job_id: str, request: Request):
    if not store.get(job_id): raise HTTPException(404, "Job not found")
    async def gen():
        last = None
        while True:
            if await request.is_disconnected(): break
            j = store.get(job_id)
            if not j: break
            payload = json.dumps(j, ensure_ascii=False)
            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload
            if j["state"] in {"completed", "failed"}: break
            await asyncio.sleep(0.7)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
