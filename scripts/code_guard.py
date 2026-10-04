#!/usr/bin/env python3
"""Deterministic code hygiene guard (no LLM, no tokens).

Commands:
  find <name> [--root DIR]      Where is a symbol (function/class/method/const) already defined?
                                Run BEFORE creating anything new.
  scan [--root DIR] [--changed F ...] [--max-fn N] [--max-file N] [--exclude DIR ...]
                                Duplicate files, duplicate function bodies (exact and renamed copies),
                                same top-level name in several files, over-long functions and files.
                                With --changed only findings involving those files are reported and the
                                exit code is 1 when a blocking duplicate exists (use it as a gate).
An incremental index (by file mtime/size) is cached in the system temp dir, so repeated scans are fast.
Languages: PHP, TS/TSX, JS/JSX, Python, Dart.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

EXTS = {".php", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".py", ".dart"}
SKIP = {"node_modules", "vendor", "storage", "dist", "build", "graphify-out", "coverage", "__pycache__",
        "bootstrap", "venv"}
SKIP_PATHS = ["public/build", "public/vendor", "resources/js/ssr", "artifacts"]
GENERATED = re.compile(r"(\.min\.js$|\.d\.ts$|\.g\.dart$|\.freezed\.dart$|\.lock$)")
DATA_FILE = re.compile(r"(^|/)(lang|locales?|i18n|translations?)(/|$)|(^|[-_./])(ar|fr|en)\.(ts|js|php)$")
COMMON = {"index", "show", "create", "store", "edit", "update", "destroy", "handle", "boot", "register",
          "render", "build", "main", "up", "down", "run", "rules", "authorize", "messages", "toArray",
          "definition", "setUp", "tearDown", "constructor", "__construct", "__init__", "default", "Page",
          "Layout", "init", "dispose", "initState", "via", "toMail", "broadcastOn", "middleware", "casts"}
DEF_PATTERNS = {
    ".php": [r"^\s*(?:(?:public|protected|private|static|final|abstract)\s+)*function\s+&?([A-Za-z_]\w*)\s*\(",
             r"^\s*(?:final\s+|abstract\s+|readonly\s+)*(?:class|interface|trait|enum)\s+([A-Za-z_]\w*)"],
    ".py": [r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", r"^\s*class\s+([A-Za-z_]\w*)"],
    ".dart": [r"^\s*(?:abstract\s+)?class\s+([A-Za-z_]\w*)",
              r"^\s*(?:static\s+)?(?:Future<[^>]*>|Stream<[^>]*>|[A-Z]\w*(?:<[^>]*>)?\??|void|int|double|bool|String|dynamic)\s+([a-z_]\w*)\s*\("],
    "js": [r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*[<(]",
           r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=>",
           r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)",
           r"^\s*(?:export\s+)?(?:interface|type|enum)\s+([A-Za-z_$][\w$]*)"],
}
COMMON_LOWER = {c.lower() for c in COMMON}
TOP_LEVEL_JS = re.compile(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|const|let|class)\s")
INDEX_VERSION = 4
MAX_FILE_BYTES = 1_000_000  # skip minified/generated giants


# ---------- file discovery ----------
def lang_key(path: Path) -> str:
    return "js" if path.suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs"} else path.suffix


def walk(root: Path, excludes: list[str]):
    skip_paths = SKIP_PATHS + excludes
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP and not d.startswith(".")]
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        if any(rel_dir == s or rel_dir.startswith(s + "/") for s in skip_paths):
            dirnames[:] = []
            continue
        for name in filenames:
            path = Path(dirpath, name)
            if path.suffix in EXTS and not GENERATED.search(name):
                try:
                    if path.stat().st_size > MAX_FILE_BYTES:
                        continue
                except OSError:
                    continue
                yield path


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ---------- parsing ----------
def strip_comments(code: str, suffix: str) -> str:
    if suffix == ".py":
        code = re.sub(r"#.*", "", code)
        return re.sub(r'("""|\'\'\')[\s\S]*?\1', "", code)
    code = re.sub(r"/\*[\s\S]*?\*/", "", code)
    return re.sub(r"(?<![:\"'])//.*", "", code)


