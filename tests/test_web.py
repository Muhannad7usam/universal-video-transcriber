from fastapi.testclient import TestClient

from web_app.main import app


def test_home_and_health():
    with TestClient(app) as c:
        r = c.get("/")
        assert r.status_code == 200
        assert "Universal Video Transcriber" in r.text
        assert "transcription-language" in r.text

        h = c.get("/health")
        assert h.status_code == 200
        assert "ffmpeg" in h.json()


def test_languages_endpoint():
    with TestClient(app) as c:
        r = c.get("/api/languages")
        assert r.status_code == 200
        languages = {x["code"]: x["name"] for x in r.json()["languages"]}
        assert languages["ar"] == "Arabic"
        assert languages["en"] == "English"


def test_unsafe_url_route():
    with TestClient(app) as c:
        r = c.post("/api/analyze", json={"url": "http://127.0.0.1/x"})
        assert r.status_code == 400


def test_invalid_language_rejected_before_download():
    with TestClient(app) as c:
        r = c.post(
            "/api/analyze",
            json={"url": "https://example.com/video", "language": "not-a-language"},
        )
        assert r.status_code == 400
        assert "Unsupported transcription language" in r.json()["detail"]
