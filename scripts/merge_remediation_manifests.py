#!/usr/bin/env python3
from __future__ import annotations
import argparse, glob, json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--input-glob', default='downloaded/**/manifest.json')
p.add_argument('--output', default='accessible-pdf-manifest.json')
p.add_argument('--expected', type=int, default=0)
a=p.parse_args()
records={}
source_count=0
for name in glob.glob(a.input_glob, recursive=True):
    data=json.loads(Path(name).read_text(encoding='utf-8'))
    source_count=max(source_count, int(data.get('sourcePdfCount',0)))
    for rec in data.get('records',[]):
        records[rec['sourcePath']]=rec
ordered=[records[k] for k in sorted(records)]
summary=Counter(r.get('status','unknown') for r in ordered)
expected=a.expected or source_count
out={
    'schemaVersion':1,
    'repository':'videha-ejournal/videha-sadeha',
    'releaseTag':'accessible-pdf-v1',
    'generated':datetime.now(timezone.utc).isoformat(),
    'expectedSourcePdfCount':expected,
    'processedPdfCount':len(ordered),
    'summary':dict(summary),
    'complete':len(ordered)==expected and summary.get('pdfua-validated',0)==expected,
    'records':ordered,
}
Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:out[k] for k in ('expectedSourcePdfCount','processedPdfCount','summary','complete')},indent=2))
raise SystemExit(0 if out['complete'] else 1)