def block_end(lines: list[str], i: int, suffix: str) -> int:
    """Return the exclusive end line index of the definition starting at line i."""
    if suffix == ".py":
        indent = len(lines[i]) - len(lines[i].lstrip())
        end = i + 1
        while end < len(lines) and (not lines[end].strip() or len(lines[end]) - len(lines[end].lstrip()) > indent):
            end += 1
        return end
    depth, opened = 0, False
    for j in range(i, min(len(lines), i + 2000)):
        seg = re.sub(r"(['\"`])(?:\\.|(?!\1)[^\\])*\1", "", lines[j])
        depth += seg.count("{") - seg.count("}")
        opened = opened or "{" in seg
        if opened and depth <= 0:
            return j + 1
        if not opened and j > i + 3:  # declaration without a body
            return i + 1
    return min(len(lines), i + 2000)


def is_top_level(path: Path, line: str) -> bool:
    if line[:1].isspace():
        return False
    return bool(TOP_LEVEL_JS.match(line.strip())) if lang_key(path) == "js" else True


def functions(path: Path, text: str):
    """Yield (name, start_line, end_line, body, top_level)."""
    lines = text.splitlines()
    patterns = [re.compile(p) for p in DEF_PATTERNS[lang_key(path)]]
    for i, line in enumerate(lines):
        match = next((m for m in (p.match(line) for p in patterns) if m), None)
        if match:
            end = block_end(lines, i, path.suffix)
            yield match.group(1), i + 1, end, "\n".join(lines[i:end]), is_top_level(path, line)


# Framework conventions that are identical on purpose (Eloquent relations, simple accessors): never duplicates.
FRAMEWORK_ONE_LINER = re.compile(
    r"\{?return\$this->(belongsTo|hasMany|hasOne|belongsToMany|morphTo|morphMany|morphOne|morphToMany|morphedByMany|"
    r"hasManyThrough|hasOneThrough)\([^;]*\);\}?|\{?return\$this->\w+;\}?|\{?return(true|false|null|\[\]);\}?")


def body_hashes(body: str, suffix: str) -> tuple[str, str, int]:
    """Exact hash (whitespace/comments ignored) and shape hash (identifiers/literals ignored)."""
    code = strip_comments(body, suffix)
    code = code.split("\n", 1)[1] if "\n" in code else ""  # ignore the signature line
    exact = re.sub(r"\s+", "", code)
    shape = re.sub(r"(['\"`])(?:\\.|(?!\1)[^\\])*\1", "S", code)
    shape = re.sub(r"\b\d+(\.\d+)?\b", "N", shape)
    shape = re.sub(r"\$?[A-Za-z_][\w$]*", "I", shape)
    shape = re.sub(r"\s+", "", shape)
    sha = lambda s: hashlib.sha1(s.encode()).hexdigest()
    return sha(exact), sha(shape), (0 if FRAMEWORK_ONE_LINER.fullmatch(exact) else len(exact))


def analyze(path: Path, rel: str) -> dict:
    text = read(path)
    norm_file = re.sub(r"\s+", "", strip_comments(text, path.suffix))
    fns = []
    for name, start, end, body, top in functions(path, text):
        exact, shape, size = body_hashes(body, path.suffix)
        fns.append({"name": name, "stem": path.stem, "line": start, "lines": end - start + 1, "top": top,
                    "exact": exact, "shape": shape, "size": size})
    return {"lines": text.count("\n") + 1, "data": bool(DATA_FILE.search(rel)),
            "file_hash": hashlib.sha1(norm_file.encode()).hexdigest() if len(norm_file) > 60 else None,
            "functions": fns}


# ---------- incremental index ----------
def index_path(root: Path) -> Path:
    key = hashlib.sha1(str(root).lower().encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "pb-code-guard" / f"{key}.json"


def build_index(root: Path, excludes: list[str]) -> dict:
    cache_file = index_path(root)
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
        if cache.get("v") != INDEX_VERSION:
            cache = {}
    except (OSError, json.JSONDecodeError):
        cache = {}
    old, files = cache.get("files", {}), {}
    for path in walk(root, excludes):
        rel = path.relative_to(root).as_posix()
        stat = path.stat()
        stamp = [stat.st_mtime, stat.st_size]
        entry = old.get(rel)
        files[rel] = entry if entry and entry.get("stamp") == stamp else {"stamp": stamp, **analyze(path, rel)}
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({"v": INDEX_VERSION, "files": files}), encoding="utf-8")
    return files


# ---------- commands ----------
def cmd_find(name: str, root: Path, excludes: list[str]) -> dict:
    needle, hits = name.lower(), []
    for rel, info in build_index(root, excludes).items():
        for fn in info["functions"]:
            low = fn["name"].lower()
            if low == needle or (len(needle) >= 4 and needle in low):
                hits.append({"name": fn["name"], "file": rel, "line": fn["line"], "lines": fn["lines"], "top_level": fn["top"]})
    exact = [h for h in hits if h["name"].lower() == needle]
    advice = ("Reuse or extend an exact hit instead of creating a new one." if exact else
              "Similar names exist: read them before creating." if hits else "No definition found: creating is OK.")
    return {"query": name, "exact": exact, "similar": [h for h in hits if h not in exact][:30], "advice": advice}


