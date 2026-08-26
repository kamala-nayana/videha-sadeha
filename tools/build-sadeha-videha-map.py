#!/usr/bin/env python3
"""Map Sadeha compilation text to original Videha article inventory.

Sadeha volumes are thematic/parallel compilations of Videha material under the same
ISSN. For Scholar discovery, the safest strategy is to identify original Videha
article identities and avoid duplicate citations for reprints.

This script downloads the public Videha article inventory + current Scholar article
list, finds high-confidence title/author occurrences in Sadeha page text, and emits:
- all high-confidence reprint matches;
- Scholar-candidate originals rediscovered through Sadeha;
- candidates not already represented by a Videha Scholar HTML page.
No metadata is invented.
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


def fetch_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Videha-Sadeha-Scholar/1.0'})
    with urllib.request.urlopen(req,timeout=60) as r:
        return json.load(r)

def norm(s):
    s=html.unescape(str(s or '')).lower()
    return PUNCT.sub('',s)

def page_texts(path):
    raw=path.read_text(encoding='utf-8',errors='ignore')
    out=[]
    for m in SEC_RE.finditer(raw):
        out.append((int(m.group(1)),html.unescape(re.sub(r'<[^>]+>',' ',m.group(2)))))
    return out

def main():
    inv=fetch_json(INV_URL)
    pub=fetch_json(PUB_URL)
    inv_rows=inv.get('rows') or inv.get('articles') or []
    published={(str(x.get('issue') or ''),norm(x.get('title')),norm(' '.join(x.get('authors') or []))) for x in pub.get('articles',[])}
    # Build compact original candidates. Very short/generic titles are unsafe to match.
    originals=[]
    for r in inv_rows:
        title=str(r.get('title') or '').strip(); author=str(r.get('author') or '').strip()
        nt,na=norm(title),norm(author)
        if len(nt)<12 or len(na)<4: continue
        originals.append((r,nt,na))
    matches=[]
    for path in sorted((ROOT/'search-documents').glob('sadeha-*.html')):
        issue=int(re.search(r'(\d+)',path.stem).group(1))
        pages=page_texts(path)
        page_norm=[(p,norm(t)) for p,t in pages]
        whole=''.join(t for _,t in page_norm)
        for r,nt,na in originals:
            # Exact normalized title is the primary identity test.
            if nt not in whole: continue
            found_page=None; author_on_page=False
            for p,t in page_norm:
                if nt in t:
                    found_page=p; author_on_page=(na in t); break
            # If title crosses a page boundary, accept only when author also occurs in issue.
            if found_page is None:
                if na not in whole: continue
                confidence='title-issue-exact+author-issue'
            else:
                confidence='title-page-exact+author-page' if author_on_page else 'title-page-exact'
            matches.append({
                'sadeha_issue':issue,
                'sadeha_page':found_page,
                'confidence':confidence,
                'videha_issue':str(r.get('issue') or ''),
                'videha_section':str(r.get('section') or ''),
                'publication_date':r.get('publication_date'),
                'author':r.get('author'),
                'title':r.get('title'),
                'classification':r.get('classification'),
                'scholar_candidate':bool(r.get('scholar_candidate')),
                'source_path':r.get('source_path'),
                'already_published':(str(r.get('issue') or ''),nt,na) in published,
            })
    # De-duplicate repeated hits within same Sadeha issue/original identity.
    dedup={}
    rank={'title-page-exact+author-page':3,'title-page-exact':2,'title-issue-exact+author-issue':1}
    for m in matches:
        k=(m['sadeha_issue'],m['videha_issue'],m['videha_section'],norm(m['title']))
        if k not in dedup or rank[m['confidence']]>rank[dedup[k]['confidence']]: dedup[k]=m
    matches=sorted(dedup.values(),key=lambda x:(x['sadeha_issue'],x['sadeha_page'] or 99999,int(x['videha_issue'] or 0),x['videha_section']))
    scholar=[m for m in matches if m['scholar_candidate']]
    new=[m for m in scholar if not m['already_published']]
    payload={
        'sadeha_issues_scanned':len(list((ROOT/'search-documents').glob('sadeha-*.html'))),
        'videha_inventory_entries':len(inv_rows),
        'high_confidence_reprint_matches':len(matches),
        'scholar_candidate_reprints':len(scholar),
        'scholar_candidates_not_yet_published':len(new),
        'matches':matches,
        'new_scholar_candidates':new,
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"Sadeha/Videha map: {payload['sadeha_issues_scanned']} Sadeha issues; {len(matches)} high-confidence reprint matches; {len(scholar)} Scholar candidates; {len(new)} not yet published")
if __name__=='__main__': main()
