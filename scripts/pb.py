#!/usr/bin/env python3
"""pb - the project-brain stack CLI, usable by ANY coding agent (Claude, Codex, Cursor, Gemini, Aider) or a human.

  python pb.py start  [--root DIR] [--name NAME]   prepare a repo: git baseline, .project-brain (lite), code graph,
                                                   baseline audits (i18n, secrets, duplication), AGENTS.md section,
                                                   git pre-commit gate. Safe to re-run.
  python pb.py finish [--root DIR] [--changed F..] gates before saying "done": duplication + size, translations,
                                                   secrets, graph refresh. Exit 1 when a gate fails.
  python pb.py find <Name> [--root DIR]            does this symbol already exist? (search before creating)
  python pb.py impact <Symbol> [--root DIR]        what depends on it? (graphify affected)
  python pb.py doctor                              is the stack installed and healthy on this machine?
  python pb.py precommit [--root DIR]              the git pre-commit gate (installed by `start`)
  python pb.py scaffold-docs [--root DIR]          copy the production docs pack into docs/ (never overwrites)
  python pb.py plan [--root DIR] [--gate G]        planning gates: data|product|engineering|implementation|production

Every command prints one JSON object. Gates exit 1 on failure so any agent or CI can rely on the exit code.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
PY = sys.executable
CODE_EXTS = {".php", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".py", ".dart"}
AGENTS_BEGIN, AGENTS_END = "<!-- project-brain:begin -->", "<!-- project-brain:end -->"


def tool(script: str, *args: str, cwd: Path | None = None) -> tuple[int, dict]:
    proc = subprocess.run([PY, str(HERE / script), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=cwd)
    try:
        return proc.returncode, json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return proc.returncode, {"raw": (proc.stdout or proc.stderr)[-800:]}


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


def graph_update(root: Path) -> str:
    exe = shutil.which("graphify")
    if not exe:
        return "graphify not installed: use code_guard find + grep"
    proc = subprocess.run([exe, "update", "."], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return "updated" if proc.returncode == 0 else "failed: " + (proc.stderr or proc.stdout)[-200:]


def agents_md_section() -> str:
    pb = SKILL.as_posix()
    return f"""{AGENTS_BEGIN}
## project-brain stack (applies to every coding agent working in this repo)

Read `{pb}/SKILL.md` sections 1 (commitments), 0 (router) and 4 (execution loop) before working, then only the
reference files your task needs (`{pb}/references/`). The repo docs (PRD, project map, decisions) are the product.

Commands (run from the repo root; each prints JSON):
- Before creating any function/class/component: `python {pb}/scripts/pb.py find <Name>`; reuse exact hits.
- Before changing a signature/schema/route: `python {pb}/scripts/pb.py impact <Symbol>`; update every consumer.
- Before saying "done": `python {pb}/scripts/pb.py finish --changed <files you touched>` must exit 0.
- Commits are gated by `.git/hooks/pre-commit` (duplicates, translations, secrets, security patterns).
- Security: the 14 weakness classes and 20 backend fundamentals in `{pb}/references/security-baseline.md` apply to every backend change.

Non-negotiable: no invented paths/APIs/versions (verify with a tool, else write UNKNOWN); smallest correct change;
functions <= 40 lines, files <= 300; no duplicated logic; all locales; tests on the real DB engine; never commit
secret files (they stay in place, ignored); owner gates for money, auth, tenancy, destructive data, deploys;
append a dated section to `.project-brain/HANDOFF.md` before stopping.

