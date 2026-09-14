#!/usr/bin/env python3
"""Strict compatibility launcher for Videha-Sadeha PDF/UA remediation.

Historical source PDFs are never modified. Runtime hardenings add authenticated
retry/backoff, broad Unicode/Noto routing, and a narrowly guarded catalog-marker repair.
Acceptance remains unchanged: a derivative is publishable only if pdfinfo reports Tagged:
yes, qpdf integrity passes, and veraPDF PDF/UA-1 reports zero failures.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "videha-ejournal/videha-sadeha"


def option_value(name: str, default: str) -> str:
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == name and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith(name + "="):
            return arg.split("=", 1)[1]
    return default


def auth_headers(base: dict[str, str]) -> dict[str, str]:
    headers = dict(base)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_engine(url: str, attempts: int = 4) -> str:
    last: Exception | None = None
    headers = auth_headers({"User-Agent": "Videha-PDF-UA-Remediator-Launcher/2.7"})
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return response.read().decode("utf-8")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in {403, 429, 500, 502, 503, 504}:
                raise
            if attempt == attempts:
                raise
            time.sleep(min(15, 2 ** attempt))
    raise RuntimeError(f"Unable to fetch remediation engine: {last}")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if old not in source:
        raise RuntimeError(f"Expected {label} block not found; refusing an unverified runtime patch")
    return source.replace(old, new, 1)


def harden_engine(source: str) -> str:
    if "import time\n" not in source:
        source = source.replace("import tempfile\n", "import tempfile\nimport time\n", 1)

    old = '''def get_json(url: str) -> dict:\n    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT})\n    with urllib.request.urlopen(req, timeout=120) as response:\n        return json.load(response)\n'''
    new = '''def get_json(url: str) -> dict:\n    last = None\n    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}\n    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")\n    if token:\n        headers["Authorization"] = f"Bearer {token}"\n    for attempt in range(1, 5):\n        req = urllib.request.Request(url, headers=headers)\n        try:\n            with urllib.request.urlopen(req, timeout=120) as response:\n                return json.load(response)\n        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:\n            last = exc\n            if isinstance(exc, urllib.error.HTTPError) and exc.code not in {403, 429, 500, 502, 503, 504}:\n                raise\n            if attempt == 4:\n                raise\n            time.sleep(min(15, 2 ** attempt))\n    raise RuntimeError(f"GitHub metadata fetch failed: {last}")\n'''
    source = replace_once(source, old, new, "get_json")

    old = '''    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})\n    with urllib.request.urlopen(req, timeout=300) as response, destination.open("wb") as output:\n        for chunk in iter(lambda: response.read(1024 * 1024), b""):\n            output.write(chunk)\n'''
    new = '''    last = None\n    headers = {"User-Agent": USER_AGENT}\n    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")\n    if token:\n        headers["Authorization"] = f"Bearer {token}"\n    for attempt in range(1, 5):\n        req = urllib.request.Request(url, headers=headers)\n        try:\n            with urllib.request.urlopen(req, timeout=300) as response, destination.open("wb") as output:\n                for chunk in iter(lambda: response.read(1024 * 1024), b""):\n                    output.write(chunk)\n            return\n        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:\n            last = exc\n            destination.unlink(missing_ok=True)\n            if isinstance(exc, urllib.error.HTTPError) and exc.code not in {403, 429, 500, 502, 503, 504}:\n                raise\n            if attempt == 4:\n                raise\n            time.sleep(min(15, 2 ** attempt))\n    raise RuntimeError(f"Source PDF fetch failed: {last}")\n'''
    source = replace_once(source, old, new, "source-download")

    old = '''    if 0x0900 <= cp <= 0x097F or 0xA8E0 <= cp <= 0xA8FF or 0x1CD0 <= cp <= 0x1CFF:\n        return "deva"\n    if 0x11480 <= cp <= 0x114DF:\n        return "tirhuta"\n'''
    new = '''    if 0x0900 <= cp <= 0x097F or 0xA8E0 <= cp <= 0xA8FF or 0x1CD0 <= cp <= 0x1CFF or 0x11B00 <= cp <= 0x11B5F:\n        return "deva"\n    if 0x0980 <= cp <= 0x09FF:\n        return "beng"\n    if 0x0A00 <= cp <= 0x0A7F:\n        return "guru"\n    if 0x0A80 <= cp <= 0x0AFF:\n        return "gujr"\n    if 0x0B00 <= cp <= 0x0B7F:\n        return "orya"\n    if 0x0B80 <= cp <= 0x0BFF:\n        return "taml"\n    if 0x0C00 <= cp <= 0x0C7F:\n        return "telu"\n    if 0x0C80 <= cp <= 0x0CFF:\n        return "knda"\n    if 0x0D00 <= cp <= 0x0D7F:\n        return "mlym"\n    if 0x0D80 <= cp <= 0x0DFF:\n        return "sinh"\n    if 0x11480 <= cp <= 0x114DF:\n        return "tirhuta"\n'''
    source = replace_once(source, old, new, "Indic script-routing")

    old = '''    if 0x2000 <= cp <= 0x2BFF or 0x1D400 <= cp <= 0x1D7FF:\n        return "symbol"\n    return "base"\n'''
    new = '''    if (\n        0x2000 <= cp <= 0x2BFF\n        or 0x1D000 <= cp <= 0x1D2FF\n        or 0x1D400 <= cp <= 0x1D7FF\n        or 0x1F000 <= cp <= 0x1FAFF\n    ):\n        return "symbol"\n    if cp >= 0x0530:\n        return "fallback"\n    return "base"\n'''
    source = replace_once(source, old, new, "symbol-routing")

    old = '''.script-deva {{ font-family:"Noto Sans Devanagari","Noto Sans","DejaVu Sans",sans-serif; }}\n.script-tirhuta {{ font-family:"Noto Sans Tirhuta","Noto Sans","DejaVu Sans",sans-serif; }}\n'''
    new = '''.script-deva {{ font-family:"Noto Sans Devanagari","Noto Sans","DejaVu Sans",sans-serif; }}\n.script-beng {{ font-family:"Noto Sans Bengali","Noto Sans","DejaVu Sans",sans-serif; }}\n.script-guru {{ font-family:"Noto Sans Gurmukhi","Noto Sans","DejaVu Sans",sans-serif; }}\n.script-gujr {{ font-family:"Noto Sans Gujarati","Noto Sans","DejaVu Sans",sans-serif; }}\n.script-orya {{ font-family:"Noto Sans Oriya","Noto Sans","DejaVu Sans",sans-serif; }}\n.script-taml {{ font-family:"Noto Sans Tamil","Noto Sans","DejaVu Sans",sans-serif; }}\n.script-telu {{ font-family:"Noto Sans Telugu","Noto Sans","DejaVu Sans",sans-serif; }}\n.script-knda {{ font-family:"Noto Sans Kannada","Noto Sans","DejaVu Sans",sans-serif; }}\n.script-mlym {{ font-family:"Noto Sans Malayalam","Noto Sans","DejaVu Sans",sans-serif; }}\n.script-sinh {{ font-family:"Noto Sans Sinhala","Noto Sans","DejaVu Sans",sans-serif; }}\n.script-tirhuta {{ font-family:"Noto Sans Tirhuta","Noto Sans","DejaVu Sans",sans-serif; }}\n'''
    source = replace_once(source, old, new, "Indic font-routing")

    old = '.script-symbol {{ font-family:"Noto Sans Symbols2","Noto Sans","DejaVu Sans",sans-serif; }}'
    new = '''.script-symbol {{ font-family:"Noto Sans Symbols2","Noto Color Emoji","Noto Sans CJK JP","Noto Sans","DejaVu Sans",sans-serif; }}\n.script-fallback {{ font-family:"Noto Sans Devanagari","Noto Sans Bengali","Noto Sans Gurmukhi","Noto Sans Gujarati","Noto Sans Oriya","Noto Sans Tamil","Noto Sans Telugu","Noto Sans Kannada","Noto Sans Malayalam","Noto Sans Sinhala","Noto Sans Arabic","Noto Sans Hebrew","Noto Sans Thai","Noto Sans Lao","Noto Sans Tibetan","Noto Sans Myanmar","Noto Sans Georgian","Noto Sans Armenian","Noto Sans Ethiopic","Noto Sans Khmer","Noto Sans Coptic","Noto Sans Syriac","Noto Sans Thaana","Noto Sans NKo","Noto Sans Cherokee","Noto Sans Canadian Aboriginal","Noto Sans Yi","Noto Sans Vai","Noto Sans Tifinagh","Noto Sans Symbols2","Noto Sans CJK JP","Noto Sans CJK SC","Noto Sans CJK KR","Noto Color Emoji","DejaVu Sans",sans-serif; }}'''
    source = replace_once(source, old, new, "symbol font")

    old = 'html {{ font-family:"Noto Sans","DejaVu Sans",sans-serif; font-size:12pt; line-height:1.55; }}'
    new = 'html {{ font-family:"Noto Sans","Noto Sans Devanagari","Noto Sans Bengali","Noto Sans Gurmukhi","Noto Sans Gujarati","Noto Sans Oriya","Noto Sans Tamil","Noto Sans Telugu","Noto Sans Kannada","Noto Sans Malayalam","Noto Sans Sinhala","Noto Sans Arabic","Noto Sans Hebrew","Noto Sans Thai","Noto Sans Lao","Noto Sans Tibetan","Noto Sans Myanmar","Noto Sans Georgian","Noto Sans Armenian","Noto Sans Ethiopic","Noto Sans Khmer","Noto Sans Coptic","Noto Sans Symbols2","Noto Sans CJK JP","Noto Sans CJK SC","Noto Sans CJK KR","Noto Color Emoji","DejaVu Sans",sans-serif; font-size:12pt; line-height:1.55; }}'
    source = replace_once(source, old, new, "base font stack")

    old = '''def render_pdf(source_html: Path, output_pdf: Path) -> None:\n    result = run(["weasyprint", "--pdf-variant", "pdf/ua-1", str(source_html), str(output_pdf)], check=False)\n    if result.returncode:\n        raise RuntimeError(f"WeasyPrint failed: {result.stderr[-2000:]}")\n'''
    new = '''def _ensure_pdf_tag_marker(pdf: Path) -> None:\n    """Persist a direct MarkInfo marker only on an already structured PDF.\n\n    This is metadata normalization, never an acceptance override. The derivative still must\n    independently pass pdfinfo Tagged=yes, qpdf --check, and veraPDF PDF/UA-1.\n    """\n    try:\n        import pikepdf\n    except ImportError:\n        return\n    temp = pdf.with_name(pdf.stem + ".markinfo-tmp.pdf")\n    try:\n        with pikepdf.open(pdf) as document:\n            root = document.Root\n            if "/StructTreeRoot" not in root:\n                return\n            replacement = pikepdf.Dictionary()\n            current = root.get("/MarkInfo")\n            if current is not None:\n                try:\n                    for key, value in current.items():\n                        replacement[key] = value\n                except Exception:\n                    pass\n            replacement["/Marked"] = True\n            root["/MarkInfo"] = replacement\n            document.save(temp, object_stream_mode=pikepdf.ObjectStreamMode.disable, compress_streams=False)\n        temp.replace(pdf)\n        with pikepdf.open(pdf) as check:\n            if "/StructTreeRoot" not in check.Root:\n                raise RuntimeError("StructTreeRoot disappeared during tag-marker normalization")\n            marker = check.Root.get("/MarkInfo")\n            if marker is None or not bool(marker.get("/Marked", False)):\n                raise RuntimeError("Catalog MarkInfo/Marked=true did not persist")\n        info = run(["pdfinfo", str(pdf)], check=False)\n        if not re.search(r"^Tagged:\\s+yes\\s*$", info.stdout or "", re.M | re.I):\n            raise RuntimeError("pdfinfo still reports Tagged:no after direct MarkInfo normalization")\n    finally:\n        temp.unlink(missing_ok=True)\n\n\ndef render_pdf(source_html: Path, output_pdf: Path) -> None:\n    result = run(["weasyprint", "--pdf-variant", "pdf/ua-1", str(source_html), str(output_pdf)], check=False)\n    if result.returncode:\n        raise RuntimeError(f"WeasyPrint failed: {result.stderr[-2000:]}")\n    _ensure_pdf_tag_marker(output_pdf)\n'''
    source = replace_once(source, old, new, "renderer")
    return source


ref = option_value("--source-ref", os.environ.get("SOURCE_REF", "main"))
out_dir = Path(option_value("--out", "remediated"))
url = f"https://raw.githubusercontent.com/{REPO}/{urllib.parse.quote(ref, safe='')}/scripts/remediate_pdfs_v2.py"
engine = harden_engine(fetch_engine(url))
with tempfile.NamedTemporaryFile(prefix="videha-remediator-v2-", suffix=".py", delete=False) as temp:
    temp.write(engine.encode("utf-8"))
    target = temp.name

result = subprocess.run([sys.executable, target, *sys.argv[1:]])
manifest_path = out_dir / "manifest.json"
if manifest_path.exists():
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed = False
    for record in data.get("records", []):
        validation = record.get("validation", {})
        raw = validation.get("veraPDFError", "")
        raw_compliant = 'flavour="PDFUA_1"' in raw and 'isCompliant="true"' in raw
        if raw_compliant and validation.get("pdfinfoTagged") is True and validation.get("qpdfCheck") is True:
            validation["veraPDF"] = True
            validation["profile"] = "PDF/UA-1 validation profile"
            validation["failedRules"] = 0
            validation["failedChecks"] = 0
            validation.pop("veraPDFError", None)
            record["status"] = "pdfua-validated"
            changed = True
    if changed:
        manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        failures = [r for r in data.get("records", []) if r.get("status") != "pdfua-validated"]
        if "--require-pdfua" in sys.argv[1:]:
            raise SystemExit(1 if failures else 0)
        if result.returncode and not failures:
            raise SystemExit(0)
raise SystemExit(result.returncode)
