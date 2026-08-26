#!/usr/bin/env python3
"""Map every existing Sadeha search HTML source to original Videha articles.

Each Sadeha HTML file is a distinct source document, including multiple versions of
the same issue. Exact/high-confidence reprints are mapped to their original Videha
bibliographic identity so Scholar does not receive competing duplicate citations.
Only source-clean, author-confirmed matches enter the automatic Scholar rediscovery
queue; malformed legacy author/title rows remain raw matches for audit only.
"""
from __future__ import annotations
import html, json, re, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'sadeha-videha-map.json'
INV_URL='https://raw.githubusercontent.com/videha-ejournal/videha/main/research/data/article-inventory.json'
PUB_URL='https://raw.githubusercontent.com/videha-ejournal/videha/main/research/data/articles.json'
SEC_RE=re.compile(r'<section class="pdf-page" data-pdf-page="(\d+)">.*?<pre>(.*?)</pre></section>',re.S|re.I)
PUNCT=re.compile(r'[\s\-–—:;,.()\[\]{}\'"’‘“”।!?/\\]+')
BAD_AUTHOR=['उपन्यास','कथा','कविता','गीत','गजल','नाटक','प्रहसन','समीक्षा','आलोचना','समालोचना','इतिहास','संस्कृति','शोध','रिपोर्ताज','सम्पादकीय','संपादकीय','ग्रन्थ','पुस्तक','व्याकरण','भाषा','लेख','पद्य','गद्य']
BAD_TITLE=['सम्पादकीय','संपादकीय','समाचार','साक्षात्कार']
CREATIVE=['कथा','कविता','गीत','गजल','नाटक','प्रहसन','उपन्यास','लघुकथा','वंदना','दोहा']
SCHOLAR_CLASSES={'research-explicit','references-present','literary-criticism','linguistics','history','culture-art','academic-review','research-article'}

def fetch_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Videha-Sadeha-Scholar/1.0'})
    with urllib.request.urlopen(req,timeout=90) as r: return json.load(r)

def norm(s): return PUNCT.sub('',html.unescape(str(s or '')).lower())
def issue_num(path):
    m=re.search(r'(\d+)',path.stem); return int(m.group(1)) if m else None

def sane_metadata(r):
    title=str(r.get('title') or '').strip(); author=str(r.get('author') or '').strip(); lowa=author.lower(); lowt=title.lower()
    if len(title)<5 or len(title)>320 or len(author)<2 or len(author)>120: return False
    if any(x.lower() in lowa for x in BAD_AUTHOR): return False
    if any(x.lower() in lowt for x in BAD_TITLE): return False
    if re.search(r'https?://|www\.',lowa): return False
    # Common legacy reversal: a long topic-like author paired with a short person-name title.
    if len(author)>55 and len(title)<35: return False
    return True

def strong_scholar_row(r):
    if not bool(r.get('scholar_candidate')) or not sane_metadata(r): return False
    title=str(r.get('title') or '').lower(); cls=str(r.get('classification') or '').lower()
    if any(x in title for x in CREATIVE) and not any(x in title for x in ['आलोचना','समालोचना','समीक्षा','अध्ययन','विश्लेषण']): return False
    try: body=int(r.get('body_chars') or 0)
    except Exception: body=0
    if body and body<1800: return False
    return cls in SCHOLAR_CLASSES or any(x in cls for x in ['research','reference','criticism','lingu','history','culture','academic'])

def page_texts(path):
    raw=path.read_text(encoding='utf-8',errors='ignore'); out=[]
    for m in SEC_RE.finditer(raw): out.append((int(m.group(1)),html.unescape(re.sub(r'<[^>]+>',' ',m.group(2)))))
    if not out: out=[(1,html.unescape(re.sub(r'<[^>]+>',' ',raw)))]
    return out

