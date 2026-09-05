import sqlite3,threading
from pathlib import Path
from datetime import datetime,timezone
class JobStore:
    def __init__(self,path:Path):
        self.path=path; self.lock=threading.RLock(); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._conn() as c: c.execute("CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, group_id TEXT, item_index INTEGER, url TEXT, title TEXT, state TEXT, progress INTEGER DEFAULT 0, language TEXT, method TEXT, result_dir TEXT, error TEXT, created_at TEXT, updated_at TEXT)")
    def _conn(self): return sqlite3.connect(self.path,check_same_thread=False)
    def create(self,job_id,url,title,group_id=None,item_index=None):
        now=datetime.now(timezone.utc).isoformat()
        with self.lock,self._conn() as c: c.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(job_id,group_id,item_index,url,title,"queued",0,None,None,None,None,now,now))
    def update(self,job_id,**fields):
        if not fields: return
        fields["updated_at"]=datetime.now(timezone.utc).isoformat(); keys=list(fields); vals=[fields[k] for k in keys]
        with self.lock,self._conn() as c: c.execute(f"UPDATE jobs SET {', '.join(k+'=?' for k in keys)} WHERE id=?",vals+[job_id])
    def get(self,job_id):
        with self.lock,self._conn() as c:
            c.row_factory=sqlite3.Row; r=c.execute("SELECT * FROM jobs WHERE id=?",(job_id,)).fetchone(); return dict(r) if r else None
    def group(self,group_id):
        with self.lock,self._conn() as c:
            c.row_factory=sqlite3.Row; return [dict(x) for x in c.execute("SELECT * FROM jobs WHERE group_id=? ORDER BY item_index",(group_id,)).fetchall()]
    def active_ids(self):
        with self.lock,self._conn() as c: return {r[0] for r in c.execute("SELECT id FROM jobs WHERE state NOT IN ('completed','failed')").fetchall()}
