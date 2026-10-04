#!/usr/bin/env python3
"""Claude Code hooks that enforce project-brain rules deterministically.

Active only inside repositories that contain a `.project-brain/` folder; elsewhere every hook exits 0.
  pre-edit    (PreToolUse Edit|Write|MultiEdit|NotebookEdit): cross-session file lock (30 min TTL) and a
              baseline of the file's existing findings (so only NEW problems block).
  post-edit   (PostToolUse Edit|Write|MultiEdit|NotebookEdit): duplication, translation and security-pattern gates
              on the edited file; only problems introduced by this edit are fed back (exit 2).
  pre-bash    (PreToolUse Bash|PowerShell): deploy/remote/destructive commands require confirmation.
  stop        (Stop): blocks ending the turn when this session edited project files after the last HANDOFF.md update.
  session-end (SessionEnd): releases this session's locks and baselines.
Shared memory files under .project-brain/ are never locked (they are append-only logs every session must write).
Usage in settings.json: python <PB>/scripts/pb_hooks.py <event>
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCK_TTL = 30 * 60
CODE_EXTS = {".php", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".py", ".dart", ".vue"}
I18N_HINT = re.compile(r"(^|/)(lang|langs|locales?|i18n|l10n|translations?)(/|$)|\.arb$")
RISKY = re.compile(
    r"\b(plink|pscp|scp|sftp|ftp)\b"
    r"|\bssh\b(?!-keygen|-add|-agent)"
    r"|\brsync\b[^\n|;]*\s\S+:\S*"
    r"|\bgit\b(\s+-C\s+\S+)?\s+push\b"
    r"|artisan\s+(migrate:(fresh|reset|rollback|refresh)\b|migrate\b[^\n]*--force|db:wipe)"
    r"|\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\s+TABLE)\b"
    r"|\brm\s+(-\w+\s+)*(-(?=[a-z]*r)(?=[a-z]*f)[a-z]+|-r\w*\s+-f\w*|-f\w*\s+-r\w*|--recursive\s+--force|--force\s+--recursive)\s+(/|~|\$HOME|\*|\.\s*$)"
    r"|Remove-Item\b(?=[^\n]*-Recurse)(?=[^\n]*-Force)"
    r"|\b(vercel|netlify|firebase|fly|heroku)\b[^\n]*(\bdeploy\b|--prod\b)",
    re.I)
READ_ONLY_PREFIX = re.compile(r"^\s*(grep|rg|findstr|Select-String|cat|type|Get-Content|echo|Write-Output)\b", re.I)
SEGMENTS = re.compile(r"&&|\|\||[;|\n]")


def is_risky(command: str) -> bool:
    """Gate when ANY chained segment is risky and not itself a read-only command (echo x && git push is risky)."""
    return any(RISKY.search(seg) and not READ_ONLY_PREFIX.match(seg) for seg in SEGMENTS.split(command or ""))


def payload() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def brain_root(start: str | None) -> Path | None:
    if not start:
        return None
    path = Path(start).resolve()
    for candidate in [path, *path.parents]:
        if (candidate / ".project-brain").is_dir():
            return candidate
    return None


def edited_file(data: dict) -> Path | None:
    tool_input = data.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(data.get("cwd") or ".") / path
    return path.resolve()


def state_dir(root: Path) -> Path:
    path = root / ".project-brain" / "locks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def key(rel: str) -> str:
    return hashlib.sha1(rel.lower().encode()).hexdigest()[:16]


def run_tool(script: str, args: list[str], root: Path) -> tuple[int, dict]:
    try:
        proc = subprocess.run([sys.executable, str(HERE / script), *args, "--root", str(root)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
        return proc.returncode, json.loads(proc.stdout or "{}")
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return 0, {}


def fingerprints(root: Path, rel: str, suffix: str) -> dict:
    """Current problems involving one file, as comparable fingerprints."""
    fp = {"dup": [], "long": {}, "vuln": [], "i18n": []}
    if suffix in CODE_EXTS:
        _, guard = run_tool("code_guard.py", ["scan", "--changed", rel], root)
        for group in guard.get("duplicate_function_bodies", []) + guard.get("duplicate_files", []):
            fp["dup"].append(json.dumps(sorted((g if isinstance(g, str) else f"{g['file']}:{g['name']}") for g in group)))
        fp["long"] = {f"{f['name']}": f["lines"] for f in guard.get("long_functions", []) if f["file"] == rel}
        _, vuln = run_tool("vuln_scan.py", ["--changed", rel], root)
        fp["vuln"] = [f"{f['cwe']}|{f['rule']}|{f.get('code', '')}" for f in vuln.get("findings", []) if f["severity"] == "high"]
    if I18N_HINT.search(rel):
        code, out = run_tool("i18n_check.py", ["--changed", rel], root)
        if code == 1:
            fp["i18n"] = [json.dumps(p.get("missing_keys", {}), sort_keys=True) + json.dumps(p.get("placeholder_mismatch", []), sort_keys=True)
                          for p in out.get("problems", [])]
    return fp


# ---------- events ----------
def pre_edit(data: dict) -> int:
    target = edited_file(data)
    root = brain_root(str(target.parent)) if target else None
    if not root:
        return 0
    rel = target.relative_to(root).as_posix()
    if rel.startswith(".project-brain/"):
        return 0  # shared append-only memory: never locked
    me, now = data.get("session_id", "unknown"), time.time()
    lock = state_dir(root) / f"{key(rel)}.json"
    try:
        held = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        held = {}
    if held and held.get("session") != me and now - held.get("ts", 0) < LOCK_TTL:
        minutes = int((now - held["ts"]) / 60)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
              "permissionDecisionReason": f"{rel} is being edited by another session ({minutes} min ago). Work on another file, "
              "coordinate through .project-brain/HANDOFF.md, or wait for the 30-minute lock to expire."}}))
        return 0
    lock.write_text(json.dumps({"session": me, "file": rel, "ts": now}), encoding="utf-8")
    baseline = state_dir(root) / f"{key(rel)}.baseline.json"
    if target.exists():
        try:
            stored = json.loads(baseline.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stored = {}
        # Re-baseline when the file changed outside our hooks (owner edit, git pull, Codex, another tool).
        if stored.get("sha") != file_sha(target):
            baseline.write_text(json.dumps({**fingerprints(root, rel, target.suffix), "sha": file_sha(target)}), encoding="utf-8")
    return 0


def file_sha(path: Path) -> str:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def post_edit(data: dict) -> int:
    target = edited_file(data)
    root = brain_root(str(target.parent)) if target else None
    if not root or not target.exists():
        return 0
    rel = target.relative_to(root).as_posix()
    if rel.startswith(".project-brain/"):
        return 0
    baseline_file = state_dir(root) / f"{key(rel)}.baseline.json"
    try:
        before = json.loads(baseline_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        before = {"dup": [], "long": {}, "vuln": [], "i18n": []}  # new file: everything is new
    after = fingerprints(root, rel, target.suffix)
    problems = []
    new_dups = [d for d in after["dup"] if d not in before.get("dup", [])]
    if new_dups:
        problems.append(f"code_guard: this edit introduced duplication involving {rel}: {new_dups[:3]}. Reuse the existing owner instead of a copy.")
    grown = [f"{n}({l})" for n, l in after["long"].items() if l > before.get("long", {}).get(n, 0) and l > 60]
    if grown:
        problems.append(f"code_guard: functions over 60 lines created or grown by this edit in {rel}: {', '.join(grown[:5])}. Split by responsibility.")
    new_vulns = [v for v in after["vuln"] if v not in before.get("vuln", [])]
    if new_vulns:
        problems.append(f"vuln_scan: this edit introduced high-severity security patterns in {rel}: {new_vulns[:3]}. "
                        "See references/security-baseline.md and fix before continuing.")
    new_i18n = [p for p in after["i18n"] if p not in before.get("i18n", [])]
    if new_i18n:
        problems.append(f"i18n_check: translation keys missing or placeholders differ after editing {rel}: {new_i18n[0][:500]}")
    if not problems:
        # Clean edit: the new state becomes the baseline. With problems the old baseline stays,
        # so the gate keeps firing until the introduced problem is removed.
        baseline_file.write_text(json.dumps({**after, "sha": file_sha(target)}), encoding="utf-8")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    return 0


def pre_bash(data: dict) -> int:
    command = (data.get("tool_input") or {}).get("command", "") or ""
    if not brain_root(data.get("cwd")) or not is_risky(command):
        return 0
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
          "permissionDecisionReason": "project-brain owner gate: deploy, remote or destructive command. "
          "Confirm it was classified safe (references/deploy-protocol.md) or that the owner approved it."}}))
    return 0


def stop(data: dict) -> int:
    root = brain_root(data.get("cwd"))
    if not root or data.get("stop_hook_active"):
        return 0
    me = data.get("session_id", "unknown")
    locks = root / ".project-brain" / "locks"
    mine = []
    for lock in locks.glob("*.json") if locks.is_dir() else []:
        if lock.name.endswith(".baseline.json"):
            continue
        try:
            held = json.loads(lock.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if held.get("session") == me:
            mine.append(held)
    if not mine:
        return 0
    handoff = root / ".project-brain" / "HANDOFF.md"
    last_handoff = handoff.stat().st_mtime if handoff.exists() else 0
    if max(h["ts"] for h in mine) > last_handoff:
        print(json.dumps({"decision": "block", "reason":
              "project-brain: you edited project files after the last HANDOFF.md update. Before stopping, append a dated "
              "section to .project-brain/HANDOFF.md (done, verified with commands, not verified, decisions, next action) "
              "and the change-log entry. If this turn changed nothing worth recording, add one line saying so."}))
    return 0


def session_end(data: dict) -> int:
    root = brain_root(data.get("cwd"))
    locks = root / ".project-brain" / "locks" if root else None
    if locks and locks.is_dir():
        for lock in locks.glob("*.json"):
            if lock.name.endswith(".baseline.json"):
                continue
            try:
                if json.loads(lock.read_text(encoding="utf-8")).get("session") == data.get("session_id"):
                    lock.unlink()
                    (locks / lock.name.replace(".json", ".baseline.json")).unlink(missing_ok=True)
            except (OSError, json.JSONDecodeError):
                continue
    return 0


EVENTS = {"pre-edit": pre_edit, "post-edit": post_edit, "pre-bash": pre_bash, "stop": stop, "session-end": session_end}

if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        sys.exit(EVENTS[event](payload()) if event in EVENTS else 0)
    except Exception as exc:  # a broken hook must never block the owner's work
        print(f"pb_hooks {event} error (ignored): {exc}", file=sys.stderr)
        sys.exit(0)
