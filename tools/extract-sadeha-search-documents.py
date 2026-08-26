#!/usr/bin/env python3
"""Extract canonical Sadeha issue PDFs into searchable HTML source documents.

- Scans Sadeha 01..NN PDFs in repository root.
- Prefers a `v2` file for an issue when present.
- Uses PyMuPDF text extraction page by page (no OCR/invention).
- Writes search-documents/sadeha-NNN.html and an extraction manifest.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "search-documents"
DATA = ROOT / "data" / "sadeha-text-extraction.json"
PDF_RE = re.compile(r"^Sadeha\s+(\d{1,2})(?:\s+v(\d+))?\.pdf$", re.I)


def canonical_pdfs() -> list[tuple[int, Path]]:
    by_issue: dict[int, list[tuple[int, Path]]] = {}
    for p in ROOT.glob("Sadeha*.pdf"):
        m = PDF_RE.match(p.name)
        if not m:
            continue
        issue = int(m.group(1))
        version = int(m.group(2) or 1)
        by_issue.setdefault(issue, []).append((version, p))
    out = []
    for issue, choices in sorted(by_issue.items()):
        choices.sort(key=lambda x: (x[0], x[1].stat().st_size), reverse=True)
        out.append((issue, choices[0][1]))
    return out


def pdf_url(path: Path) -> str:
    from urllib.parse import quote
    return "https://videha-ejournal.github.io/videha-sadeha/" + quote(path.name)


def extract(issue: int, path: Path) -> dict:
    doc = fitz.open(path)
    pages = []
    total_chars = 0
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text") or ""
        text = text.replace("\x00", "").strip()
        total_chars += len(text)
        pages.append((i, text))
    title = f"SADEHA — Issue {issue:02d} / अंक {issue}"
    body = []
    for page_no, text in pages:
        body.append(f'<section class="pdf-page" data-pdf-page="{page_no}"><h2>PDF page {page_no}</h2><pre>{html.escape(text)}</pre></section>')
    out_path = OUT / f"sadeha-{issue:03d}.html"
    out_path.write_text(
        "<!doctype html>\n<html lang=\"mai-Deva\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title>"
        '<meta name="robots" content="index,follow">'
        f'<meta data-pagefind-meta="title" content="{html.escape(title)}">'
        '<meta data-pagefind-meta="publication" content="SADEHA">'
        f'<meta data-pagefind-filter="issue[content]" content="{issue}">'
        '<meta data-pagefind-filter="videha_type[content]" content="Sadeha archive document">'
        "<style>body{max-width:78rem;margin:auto;padding:1.2rem;font:18px/1.6 Georgia,serif}.pdf-page{border-top:1px solid #bbb;margin-top:2rem}pre{white-space:pre-wrap;font:inherit}</style>"
        "</head><body><main data-pagefind-body>"
        f"<h1>{html.escape(title)}</h1><p><a href=\"{html.escape(pdf_url(path))}\">Original Sadeha PDF</a></p>"
        + "\n".join(body)
        + "</main></body></html>\n",
        encoding="utf-8",
    )
    return {
        "issue": issue,
        "pdf": path.name,
        "pages": len(pages),
        "text_chars": total_chars,
        "search_document": out_path.relative_to(ROOT).as_posix(),
        "source_url": pdf_url(path),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # Remove prior generated Sadeha source docs so deleted/renamed PDFs do not linger.
    for old in OUT.glob("sadeha-*.html"):
        old.unlink()
    rows = [extract(issue, path) for issue, path in canonical_pdfs()]
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps({"issues": len(rows), "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Sadeha extraction: {len(rows)} canonical issue PDFs -> {len(rows)} searchable HTML documents")
    if rows:
        print(f"Issue range: {rows[0]['issue']}–{rows[-1]['issue']}")
        print(f"Total extracted text chars: {sum(r['text_chars'] for r in rows)}")


if __name__ == "__main__":
    main()
