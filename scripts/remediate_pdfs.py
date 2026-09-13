#!/usr/bin/env python3
"""Compatibility launcher for the hardened Videha PDF/UA remediation engine."""
from __future__ import annotations
import os
import sys
import tempfile
import urllib.parse
import urllib.request

REPO = "videha-ejournal/videha-sadeha"


def source_ref() -> str:
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--source-ref" and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith("--source-ref="):
            return arg.split("=", 1)[1]
    return os.environ.get("SOURCE_REF", "main")


ref = source_ref()
url = (
    f"https://raw.githubusercontent.com/{REPO}/"
    f"{urllib.parse.quote(ref, safe='')}/scripts/remediate_pdfs_v2.py"
)
request = urllib.request.Request(url, headers={"User-Agent": "Videha-PDF-UA-Remediator-Launcher/2.0"})
with tempfile.NamedTemporaryFile(prefix="videha-remediator-v2-", suffix=".py", delete=False) as temp:
    with urllib.request.urlopen(request, timeout=120) as response:
        temp.write(response.read())
    target = temp.name
os.execv(sys.executable, [sys.executable, target, *sys.argv[1:]])
