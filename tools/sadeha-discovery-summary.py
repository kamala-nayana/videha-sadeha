#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'data'/'sadeha-structure-profile.json'
OUT=ROOT/'data'/'sadeha-discovery-summary.json'

def main():
    data=json.loads(SRC.read_text(encoding='utf-8'))
    rows=[]
    for r in data.get('rows',[]):
        head=r.get('head',[])
        key=r.get('keyword_lines',[])
        num=r.get('numbered_lines',[])
        # Keep concise front matter plus the earliest structural/scholarly lines.
        rows.append({
            'issue':r.get('issue'),
            'head':head[:30],
            'keyword_lines':key[:35],
            'numbered_lines':num[:60],
            'line_count':r.get('line_count'),
            'text_chars':r.get('text_chars'),
        })
    OUT.write_text(json.dumps({'issues':len(rows),'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Sadeha discovery summary: {len(rows)} issues')
if __name__=='__main__': main()
