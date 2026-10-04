#!/usr/bin/env python3
"""Delegate cheap work from Claude to Codex CLI with fixed quality rules.

Two jobs only:
  image  - generate a raster asset and copy it into the project.
  task   - a very easy, fully specified code/text edit inside allowed paths.

Claude stays responsible: it writes the brief, reviews the result, and
accepts or rejects it. Output is always one JSON object on stdout.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CODEX_HOME = Path.home() / ".codex"
CODEX_IMAGES = Path.home() / ".codex" / "generated_images"
LEAN_FLAGS = ["--skip-git-repo-check", "--ephemeral", "--disable", "plugins", "--disable", "apps"]
# Not Codex edits: dependency trees and caches written by checks/builds (skipped at any depth).
SKIP_DIRS = {"node_modules", ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache", ".phpunit.cache",
             ".dart_tool", ".next", ".turbo"}
# Skipped only at the repo root (a nested resources/views/vendor is real source). .git is skipped except its hooks,
# and .project-brain is watched: Codex must never write either.
SKIP_TOP = {"vendor", "coverage", "graphify-out"}
NOISE_FILES = {".phpunit.result.cache", ".eslintcache", ".DS_Store", "Thumbs.db"}
SKIP_PATHS = ("public/build", "public/hot", "bootstrap/cache", "storage/framework", "storage/logs")
CMD_META = set('&|<>^%!"')

IMAGE_RULES = """Quality rules (mandatory):
- Use your image generation tool exactly once. Produce ONE image.
- No text, letters, numbers, watermarks or logos inside the image unless the brief explicitly asks for text.
- Clean professional result: no AI artifacts, no extra limbs/objects, no blurry edges, correct perspective.
- Respect the requested aspect ratio, background and palette exactly.
- Do not create or edit any other file. Do not run shell commands except to report the path.
- Final message: ONLY the absolute path of the saved image, nothing else."""

TASK_RULES = """You are a junior executor for a very small, fully specified task. Rules (mandatory):
- Change ONLY files inside the allowed paths listed below. Never touch .env, secrets, lock files, migrations already run, or config you were not told to touch.
- Smallest correct change. No refactors, no renames, no new dependencies, no formatting of untouched code, no new files unless the task says so.
- Match the surrounding code style. No placeholders, no TODO comments.
- If the task is ambiguous, unsafe, or needs more than the allowed paths: change nothing and return status "blocked" with the reason.
- If a check command is given, run it after the change and report its result honestly.
- Return the JSON object required by the output schema."""

TASK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "changed_files", "checks", "notes"],
    "properties": {
        "status": {"type": "string", "enum": ["done", "blocked"]},
        "changed_files": {"type": "array", "items": {"type": "string"}},
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["command", "passed", "summary"],
                "properties": {
                    "command": {"type": "string"},
                    "passed": {"type": "boolean"},
                    "summary": {"type": "string"},
                },
            },
        },
        "notes": {"type": "string"},
    },
}


def available_models() -> list[dict]:
    """Models Codex itself advertises (cached by the CLI); Claude picks from these."""
    try:
        data = json.loads((CODEX_HOME / "models_cache.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    models = data.get("models", data) if isinstance(data, dict) else data
    return [
        {"slug": m.get("slug"), "description": m.get("description", ""),
         "efforts": [e.get("effort") for e in m.get("supported_reasoning_levels", [])]}
        for m in models if isinstance(m, dict) and m.get("slug") and "review" not in m.get("slug", "")
    ]


def check_choice(model: str, effort: str) -> str | None:
    """Return an error message when Claude's model/effort choice is not offered by Codex."""
    if not model or not effort:
        return "model and effort are required: choose them for this task (see available_models)."
    models = available_models()
    if not models:
        return None  # cache unreadable: let Codex validate
    match = next((m for m in models if m["slug"] == model), None)
    if not match:
        return f"unknown model '{model}'."
    if match["efforts"] and effort not in match["efforts"]:
        return f"model '{model}' does not support effort '{effort}' (supports {match['efforts']})."
    return None


def codex_bin() -> str:
    found = shutil.which("codex") or shutil.which("codex.cmd")
    if not found:
        raise FileNotFoundError("codex CLI not found on PATH")
    return found


