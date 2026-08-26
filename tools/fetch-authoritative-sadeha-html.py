#!/usr/bin/env python3
"""Fetch every authoritative Sadeha search HTML from GitHub Contents API.

Used in Actions to avoid checking out the very large PDF repository. The downloaded
files are temporary workflow inputs and are never committed back over the source
corpus.
"""
from __future__ import annotations
import json,os,urllib.request
from pathlib import Path
REPO=os.environ.get('GITHUB_REPOSITORY','videha-ejournal/videha-sadeha')
REF=os.environ.get('GITHUB_SHA') or 'main'
API=f'https://api.github.com/repos/{REPO}/contents/search-documents?ref={REF}'
ROOT=Path(__file__).resolve().parents[1]; DEST=ROOT/'search-documents'

def request(url):
 headers={'User-Agent':'Videha-Sadeha-Scholar/1.0','Accept':'application/vnd.github+json'}
 token=os.environ.get('GITHUB_TOKEN')
 if token: headers['Authorization']=f'Bearer {token}'
 return urllib.request.Request(url,headers=headers)

def main():
 with urllib.request.urlopen(request(API),timeout=90) as r: items=json.load(r)
 files=sorted([x for x in items if x.get('type')=='file' and x.get('name','').lower().startswith('sadeha-') and x.get('name','').lower().endswith('.html')],key=lambda x:x['name'].lower())
 print(f'Authoritative Sadeha search HTML files listed by GitHub: {len(files)}')
 if len(files)<38: raise SystemExit(f'Expected at least 38 Sadeha search HTML files; found {len(files)}')
 DEST.mkdir(parents=True,exist_ok=True)
 manifest=[]
 for x in files:
  name=x['name']; url=x.get('download_url')
  if not url: raise SystemExit(f'Missing download_url for {name}')
  with urllib.request.urlopen(request(url),timeout=180) as r: data=r.read()
  (DEST/name).write_bytes(data)
  manifest.append({'name':name,'size':len(data),'sha':x.get('sha')})
  print(name,len(data))
 (ROOT/'data'/'sadeha-authoritative-source-manifest.json').write_text(json.dumps({'count':len(manifest),'files':manifest},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__': main()
