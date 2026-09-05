from pathlib import Path
from core.jobs import JobStore

def test_job_store(tmp_path):
    store=JobStore(tmp_path/"jobs.db")
    store.create("1","https://example.com","Title")
    store.update("1",state="completed",progress=100)
    assert store.get("1")["state"]=="completed"

def test_cleanup(tmp_path):
    p=tmp_path/"old"; p.mkdir(); assert p.is_dir()
