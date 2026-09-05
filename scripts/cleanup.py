import argparse
import shutil
from datetime import datetime, timezone, timedelta

from core.config import settings
from core.security.filenames import inside
from core.jobs import JobStore


def cleanup(dry_run=False):
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.result_retention_days)
    active = JobStore(settings.jobs_dir / "jobs.db").active_ids()
    targets = []

    for base in (settings.results_dir, settings.temp_dir, settings.cache_dir):
        if not base.exists():
            continue
        for p in base.iterdir():
            if not p.is_dir() or not inside(settings.data_dir, p):
                continue
            if base != settings.cache_dir and p.name in active:
                continue
            try:
                old = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc) < cutoff
            except OSError:
                continue
            if old:
                targets.append(p)

    for p in targets:
        if not dry_run:
            shutil.rmtree(p, ignore_errors=True)
    return targets


def main():
    parser = argparse.ArgumentParser(description="Remove expired generated data safely")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    targets = cleanup(args.dry_run)
    print("Would delete:" if args.dry_run else "Deleted:")
    for p in targets:
        print(p)


if __name__ == "__main__":
    main()
