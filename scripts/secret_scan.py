#!/usr/bin/env python3
"""Secret / credential leak scanner (no LLM).

Usage:
  python secret_scan.py [--root DIR]               scan the working tree (skips vendor, node_modules, .git)
  python secret_scan.py --root DIR --files F ...   scan only these files (e.g. what is about to be committed)
Exit code 1 when a high-severity finding exists. Values are masked in the output.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKIP = {".git", "node_modules", "vendor", "storage", "dist", "build", "graphify-out", "coverage", "__pycache__"}
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".ico", ".pdf", ".zip", ".woff", ".woff2", ".ttf", ".otf",
          ".mp4", ".mp3", ".exe", ".dll", ".so", ".sqlite", ".db", ".lock"}
SECRET_FILES = re.compile(r"(^|/)(\.env(\.(?!example$|sample$|dist$)[\w.-]+)?|.*\.(ppk|pem|p12|pfx|key|keystore|jks)|id_(rsa|ed25519|ecdsa)|"
                          r"(passwords?|passwd|credentials?|secrets?)\.(txt|json)|admin-login[^/]*|pass\.txt)$", re.I)
PATTERNS = [
    ("high", "private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("high", "PuTTY private key", re.compile(r"PuTTY-User-Key-File-\d")),
    ("high", "Stripe live key", re.compile(r"\b(sk|rk)_live_[A-Za-z0-9]{16,}")),
    ("high", "AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("high", "Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("high", "OpenAI/Anthropic key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{24,}")),
    ("high", "GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("high", "Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("high", "secret exposed to the browser bundle",
     re.compile(r"^[ \t]*VITE_[A-Z0-9_]*(SECRET|PRIVATE|PASSWORD|TOKEN)[A-Z0-9_]*[ \t]*=[ \t]*[^\s#]+", re.M)),
    ("medium", "hard-coded credential", re.compile(
        r"""(?i)['"]?\w*(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|client[_-]?secret)\w*['"]?\s*(=>|:|=)\s*['"][^'"\s]{8,}['"]""")),
    ("medium", "credentials in URL", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s:@]{6,}@[^\s/]+")),
    ("medium", "APP_DEBUG on in a production env file", re.compile(r"^APP_DEBUG\s*=\s*true", re.M)),
]
DATA_FILE = re.compile(r"(^|/)(lang|locales?|i18n|translations?)(/|$)|(^|[-_./])(ar|fr|en)\.(ts|js|json|php)$")
ALLOW = re.compile(r"(?i)(required\||\|min:|\|confirmed|nullable\||example|placeholder|changeme|your[-_]|xxxx|dummy|fake|test[-_]?(key|secret)|\*\*\*|<[^>]+>|\$\{|env\()")


def mask(text: str) -> str:
    return text if len(text) <= 8 else text[:4] + "..." + text[-2:]


def scan_file(root: Path, path: Path, commit_mode: bool = True) -> list[dict]:
    """commit_mode: the file is about to be committed (secret files are high). Otherwise a working-tree audit."""
    rel = path.relative_to(root).as_posix()
    findings = []
    if SECRET_FILES.search(rel):
        findings.append({"severity": "high" if commit_mode else "info", "file": rel, "line": 0,
                         "rule": "secret-bearing file: must never be committed (keep it in .gitignore)", "match": path.name})
    if path.suffix.lower() in BINARY or path.stat().st_size > 2_000_000:
        return findings
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings
    for severity, rule, pattern in PATTERNS:
        if rule.startswith("APP_DEBUG") and "production" not in rel and not rel.endswith(".env"):
            continue
        for m in pattern.finditer(text):
            if severity == "medium" and (ALLOW.search(m.group(0)) or DATA_FILE.search(rel)):
                continue
            if rule.startswith("secret exposed") and (rel.endswith((".example", ".sample", ".dist")) or ALLOW.search(m.group(0))):
                continue
            line = text.count("\n", 0, m.start()) + 1
            if not commit_mode and SECRET_FILES.search(rel):
                severity = "info"  # already reported as a secret file; blocking only when about to be committed
            findings.append({"severity": severity, "file": rel, "line": line, "rule": rule, "match": mask(m.group(0).strip())})
    return findings


def iter_files(root: Path, only: list[str]):
    if only:
        for f in only:
            p = (root / f) if not Path(f).is_absolute() else Path(f)
            if p.is_file():
                yield p
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP and (not d.startswith(".") or d == ".github")]
        for name in filenames:
            yield Path(dirpath, name)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--files", nargs="*", default=[])
    args = ap.parse_args()
    root = Path(args.root).resolve()
    findings = [f for p in iter_files(root, args.files) for f in scan_file(root, p, commit_mode=bool(args.files))]
    high = [f for f in findings if f["severity"] == "high"]
    medium = [f for f in findings if f["severity"] == "medium"]
    print(json.dumps({"root": str(root), "high": len(high), "medium": len(medium),
                      "info": len(findings) - len(high) - len(medium),
                      "findings": findings[:200],
                      "advice": "Keep secret files where they are but out of git (.gitignore); keep code secrets in .env; rotate any credential that was ever committed or shared."
                      if findings else "No secrets found."}, ensure_ascii=False, indent=2))
    return 1 if high else 0


if __name__ == "__main__":
    sys.exit(main())
