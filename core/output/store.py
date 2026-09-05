import json
from datetime import datetime,timezone
from core.security.filenames import safe_filename
from core.config import settings
def result_dir(title:str,key:str):
    d=settings.results_dir/safe_filename(title)/safe_filename(key); d.mkdir(parents=True,exist_ok=True); return d
def save_result(*,title,url,platform,language,method,segments,clean,timestamped,job_id):
    d=result_dir(title,job_id); (d/"transcript.txt").write_text(clean,encoding="utf-8"); (d/"transcript_timestamped.txt").write_text(timestamped,encoding="utf-8")
    (d/"metadata.json").write_text(json.dumps({"title":title,"url":url,"platform":platform,"language":language,"method":method,"job_id":job_id,"created_at":datetime.now(timezone.utc).isoformat()},ensure_ascii=False,indent=2),encoding="utf-8"); return d
