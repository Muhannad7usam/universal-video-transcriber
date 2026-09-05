from pathlib import Path
import core.pipeline as pipeline

def test_caption_preference(monkeypatch,tmp_path):
    assert hasattr(pipeline,"run_job")