Without Claude Code hooks you must do these yourself: ask the owner before git push, ssh/plink/scp/rsync, deploy commands,
migrate --force or migrate:fresh/reset/refresh, DROP/TRUNCATE, rm -rf; check `git status` and recently modified files
before editing (another agent may be working); if you are Codex, steps that say "delegate to Codex" mean do it yourself.
{AGENTS_END}
"""


def ensure_ignored(root: Path, patterns: list[str]) -> list[str]:
    """Keep generated graph caches and hook state out of git (and out of the gates)."""
    path = root / ".gitignore"
    current = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    missing = [p for p in patterns if p not in {l.strip() for l in current.splitlines()}]
    if missing:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            prefix = "\n" if current and not current.endswith("\n") else ""
            handle.write(prefix + "\n".join(missing) + "\n")
    return missing


def write_agents_md(root: Path, filename: str = "AGENTS.md") -> str:
    path = root / filename
    text = path.read_text(encoding="utf-8") if path.exists() else "# Agent instructions\n\n"
    section = agents_md_section()
    if AGENTS_BEGIN in text and AGENTS_END in text:
        start, end = text.index(AGENTS_BEGIN), text.index(AGENTS_END) + len(AGENTS_END)
        new = text[:start] + section.strip() + text[end:]
    else:
        new = text.rstrip() + "\n\n" + section
    if new != text:
        path.write_text(new, encoding="utf-8", newline="\n")
        return "written"
    return "up to date"


def install_precommit(root: Path) -> str:
    hooks = root / ".git" / "hooks"
    if not hooks.is_dir():
        return "no git repo"
    hook = hooks / "pre-commit"
    body = ("#!/bin/sh\n# project-brain gate (any agent, any human)\n"
            f'PY="{Path(PY).as_posix()}"\n[ -x "$PY" ] || PY=python\n'
            f'"$PY" "{(HERE / "pb.py").as_posix()}" precommit --root "$(git rev-parse --show-toplevel)"\n')
    if hook.exists() and "project-brain gate" not in hook.read_text(encoding="utf-8", errors="replace"):
        return "existing foreign pre-commit hook left untouched: chain it manually"
    hook.write_text(body, encoding="utf-8", newline="\n")
    return "installed"


# ---------- commands ----------
def cmd_start(root: Path, name: str | None) -> tuple[int, dict]:
    report = {"root": root.as_posix()}
    report["git"] = tool("git_baseline.py", "--root", str(root))[1]
    if not (root / ".project-brain").is_dir():
        code, _ = tool("project_brain.py", "init", "--lite", "--project-name", name or root.name, cwd=root)
        report["project_brain"] = "initialized (lite)" if code == 0 else "init failed"
    else:
        report["project_brain"] = "present"
    report["graph"] = graph_update(root)
    report["gitignore"] = ensure_ignored(root, ["graphify-out/cache/", "graphify-out/20*/", ".project-brain/locks/"])
    _, i18n = tool("i18n_check.py", "--root", str(root))
    _, secrets = tool("secret_scan.py", "--root", str(root))
    _, guard = tool("code_guard.py", "scan", "--root", str(root))
    _, plan = tool("plan_check.py", "--root", str(root), "--gate", "none")
    report["baseline"] = {
        "i18n_families_with_problems": i18n.get("families_with_problems"),
        "secrets": {k: secrets.get(k) for k in ("high", "medium", "info")},
        "duplicates": {k: len(guard.get(k, [])) for k in ("duplicate_files", "duplicate_function_bodies", "renamed_copies")},
        "planning": {"data_gate": plan.get("data_gate_answered"), "steps_missing": len(plan.get("steps_missing", [])),
                     "next_gate": next((g for g, v in plan.get("gates", {}).items() if not v.get("passed")), "all passed"),
                     "templates_unfilled": len(plan.get("templates_unfilled", []))},
    }
    report["agents_md"] = write_agents_md(root)
    report["gemini_md"] = write_agents_md(root, "GEMINI.md")  # Gemini CLI reads GEMINI.md; Aider: `aider --read AGENTS.md`
    report["precommit"] = install_precommit(root)
    report["next"] = "Record baseline findings in [ORPHANS & PENDING]; do not fix them unasked."
    return 0, report


def cmd_finish(root: Path, changed: list[str], refresh_graph: bool = True) -> tuple[int, dict]:
    if not changed and (root / ".git").is_dir():
        tracked = git(root, "diff", "--name-only", "--diff-filter=ACMR", "HEAD").stdout.splitlines()
        untracked = git(root, "ls-files", "--others", "--exclude-standard").stdout.splitlines()
        changed = [f for f in dict.fromkeys(tracked + untracked) if f and not f.startswith("graphify-out/")]
    code_files = [c for c in changed if Path(c).suffix in CODE_EXTS]
    gates = {}
    gates["code_guard"] = tool("code_guard.py", "scan", "--root", str(root), "--changed", *code_files) if code_files else (0, {"skipped": "no code files"})
    gates["i18n"] = tool("i18n_check.py", "--root", str(root), "--changed", *changed) if changed else (0, {"skipped": "nothing changed"})
    gates["secrets"] = tool("secret_scan.py", "--root", str(root), "--files", *changed) if changed else (0, {"skipped": "nothing changed"})
    gates["security"] = tool("vuln_scan.py", "--root", str(root), "--changed", *code_files) if code_files else (0, {"skipped": "no code files"})
    failed = [k for k, (code, _) in gates.items() if code != 0]
    report = {"changed": changed, "failed_gates": failed,
              "details": {k: v for k, (c, v) in gates.items() if c != 0},
              "graph": graph_update(root) if refresh_graph and (root / "graphify-out").is_dir() else "not refreshed",
              "next": "Fix the failed gates, then rerun." if failed else
                      "Gates passed. Still required: tests on the real stack, browser check for UI, HANDOFF entry."}
    return (1 if failed else 0), report


def cmd_precommit(root: Path) -> tuple[int, dict]:
    staged = [f for f in git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR").stdout.splitlines() if f]
    unstaged = set(git(root, "diff", "--name-only").stdout.splitlines())
    mixed = [f for f in staged if f in unstaged]
    if mixed:
        # The gates read the working tree; refuse when it differs from what is about to be committed.
        report = {"failed_gates": ["staged-content"], "files": mixed,
                  "next": "These files have unstaged changes: stage them (git add) or stash them, then commit again."}
        print("project-brain pre-commit gate: stage or stash the unstaged changes in " + ", ".join(mixed), file=sys.stderr)
        return 1, report
    code, report = cmd_finish(root, staged, refresh_graph=False) if staged else (0, {"staged": []})
    if code:
        print("project-brain pre-commit gate failed: " + ", ".join(report["failed_gates"]), file=sys.stderr)
    return code, report


def cmd_scaffold_docs(root: Path) -> tuple[int, dict]:
    """Copy the production docs pack into docs/ without overwriting; an existing doc with the same name wins."""
    pack = HERE.parent / "assets" / "production-docs"
    docs = root / "docs"
    existing = {p.name.lower(): p.relative_to(root).as_posix() for p in docs.rglob("*") if p.is_file()} if docs.is_dir() else {}
    created, kept = [], {}
    for src in sorted(pack.rglob("*.md")):
        rel = src.relative_to(pack)
        if src.name.lower() in existing:
            kept[rel.as_posix()] = existing[src.name.lower()]
            continue
        dst = docs / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        created.append(dst.relative_to(root).as_posix())
    return 0, {"created": created, "kept_existing": kept,
               "next": "Fill each created file with project facts (or 'N/A - reason'), then delete its first "
                       "'<!-- pb:template' line; plan_check ignores files that still carry it."}


def cmd_doctor() -> tuple[int, dict]:
    code, report = tool("install.py", "--check")
    report["codex_skill_copy"] = (Path.home() / ".codex" / "skills" / "project-brain" / "SKILL.md").exists()
    return code, report


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("start", "finish", "find", "impact", "precommit", "scaffold-docs", "plan"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".")
        if name == "start":
            p.add_argument("--name")
        if name == "finish":
            p.add_argument("--changed", nargs="*", default=[])
        if name in ("find", "impact"):
            p.add_argument("symbol")
        if name == "plan":
            p.add_argument("--gate", default="data")
    sub.add_parser("doctor")
    args = ap.parse_args()
    root = Path(getattr(args, "root", ".")).resolve()
    if args.cmd == "start":
        code, out = cmd_start(root, args.name)
    elif args.cmd == "finish":
        code, out = cmd_finish(root, args.changed)
    elif args.cmd == "find":
        code, out = tool("code_guard.py", "find", args.symbol, "--root", str(root))
    elif args.cmd == "impact":
        exe = shutil.which("graphify")
        if not exe or not (root / "graphify-out").is_dir():
            code, out = 0, {"note": "no graph: run `pb.py start` first or grep for callers", "symbol": args.symbol}
        else:
            proc = subprocess.run([exe, "affected", args.symbol], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
            code, out = 0, {"symbol": args.symbol, "affected": [l for l in proc.stdout.splitlines() if l.startswith("- ")]}
    elif args.cmd == "precommit":
        code, out = cmd_precommit(root)
    elif args.cmd == "scaffold-docs":
        code, out = cmd_scaffold_docs(root)
    elif args.cmd == "plan":
        code, out = tool("plan_check.py", "--root", str(root), "--gate", args.gate)
    else:
        code, out = cmd_doctor()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
