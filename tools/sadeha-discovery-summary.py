#!/usr/bin/env python3
from __future__ import annotations
import html,json,re
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'sadeha-discovery-summary.json'
FILES_OUT=ROOT/'data'/'sadeha-source-files.json'
KEYWORDS=['शोध','समालोचना','आलोचना','समीक्षा','इतिहास','भाषा','व्याकरण','संस्कृति','लोक','दर्शन','न्याय','तर्क','research','criticism','history','linguistic']

class TextParser(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]
    def handle_data(self,data):
        if data and data.strip(): self.parts.append(data)
    def text(self): return '\n'.join(self.parts)

def issue_num(path:Path)->int|None:
    m=re.search(r'(\d+)',path.stem)
    return int(m.group(1)) if m else None

def main():
    paths=sorted((ROOT/'search-documents').glob('sadeha-*.html'), key=lambda p:(issue_num(p) or 9999,p.name.lower()))
    rows=[]
    for p in paths:
        raw=p.read_text(encoding='utf-8',errors='ignore')
        parser=TextParser()
        try: parser.feed(raw)
        except Exception: pass
        text=html.unescape(parser.text())
        lines=[re.sub(r'\s+',' ',x).strip() for x in text.splitlines()]
        lines=[x for x in lines if x]
        key=[]; numbered=[]
        for i,line in enumerate(lines,1):
            low=line.lower()
            if any(k.lower() in low for k in KEYWORDS): key.append({'line':i,'text':line})
            if re.match(r'^(?:[०-९0-9]{1,4}[.)]?|[०-९0-9]+\s*[–-]\s*[०-९0-9]+)$',line): numbered.append({'line':i,'text':line})
        rows.append({
            'source_file':p.name,
            'source_key':p.stem,
            'issue':issue_num(p),
            'head':lines[:30],
            'keyword_lines':key[:50],
            'numbered_lines':numbered[:80],
            'line_count':len(lines),
            'text_chars':len(text),
        })
    payload={'source_html_files':len(paths),'distinct_issue_numbers':len({r['issue'] for r in rows if r['issue'] is not None}),'rows':rows}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    FILES_OUT.write_text(json.dumps({'count':len(paths),'files':[{'source_file':r['source_file'],'issue':r['issue'],'source_key':r['source_key']} for r in rows]},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"Sadeha discovery summary: {len(paths)} source HTML files; {payload['distinct_issue_numbers']} distinct issue numbers")
if __name__=='__main__': main()
