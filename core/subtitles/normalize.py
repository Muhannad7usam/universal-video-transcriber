import html,json,re
from pathlib import Path
from xml.etree import ElementTree as ET
def _clean_line(s): return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>","",s)).replace("\ufeff","")).strip()
def _seconds(v):
    if v is None:return 0.0
    if isinstance(v,(int,float)):return float(v)
    parts=v.replace(",",".").strip().split(":")
    try:
        if len(parts)==3:return int(parts[0])*3600+int(parts[1])*60+float(parts[2])
        if len(parts)==2:return int(parts[0])*60+float(parts[1])
        return float(parts[0])
    except (ValueError,TypeError):return 0.0
def parse_vtt_srt_segments(text):
    lines=text.replace("\r\n","\n").split("\n"); segments=[]; i=0
    while i<len(lines):
        line=lines[i].strip()
        if not line or line.upper()=="WEBVTT" or line.startswith("NOTE"): i+=1; continue
        if "-->" not in line and i+1<len(lines) and "-->" in lines[i+1]: i+=1; line=lines[i].strip()
        if "-->" in line:
            a,b=[x.strip().split()[0] for x in line.split("-->",1)]; i+=1; text_lines=[]
            while i<len(lines) and lines[i].strip(): text_lines.append(lines[i].strip()); i+=1
            value=_clean_line(" ".join(text_lines))
            if value and (not segments or segments[-1]["text"]!=value): segments.append({"start":_seconds(a),"end":max(_seconds(b),_seconds(a)),"text":value})
            continue
        i+=1
    return segments
def parse_vtt_srt(text): return " ".join(s["text"] for s in parse_vtt_srt_segments(text))
def parse_ttml_segments(text):
    root=ET.fromstring(text); vals=[]
    for el in root.iter():
        if el.tag.endswith("p") and "".join(el.itertext()).strip():
            v=_clean_line("".join(el.itertext())); a=_seconds(el.attrib.get("begin")); b=_seconds(el.attrib.get("end")); vals.append({"start":a,"end":max(b,a),"text":v})
    return vals
def parse_ttml(text): return " ".join(s["text"] for s in parse_ttml_segments(text))
def parse_json3_segments(text):
    vals=[]
    for ev in json.loads(text).get("events",[]):
        v=_clean_line("".join(x.get("utf8","") for x in ev.get("segs",[])))
        if v:
            a=float(ev.get("tStartMs",0))/1000; b=a+float(ev.get("dDurationMs",0))/1000
            if not vals or vals[-1]["text"]!=v: vals.append({"start":a,"end":max(b,a),"text":v})
    return vals
def parse_json3(text): return " ".join(s["text"] for s in parse_json3_segments(text))
def normalize_segments(path:Path):
    text=path.read_text(encoding="utf-8",errors="replace"); ext=path.suffix.lower()
    if ext in {".vtt",".srt"}: return parse_vtt_srt_segments(text)
    if ext in {".ttml",".xml"}: return parse_ttml_segments(text)
    if ext in {".json3",".json"}: return parse_json3_segments(text)
    value=_clean_line(text); return [{"start":0.0,"end":0.0,"text":value}] if value else []
def normalize_file(path:Path)->str: return " ".join(s["text"] for s in normalize_segments(path))
