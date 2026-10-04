#!/usr/bin/env python3
"""Translation completeness checker (no LLM).

Finds translation families across locales and reports, per family:
  missing files, missing keys, empty values, placeholder mismatches and Arabic values that look untranslated.
Formats: Laravel PHP arrays (lang/<loc>/*.php, needs `php` on PATH, falls back to a parser),
JSON (lang/<loc>.json, locales/<loc>/*.json, i18next), Flutter ARB (app_<loc>.arb),
TS/JS message objects (app-<loc>.ts, <loc>.ts inside lang/locales/i18n dirs).

Usage: python i18n_check.py [--root DIR] [--locales ar fr en] [--changed FILES...] [--ref en]
Exit code 1 when keys are missing (use as a gate after touching UI strings).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

KNOWN = {"ar", "fr", "en", "es", "de", "it", "pt", "tr", "nl", "zgh"}
SKIP = {"node_modules", "vendor", "storage", "dist", "build", "graphify-out", "public", "bootstrap", "coverage"}
LANG_DIR = re.compile(r"(^|/)(lang|langs|locales?|i18n|l10n|translations?)(/|$)")
PLACEHOLDER = re.compile(r":[A-Za-z_]\w*|\{\{?\s*[A-Za-z_][\w.]*\s*\}?\}|%[sd]|\$\{[^}]+\}")
ARABIC = re.compile(r"[؀-ۿ]")
PLURALS = {"zero", "one", "two", "few", "many", "other"}  # CLDR categories differ per locale


def plural_base(key: str) -> str:
    head, _, last = key.rpartition(".")
    if head and last in PLURALS:
        return f"{head}.#plural"
    suffix = re.match(r"^(.*)_(zero|one|two|few|many|other)$", last)  # i18next style: key_one, key_other
    if suffix:
        return (f"{head}." if head else "") + f"{suffix.group(1)}#plural"
    return key


def is_plural(key: str) -> bool:
    return bool(re.search(r"(^|[._])(zero|one|two|few|many|other)$", key))


COMMENTS = re.compile(r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)|/\*[\s\S]*?\*/|//[^\n]*""")


# ---------- discovery ----------
def family_of(rel: str, locales: set[str]) -> tuple[str, str] | None:
    """Return (family pattern, locale) when the path is a per-locale translation file."""
    parts = rel.split("/")
    for i, part in enumerate(parts[:-1]):
        if part in locales and (i == 0 or LANG_DIR.search("/".join(parts[:i]) + "/")):
            return "/".join(parts[:i] + ["{L}"] + parts[i + 1:]), part
    name = parts[-1]
    m = re.match(r"^(.*?)([-_.]?)([a-z]{2,3})(\.(?:json|arb|ts|js|php))$", name)
    if m and m.group(3) in locales and (LANG_DIR.search(rel) or name.endswith(".arb")):
        return "/".join(parts[:-1] + [m.group(1) + m.group(2) + "{L}" + m.group(4)]), m.group(3)
    return None


def discover(root: Path, locales: set[str]) -> dict:
    families = defaultdict(dict)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP and not d.startswith(".")]
        for name in filenames:
            if not name.endswith((".json", ".arb", ".ts", ".js", ".php")):
                continue
            rel = Path(dirpath, name).relative_to(root).as_posix()
            hit = family_of(rel, locales)
            if hit:
                families[hit[0]][hit[1]] = rel
    return {k: v for k, v in families.items() if len(v) > 1 or len(locales) == 1}


# ---------- loading ----------
def flatten(obj, prefix="") -> dict:
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).startswith("@"):  # ARB metadata
                continue
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        out[prefix] = " | ".join(map(str, obj))
    else:
        out[prefix] = "" if obj is None else str(obj)
    return out


