#!/usr/bin/env python3
"""Put a project under git safely (local only, never pushes).

  python git_baseline.py --root DIR [--dry-run]

- Already a git repo: reports branch, dirty files and whether .gitignore covers secrets. Changes nothing.
- Not a repo: writes/extends .gitignore with safe defaults (env files, keys, vendor, builds, caches, server
  credential folders), runs the secret scanner on every file that would be committed, and ABORTS if any
  high-severity secret would enter history. Otherwise `git init` + one baseline commit.
Output: one JSON object. Exit 1 when it refused to commit.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import secret_scan  # noqa: E402

DEFAULT_IGNORE = """
# --- project-brain safe defaults ---
.env
.env.*
!.env.example
*.ppk
*.pem
*.key
*.p12
*.pfx
*.keystore
*.jks
id_rsa*
id_ed25519*
vps/
**/pass.txt
**/*password*.txt
**/admin-login*
/vendor/
node_modules/
/public/build/
/public/hot
/public/storage
/storage/*.key
/storage/logs/
/storage/framework/cache/
/storage/framework/sessions/
/storage/framework/views/
/bootstrap/cache/*.php
/bootstrap/ssr/
.project-brain/locks/
graphify-out/20*/
dist/
build/
coverage/
graphify-out/cache/
.claude/audit-snapshots/
*.log
.DS_Store
Thumbs.db
"""


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


def ensure_gitignore(root: Path, dry: bool) -> list[str]:
    path = root / ".gitignore"
    current = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    present = {line.strip() for line in current.splitlines()}
    missing = [l for l in DEFAULT_IGNORE.strip().splitlines() if l.strip() and l.strip() not in present]
    if missing and not dry:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(("\n" if current and not current.endswith("\n") else "") + "\n".join(missing) + "\n")
    return [m for m in missing if not m.startswith("#")]


def existing_repo_report(root: Path) -> dict:
    status = git(root, "status", "--porcelain").stdout.splitlines()
    tracked_secrets = [f for f in git(root, "ls-files").stdout.splitlines() if secret_scan.SECRET_FILES.search(f)]
    return {"ok": True, "state": "already_git", "branch": git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
            "dirty_files": len(status), "tracked_secret_files": tracked_secrets,
            "advice": "Remove tracked secret files from the index (git rm --cached) and rotate them." if tracked_secrets else "OK"}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    has_commits = (root / ".git").exists() and git(root, "rev-parse", "--verify", "HEAD").returncode == 0
    if has_commits:
        print(json.dumps(existing_repo_report(root), indent=2))
        return 0
    # No repo, or a repo left without a baseline commit by an earlier refused run: (re)do the baseline.
    added_rules = ensure_gitignore(root, args.dry_run)
    if args.dry_run:
        print(json.dumps({"ok": True, "state": "dry_run", "gitignore_rules_to_add": added_rules}, indent=2))
        return 0
    if not (root / ".git").exists():
        git(root, "init", "-q")
    git(root, "config", "core.autocrlf", "false")
    files = git(root, "ls-files", "--others", "--exclude-standard").stdout.splitlines()
    leaks = [f for path in files for f in secret_scan.scan_file(root, root / path) if f["severity"] == "high"]
    if leaks:
        print(json.dumps({"ok": False, "state": "initialized_without_commit", "reason": "secrets would enter history",
                          "leaks": leaks[:50], "next": "Move or ignore these files, rotate exposed secrets, then rerun."}, indent=2))
        return 1
    git(root, "add", "-A")
    commit = git(root, "-c", "user.name=project-brain", "-c", "user.email=project-brain@local", "commit", "-q",
                 "-m", "Baseline snapshot (project-brain)")
    print(json.dumps({"ok": commit.returncode == 0, "state": "initialized", "files_committed": len(files),
                      "gitignore_rules_added": added_rules, "error": commit.stderr.strip()[:300] or None}, indent=2))
    return 0 if commit.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