def group(index: dict, key: str, keep) -> dict:
    groups = defaultdict(list)
    for rel, info in index.items():
        for fn in info["functions"]:
            if keep(fn, info):
                groups[fn[key]].append({"file": rel, "name": fn["name"], "line": fn["line"]})
    return groups


def cmd_scan(root: Path, changed: list[str], max_fn: int, max_file: int, excludes: list[str]) -> dict:
    index = build_index(root, excludes)
    changed_set = {Path(c).resolve().relative_to(root).as_posix() if Path(c).is_absolute() else Path(c).as_posix().lstrip("./")
                   for c in changed}
    involves = lambda files: not changed_set or any(f in changed_set for f in files)
    by_file = defaultdict(list)
    for rel, info in index.items():
        if info["file_hash"]:
            by_file[info["file_hash"]].append(rel)
    exact = group(index, "exact", lambda f, i: f["lines"] >= 4 and f["size"] >= 40
                  and f["name"] not in ("__construct", "constructor", "__init__"))
    shape = group(index, "shape", lambda f, i: f["lines"] >= 8 and f["size"] >= 120 and not i["data"])
    names = group(index, "name", lambda f, i: f["top"] and not i["data"] and f["name"].lower() not in COMMON_LOWER
                  and not f["name"].startswith("test") and f["name"] != f.get("stem"))
    dup_files = [v for v in by_file.values() if len(v) > 1 and involves(v)]
    dup_exact = [v for v in exact.values() if len(v) > 1 and involves([x["file"] for x in v])]
    exact_keys = {tuple(sorted((x["file"], x["line"]) for x in v)) for v in dup_exact}
    dup_shape = [v for v in shape.values() if len(v) > 1 and involves([x["file"] for x in v])
                 and tuple(sorted((x["file"], x["line"]) for x in v)) not in exact_keys]
    dup_names = [{"name": k, "defs": v} for k, v in names.items()
                 if len({d["file"] for d in v}) > 1 and involves([d["file"] for d in v])]
    long_fn = [{"file": rel, "name": fn["name"], "line": fn["line"], "lines": fn["lines"]}
               for rel, info in index.items() if not info["data"] and involves([rel])
               for fn in info["functions"] if fn["lines"] > max_fn and not fn["name"][:1].isupper()]
    long_file = [{"file": rel, "lines": info["lines"]} for rel, info in index.items()
                 if info["lines"] > max_file and not info["data"] and involves([rel])]
    # Same name in several files is advisory: frameworks repeat names on purpose (Index.tsx, Controller methods).
    blocking = bool(dup_files or dup_exact)
    return {"root": str(root), "changed_only": bool(changed_set), "files_indexed": len(index),
            "duplicate_files": dup_files, "duplicate_function_bodies": dup_exact,
            "renamed_copies": dup_shape[:50], "same_name_in_several_files": dup_names[:50],
            "long_functions": sorted(long_fn, key=lambda x: -x["lines"])[:50],
            "long_files": sorted(long_file, key=lambda x: -x["lines"])[:50], "blocking": blocking,
            "advice": ("Merge duplicates into one owner (reuse the existing one); renamed copies usually mean "
                       "copy-paste; split long functions by responsibility.") if blocking or dup_shape or long_fn else "Clean."}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find")
    f.add_argument("name")
    s = sub.add_parser("scan")
    s.add_argument("--changed", nargs="*", default=[])
    s.add_argument("--max-fn", type=int, default=60)
    s.add_argument("--max-file", type=int, default=400)
    for p in (f, s):
        p.add_argument("--root", default=".")
        p.add_argument("--exclude", nargs="*", default=[], help="Extra relative dirs to skip (e.g. asstes docs/mockups).")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    excludes = [e.replace("\\", "/").strip("/") for e in args.exclude]
    if args.cmd == "find":
        print(json.dumps(cmd_find(args.name, root, excludes), ensure_ascii=False, indent=2))
        return 0
    out = cmd_scan(root, args.changed, args.max_fn, args.max_file, excludes)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 1 if (args.changed and out["blocking"]) else 0


if __name__ == "__main__":
    sys.exit(main())
