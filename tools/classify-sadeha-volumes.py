#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'data'/'sadeha-discovery-summary.json'; OUT=ROOT/'data'/'sadeha-volume-classes.json'
SCH=['समालोचना','आलोचना','प्रबन्ध','प्रबंध','निबन्ध','निबंध','इतिहास','भाषा','व्याकरण','शोध','समीक्षा','संस्कृति','चित्रकला','दर्शन','न्याय','तर्क','लोक']
CRE=['लघुकथा','कथा','पद्य','कविता','नाट्य','नाटक','शिशु','बाल','उपन्यास','गीत','गजल']

def main():
 d=json.loads(SRC.read_text(encoding='utf-8')); rows=[]
 for r in d.get('rows',[]):
  head=' | '.join(r.get('head',[])[:28]); sch=sorted({x for x in SCH if x in head}); cre=sorted({x for x in CRE if x in head})
  title_lines=[]
  for line in r.get('head',[])[3:28]:
   if line.isdigit() or line.startswith('PDF page') or 'ISSN' in line or 'ISBN' in line: continue
   if len(line)>3: title_lines.append(line)
  cls='scholarly-priority' if sch and not (cre and not any(x in sch for x in ['समालोचना','आलोचना','शोध','इतिहास','भाषा'])) else ('creative-low-priority' if cre and not sch else 'mixed-review')
  rows.append({'source_file':r.get('source_file'),'source_key':r.get('source_key'),'issue':r.get('issue'),'classification':cls,'scholarly_signals':sch,'creative_signals':cre,'front_matter_lines':title_lines[:8]})
 payload={'source_html_files':len(rows),'distinct_issue_numbers':len({x.get('issue') for x in rows if x.get('issue') is not None}),'rows':rows}
 OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Sadeha source classes:',len(rows),'HTML sources;',sum(x['classification']=='scholarly-priority' for x in rows),'scholarly-priority,',sum(x['classification']=='mixed-review' for x in rows),'mixed,',sum(x['classification']=='creative-low-priority' for x in rows),'creative-low-priority')
if __name__=='__main__': main()
