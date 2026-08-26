#!/usr/bin/env python3
"""Create compact structural profiles from generated Sadeha source HTML."""
from __future__ import annotations
import html, json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'sadeha-structure-profile.json'
TAG=re.compile(r'<[^>]+>')
KEYS=('अनुक्रम','विषय सूची','विषयसूची','CONTENTS','Contents','शोध','आलोचना','समालोचना','समीक्षा','इतिहास','भाषा','व्याकरण','संदर्भ','सन्दर्भ','References','Bibliography')

def text_of(path:Path)->str:
    raw=path.read_text(encoding='utf-8',errors='ignore')
    raw=re.sub(r'</(?:pre|h\d|p|section)>','\n',raw,flags=re.I)
    return html.unescape(TAG.sub('',raw)).replace('\r','')

def main():
    rows=[]
    for p in sorted((ROOT/'search-documents').glob('sadeha-*.html')):
        issue=int(re.search(r'(\d+)',p.stem).group(1))
        text=text_of(p)
        lines=[re.sub(r'\s+',' ',x).strip() for x in text.splitlines()]
        lines=[x for x in lines if x]
        key_lines=[]
        numbered=[]
        for i,line in enumerate(lines):
            if any(k.lower() in line.lower() for k in KEYS) and len(line)<400:
                key_lines.append({'line':i+1,'text':line})
            if re.match(r'^(?:[०-९0-9]{1,3}(?:\.[०-९0-9]{1,3}){0,2})[.)]?\s*',line) and len(line)<350:
                numbered.append({'line':i+1,'text':line})
        rows.append({
            'issue':issue,
            'head':lines[:80],
            'keyword_lines':key_lines[:120],
            'numbered_lines':numbered[:250],
            'line_count':len(lines),
            'text_chars':len(text),
        })
    OUT.write_text(json.dumps({'issues':len(rows),'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Sadeha structural profile: {len(rows)} issues')
if __name__=='__main__': main()
