#!/usr/bin/env python3
"""Extract canonical Sadeha PDF bookmarks/outlines for Scholar article boundaries."""
from __future__ import annotations
import json,re
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'sadeha-pdf-outlines.json'
PDF_RE=re.compile(r'^Sadeha\s+(\d{1,2})(?:\s+v(\d+))?\.pdf$',re.I)

def canonical():
    d={}
    for p in ROOT.glob('Sadeha*.pdf'):
        m=PDF_RE.match(p.name)
        if not m: continue
        issue=int(m.group(1)); ver=int(m.group(2) or 1)
        cur=d.get(issue)
        if cur is None or (ver,p.stat().st_size)>(cur[0],cur[1].stat().st_size): d[issue]=(ver,p)
    return [(i,x[1]) for i,x in sorted(d.items())]

def main():
    rows=[]
    for issue,p in canonical():
        doc=fitz.open(p)
        toc=doc.get_toc(simple=True) or []
        rows.append({'issue':issue,'pdf':p.name,'pages':doc.page_count,'outline_count':len(toc),
                     'outline':[{'level':int(x[0]),'title':str(x[1]).strip(),'page':int(x[2])} for x in toc]})
    OUT.write_text(json.dumps({'issues':len(rows),'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Sadeha PDF outlines:',len(rows),'issues;',sum(r['outline_count'] for r in rows),'outline entries')
if __name__=='__main__': main()
