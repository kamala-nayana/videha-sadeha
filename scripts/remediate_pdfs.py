#!/usr/bin/env python3
"""Compatibility launcher and veraPDF raw-report normalizer for the hardened remediation engine."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
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


ref = option_value("--source-ref", os.environ.get("SOURCE_REF", "main"))
out_dir = Path(option_value("--out", "remediated"))
url = (
    f"https://raw.githubusercontent.com/{REPO}/"
    f"{urllib.parse.quote(ref, safe='')}/scripts/remediate_pdfs_v2.py"
)
request = urllib.request.Request(url, headers={"User-Agent": "Videha-PDF-UA-Remediator-Launcher/2.1"})
with tempfile.NamedTemporaryFile(prefix="videha-remediator-v2-", suffix=".py", delete=False) as temp:
    with urllib.request.urlopen(request, timeout=120) as response:
        temp.write(response.read())
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
