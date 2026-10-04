#!/usr/bin/env python3
"""Install / repair project-brain on this machine (idempotent, portable).

  python install.py            install or repair everything
  python install.py --check    report only, change nothing
  python install.py --uninstall  remove the hooks, the pb-* agents and the MCP registration (settings backed up first);
                                 the skill folder and the projects' .project-brain/ folders are left untouched

Steps: dependency check (python, git, node, php, codex, graphify, claude) -> localize paths in workflows (build.py)
-> install pb-* agents into ~/.claude/agents with this machine's paths -> register the codex-delegate MCP server
(user scope) -> merge project-brain hooks into ~/.claude/settings.json (backup first) -> run the regression tests.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
HOME_CLAUDE = Path.home() / ".claude"
PY = Path(sys.executable).as_posix()
OLD_PATH = re.compile(r"[A-Za-z]:/[^\s'\"`)]*?/\.claude/skills/project-brain|/(?:home|Users)/[^\s'\"`)]*?/\.claude/skills/project-brain"
                      r"|~/\.claude/skills/project-brain")
HOOKS = [("PreToolUse", "Edit|Write|MultiEdit|NotebookEdit", "pre-edit", 30, None),
         ("PreToolUse", "Bash|PowerShell", "pre-bash", 10, None),
         ("PostToolUse", "Edit|Write|MultiEdit|NotebookEdit", "post-edit", 90, "project-brain: duplicate/i18n/security check"),
         ("Stop", None, "stop", 15, None),
         ("SessionEnd", None, "session-end", 15, None)]


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def deps() -> dict:
    out = {}
    for tool, args in {"git": ["--version"], "node": ["--version"], "php": ["-v"], "codex": ["--version"],
                       "graphify": ["--help"], "claude": ["--version"]}.items():
        path = shutil.which(tool)
        out[tool] = (run([path, *args]).stdout.splitlines() or ["?"])[0][:60] if path else "MISSING"
    out["python"] = sys.version.split()[0]
    return out


def install_agents(check: bool) -> list[str]:
    target = HOME_CLAUDE / "agents"
    done = []
    for src in sorted((SKILL / "agents").glob("pb-*.md")):
        text = OLD_PATH.sub(SKILL.as_posix(), src.read_text(encoding="utf-8"))
        dst = target / src.name
        if not dst.exists() or dst.read_text(encoding="utf-8") != text:
            done.append(src.name)
            if not check:
                target.mkdir(parents=True, exist_ok=True)
                dst.write_text(text, encoding="utf-8", newline="\n")
    return done


def register_mcp(check: bool) -> str:
    claude = shutil.which("claude")
    if not claude:
        return "claude CLI missing: register manually"
    if "codex-delegate" in run([claude, "mcp", "list"], timeout=60).stdout:
        return "already registered"
    if check:
        return "would register"
    res = run([claude, "mcp", "add", "--scope", "user", "codex-delegate", "--", PY,
               (SKILL / "scripts" / "codex_mcp.py").as_posix()], timeout=60)
    return "registered" if res.returncode == 0 else "failed: " + res.stderr[:200]


def strip_hooks(hooks: dict) -> None:
    """Remove every project-brain hook entry; the user's other hooks (even in the same group) stay."""
    for event in list(hooks):
        groups = []
        for group in hooks[event]:
            own = [h for h in group.get("hooks", []) if "pb_hooks.py" not in json.dumps(h)]
            if own:
                groups.append({**group, "hooks": own})
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]


def save_settings(path: Path, settings: dict) -> None:
    if path.exists():
        shutil.copyfile(path, path.with_name(f"settings.json.bak-{int(time.time())}"))
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def uninstall() -> dict:
    out = {}
    path = HOME_CLAUDE / "settings.json"
    if path.exists():
        settings = json.loads(path.read_text(encoding="utf-8"))
        before = json.dumps(settings.get("hooks", {}), sort_keys=True)
        strip_hooks(settings.setdefault("hooks", {}))
        if not settings["hooks"]:
            del settings["hooks"]
        changed = json.dumps(settings.get("hooks", {}), sort_keys=True) != before
        if changed:
            save_settings(path, settings)
        out["hooks"] = "removed (backup written)" if changed else "none found"
    removed = []
    for src in (SKILL / "agents").glob("pb-*.md"):
        dst = HOME_CLAUDE / "agents" / src.name
        if dst.exists():
            dst.unlink()
            removed.append(src.name)
    out["agents_removed"] = removed
    claude = shutil.which("claude")
    out["mcp"] = (run([claude, "mcp", "remove", "--scope", "user", "codex-delegate"], timeout=60).returncode == 0
                  and "removed" or "not registered") if claude else "claude CLI missing"
    out["kept"] = "the skill folder and every project's .project-brain/ memory (delete them yourself if you want)"
    return out


def merge_hooks(check: bool) -> list[str]:
    """Replace every existing project-brain hook entry (any path/python) with the current definition."""
    path = HOME_CLAUDE / "settings.json"
    settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    hooks = settings.setdefault("hooks", {})
    script = (SKILL / "scripts" / "pb_hooks.py").as_posix()
    before = json.dumps(hooks, sort_keys=True)
    strip_hooks(hooks)
    for event, matcher, name, timeout, status in HOOKS:
        hook = {"type": "command", "command": PY, "args": [script, name], "timeout": timeout}
        if status:
            hook["statusMessage"] = status
        hooks.setdefault(event, []).append({**({"matcher": matcher} if matcher else {}), "hooks": [hook]})
    changed = json.dumps(hooks, sort_keys=True) != before
    if changed and not check:
        save_settings(path, settings)
    return [f"{e}:{n}" for e, _, n, _, _ in HOOKS] if changed else []


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    args = ap.parse_args()
    if args.uninstall:
        print(json.dumps(uninstall(), ensure_ascii=False, indent=2))
        return 0
    check = args.check
    report = {"skill": SKILL.as_posix(), "dependencies": deps()}
    if not check:
        build = run([sys.executable, str(SKILL / "workflows" / "build.py")])
        report["workflows_build"] = "ok" if build.returncode == 0 else build.stdout[-400:]
    report["agents_updated"] = install_agents(check)
    report["mcp"] = register_mcp(check)
    report["hooks_added"] = merge_hooks(check)
    tests = run([sys.executable, "-m", "unittest", "discover", "-s", str(SKILL / "tests")], cwd=SKILL)
    report["tests"] = (tests.stderr.strip().splitlines() or ["?"])[-1]
    report["missing_dependencies"] = [k for k, v in report["dependencies"].items() if v == "MISSING"]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["tests"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
