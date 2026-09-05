import re
from pathlib import Path


def safe_filename(value: str, max_len: int = 120) -> str:
    value = str(value or "")
    # Normalize separators first so user/media titles can never retain path-like
    # prefixes. Then replace filesystem-unsafe characters and trim traversal-like
    # leading punctuation left by values such as "../title".
    value = value.replace("\\", "/").split("/")[-1]
    value = re.sub(r"[^\w .-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip(" ._")
    if not value or value in {".", ".."}:
        value = "untitled"
    return value[:max_len].rstrip(" .") or "untitled"


def inside(base: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False
