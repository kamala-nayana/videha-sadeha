#!/usr/bin/env python3
"""Fetch every authoritative Sadeha search HTML without checking out large PDFs.

The Git Trees API is used instead of directory Contents listing because the
search-documents directory can exceed the Contents API's practical directory limit.
Downloaded HTMLs are temporary workflow inputs and are never written back over the
source corpus.
"""
from __future__ import annotations
import json,os,urllib.parse,urllib.request
from pathlib import Path
REPO=os.environ.get('GITHUB_REPOSITORY','videha-ejournal/videha-sadeha')
REF=os.environ.get('GITHUB_SHA') or 'main'
ROOT=Path(__file__).resolve().parents[1]; DEST=ROOT/'search-documents'

def request(url):
 headers={'User-Agent':'Videha-Sadeha-Scholar/1.0','Accept':'application/vnd.github+json'}
 token=os.environ.get('GITHUB_TOKEN')
 if token: headers['Authorization']=f'Bearer {token}'
 return urllib.request.Request(url,headers=headers)

def get_json(url):
 with urllib.request.urlopen(request(url),timeout=90) as r: return json.load(r)

def main():
 tree=get_json(f'https://api.github.com/repos/{REPO}/git/trees/{REF}?recursive=1')
 if tree.get('truncated'): raise SystemExit('Git tree response truncated; cannot verify complete Sadeha source corpus')
 items=[]
 for x in tree.get('tree',[]):
  path=str(x.get('path') or '')
  name=Path(path).name
  if x.get('type')=='blob' and path.startswith('search-documents/') and name.lower().startswith('sadeha-') and name.lower().endswith('.html'):
   items.append({'path':path,'name':name,'sha':x.get('sha'),'size':x.get('size')})
 items.sort(key=lambda x:x['name'].lower())
 print(f'Authoritative Sadeha search HTML files listed by Git tree: {len(items)}')
 if len(items)<38: raise SystemExit(f'Expected at least 38 Sadeha search HTML files; found {len(items)}')
 DEST.mkdir(parents=True,exist_ok=True)
 manifest=[]
 for x in items:
  raw=f'https://raw.githubusercontent.com/{REPO}/{urllib.parse.quote(REF,safe="")}/{urllib.parse.quote(x["path"],safe="/")}'
  with urllib.request.urlopen(request(raw),timeout=180) as r: data=r.read()
  (DEST/x['name']).write_bytes(data)
  manifest.append({'name':x['name'],'path':x['path'],'size':len(data),'sha':x.get('sha')})
  print(x['name'],len(data))
 (ROOT/'data'/'sadeha-authoritative-source-manifest.json').write_text(json.dumps({'count':len(manifest),'files':manifest},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__': main()