def load_php(path: Path) -> dict:
    php = shutil.which("php")
    if php:
        code = "echo json_encode(include $argv[1], JSON_UNESCAPED_UNICODE);"
        proc = subprocess.run([php, "-r", code, str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode == 0 and proc.stdout.strip().startswith(("{", "[")):
            return flatten(json.loads(proc.stdout))
    return parse_object_literal(path.read_text(encoding="utf-8", errors="replace"), php_style=True)


def parse_object_literal(text: str, php_style: bool = False) -> dict:
    """Small tolerant parser for nested key/value literals in TS/JS objects or PHP arrays."""
    text = COMMENTS.sub(lambda m: m.group(1) or "", text)  # string-aware: never cut // inside a URL string
    sep = r"=>" if php_style else r":"
    token = re.compile(r"""(['"`])((?:\\.|(?!\1)[^\\])*)\1|([A-Za-z_$][\w$]*)|(""" + sep + r""")|([{\[(])|([}\])])|(,)""")
    stack, out, last_key, pending, started = [], {}, None, None, False
    for m in token.finditer(text):
        s, ident, colon, opener, closer = m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)
        if opener:
            started = started or opener in "{["
            stack.append(pending if pending is not None else None)
            pending = None
        elif closer:
            if stack:
                stack.pop()
        elif colon:
            pending = last_key
        elif s is not None or ident:
            value = s if s is not None else ident
            if ident and pending is not None and text[m.end():m.end() + 2].lstrip()[:1] == "(":
                last_key = value  # wrapper call such as p({...}): keep the pending key for the inner object
                continue
            if pending is not None and started:
                path = ".".join([k for k in stack if k] + [pending])
                if s is not None:
                    out[path] = value
                pending = None
            last_key = value
        elif m.group(7):
            pending = None
    return out


def load(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix in (".json", ".arb"):
        try:
            return flatten(json.loads(text))
        except json.JSONDecodeError:
            return {}
    if path.suffix == ".php":
        return load_php(path)
    return parse_object_literal(text)


# ---------- checks ----------
def check_family(root: Path, pattern: str, files: dict, locales: list[str], ref: str) -> dict:
    data = {loc: load(root / rel) for loc, rel in files.items()}
    reference = ref if ref in data else next(iter(data))
    all_keys = set().union(*[set(d) for d in data.values()])
    bases = {loc: {plural_base(k) for k in d} for loc, d in data.items()}
    all_bases = set().union(*bases.values())
    report = {"family": pattern, "files": files, "missing_files": [l for l in locales if l not in files],
              "missing_keys": {}, "empty": {}, "placeholder_mismatch": [], "arabic_untranslated": []}
    for loc, d in data.items():
        missing = sorted(all_bases - bases[loc])
        if missing:
            report["missing_keys"][loc] = missing[:100]
        empty = sorted(k for k, v in d.items() if not str(v).strip())
        if empty:
            report["empty"][loc] = empty[:50]
    for key in sorted(all_keys):
        ref_val = data[reference].get(key)
        if ref_val is None:
            continue
        if is_plural(key):
            continue  # plural forms may legitimately drop the count (Arabic "one"/"two")
        ref_ph = sorted(set(PLACEHOLDER.findall(ref_val)))
        for loc, d in data.items():
            val = d.get(key)
            if val is not None and loc != reference and sorted(set(PLACEHOLDER.findall(val))) != ref_ph:
                report["placeholder_mismatch"].append({"key": key, "locale": loc, "expected": ref_ph,
                                                       "found": sorted(set(PLACEHOLDER.findall(val)))})
    if "ar" in data:
        report["arabic_untranslated"] = sorted(k for k, v in data["ar"].items()
                                               if len(re.sub(PLACEHOLDER, "", v).strip()) > 3 and not ARABIC.search(v))[:50]
    return report


def rel_path(root: Path, raw: str) -> str:
    p = Path(raw)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(root).as_posix()
        except ValueError:
            return p.as_posix()
    s = p.as_posix()
    return s[2:] if s.startswith("./") else s


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--locales", nargs="*", default=[], help="Default: the locales actually present in the repo.")
    ap.add_argument("--ref", default="en", help="Reference locale for placeholders (default en).")
    ap.add_argument("--changed", nargs="*", default=[], help="Only families containing these files.")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    families = discover(root, set(args.locales) if args.locales else KNOWN)
    found = sorted({loc for files in families.values() for loc in files})
    locales = [l for l in args.locales if l] or found
    changed = {rel_path(root, c) for c in args.changed}
    reports = [check_family(root, pat, files, locales, args.ref) for pat, files in sorted(families.items())
               if not changed or changed & set(files.values())]
    problems = [r for r in reports if r["missing_files"] or r["missing_keys"] or r["empty"]
                or r["placeholder_mismatch"] or r["arabic_untranslated"]]
    # Missing files are reported, not blocking: a project may legitimately not ship every locale for a family.
    blocking = any(r["missing_keys"] or r["placeholder_mismatch"] for r in problems)
    print(json.dumps({"root": str(root), "locales": locales, "families": len(reports),
                      "families_with_problems": len(problems), "blocking": blocking, "problems": problems},
                     ensure_ascii=False, indent=2))
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
