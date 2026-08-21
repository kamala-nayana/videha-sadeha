#!/usr/bin/env python3
"""Prepare ordinary Sadeha HTML/HTM for federated Search All Videha; heavy Panji data remains shard-searched separately."""
from pathlib import Path
import shutil,re,sys
SRC=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve(); DST=Path(sys.argv[2] if len(sys.argv)>2 else '_pagefind_videha_build').resolve()
EXCLUDE={'.git','.github','pagefind','pagefind-videha-search','_pagefind_videha_build','node_modules','panji-shards','data'}
if DST.exists(): shutil.rmtree(DST)
DST.mkdir(parents=True); count=0
for p in SRC.rglob('*'):
    if not p.is_file() or p.suffix.lower() not in ('.htm','.html'): continue
    rel=p.relative_to(SRC)
    if any(part in EXCLUDE for part in rel.parts): continue
    raw=p.read_text('utf-8',errors='replace')
    if 'data-pagefind-body' not in raw and re.search(r'<body\b',raw,re.I): raw=re.sub(r'<body\b','<body data-pagefind-body',raw,count=1,flags=re.I)
    dest=DST/rel; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_text(raw,encoding='utf-8'); count+=1
print(f'Prepared {count} Sadeha HTML/HTM pages')
