import re
from pathlib import Path
def safe_filename(value:str,max_len=120)->str:
    value=re.sub(r"[^\w .-]+","_",value,flags=re.UNICODE).strip(" .") or "untitled"; return value[:max_len]
def inside(base:Path,child:Path)->bool:
    try: child.resolve().relative_to(base.resolve()); return True
    except ValueError: return False
