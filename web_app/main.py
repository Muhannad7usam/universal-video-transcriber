import asyncio
import ipaddress
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
from core.formatting.transcript import LANGUAGE_NAMES
from core.jobs import JobStore
from core.pipeline import run_job
from core.security.filenames import inside
from core.security.urls import validate_media_url
from core.transcription.whisper_engine import runtime_info
from scripts.cleanup import cleanup

store = JobStore(settings.jobs_dir / "jobs.db")
executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_jobs)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app = FastAPI(title="Universal Video Transcriber", version="1.3.0")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
_rate = {}
_RATE_WINDOW = 600
_RATE_LIMIT = 30


class LinkIn(BaseModel):
    url: str = Field(min_length=8, max_length=4096)
    language: str | None = Field(default=None, max_length=16)


class PlaylistJobsIn(BaseModel):
    group_id: str | None = None
    items: list[int] = Field(min_length=1, max_length=100)
    playlist_url: str = Field(min_length=8, max_length=4096)
    language: str | None = Field(default=None, max_length=16)


def _normalize_language(value: str | None) -> str | None:
    if value in (None, "", "auto"):
        return None
    code = value.lower().replace("_", "-").split("-")[0]
    if code not in LANGUAGE_NAMES:
        raise HTTPException(400, "Unsupported transcription language.")
    return code


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _client_key(request: Request) -> str:
    """Return a stable per-client key without trusting arbitrary proxy headers.

    cloudflared connects to Uvicorn from loopback. Only in that case do we trust
    Cloudflare's CF-Connecting-IP header; direct LAN clients are keyed by their
    actual socket address and cannot spoof their rate-limit identity.
    """
    peer = request.client.host if request.client else None
    peer_ip = _valid_ip(peer)
    if peer_ip:
        try:
            if ipaddress.ip_address(peer_ip).is_loopback:
                cf_ip = _valid_ip(request.headers.get("cf-connecting-ip"))
                if cf_ip:
                    return cf_ip
        except ValueError:
            pass
        return peer_ip
    return "unknown"


def _rate_check(request: Request):
    now = time.monotonic()
    key = _client_key(request)
    hits = [t for t in _rate.get(key, []) if now - t < _RATE_WINDOW]
    if len(hits) >= _RATE_LIMIT:
        raise HTTPException(429, "Too many requests. Please try again later.")
    hits.append(now)
    _rate[key] = hits


def _is_quick_tunnel(request: Request) -> bool:
    host = (request.headers.get("host") or "").split(":", 1)[0].lower()
    return host.endswith(".trycloudflare.com")


def submit(url, title, group_id=None, item_index=None, language=None):
    jid = str(uuid.uuid4())
    store.create(jid, url, title, group_id, item_index)
    executor.submit(
        run_job,
        jid,
        url,
        store,
        lambda p, s: store.update(jid, progress=p, state=s),
        language,
    )
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
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' https: data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'"
    )

    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").lower()
    if request.url.scheme == "https" or forwarded_proto == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"

    if request.url.path.startswith("/api/") or request.url.path in {"/health", "/ready"}:
        response.headers["Cache-Control"] = "no-store"
    elif request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=300"

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

    return {
        "status": "ok",
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "yt_dlp": y,
        "transcription_engine": w,
        "runtime": runtime_info(),
        "network": {
            "bind_host": settings.host,
            "port": settings.port,
        },
        "long_form": {
            "duration_limit_seconds": settings.max_video_duration_seconds,
            "chunk_threshold_seconds": settings.long_video_chunk_threshold_seconds,
            "chunk_seconds": settings.long_video_chunk_seconds,
            "chunk_overlap_seconds": settings.long_video_chunk_overlap_seconds,
        },
    }


@app.get("/ready")
async def ready():
    h = await health()
    required = ("ffmpeg", "ffprobe", "yt_dlp", "transcription_engine")
    return h if all(h[k] for k in required) else JSONResponse(h, status_code=503)


@app.get("/api/languages")
async def languages():
    return {
        "languages": [
            {"code": code, "name": name}
            for code, name in sorted(LANGUAGE_NAMES.items(), key=lambda item: item[1])
        ]
    }


