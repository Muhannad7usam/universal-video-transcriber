import re
def _join_segments(segments): return " ".join(s["text"].strip() for s in segments if s.get("text","").strip())
def clean_transcript(segments):
    text=_join_segments(segments); text=re.sub(r"[ \t]+"," ",text); text=re.sub(r" *([.!?؟]) +",r"\1\n\n",text); return text.strip()
def timestamped_transcript(segments):
    def ts(x): x=int(max(0,x)); return f"{x//3600:02d}:{(x%3600)//60:02d}:{x%60:02d}"
    return "\n\n".join(f"{ts(s['start'])} – {ts(s['end'])}\n{s['text'].strip()}" for s in segments if s.get("text","").strip())
def language_label(code:str)->str: return {"ar":"Arabic","en":"English","fr":"French","es":"Spanish","de":"German"}.get(code,code or "Unknown")
def format_caption_text(text:str): return "\n\n".join(p.strip() for p in re.split(r"(?<=[.!?؟])\s+",text) if p.strip())
