from pathlib import Path
from core.security.urls import validate_media_url
from core.security.filenames import safe_filename, inside
from core.playlist.selection import select_indices
from core.subtitles.normalize import parse_vtt_srt, parse_json3
from core.formatting.transcript import clean_transcript, timestamped_transcript

def test_url_security():
    for u in ["file:///etc/passwd", "http://127.0.0.1/x", "http://localhost/x", "http://10.0.0.1/x"]:
        try: validate_media_url(u); assert False
        except ValueError: pass
    assert validate_media_url("https://example.com/video") == "https://example.com/video"

def test_filename_and_path():
    assert safe_filename("../hello<>world") == "hello_world"
    base=Path("/tmp/base"); assert inside(base,base/"child/file.txt"); assert not inside(base,Path("/tmp/base2"))

def test_playlist_selection():
    assert select_indices(10,video=3)==[3]
    assert select_indices(10,range_=(2,4))==[2,3,4]
    assert select_indices(10,first=3)==[1,2,3]
    assert select_indices(4,all_items=True)==[1,2,3,4]

def test_subtitles_utf8():
    assert parse_vtt_srt('WEBVTT\n\n00:00.000 --> 00:01.000\nالنهاردة hello\n\n00:01.000 --> 00:02.000\nالنهاردة hello') == 'النهاردة hello النهاردة hello'
    assert parse_json3('{"events":[{"tStartMs":0,"dDurationMs":1000,"segs":[{"utf8":"Hello"}]}]}') == 'Hello'

def test_transcript_formatting():
    seg=[{"start":0,"end":1,"text":"Hello."},{"start":2,"end":4,"text":"أهلا"}]
    assert "Hello." in clean_transcript(seg); assert "00:00:00" in timestamped_transcript(seg)