@app.post("/api/analyze")
async def analyze(payload: LinkIn, request: Request):
    _rate_check(request)
    language = _normalize_language(payload.language)
    try:
        url = validate_media_url(payload.url)
        # One-entry flat probe is enough to distinguish a video from a playlist
        # and avoids enumerating a huge playlist twice before the selector opens.
        info = extract_info(url, flat=True, playlist_end=1)
    except Exception as e:
        raise HTTPException(400, str(e)) from e

    if is_playlist(info):
        try:
            return {
                "type": "playlist",
                "requested_language": language,
                **playlist_items(url, settings.max_playlist_items),
            }
        except Exception as e:
            raise HTTPException(400, str(e)) from e

    return {
        "type": "video",
        "job_id": submit(
            url,
            info.get("title") or "Untitled video",
            language=language,
        ),
        "title": info.get("title"),
        "thumbnail": info.get("thumbnail"),
        "duration": info.get("duration"),
        "platform": info.get("extractor_key") or info.get("extractor") or "Unknown",
        "url": url,
        "requested_language": language,
    }


@app.post("/api/playlist/jobs")
async def playlist_jobs(payload: PlaylistJobsIn, request: Request):
    _rate_check(request)
    language = _normalize_language(payload.language)
    try:
        url = validate_media_url(payload.playlist_url)
        meta = playlist_items(url, settings.max_playlist_items)
    except Exception as e:
        raise HTTPException(400, str(e)) from e

    selected = {x["index"]: x for x in meta["items"]}
    if any(i not in selected for i in payload.items):
        raise HTTPException(400, "One or more selected videos are invalid.")

    gid = payload.group_id or str(uuid.uuid4())
    jobs = [
        submit(selected[i]["url"], selected[i]["title"], gid, i, language)
        for i in payload.items
    ]
    return {
        "group_id": gid,
        "job_ids": jobs,
        "items": [store.get(j) for j in jobs],
    }


@app.get("/api/jobs/{job_id}")
async def job(job_id: str):
    j = store.get(job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return j


@app.get("/api/groups/{group_id}")
async def group(group_id: str):
    return {"group_id": group_id, "jobs": store.group(group_id)}


@app.get("/api/results/{job_id}")
async def result(job_id: str):
    j = store.get(job_id)
    if not j or j["state"] != "completed":
        raise HTTPException(404, "Result not found")

    d = Path(j["result_dir"]).resolve()
    if not inside(settings.results_dir, d):
        raise HTTPException(403, "Invalid result path")

    transcript_path = d / "transcript.txt"
    if not transcript_path.is_file():
        raise HTTPException(404, "Transcript not found")

    metadata = {}
    metadata_path = d / "metadata.json"
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            metadata = {}

    return {
        "title": j["title"],
        "language": j["language"],
        "method": j["method"],
        "url": j["url"],
        "transcript": transcript_path.read_text(encoding="utf-8"),
        "timestamped": (
            (d / "transcript_timestamped.txt").read_text(encoding="utf-8")
            if (d / "transcript_timestamped.txt").exists()
            else ""
        ),
        "model": metadata.get("model"),
        "device": metadata.get("device"),
        "confidence": metadata.get("confidence"),
        "processing_seconds": metadata.get("processing_seconds"),
        "cache_hit": bool(metadata.get("cache_hit")),
    }


@app.get("/api/jobs/{job_id}/events")
async def events(job_id: str, request: Request):
    if not store.get(job_id):
        raise HTTPException(404, "Job not found")

    # TryCloudflare Quick Tunnels buffer SSE and officially do not support it.
    # Return one event and close there; the existing browser EventSource error
    # handler then switches to JSON polling. Named tunnels and LAN keep real SSE.
    if _is_quick_tunnel(request):
        async def one_shot():
            j = store.get(job_id)
            if j:
                yield f"data: {json.dumps(j, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            one_shot(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def gen():
        last = None
        while True:
            if await request.is_disconnected():
                break
            j = store.get(job_id)
            if not j:
                break
            payload = json.dumps(j, ensure_ascii=False)
            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload
            if j["state"] in {"completed", "failed"}:
                break
            await asyncio.sleep(0.35)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/groups/{group_id}/events")
async def group_events(group_id: str, request: Request):
    if _is_quick_tunnel(request):
        async def one_shot():
            jobs = store.group(group_id)
            payload = json.dumps({"group_id": group_id, "jobs": jobs}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

        return StreamingResponse(
            one_shot(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def gen():
        last = None
        while True:
            if await request.is_disconnected():
                break
            jobs = store.group(group_id)
            payload = json.dumps({"group_id": group_id, "jobs": jobs}, ensure_ascii=False)
            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload
            if jobs and all(j["state"] in {"completed", "failed"} for j in jobs):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
