#!/usr/bin/env python3
from pathlib import Path
import json,re,sys,urllib.parse
ROOT=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
OUT=Path(sys.argv[2] if len(sys.argv)>2 else 'data/sadeha-pdf-catalog.json')
BASE='https://videha-ejournal.github.io/videha-sadeha/'
def title_for(path):
    s=path.stem.replace('_',' ').replace('-',' ')
    s=re.sub(r'\s+',' ',s).strip()
    return s or path.name
items=[]
for p in ROOT.rglob('*.pdf'):
    if '.git' in p.parts: continue
    rel=p.relative_to(ROOT).as_posix()
    items.append({'path':rel,'name':p.name,'title':title_for(p),'url':BASE+urllib.parse.quote(rel,safe='/')})
items.sort(key=lambda x:x['path'].lower())
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps({'version':'2026-08-21-sadeha','count':len(items),'items':items},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
print(f'Wrote {len(items)} Sadeha PDF entries to {OUT}')