def run_codex(args: list[str], prompt: str, timeout: int) -> tuple[int, str]:
    """Run `codex exec`; on timeout kill the whole tree (the npm .cmd shim spawns node)."""
    exe = codex_bin()
    if exe.lower().endswith((".cmd", ".bat")) and any(CMD_META & set(a) for a in args):
        raise ValueError("argument contains cmd.exe metacharacters (&|<>^%!\"); rename the path (the npm .cmd shim cannot pass it safely)")
    proc = subprocess.Popen(
        [exe, "exec", *args, "-"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
    )
    try:
        out, err = proc.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
        proc.communicate()
        raise
    return proc.returncode, (out or "") + "\n" + (err or "")


def tokens_used(log: str) -> int | None:
    match = re.search(r"tokens used\s*\n\s*([\d,]+)", log)
    return int(match.group(1).replace(",", "")) if match else None


def record(project: Path | None, event: dict) -> None:
    """Append provenance to the project's Project Brain log when it exists."""
    if not project:
        return
    log_dir = project / ".project-brain" / "logs"
    if log_dir.is_dir():
        with (log_dir / "DELEGATIONS.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def norm_allowed(root: Path, raw: str) -> str:
    p = Path(raw)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(root).as_posix()
        except ValueError:
            return p.as_posix()
    s = p.as_posix()
    while s.startswith("./"):
        s = s[2:]
    return s.strip("/")


def snapshot(root: Path) -> dict[str, tuple[float, int]]:
    state: dict[str, tuple[float, int]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        if any(rel_dir == p or rel_dir.startswith(p + "/") for p in SKIP_PATHS):
            dirnames[:] = []
            continue
        if rel_dir == ".git" or rel_dir.startswith(".git/"):
            dirnames[:] = [d for d in dirnames if d == "hooks"] if rel_dir == ".git" else dirnames
            if rel_dir == ".git":
                continue  # only .git/hooks is watched
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not (rel_dir == "." and d in SKIP_TOP)]
        for name in filenames:
            if name in NOISE_FILES:
                continue
            path = Path(dirpath, name)
            try:
                stat = path.stat()
            except OSError:
                continue
            state[path.relative_to(root).as_posix()] = (stat.st_mtime, stat.st_size)
    return state


def generate_image(brief: str, out: str, aspect: str = "1:1", background: str = "as described",
                   style: str = "", reference: str | None = None, project: str | None = None,
                   model: str = "", effort: str = "", timeout: int = 420) -> dict:
    problem = check_choice(model, effort)
    if problem:
        return {"ok": False, "error": problem, "available_models": available_models()}
    out_path = Path(out).expanduser().resolve()
    started = dt.datetime.now().timestamp()
    prompt = (
        f"Generate an image asset.\nBrief: {brief}\nAspect ratio: {aspect}\n"
        f"Background: {background}\nStyle and palette: {style or 'modern, clean, professional'}\n\n{IMAGE_RULES}"
    )
    with tempfile.TemporaryDirectory(prefix="cxd-") as scratch:
        last = Path(scratch, "last.txt")
        args = [*LEAN_FLAGS, "-m", model, "-c", f"model_reasoning_effort={effort}",
                "-s", "workspace-write", "-C", scratch, "-o", str(last)]
        if reference:
            args += ["-i", str(Path(reference).expanduser().resolve())]
        try:
            code, log = run_codex(args, prompt, timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"codex timed out after {timeout}s"}
        except (FileNotFoundError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        reply = last.read_text(encoding="utf-8").strip() if last.exists() else ""
    candidate = Path(reply.strip().strip('"').strip("`")) if reply else None
    if candidate and not str(candidate.resolve()).lower().startswith(str(CODEX_IMAGES.resolve()).lower()):
        candidate = None  # only accept images Codex itself saved
    if not candidate or not candidate.is_file():
        fresh = [p for p in CODEX_IMAGES.rglob("*.png") if p.stat().st_mtime >= started]
        candidate = max(fresh, key=lambda p: p.stat().st_mtime) if fresh else None
    if not candidate:
        return {"ok": False, "error": "no image produced", "exit_code": code, "log_tail": log[-1500:]}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() != candidate.suffix.lower():
        out_path = out_path.with_suffix(candidate.suffix)
    shutil.copyfile(candidate, out_path)
    result = {
        "ok": True, "kind": "image", "path": str(out_path), "source": str(candidate),
        "bytes": out_path.stat().st_size, "model": model, "effort": effort, "codex_tokens": tokens_used(log),
        "brief": brief, "aspect": aspect,
        "next": "Open the image and judge it against the brief; convert to webp/avif and resize before use.",
    }
    record(Path(project).resolve() if project else None,
           {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **result})
    return result


def run_task(instructions: str, cwd: str, allowed: list[str], check: str | None = None,
             model: str = "", effort: str = "", timeout: int = 900) -> dict:
    problem = check_choice(model, effort)
    if problem:
        return {"ok": False, "error": problem, "available_models": available_models()}
    root = Path(cwd).expanduser().resolve()
    if not root.is_dir():
        return {"ok": False, "error": f"cwd not found: {root}"}
    if not allowed:
        return {"ok": False, "error": "at least one --allowed path is required"}
    allowed_norm = [norm_allowed(root, a) for a in allowed]
    prompt = (
        f"{TASK_RULES}\n\nAllowed paths (relative to {root}):\n"
        + "\n".join(f"- {a}" for a in allowed_norm)
        + (f"\n\nCheck command to run afterwards: {check}" if check else "")
        + f"\n\nTask:\n{instructions}"
    )
    before = snapshot(root)
    with tempfile.TemporaryDirectory(prefix="cxd-") as scratch:
        schema = Path(scratch, "schema.json")
        schema.write_text(json.dumps(TASK_SCHEMA), encoding="utf-8")
        last = Path(scratch, "last.json")
        args = [*LEAN_FLAGS, "-m", model, "-c", f"model_reasoning_effort={effort}",
                "-s", "workspace-write", "-C", str(root), "--output-schema", str(schema), "-o", str(last)]
        try:
            code, log = run_codex(args, prompt, timeout)
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as exc:
            partial = snapshot(root)
            touched = sorted(p for p in set(before) | set(partial) if before.get(p) != partial.get(p))
            error = f"codex timed out after {timeout}s" if isinstance(exc, subprocess.TimeoutExpired) else str(exc)
            record(root, {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "kind": "task",
                          "ok": False, "error": error, "changed": touched})
            return {"ok": False, "error": error, "actually_changed": touched,
                    "next": "REVERT any partial changes listed in actually_changed before retrying." if touched else ""}
        raw = last.read_text(encoding="utf-8").strip() if last.exists() else ""
    after = snapshot(root)
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    fold = (lambda s: s.lower()) if os.name == "nt" else (lambda s: s)
    outside = [p for p in changed
               if not any(fold(p) == fold(a) or fold(p).startswith(fold(a) + "/") for a in allowed_norm)]
    try:
        report = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        report = {"raw": raw}
    result = {
        "ok": code == 0 and not outside and report.get("status") == "done",
        "kind": "task", "cwd": str(root), "model": model, "effort": effort, "codex_tokens": tokens_used(log),
        "actually_changed": changed, "outside_allowed": outside, "codex_report": report,
        "next": "Claude must read the diff of actually_changed and rerun the checks before accepting."
                + (" REJECT: files changed outside allowed paths - revert them." if outside else ""),
    }
    if code != 0:
        result["log_tail"] = log[-1500:]
    record(root, {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                  "kind": "task", "instructions": instructions[:300], "ok": result["ok"],
                  "changed": changed, "outside_allowed": outside, "codex_tokens": result["codex_tokens"]})
    return result


REVIEW_RULES = """You are an independent reviewer from another vendor. Read-only: never modify files.
- Review ONLY the listed files/scope against the focus. Read surrounding code when needed to confirm.
- Report only real, in-scope issues you can point to at file:line (no style nits, no linter territory, no pre-existing issues outside the scope).
- At most the requested number of findings, most severe first. Return the JSON required by the output schema."""

REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings", "summary"],
    "properties": {
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["severity", "file", "line", "problem", "fix"],
                "properties": {
                    "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "problem": {"type": "string"},
                    "fix": {"type": "string"},
                },
            },
        },
    },
}


