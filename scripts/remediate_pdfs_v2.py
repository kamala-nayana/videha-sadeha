#!/usr/bin/env python3
"""Generate and validate text-first PDF/UA-1 reading derivatives for Videha-Sadeha PDFs.

Historical source PDFs remain unchanged. Embedded text is retained where usable; weak or
missing text pages are OCRed. Extracted text is normalized, obvious extraction garbage is
removed, and Unicode script runs are rendered with appropriate Noto families so Greek,
Coptic, Devanagari, Tirhuta and symbol text do not fall through to a .notdef glyph.
Every published derivative must pass PDF tagging, qpdf integrity and veraPDF PDF/UA-1
machine validation.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO = "videha-ejournal/videha-sadeha"
RELEASE_TAG = os.environ.get("ACCESSIBLE_PDF_RELEASE", "accessible-pdf-v1")
USER_AGENT = "Videha-PDF-UA-Remediator/2.3"
EMBEDDED_TEXT_MIN = 80
PRESERVED_FORMAT_CHARS = {"\u200c", "\u200d"}


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def pdf_entries(ref: str) -> list[dict]:
    ref_q = urllib.parse.quote(ref, safe="")
    tree = get_json(f"https://api.github.com/repos/{REPO}/git/trees/{ref_q}?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError("GitHub recursive tree response was truncated; refusing an incomplete archive run")
    items = [
        item for item in tree.get("tree", [])
        if item.get("type") == "blob" and str(item.get("path", "")).lower().endswith(".pdf")
    ]
    return sorted(items, key=lambda item: item["path"])


def download_source(ref: str, source_path: str, destination: Path) -> None:
    ref_q = urllib.parse.quote(ref, safe="")
    path_q = urllib.parse.quote(source_path, safe="/")
    url = f"https://raw.githubusercontent.com/{REPO}/{ref_q}/{path_q}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as response, destination.open("wb") as output:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            output.write(chunk)


def sha256(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_stem(source_path: str) -> str:
    stem = unicodedata.normalize("NFKD", Path(source_path).stem).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-").lower() or "document"
    return f"{stem[:70]}-{hashlib.sha1(source_path.encode('utf-8')).hexdigest()[:10]}"


def sanitize_text(value: str) -> tuple[str, list[str]]:
    """Normalize text and remove known PDF extraction garbage before HTML/PDF rendering."""
    value = value.replace("\x0c", "\n").replace("\r\n", "\n").replace("\r", "\n")
    value = unicodedata.normalize("NFC", value)
    removed: set[str] = set()
    cleaned: list[str] = []
    for ch in value:
        cp = ord(ch)
        category = unicodedata.category(ch)
        remove = (
            ch in {"\ufffd", "\ufffc"}
            or 0xFFA0 <= cp <= 0xFFDC
            or category in {"Cc", "Cs", "Co", "Cn"}
            or (category == "Cf" and ch not in PRESERVED_FORMAT_CHARS)
        )
        if ch in {"\n", "\t"}:
            remove = False
        if remove:
            removed.add(f"U+{cp:04X} {unicodedata.name(ch, 'UNNAMED')}")
            cleaned.append(" ")
        else:
            cleaned.append(ch)
    normalized = "".join(cleaned)
    normalized = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines())
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    return normalized, sorted(removed)


def page_count(pdf: Path) -> int:
    result = run(["pdfinfo", str(pdf)])
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.M)
    if not match:
        raise RuntimeError("pdfinfo did not return a page count")
    return int(match.group(1))


def useful_text(text: str) -> bool:
    return sum(ch.isalpha() or ch.isdigit() for ch in text) >= EMBEDDED_TEXT_MIN


def embedded_text(pdf: Path, page: int) -> tuple[str, list[str]]:
    result = run([
        "pdftotext", "-enc", "UTF-8", "-f", str(page), "-l", str(page), "-layout", str(pdf), "-"
    ], check=False)
    if result.returncode:
        return "", []
    return sanitize_text(result.stdout or "")


def tesseract_language() -> str:
    result = run(["tesseract", "--list-langs"], check=False)
    langs = set((result.stdout or "").splitlines())
    for dev in ("script/Devanagari", "Devanagari"):
        if dev in langs:
            return f"{dev}+eng" if "eng" in langs else dev
    if "hin" in langs:
        return "hin+eng" if "eng" in langs else "hin"
    return "eng"


def ocr_text(pdf: Path, page: int, work: Path, language: str) -> tuple[str, list[str]]:
    prefix = work / f"page-{page:05d}"
    raster = run([
        "pdftoppm", "-f", str(page), "-l", str(page), "-singlefile", "-r", "200", "-png", str(pdf), str(prefix)
    ], check=False)
    image = prefix.with_suffix(".png")
    if raster.returncode or not image.exists():
        return "", []
    try:
        result = run(["tesseract", str(image), "stdout", "-l", language, "--psm", "6"], check=False)
        return sanitize_text(result.stdout or "") if result.returncode == 0 else ("", [])
    finally:
        image.unlink(missing_ok=True)


def script_kind(ch: str) -> str:
    cp = ord(ch)
    if 0x0900 <= cp <= 0x097F or 0xA8E0 <= cp <= 0xA8FF or 0x1CD0 <= cp <= 0x1CFF:
        return "deva"
    if 0x11480 <= cp <= 0x114DF:
        return "tirhuta"
    if 0x03E2 <= cp <= 0x03EF or 0x2C80 <= cp <= 0x2CFF:
        return "coptic"
    if 0x0370 <= cp <= 0x03FF or 0x1F00 <= cp <= 0x1FFF:
        return "greek"
    if 0x2000 <= cp <= 0x2BFF or 0x1D400 <= cp <= 0x1D7FF:
        return "symbol"
    return "base"


def script_aware_escape(value: str) -> str:
    """Escape HTML while assigning non-Latin scripts to fonts that actually cover them."""
    if not value:
        return ""
    pieces: list[str] = []
    run_chars: list[str] = []
    run_kind = script_kind(value[0])
    for ch in value:
        kind = script_kind(ch)
        if kind != run_kind and run_chars:
            escaped = html.escape("".join(run_chars))
            pieces.append(escaped if run_kind == "base" else f'<span class="script-{run_kind}">{escaped}</span>')
            run_chars = []
            run_kind = kind
        run_chars.append(ch)
    if run_chars:
        escaped = html.escape("".join(run_chars))
        pieces.append(escaped if run_kind == "base" else f'<span class="script-{run_kind}">{escaped}</span>')
    return "".join(pieces)


def paragraphs(text: str) -> str:
    if not text:
        return '<p class="unrecovered">No machine-readable text was recovered from this source page. Consult the preserved visual facsimile.</p>'
    output: list[str] = []
    for block in (part.strip() for part in re.split(r"\n\s*\n", text)):
        if not block:
            continue
        lines = [script_aware_escape(line) for line in block.splitlines() if line.strip()]
        if lines:
            output.append("<p>" + "<br>".join(lines) + "</p>")
    return "\n".join(output)


def html_document(source_path: str, source_ref: str, source_hash: str, pages: list[dict], generated: str) -> str:
    title = f"{Path(source_path).stem} - accessible reading derivative"
    source_url = (
        f"https://github.com/{REPO}/blob/{urllib.parse.quote(source_ref, safe='')}/"
        + urllib.parse.quote(source_path, safe="/")
    )
    embedded = sum(page["method"] == "embedded" for page in pages)
    ocr = sum(page["method"] == "ocr" for page in pages)
    unrecovered = [str(page["page"]) for page in pages if not page["text"]]
    provenance = f"Embedded text was retained on {embedded} page(s); OCR was used on {ocr} page(s)."
    if unrecovered:
        provenance += " No text was recovered on page(s): " + ", ".join(unrecovered) + "."
    sections = "".join(
        f'<section class="page" aria-labelledby="page-{page["page"]}">'
        f'<h2 id="page-{page["page"]}">Source page {page["page"]}</h2>'
        f'<p class="method">Text source: {html.escape(page["method"])}.</p>'
        f'{paragraphs(page["text"])}</section>'
        for page in pages
    )
    return f'''<!doctype html>
<html lang="mai-Deva"><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<meta name="author" content="Videha - First Maithili Fortnightly eJournal, ISSN 2229-547X">
<meta name="dcterms.source" content="{html.escape(source_path)}"><meta name="dcterms.created" content="{generated}">
<style>
@page {{ size:A4; margin:18mm 17mm 20mm; @bottom-center {{ content:counter(page); font-size:9pt; }} }}
html {{ font-family:"Noto Sans","DejaVu Sans",sans-serif; font-size:12pt; line-height:1.55; }}
.script-deva {{ font-family:"Noto Sans Devanagari","Noto Sans","DejaVu Sans",sans-serif; }}
.script-tirhuta {{ font-family:"Noto Sans Tirhuta","Noto Sans","DejaVu Sans",sans-serif; }}
.script-greek {{ font-family:"Noto Sans","DejaVu Sans",sans-serif; }}
.script-coptic {{ font-family:"Noto Sans Coptic","Noto Sans","DejaVu Sans",sans-serif; }}
.script-symbol {{ font-family:"Noto Sans Symbols2","Noto Sans","DejaVu Sans",sans-serif; }}
body {{ margin:0; }} h1 {{ font-size:22pt; line-height:1.25; }} h2 {{ font-size:15pt; margin-top:0; }}
a {{ color:#6e1322; text-decoration-thickness:.08em; }}
.notice {{ border:1px solid #555; padding:10pt; margin:12pt 0; }}
.page {{ break-before:page; }} .page:first-of-type {{ break-before:auto; }}
.method {{ font-size:9.5pt; font-style:italic; }} .unrecovered {{ font-weight:600; }} p {{ orphans:3; widows:3; }}
</style></head><body><main>
<h1>{html.escape(title)}</h1>
<div class="notice" role="note"><p><strong>Accessible derivative.</strong> This text-first PDF/UA reading copy preserves the historical source PDF unchanged. Embedded text is retained where usable; pages without a usable text layer are processed with Devanagari/English OCR. OCR text is machine-generated and is not represented as an editorially proofread transcription.</p>
<p>{html.escape(provenance)}</p><p>Source SHA-256: <code>{source_hash}</code>. <a href="{html.escape(source_url)}">Open the preserved source PDF</a>.</p></div>
{sections}</main></body></html>'''


def render_pdf(source_html: Path, output_pdf: Path) -> None:
    result = run(["weasyprint", "--pdf-variant", "pdf/ua-1", str(source_html), str(output_pdf)], check=False)
    if result.returncode:
        raise RuntimeError(f"WeasyPrint failed: {result.stderr[-2000:]}")


def basic_validation(pdf: Path) -> tuple[bool, dict]:
    info = run(["pdfinfo", str(pdf)], check=False)
    tagged = bool(re.search(r"^Tagged:\s+yes\s*$", info.stdout or "", re.M | re.I))
    integrity = run(["qpdf", "--check", str(pdf)], check=False).returncode == 0
    return tagged and integrity, {"pdfinfoTagged": tagged, "qpdfCheck": integrity}


def _first_xml_start(raw: str) -> int:
    starts = [pos for pos in (raw.find("<rawResults"), raw.find("<report")) if pos >= 0]
    return min(starts) if starts else -1


def _local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _first_local(root: ET.Element, *names: str) -> ET.Element | None:
    wanted = set(names)
    return next((node for node in root.iter() if _local_name(node.tag) in wanted), None)


def _child_local(parent: ET.Element | None, name: str) -> ET.Element | None:
    if parent is None:
        return None
    return next((node for node in list(parent) if _local_name(node.tag) == name), None)


def _descendant_text(parent: ET.Element | None, *path: str) -> str:
    node = parent
    for name in path:
        node = _child_local(node, name)
        if node is None:
            return ""
    return (node.text or "").strip()


def verapdf_validation(pdf: Path, image: str) -> tuple[bool, dict]:
    mount = pdf.parent.resolve()
    result = run([
        "docker", "run", "--rm", "-v", f"{mount}:/data:ro", image,
        "-f", "ua1", "--format", "raw", f"/data/{pdf.name}"
    ], check=False)
    raw = result.stdout or ""
    start = _first_xml_start(raw)
    if start < 0:
        return False, {"veraPDF": False, "veraPDFError": (result.stderr or raw)[-4000:]}
    try:
        root = ET.fromstring(raw[start:])
        report = _first_local(root, "validationResult", "validationReport")
        compliant = report is not None and str(report.attrib.get("isCompliant", "")).lower() == "true"
        details = _first_local(report, "details") if report is not None else None
        failures: list[dict] = []
        seen: set[tuple[str, str, str, str]] = set()
        all_failed = [
            node for node in root.iter()
            if _local_name(node.tag) == "assertion" and str(node.attrib.get("status", "")).upper() == "FAILED"
        ]
        pdf_pages: set[int] = set()
        for assertion in all_failed:
            rule = _child_local(assertion, "ruleId")
            rule_text = ""
            if rule is not None:
                rule_text = f"{rule.attrib.get('specification','')} {rule.attrib.get('clause','')} test {rule.attrib.get('testNumber','')}".strip()
            message = _descendant_text(assertion, "message")
            error = _descendant_text(assertion, "errorMessage")
            context = _descendant_text(assertion, "location", "context")
            match = re.search(r"pages\[(\d+)\]", context)
            if match:
                pdf_pages.add(int(match.group(1)) + 1)
            key = (rule_text, message, error, context)
            if key in seen:
                continue
            seen.add(key)
            if len(failures) < 25:
                failures.append({"rule": rule_text, "message": message, "error": error, "context": context})
        profile = "PDF/UA-1"
        if report is not None:
            profile = report.attrib.get("profileName") or report.attrib.get("flavour") or profile
        failed_rules = int(details.attrib.get("failedRules", "0")) if details is not None else len({f["rule"] for f in failures if f["rule"]})
        failed_checks = int(details.attrib.get("failedChecks", "0")) if details is not None else len(all_failed)
        return compliant, {
            "veraPDF": compliant,
            "profile": profile,
            "failedRules": failed_rules,
            "failedChecks": failed_checks,
            "failedAssertions": failures,
            "failedPdfPages": sorted(pdf_pages),
        }
    except Exception as exc:
        return False, {"veraPDF": False, "veraPDFError": str(exc), "veraPDFOutputTail": raw[-4000:]}


def remediate(entry: dict, source_ref: str, output: Path, verapdf_image: str | None) -> dict:
    source_path = entry["path"]
    generated = datetime.now(timezone.utc).isoformat()
    stem = safe_stem(source_path)
    source_pdf = output / f".{stem}-source.pdf"
    accessible_html = output / f"{stem}-accessible.html"
    accessible_pdf = output / f"{stem}-accessible.pdf"
    record = {
        "sourcePath": source_path,
        "sourceGitBlobSha": entry.get("sha", ""),
        "sourceBytes": entry.get("size"),
        "sourceRepository": REPO,
        "sourceRef": source_ref,
        "releaseTag": RELEASE_TAG,
        "generated": generated,
        "status": "processing",
        "textSanitization": "NFC normalization; control/private-use/unassigned/replacement/object-marker and half-width-Hangul extraction artifacts removed; ZWNJ/ZWJ preserved; Unicode script runs use script-appropriate Noto fonts",
    }
    try:
        download_source(source_ref, source_path, source_pdf)
        record["sourceBytes"] = source_pdf.stat().st_size
        record["sourceSha256"] = sha256(source_pdf)
        count = page_count(source_pdf)
        record["pages"] = count
        language = tesseract_language()
        record["ocrLanguage"] = language
        page_records: list[dict] = []
        removed_characters: set[str] = set()
        with tempfile.TemporaryDirectory(prefix="videha-ocr-") as temp:
            work = Path(temp)
            for page_number in range(1, count + 1):
                text, removed = embedded_text(source_pdf, page_number)
                removed_characters.update(removed)
                if useful_text(text):
                    page_records.append({"page": page_number, "method": "embedded", "text": text})
                else:
                    text, removed = ocr_text(source_pdf, page_number, work, language)
                    removed_characters.update(removed)
                    page_records.append({"page": page_number, "method": "ocr", "text": text})
        record["removedExtractionArtifacts"] = sorted(removed_characters)
        record["embeddedTextPages"] = sum(page["method"] == "embedded" for page in page_records)
        record["ocrPages"] = [page["page"] for page in page_records if page["method"] == "ocr"]
        record["unrecoveredTextPages"] = [page["page"] for page in page_records if not page["text"]]
        record["textMethod"] = (
            "embedded-text" if not record["ocrPages"] else
            "ocr" if len(record["ocrPages"]) == count else "mixed"
        )
        accessible_html.write_text(
            html_document(source_path, source_ref, record["sourceSha256"], page_records, generated),
            encoding="utf-8",
        )
        render_pdf(accessible_html, accessible_pdf)
        basic_ok, validation = basic_validation(accessible_pdf)
        record["validation"] = validation
        vera_ok: bool | None = None
        if verapdf_image:
            vera_ok, data = verapdf_validation(accessible_pdf, verapdf_image)
            record["validation"].update(data)
        compliant = basic_ok and (vera_ok is not False)
        record["status"] = "pdfua-validated" if compliant and verapdf_image else "tagged-derivative"
        if not compliant:
            record["status"] = "validation-failed"
        record["accessiblePdfAsset"] = accessible_pdf.name
        record["accessiblePdfUrl"] = (
            f"https://github.com/{REPO}/releases/download/{RELEASE_TAG}/" + urllib.parse.quote(accessible_pdf.name)
        )
        record["accessibleHtmlArtifact"] = accessible_html.name
        record["outputBytes"] = accessible_pdf.stat().st_size
        record["outputSha256"] = sha256(accessible_pdf)
        record["editorialTextVerification"] = "not-reviewed"
        record["humanReviewRequired"] = bool(record["ocrPages"] or record["unrecoveredTextPages"] or record["removedExtractionArtifacts"])
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        source_pdf.unlink(missing_ok=True)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-ref", default=os.environ.get("SOURCE_REF", "main"))
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default="remediated")
    parser.add_argument("--verapdf-image", default="")
    parser.add_argument("--require-pdfua", action="store_true")
    args = parser.parse_args()

    entries = pdf_entries(args.source_ref)
    selected = [entry for index, entry in enumerate(entries) if index % args.shard_count == args.shard_index]
    if args.limit:
        selected = selected[:args.limit]
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    print(f"Archive PDFs: {len(entries)}; shard {args.shard_index}/{args.shard_count}: {len(selected)}")
    for index, entry in enumerate(selected, 1):
        print(f"[{index}/{len(selected)}] {entry['path']}", flush=True)
        record = remediate(entry, args.source_ref, output, args.verapdf_image or None)
        records.append(record)
        print(f"  -> {record['status']}", flush=True)
        if record.get("status") == "validation-failed":
            for failure in record.get("validation", {}).get("failedAssertions", [])[:5]:
                print(f"     {failure.get('rule')}: {failure.get('error') or failure.get('message')}", flush=True)

    manifest = {
        "schemaVersion": 3,
        "repository": REPO,
        "sourceRef": args.source_ref,
        "releaseTag": RELEASE_TAG,
        "generated": datetime.now(timezone.utc).isoformat(),
        "sourcePdfCount": len(entries),
        "shardIndex": args.shard_index,
        "shardCount": args.shard_count,
        "records": records,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [record for record in records if record["status"] in {"failed", "validation-failed"}]
    if args.require_pdfua:
        failed.extend(record for record in records if record["status"] != "pdfua-validated" and record not in failed)
    print(f"Completed {len(records)}; failures: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
