from fastapi.testclient import TestClient
from web_app.main import app

def test_home_and_health():
    with TestClient(app) as c:
        r=c.get('/'); assert r.status_code==200; assert 'Universal Video Transcriber' in r.text
        h=c.get('/health'); assert h.status_code==200; assert h.json()['ffmpeg'] is True

def test_unsafe_url_route():
    with TestClient(app) as c:
        r=c.post('/api/analyze',json={'url':'http://127.0.0.1/x'}); assert r.status_code==400
