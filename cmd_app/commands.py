import argparse
import sys
import uuid
from pathlib import Path

from core.config import settings
from core.downloader.metadata import extract_info, is_playlist, playlist_items
from core.formatting.transcript import LANGUAGE_NAMES
from core.jobs import JobStore
from core.pipeline import run_job
from core.playlist.selection import select_indices
from core.security.urls import validate_media_url


def build_parser():
    parser = argparse.ArgumentParser(
        prog="transcribe",
        description="Local-first video and playlist transcription.",
    )
    parser.add_argument("url", help="Public video or playlist URL")
    parser.add_argument(
        "--language",
        "-l",
        default="auto",
        help="Spoken language code such as ar or en; default: auto",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--video", type=int, help="Transcribe one playlist item by 1-based index")
    group.add_argument("--range", dest="range_", nargs=2, type=int, metavar=("START", "END"))
    group.add_argument("--first", type=int, help="Transcribe the first N playlist items")
    group.add_argument("--all", dest="all_items", action="store_true", help="Transcribe the entire playlist")
    return parser


def _language(value: str):
    if not value or value.lower() == "auto":
        return None
    code = value.lower().replace("_", "-").split("-")[0]
    if code not in LANGUAGE_NAMES:
        raise ValueError(f"Unsupported transcription language: {value}")
    return code


def _progress(prefix: str):
    last = {"value": None}

    def callback(percent, state):
        key = (percent, state)
        if last["value"] == key:
            return
        last["value"] = key
        print(f"\r{prefix}: {state.replace('_', ' ')} {percent:3d}%", end="", flush=True)
        if state in {"completed", "failed"}:
            print()

    return callback


def _run_one(store: JobStore, url: str, title: str, language: str | None, prefix: str):
    job_id = str(uuid.uuid4())
    store.create(job_id, url, title)
    run_job(job_id, url, store, _progress(prefix), language)
    job = store.get(job_id)
    if not job or job["state"] != "completed":
        raise RuntimeError((job or {}).get("error") or "Transcription failed")
    result_dir = Path(job["result_dir"])
    transcript = result_dir / "transcript.txt"
    print(transcript.resolve())


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        language = _language(args.language)
        url = validate_media_url(args.url)
        info = extract_info(url, flat=True)
        store = JobStore(settings.jobs_dir / "jobs.db")

        if not is_playlist(info):
            _run_one(
                store,
                url,
                info.get("title") or "Untitled video",
                language,
                "video",
            )
            return 0

        meta = playlist_items(url, settings.max_playlist_items)
        indices = select_indices(
            meta["count"],
            all_items=args.all_items,
            video=args.video,
            range_=tuple(args.range_) if args.range_ else None,
            first=args.first,
        )
        if not indices:
            raise ValueError("For a playlist, choose --video, --range, --first, or --all.")

        by_index = {item["index"]: item for item in meta["items"]}
        for position, index in enumerate(indices, 1):
            item = by_index[index]
            _run_one(
                store,
                item["url"],
                item["title"],
                language,
                f"{position}/{len(indices)}",
            )
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
