#!/usr/bin/env python3
"""Build text-first PDF/UA-1 accessibility derivatives for the Videha–Sadeha archive.

Historical source PDFs are never modified. Embedded text is used where it is sufficiently
readable; weak/missing text pages are OCRed with a Devanagari-capable Tesseract model.
The resulting semantic HTML is rendered with WeasyPrint PDF/UA-1 and validated with
pdfinfo, qpdf and, when requested, veraPDF's PDF/UA-1 profile.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO = "videha-ejournal/videha-sadeha"
RELEASE_TAG = os.environ.get("ACCESSIBLE_PDF_RELEASE", "accessible-pdf-v1")
EMBEDDED_TEXT_MIN = 80


def run(cmd: list[str], *, text: bool = True, check: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=text, capture_output=True, check=check, cwd=cwd)


def pdf_paths() -> list[str]:
    cp = run(["git", "ls-tree", "-r", "--name-only", "HEAD"])
    return sorted(p for p in cp.stdout.splitlines() if p.lower().endswith(".pdf"))


def git_blob_sha(path: str) -> str:
    cp = run(["git", "ls-tree", "HEAD", "--", path])
    if not cp.stdout.strip():
        return ""
    return cp.stdout.split()[2]


def materialize(path: str, dest: Path) -> None:
    # In a blobless checkout this fetches only the requested PDF blob.
    with dest.open("wb") as fh:
        proc = subprocess.run(["git", "show", f"HEAD:{path}"], stdout=fh, stderr=subprocess.PIPE)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_stem(source_path: str) -> str:
    stem = Path(source_path).stem
    ascii_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    ascii_stem = re.sub(r"[^A-Za-z0-9]+", "-", ascii_stem).strip("-").lower()
    if not ascii_stem:
        ascii_stem = "document"
    suffix = hashlib.sha1(source_path.encode("utf-8")).hexdigest()[:10]
    return f"{ascii_stem[:70]}-{suffix}"


def pages_in(pdf: Path) -> int:
    cp = run(["pdfinfo", str(pdf)])
    m = re.search(r"^Pages:\s+(\d+)\s*$", cp.stdout, re.M)
    if not m:
        raise RuntimeError("pdfinfo did not report a page count")
    return int(m.group(1))


def clean_text(value: str) -> str:
    value = value.replace("\x0c", "\n").replace("\r\n", "\n").replace("\r", "\n")
    value = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines())
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def useful_text(value: str) -> bool:
    meaningful = sum(ch.isalpha() or ch.isdigit() for ch in value)
    return meaningful >= EMBEDDED_TEXT_MIN


def extract_embedded(pdf: Path, page: int) -> str:
    cp = run([
        "pdftotext", "-enc", "UTF-8", "-f", str(page), "-l", str(page), "-layout", str(pdf), "-"
    ], check=False)
    return clean_text(cp.stdout or "") if cp.returncode == 0 else ""


def tesseract_lang() -> str:
    cp = run(["tesseract", "--list-langs"], check=False)
    langs = set((cp.stdout or "").splitlines())
    if "script/Devanagari" in langs:
        return "script/Devanagari+eng" if "eng" in langs else "script/Devanagari"
    if "hin" in langs:
        return "hin+eng" if "eng" in langs else "hin"
    return "eng"


def ocr_page(pdf: Path, page: int, work: Path, lang: str) -> str:
    prefix = work / f"page-{page:05d}"
    cp = run([
        "pdftoppm", "-f", str(page), "-l", str(page), "-singlefile", "-r", "200", "-png", str(pdf), str(prefix)
    ], check=False)
    image = prefix.with_suffix(".png")
    if cp.returncode != 0 or not image.exists():
        return ""
    try:
        tc = run(["tesseract", str(image), "stdout", "-l", lang, "--psm", "6"], check=False)
        return clean_text(tc.stdout or "")
    finally:
        image.unlink(missing_ok=True)


def paragraph_html(text: str) -> str:
    if not text:
        return '<p class="unrecovered">No machine-readable text was recovered from this page. Consult the preserved visual facsimile.</p>'
    chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    parts: list[str] = []
    for chunk in chunks:
        lines = [html.escape(line) for line in chunk.splitlines() if line.strip()]
        if lines:
            parts.append("<p>" + "<br>".join(lines) + "</p>")
    return "\n".join(parts) or '<p class="unrecovered">No machine-readable text was recovered from this page.</p>'


def build_html(source_path: str, source_sha: str, page_text: list[dict], created: str) -> str:
    title = f"{Path(source_path).stem} — accessible reading derivative"
    source_url = "https://github.com/videha-ejournal/videha-sadeha/blob/main/" + urllib.parse.quote(source_path, safe="/")
    ocr_pages = [str(p["page"]) for p in page_text if p["method"] == "ocr"]
    unrecovered = [str(p["page"]) for p in page_text if not p["text"]]
    provenance = (
        f"Embedded text was retained on {sum(p['method']=='embedded' for p in page_text)} page(s); "
        f"OCR was used on {len(ocr_pages)} page(s)."
    )
    if unrecovered:
        provenance += f" No text was recovered on page(s): {', '.join(unrecovered)}."
    sections = []
    for p in page_text:
        sections.append(
            f'<section class="page" aria-labelledby="page-{p["page"]}">'
            f'<h2 id="page-{p["page"]}">Source page {p["page"]}</h2>'
            f'<p class="method">Text source: {html.escape(p["method"])}.</p>'
            f'{paragraph_html(p["text"])}</section>'
        )
    return f'''<!doctype html>
<html lang="mai-Deva">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<meta name="author" content="Videha — First Maithili Fortnightly eJournal, ISSN 2229-547X">
<meta name="dcterms.source" content="{html.escape(source_path)}">
<meta name="dcterms.created" content="{created}">
<style>
@page {{ size: A4; margin: 18mm 17mm 20mm; @bottom-center {{ content: counter(page); font-size: 9pt; }} }}
html {{ font-family: "Noto Serif Devanagari", "Noto Sans Devanagari", serif; font-size: 12pt; line-height: 1.55; }}
body {{ margin: 0; }} h1 {{ font-size: 22pt; line-height: 1.25; }} h2 {{ font-size: 15pt; margin-top: 0; }}
a {{ color: #6e1322; text-decoration-thickness: .08em; }}
.notice {{ border: 1px solid #555; padding: 10pt; margin: 12pt 0; }}
.page {{ break-before: page; }} .page:first-of-type {{ break-before: auto; }}
.method {{ font-size: 9.5pt; font-style: italic; }} .unrecovered {{ font-weight: 600; }}
p {{ orphans: 3; widows: 3; }}
</style>
</head>
<body>
<main>
<h1>{html.escape(title)}</h1>
<div class="notice" role="note">
<p><strong>Accessible derivative.</strong> This text-first PDF/UA reading copy preserves the historical source PDF unchanged. It was generated from the source's embedded text where usable and from Devanagari/English OCR where a page lacked a usable text layer. OCR text is machine-generated and should not be treated as an editorially proofread transcription.</p>
<p>{html.escape(provenance)}</p>
<p>Source SHA-256: <code>{source_sha}</code>. <a href="{html.escape(source_url)}">Open the preserved source PDF</a>.</p>
</div>
{''.join(sections)}
</main>
</body>
</html>'''


def render_pdf(html_path: Path, pdf_path: Path) -> None:
    cp = run(["weasyprint", "--pdf-variant", "pdf/ua-1", str(html_path), str(pdf_path)], check=False)
    if cp.returncode:
        raise RuntimeError(f"WeasyPrint failed: {cp.stderr}")


def basic_validation(pdf: Path) -> tuple[bool, dict]:
    info = run(["pdfinfo", str(pdf)], check=False)
    tagged = bool(re.search(r"^Tagged:\s+yes\s*$", info.stdout or "", re.M | re.I))
    q = run(["qpdf", "--check", str(pdf)], check=False)
    q_ok = q.returncode == 0
    return tagged and q_ok, {"pdfinfoTagged": tagged, "qpdfCheck": q_ok}


def verapdf_validation(pdf: Path, image: str) -> tuple[bool, dict]:
    mount = pdf.parent.resolve()
    cp = run([
        "docker", "run", "--rm", "-v", f"{mount}:/data:ro", image,
        "-f", "ua1", "--format", "raw", f"/data/{pdf.name}"
    ], check=False)
    raw = cp.stdout or ""
    start = raw.find("<report")
    if start < 0:
        return False, {"veraPDF": False, "veraPDFError": (cp.stderr or raw)[-1200:]}
    try:
        root = ET.fromstring(raw[start:])
        report = root.find(".//validationReport")
        compliant = report is not None and report.attrib.get("isCompliant") == "true"
        details = report.find("details") if report is not None else None
        return compliant, {
            "veraPDF": compliant,
            "profile": report.attrib.get("profileName") if report is not None else "PDF/UA-1",
            "failedRules": int(details.attrib.get("failedRules", "0")) if details is not None else None,
            "failedChecks": int(details.attrib.get("failedChecks", "0")) if details is not None else None,
        }
    except Exception as exc:
        return False, {"veraPDF": False, "veraPDFError": str(exc), "veraPDFOutputTail": raw[-1200:]}


def source_blob_size(path: str) -> int | None:
    cp = run(["git", "cat-file", "-s", f"HEAD:{path}"], check=False)
    try:
        return int((cp.stdout or "").strip()) if cp.returncode == 0 else None
    except ValueError:
        return None


def process_one(source_path: str, out_dir: Path, vera_image: str | None) -> dict:
    created = datetime.now(timezone.utc).isoformat()
    slug = safe_stem(source_path)
    source_pdf = out_dir / f".{slug}-source.pdf"
    html_path = out_dir / f"{slug}-accessible.html"
    pdf_path = out_dir / f"{slug}-accessible.pdf"
    record = {
        "sourcePath": source_path,
        "sourceGitBlobSha": git_blob_sha(source_path),
        "sourceRepository": REPO,
        "releaseTag": RELEASE_TAG,
        "generated": created,
        "status": "processing",
    }
    try:
        materialize(source_path, source_pdf)
        record["sourceBytes"] = source_pdf.stat().st_size
        record["sourceSha256"] = sha256(source_pdf)
        pages = pages_in(source_pdf)
        record["pages"] = pages
        lang = tesseract_lang()
        record["ocrLanguage"] = lang
        page_text: list[dict] = []
        with tempfile.TemporaryDirectory(prefix="videha-ocr-") as tmp:
            work = Path(tmp)
            for page in range(1, pages + 1):
                embedded = extract_embedded(source_pdf, page)
                if useful_text(embedded):
                    page_text.append({"page": page, "method": "embedded", "text": embedded})
                else:
                    ocr = ocr_page(source_pdf, page, work, lang)
                    page_text.append({"page": page, "method": "ocr", "text": ocr})
        record["embeddedTextPages"] = sum(p["method"] == "embedded" for p in page_text)
        record["ocrPages"] = [p["page"] for p in page_text if p["method"] == "ocr"]
        record["unrecoveredTextPages"] = [p["page"] for p in page_text if not p["text"]]
        record["textMethod"] = (
            "embedded-text" if not record["ocrPages"] else
            "ocr" if len(record["ocrPages"]) == pages else "mixed"
        )
        html_text = build_html(source_path, record["sourceSha256"], page_text, created)
        html_path.write_text(html_text, encoding="utf-8")
        render_pdf(html_path, pdf_path)
        basic_ok, validation = basic_validation(pdf_path)
        record["validation"] = validation
        vera_ok = None
        if vera_image:
            vera_ok, vera_data = verapdf_validation(pdf_path, vera_image)
            record["validation"].update(vera_data)
        compliant = basic_ok and (vera_ok is not False)
        record["status"] = "pdfua-validated" if compliant and vera_image else "tagged-derivative"
        if not compliant:
            record["status"] = "validation-failed"
        record["accessiblePdfAsset"] = pdf_path.name
        record["accessiblePdfUrl"] = (
            f"https://github.com/{REPO}/releases/download/{RELEASE_TAG}/" + urllib.parse.quote(pdf_path.name)
        )
        record["accessibleHtmlArtifact"] = html_path.name
        record["outputBytes"] = pdf_path.stat().st_size
        record["outputSha256"] = sha256(pdf_path)
        record["editorialTextVerification"] = "not-reviewed"
        record["humanReviewRequired"] = bool(record["ocrPages"] or record["unrecoveredTextPages"])
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        source_pdf.unlink(missing_ok=True)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default="remediated")
    parser.add_argument("--verapdf-image", default="")
    parser.add_argument("--require-pdfua", action="store_true")
    args = parser.parse_args()

    all_paths = pdf_paths()
    selected = [p for i, p in enumerate(all_paths) if i % args.shard_count == args.shard_index]
    if args.limit:
        selected = selected[: args.limit]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    print(f"Archive PDFs: {len(all_paths)}; shard {args.shard_index}/{args.shard_count}: {len(selected)}")
    for number, source_path in enumerate(selected, 1):
        print(f"[{number}/{len(selected)}] {source_path}", flush=True)
        rec = process_one(source_path, out_dir, args.verapdf_image or None)
        records.append(rec)
        print(f"  -> {rec['status']}", flush=True)

    manifest = {
        "schemaVersion": 1,
        "repository": REPO,
        "releaseTag": RELEASE_TAG,
        "generated": datetime.now(timezone.utc).isoformat(),
        "sourcePdfCount": len(all_paths),
        "shardIndex": args.shard_index,
        "shardCount": args.shard_count,
        "records": records,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [r for r in records if r["status"] in {"failed", "validation-failed"}]
    if args.require_pdfua:
        failed += [r for r in records if r["status"] != "pdfua-validated" and r not in failed]
    print(f"Completed {len(records)}; failures: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
