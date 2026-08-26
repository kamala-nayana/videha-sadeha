#!/usr/bin/env python3
"""Find scholarly-looking Sadeha pages not already explained by a Videha reprint.

This is a review-only residual audit. It does not create Scholar pages. It works on
every authoritative Sadeha search HTML source independently, including source
variants, and records only source text/snippets plus exact match coverage.
"""
from __future__ import annotations
import html,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MAP=ROOT/'data'/'sadeha-videha-map.json'; OUT=ROOT/'data'/'sadeha-unique-scholar-audit.json'
SEC_RE=re.compile(r'<section class="pdf-page" data-pdf-page="(\d+)">.*?<pre>(.*?)</pre></section>',re.S|re.I)
SCH=['शोध','समालोचना','आलोचना','समीक्षा','इतिहास','भाषा','व्याकरण','संस्कृति','दर्शन','न्याय','तर्क','लोक','research','criticism','history','linguistic','reference','सन्दर्भ','संदर्भ']
NEG=['कविता','गीत','गजल','कथा','लघुकथा','नाटक','प्रहसन','उपन्यास','समाचार','साक्षात्कार']

def clean(s): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',s))).strip()
def pages(path):
 raw=path.read_text(encoding='utf-8',errors='ignore'); out=[]
 for m in SEC_RE.finditer(raw): out.append((int(m.group(1)),clean(m.group(2))))
 if not out: out=[(1,clean(raw))]
 return out

def main():
 mapping=json.loads(MAP.read_text(encoding='utf-8')) if MAP.exists() else {'matches':[]}
 covered={}
 for m in mapping.get('matches',[]):
  sf=m.get('sadeha_source_file'); pg=m.get('sadeha_page')
  if sf and pg is not None: covered.setdefault((sf,int(pg)),[]).append(m)
 rows=[]
 for path in sorted((ROOT/'search-documents').glob('sadeha-*.html')):
  for page,text in pages(path):
   low=text.lower(); sig=sorted({k for k in SCH if k.lower() in low}); neg=sorted({k for k in NEG if k.lower() in low})
   if not sig: continue
   lines=[x.strip() for x in re.split(r'[\n\r]+',text) if x.strip()]
   concise=[re.sub(r'\s+',' ',x) for x in lines if 3<=len(x)<=220]
   mapped=covered.get((path.name,page),[])
   scholarly_mapped=[m for m in mapped if m.get('safe_scholar_rediscovery')]
   # A page remains interesting if it has scholarly signals and no safe scholarly
   # original mapped on that page. Creative signals lower priority but do not erase
   # a page because a compilation page can contain multiple pieces.
   if scholarly_mapped: continue
   score=len(sig)*2 - len(neg)
   if any(x in low for x in ['शोध','research','समालोचना','आलोचना','इतिहास','व्याकरण','linguistic']): score+=3
   rows.append({
    'source_file':path.name,'page':page,'score':score,'scholarly_signals':sig,'creative_signals':neg,
    'mapped_originals_on_page':len(mapped),'mapped_titles':[m.get('title') for m in mapped[:8]],
    'heading_candidates':concise[:12],
    'snippet':text[:1600],
   })
 rows.sort(key=lambda r:(-r['score'],r['source_file'],r['page']))
 OUT.write_text(json.dumps({'source_html_files':len(list((ROOT/'search-documents').glob('sadeha-*.html'))),'residual_scholarly_pages':len(rows),'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
 print(f'Sadeha residual scholarly audit: {len(rows)} pages')
if __name__=='__main__': main()