def main():
    inv=fetch_json(INV_URL); pub=fetch_json(PUB_URL)
    inv_rows=inv.get('rows') or inv.get('articles') or []
    published={(str(x.get('issue') or ''),norm(x.get('title')),norm(' '.join(x.get('authors') or []))) for x in pub.get('articles',[])}
    originals=[]
    for r in inv_rows:
        title=str(r.get('title') or '').strip(); author=str(r.get('author') or '').strip(); nt,na=norm(title),norm(author)
        if len(nt)<12 or len(na)<4: continue
        originals.append((r,nt,na))
    paths=sorted((ROOT/'search-documents').glob('sadeha-*.html'),key=lambda p:(issue_num(p) or 9999,p.name.lower()))
    matches=[]
    for path in paths:
        issue=issue_num(path); pages=page_texts(path); page_norm=[(p,norm(t)) for p,t in pages]; whole=''.join(t for _,t in page_norm)
        for r,nt,na in originals:
            if nt not in whole: continue
            found_page=None; author_on_page=False
            for p,t in page_norm:
                if nt in t: found_page=p; author_on_page=(na in t); break
            if found_page is None:
                if na not in whole: continue
                confidence='title-source-exact+author-source'
            else: confidence='title-page-exact+author-page' if author_on_page else 'title-page-exact'
            matches.append({
                'sadeha_source_file':path.name,'sadeha_source_key':path.stem,'sadeha_issue':issue,'sadeha_page':found_page,
                'confidence':confidence,'videha_issue':str(r.get('issue') or ''),'videha_section':str(r.get('section') or ''),
                'publication_date':r.get('publication_date'),'author':r.get('author'),'title':r.get('title'),'classification':r.get('classification'),
                'body_chars':r.get('body_chars'),'scholar_candidate':bool(r.get('scholar_candidate')),'metadata_sane':sane_metadata(r),
                'safe_scholar_rediscovery':strong_scholar_row(r) and confidence=='title-page-exact+author-page',
                'source_path':r.get('source_path'),'already_published':(str(r.get('issue') or ''),nt,na) in published,
            })
    dedup={}; rank={'title-page-exact+author-page':3,'title-page-exact':2,'title-source-exact+author-source':1}
    for m in matches:
        k=(m['sadeha_source_file'],m['videha_issue'],m['videha_section'],norm(m['title']))
        if k not in dedup or rank[m['confidence']]>rank[dedup[k]['confidence']]: dedup[k]=m
    matches=sorted(dedup.values(),key=lambda x:(x['sadeha_issue'] or 9999,x['sadeha_source_file'],x['sadeha_page'] or 99999,int(x['videha_issue'] or 0),x['videha_section']))
    scholar=[m for m in matches if m['safe_scholar_rediscovery']]; new=[m for m in scholar if not m['already_published']]
    unique_originals={(m['videha_issue'],m['videha_section'],norm(m['title'])) for m in matches}
    unique_scholar={(m['videha_issue'],m['videha_section'],norm(m['title'])) for m in scholar}
    unique_new={(m['videha_issue'],m['videha_section'],norm(m['title'])) for m in new}
    payload={
        'sadeha_source_html_files_scanned':len(paths),'sadeha_distinct_issue_numbers':len({issue_num(p) for p in paths if issue_num(p) is not None}),
        'source_files':[p.name for p in paths],'videha_inventory_entries':len(inv_rows),'high_confidence_reprint_matches_by_source':len(matches),
        'unique_videha_originals_rediscovered':len(unique_originals),'safe_scholar_reprint_matches_by_source':len(scholar),
        'unique_safe_scholar_originals_rediscovered':len(unique_scholar),'safe_scholar_matches_not_yet_published_by_source':len(new),
        'unique_safe_scholar_originals_not_yet_published':len(unique_new),'matches':matches,'new_scholar_candidates':new,
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"Sadeha/Videha map: {len(paths)} source HTML files; {len(unique_originals)} unique originals; {len(unique_scholar)} safe Scholar originals; {len(unique_new)} not yet published")
if __name__=='__main__': main()
