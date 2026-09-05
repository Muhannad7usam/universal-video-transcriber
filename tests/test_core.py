from pathlib import Path

from core.security.urls import validate_media_url
from core.security.filenames import safe_filename, inside
from core.playlist.selection import select_indices
from core.subtitles.normalize import parse_vtt_srt, parse_vtt_srt_segments, parse_json3
from core.subtitles.engine import find_usable_caption
from core.formatting.transcript import clean_transcript, timestamped_transcript, language_label
from core.pipeline import duration_tier


def test_url_security():
    for u in ["file:///etc/passwd", "http://127.0.0.1/x", "http://localhost/x", "http://10.0.0.1/x"]:
        try:
            validate_media_url(u)
            assert False
        except ValueError:
            pass
    assert validate_media_url("https://example.com/video") == "https://example.com/video"


def test_filename_and_path():
    assert safe_filename("../hello<>world") == "hello_world"
    base = Path("/tmp/base")
    assert inside(base, base / "child/file.txt")
    assert not inside(base, Path("/tmp/base2"))


def test_playlist_selection():
    assert select_indices(10, video=3) == [3]
    assert select_indices(10, range_=(2, 4)) == [2, 3, 4]
    assert select_indices(10, first=3) == [1, 2, 3]
    assert select_indices(4, all_items=True) == [1, 2, 3, 4]


def test_duration_tiers_cover_short_to_extremely_long():
    assert duration_tier(60) == "short"
    assert duration_tier(15 * 60) == "medium"
    assert duration_tier(60 * 60) == "long"
    assert duration_tier(4 * 60 * 60) == "extremely_long"
    assert duration_tier(24 * 60 * 60) == "extremely_long"
    assert duration_tier(None) == "unknown"


def test_subtitles_utf8():
    text = "WEBVTT\n\n00:00.000 --> 00:01.000\nالنهاردة hello\n\n00:01.000 --> 00:02.000\nالنهاردة hello"
    assert parse_vtt_srt(text) == "النهاردة hello"
    assert parse_json3('{"events":[{"tStartMs":0,"dDurationMs":1000,"segs":[{"utf8":"Hello"}]}]}') == "Hello"


def test_rolling_captions_are_deoverlapped():
    text = (
        "WEBVTT\n\n"
        "00:00.000 --> 00:01.000\nانا مستعجل عايز اطمن على الوحده\n\n"
        "00:01.000 --> 00:02.000\nانا مستعجل عايز اطمن على الوحده بتاعتي\n\n"
        "00:02.000 --> 00:03.000\nانا مستعجل عايز اطمن على الوحده بتاعتي\n\n"
        "00:03.000 --> 00:04.000\nهو البي ظابط ولا ايه\n"
    )
    segments = parse_vtt_srt_segments(text)
    assert [s["text"] for s in segments] == [
        "انا مستعجل عايز اطمن على الوحده",
        "بتاعتي",
        "هو البي ظابط ولا ايه",
    ]
    joined = " ".join(s["text"] for s in segments)
    assert joined.count("انا مستعجل") == 1


def test_repeated_blocks_inside_one_caption_are_collapsed():
    text = (
        "WEBVTT\n\n"
        "00:00.000 --> 00:03.000\n"
        "عايزين حقنا دلوقتي عايزين حقنا دلوقتي عايزين حقنا دلوقتي\n"
    )
    assert parse_vtt_srt(text) == "عايزين حقنا دلوقتي"


def test_preferred_caption_language():
    info = {
        "language": "ar",
        "subtitles": {
            "en": [{"ext": "vtt"}],
            "ar": [{"ext": "json3"}],
        },
    }
    cap = find_usable_caption(info, "ar")
    assert cap is not None
    assert cap["language"] == "ar"
    assert cap["ext"] == "json3"
    assert find_usable_caption(info, "fr") is None


def test_auto_detect_never_picks_random_translated_caption():
    info = {
        "language": "ar",
        "automatic_captions": {
            "ab": [{"ext": "vtt"}],
            "en": [{"ext": "vtt"}],
            "ar": [{"ext": "json3"}],
        },
    }
    cap = find_usable_caption(info, None)
    assert cap is not None
    assert cap["language"] == "ar"


def test_selected_language_does_not_use_translated_auto_caption():
    info = {
        "language": "en",
        "automatic_captions": {
            "en": [{"ext": "json3"}],
            "ar": [{"ext": "vtt"}],
        },
    }
    assert find_usable_caption(info, "ar") is None


def test_transcript_formatting():
    seg = [
        {"start": 0, "end": 1, "text": "Hello."},
        {"start": 2, "end": 4, "text": ">> أهلا"},
    ]
    clean = clean_transcript(seg)
    assert "Hello." in clean
    assert "أهلا" in clean
    assert ">>" not in clean
    assert "00:00:00" in timestamped_transcript(seg)
    assert language_label("ar") == "Arabic"
    assert language_label("tr") == "Turkish"
