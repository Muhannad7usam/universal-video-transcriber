import html
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET


def _clean_line(s):
    return re.sub(
        r"\s+",
        " ",
        html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\ufeff", ""),
    ).strip()


def _seconds(v):
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    parts = v.replace(",", ".").strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except (ValueError, TypeError):
        return 0.0


def _norm_word(token: str) -> str:
    return re.sub(r"[^\w]+", "", token, flags=re.UNICODE).casefold()


def _collapse_repeated_blocks(text: str) -> str:
    """Collapse obvious immediate duplicated subtitle blocks.

    YouTube rolling captions sometimes place the same multi-word phrase two or
    three times inside one cue. Only blocks of at least three words are
    collapsed so normal emphasis such as "لا لا" is preserved.
    """
    tokens = text.split()
    if len(tokens) < 6:
        return text

    out = []
    i = 0
    while i < len(tokens):
        matched = False
        max_size = min(40, (len(tokens) - i) // 2)
        for size in range(max_size, 2, -1):
            base = [_norm_word(x) for x in tokens[i : i + size]]
            if not all(base):
                continue
            count = 1
            pos = i + size
            while pos + size <= len(tokens):
                candidate = [_norm_word(x) for x in tokens[pos : pos + size]]
                if candidate != base:
                    break
                count += 1
                pos += size
            if count >= 2:
                out.extend(tokens[i : i + size])
                i = pos
                matched = True
                break
        if not matched:
            out.append(tokens[i])
            i += 1
    return " ".join(out)


def _dedupe_rolling_segments(segments):
    """Turn rolling/overlapping captions into incremental transcript text.

    Auto-captions frequently repeat the previous cue and append only a few new
    words. We keep the first occurrence and remove only a >=3-word overlap with
    already-emitted text. Timestamps remain attached to the newly introduced
    words, which also keeps the timestamped transcript useful.
    """
    result = []
    history = []
    previous_norm = None

    for segment in segments:
        text = _collapse_repeated_blocks(_clean_line(segment.get("text", "")))
        if not text:
            continue

        raw_tokens = text.split()
        pairs = []
        for raw_index, token in enumerate(raw_tokens):
            norm = _norm_word(token)
            if norm:
                pairs.append((raw_index, norm))

        current_norm = [norm for _, norm in pairs]
        if not current_norm:
            continue

        # Exact consecutive duplicate cue, including short cues.
        if previous_norm == current_norm:
            continue

        overlap = 0
        max_overlap = min(len(history), len(current_norm), 120)
        for size in range(max_overlap, 2, -1):
            if history[-size:] == current_norm[:size]:
                overlap = size
                break

        if overlap:
            cutoff = pairs[overlap - 1][0] + 1
            raw_tokens = raw_tokens[cutoff:]
            current_norm = current_norm[overlap:]
            text = " ".join(raw_tokens).strip()
            if not text or not current_norm:
                previous_norm = [norm for _, norm in pairs]
                continue

        result.append(
            {
                "start": float(segment.get("start", 0.0) or 0.0),
                "end": float(segment.get("end", 0.0) or 0.0),
                "text": text,
            }
        )
        history.extend(current_norm)
        history = history[-240:]
        previous_norm = [norm for _, norm in pairs]

    return result


def parse_vtt_srt_segments(text):
    lines = text.replace("\r\n", "\n").split("\n")
    segments = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.upper() == "WEBVTT" or line.startswith("NOTE"):
            i += 1
            continue
        if "-->" not in line and i + 1 < len(lines) and "-->" in lines[i + 1]:
            i += 1
            line = lines[i].strip()
        if "-->" in line:
            a, b = [x.strip().split()[0] for x in line.split("-->", 1)]
            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1
            value = _clean_line(" ".join(text_lines))
            if value:
                segments.append(
                    {
                        "start": _seconds(a),
                        "end": max(_seconds(b), _seconds(a)),
                        "text": value,
                    }
                )
            continue
        i += 1
    return _dedupe_rolling_segments(segments)


def parse_vtt_srt(text):
    return " ".join(s["text"] for s in parse_vtt_srt_segments(text))


def parse_ttml_segments(text):
    root = ET.fromstring(text)
    vals = []
    for el in root.iter():
        if el.tag.endswith("p") and "".join(el.itertext()).strip():
            value = _clean_line("".join(el.itertext()))
            a = _seconds(el.attrib.get("begin"))
            b = _seconds(el.attrib.get("end"))
            vals.append({"start": a, "end": max(b, a), "text": value})
    return _dedupe_rolling_segments(vals)


def parse_ttml(text):
    return " ".join(s["text"] for s in parse_ttml_segments(text))


def parse_json3_segments(text):
    vals = []
    for ev in json.loads(text).get("events", []):
        value = _clean_line("".join(x.get("utf8", "") for x in ev.get("segs", [])))
        if value:
            a = float(ev.get("tStartMs", 0)) / 1000
            b = a + float(ev.get("dDurationMs", 0)) / 1000
            vals.append({"start": a, "end": max(b, a), "text": value})
    return _dedupe_rolling_segments(vals)


def parse_json3(text):
    return " ".join(s["text"] for s in parse_json3_segments(text))


def normalize_segments(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    ext = path.suffix.lower()
    if ext in {".vtt", ".srt"}:
        return parse_vtt_srt_segments(text)
    if ext in {".ttml", ".xml"}:
        return parse_ttml_segments(text)
    if ext in {".json3", ".json"}:
        return parse_json3_segments(text)
    value = _clean_line(text)
    return _dedupe_rolling_segments(
        [{"start": 0.0, "end": 0.0, "text": value}] if value else []
    )


def normalize_file(path: Path) -> str:
    return " ".join(s["text"] for s in normalize_segments(path))