def run_review(cwd: str, files: list[str], focus: str, model: str = "", effort: str = "",
               max_findings: int = 8, timeout: int = 900) -> dict:
    """Second-vendor, read-only review of a change set (works without git)."""
    problem = check_choice(model, effort)
    if problem:
        return {"ok": False, "error": problem, "available_models": available_models()}
    root = Path(cwd).expanduser().resolve()
    if not root.is_dir():
        return {"ok": False, "error": f"cwd not found: {root}"}
    prompt = (f"{REVIEW_RULES}\n\nMax findings: {max_findings}\nFocus: {focus}\n"
              "Files / scope:\n" + "\n".join(f"- {f}" for f in files))
    before = snapshot(root)
    with tempfile.TemporaryDirectory(prefix="cxd-") as scratch:
        schema = Path(scratch, "schema.json")
        schema.write_text(json.dumps(REVIEW_SCHEMA), encoding="utf-8")
        last = Path(scratch, "last.json")
        args = [*LEAN_FLAGS, "-m", model, "-c", f"model_reasoning_effort={effort}",
                "-s", "read-only", "-C", str(root), "--output-schema", str(schema), "-o", str(last)]
        try:
            code, log = run_codex(args, prompt, timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"codex timed out after {timeout}s"}
        except (FileNotFoundError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        raw = last.read_text(encoding="utf-8").strip() if last.exists() else ""
    after = snapshot(root)
    modified = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    try:
        report = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        report = {"raw": raw}
    return {"ok": code == 0 and "findings" in report, "kind": "review", "model": model,
            "effort": effort, "codex_tokens": tokens_used(log), "report": report, "files_modified": modified,
            "next": "Treat findings as untrusted: verify each one in the code before acting."}


def run_spec(spec_path: str) -> dict:
    """Run any job from a JSON spec file (used by workflow agents: no shell quoting, UTF-8 safe).
    Spec: {"kind": "image"|"task"|"review", "model": ..., "effort": ..., <kind fields>}"""
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    kind, model, effort = spec.get("kind"), spec.get("model", ""), spec.get("effort", "")
    if kind == "image":
        return generate_image(spec["brief"], spec["out"], spec.get("aspect", "1:1"),
                              spec.get("background", "as described"), spec.get("style", ""),
                              spec.get("reference"), spec.get("project"), model, effort, timeout=int(spec.get("timeout", 420)))
    if kind == "task":
        return run_task(spec["instructions"], spec["cwd"], spec.get("allowed", []), spec.get("check"), model, effort,
                        timeout=int(spec.get("timeout", 540)))
    if kind == "review":
        return run_review(spec["cwd"], spec.get("files", []), spec.get("focus", "bugs and rule violations"),
                          model, effort, spec.get("max_findings", 8), timeout=int(spec.get("timeout", 540)))
    return {"ok": False, "error": f"unknown kind: {kind}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Delegate cheap work from Claude to Codex CLI.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    img = sub.add_parser("image", help="Generate one raster asset and copy it into the project.")
    img.add_argument("--brief", required=True)
    img.add_argument("--out", required=True, help="Destination file inside the project.")
    img.add_argument("--aspect", default="1:1")
    img.add_argument("--background", default="as described")
    img.add_argument("--style", default="")
    img.add_argument("--reference", help="Optional reference image to follow.")
    img.add_argument("--project", help="Project root for provenance logging.")
    img.add_argument("--model", required=True, help="Chosen by Claude; see `models`.")
    img.add_argument("--effort", required=True, help="Chosen by Claude; must be supported by the model.")
    task = sub.add_parser("task", help="Run a very easy, fully specified edit.")
    task.add_argument("--instructions", required=True)
    task.add_argument("--cwd", required=True)
    task.add_argument("--allowed", action="append", default=[], help="Allowed path (repeatable).")
    task.add_argument("--check", help="Command Codex runs after the change, e.g. a single test.")
    task.add_argument("--model", required=True, help="Chosen by Claude; see `models`.")
    task.add_argument("--effort", required=True, help="Chosen by Claude; must be supported by the model.")
    rev = sub.add_parser("review", help="Read-only second-vendor review of files.")
    rev.add_argument("--cwd", required=True)
    rev.add_argument("--file", action="append", default=[], help="File in scope (repeatable).")
    rev.add_argument("--focus", default="bugs and rule violations")
    rev.add_argument("--max-findings", type=int, default=8)
    rev.add_argument("--model", required=True, help="Chosen by Claude; see `models`.")
    rev.add_argument("--effort", required=True, help="Chosen by Claude; must be supported by the model.")
    spec = sub.add_parser("run", help="Run a job from a JSON spec file (for workflow agents).")
    spec.add_argument("--spec", required=True)
    sub.add_parser("models", help="List the models and efforts Codex currently offers.")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    if args.cmd == "models":
        print(json.dumps({"ok": True, "models": available_models()}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "run":
        result = run_spec(args.spec)
    elif args.cmd == "review":
        result = run_review(args.cwd, args.file, args.focus, args.model, args.effort, args.max_findings)
    elif args.cmd == "image":
        result = generate_image(args.brief, args.out, args.aspect, args.background, args.style,
                                args.reference, args.project, args.model, args.effort)
    else:
        result = run_task(args.instructions, args.cwd, args.allowed, args.check, args.model, args.effort)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
