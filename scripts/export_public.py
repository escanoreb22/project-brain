#!/usr/bin/env python3
"""Build a clean public copy of project-brain (nothing is pushed or published).

  python export_public.py --out DIR [--private WORD ...]

What it does:
  1. copies the skill's files (tracked + untracked, minus .gitignore'd) into DIR (DIR must be empty or absent),
  2. leaves out the personal owner profile and the bundled third-party modules (their licenses do not allow
     or do not document redistribution); `public/` supplies the README, LICENSE, THIRD_PARTY, an owner-profile
     template and modules/README.md instead,
  3. rewrites absolute machine paths to ~/.claude/skills/project-brain and example project paths to a placeholder,
  4. refuses the result (exit 1) when a private marker is still present: words passed with --private plus one
     word per line in the untracked file `.private-markers` next to SKILL.md (names, emails, project names),
  5. runs secret_scan on the copy and the copy's own test suite.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SKIP_PREFIXES = ("modules/", "public/")
SKIP_FILES = {"references/owner-profile.md"}
TEXT_EXTS = {".md", ".py", ".js", ".json", ".yaml", ".yml", ".txt", ".toml"}
ABS_SKILL = re.compile(r"[A-Za-z]:[\\/][^\s'\"`)]*?[\\/]\.claude[\\/]skills[\\/]project-brain"
                       r"|/(?:home|Users)/[^\s'\"`)]*?/\.claude/skills/project-brain")
ABS_PROJECT = re.compile(r"[A-Za-z]:/Users/[^/\s'\"`]+/(?:Desktop|Documents|Projects|code)/[\w.-]+")


def tracked() -> list[str]:
    res = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=SKILL,
                         capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        raise SystemExit("export_public needs the skill folder to be a git repo (it uses .gitignore to choose files)")
    return [f for f in res.stdout.splitlines() if f and not f.startswith(SKIP_PREFIXES) and f not in SKIP_FILES]


def sanitize(text: str) -> str:
    return ABS_PROJECT.sub("C:/path/to/your-project", ABS_SKILL.sub("~/.claude/skills/project-brain", text))


def copy_tree(out: Path) -> int:
    count = 0
    for rel in tracked():
        src, dst = SKILL / rel, out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix.lower() in TEXT_EXTS:
            dst.write_text(sanitize(src.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
        else:
            shutil.copyfile(src, dst)
        count += 1
    for src in (SKILL / "public").rglob("*"):
        if src.is_file():
            dst = out / src.relative_to(SKILL / "public")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            count += 1
    return count


def leaks(out: Path, markers: list[str]) -> list[str]:
    rx = re.compile("|".join(re.escape(m) for m in markers), re.I) if markers else None
    found = []
    for p in out.rglob("*"):
        if p.is_file() and p.suffix.lower() in TEXT_EXTS:
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if (rx and rx.search(line)) or ABS_SKILL.search(line):
                    found.append(f"{p.relative_to(out).as_posix()}:{i}")
    return found[:50]


def run_tests(out: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="pb-export-test-") as tmp:  # tests rebuild workflows: keep the copy pristine
        probe = Path(tmp) / "project-brain"
        shutil.copytree(out, probe)
        tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=probe,
                               capture_output=True, text=True, encoding="utf-8")
    return (tests.stderr.strip().splitlines() or ["?"])[-1]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--private", nargs="*", default=[])
    ap.add_argument("--skip-tests", action="store_true", help="used by the skill's own test of this script")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        print(json.dumps({"error": f"{out} is not empty: choose a new folder"}))
        return 1
    if SKILL == out or SKILL in out.parents:
        print(json.dumps({"error": "export inside the skill folder is not allowed"}))
        return 1
    marker_file = SKILL / ".private-markers"
    markers = args.private + ([w.strip() for w in marker_file.read_text(encoding="utf-8").splitlines() if w.strip()]
                              if marker_file.exists() else [])
    report = {"out": out.as_posix(), "files": copy_tree(out), "private_markers_checked": len(markers)}
    report["leaks"] = leaks(out, markers)
    sec = subprocess.run([sys.executable, str(out / "scripts" / "secret_scan.py"), "--root", str(out)],
                         capture_output=True, text=True, encoding="utf-8")
    report["secret_scan"] = "clean" if sec.returncode == 0 else sec.stdout[-600:]
    if args.skip_tests:
        report["tests"] = "skipped"
    else:
        report["tests"] = run_tests(out)
    ok = not report["leaks"] and report["secret_scan"] == "clean" and (report["tests"].startswith("OK") or report["tests"] == "skipped")
    report["verdict"] = "ready to review and publish" if ok else "NOT ready: fix the items above"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
