#!/usr/bin/env python3
"""Minimal stdio MCP server exposing Codex delegation to Claude Code.

Tools: codex_generate_image, codex_easy_task. Both wrap codex_delegate.py so
the same quality rules apply whether Claude calls the MCP tool or the CLI.
No third-party dependencies.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codex_delegate as cd  # noqa: E402

TOOLS = [
    {
        "name": "codex_generate_image",
        "description": (
            "Generate ONE raster image asset (illustration, hero, icon, background, mockup) with Codex "
            "image generation and copy it to `out` inside the project. Cheap alternative to Higgsfield for "
            "still images. Write a precise brief (subject, composition, palette from the design system, "
            "background, aspect). Review the returned file before using it; convert to webp/avif."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["brief", "out", "model", "effort"],
            "properties": {
                "brief": {"type": "string", "description": "What to draw, composition, mood, details to include/avoid."},
                "out": {"type": "string", "description": "Absolute destination path inside the project (e.g. .../public/images/hero.png)."},
                "aspect": {"type": "string", "default": "1:1", "description": "e.g. 1:1, 16:9, 4:3, 9:16"},
                "background": {"type": "string", "default": "as described", "description": "transparent, flat #RRGGBB, scene..."},
                "style": {"type": "string", "description": "Style + palette tokens, e.g. 'flat vector, primary #0D5A40, canvas #EEF1F0'"},
                "reference": {"type": "string", "description": "Optional absolute path of a reference image."},
                "project": {"type": "string", "description": "Project root, for provenance in .project-brain/logs/DELEGATIONS.jsonl"},
                "model": {"type": "string", "description": "REQUIRED. Codex model chosen by Claude for this job (see codex_models / list below)."},
                "effort": {"type": "string", "description": "REQUIRED. Reasoning effort chosen by Claude; must be one the model supports."},
            },
        },
    },
    {
        "name": "codex_easy_task",
        "description": (
            "Delegate a VERY easy, fully specified edit to Codex (Claude picks model + effort): "
            "translations/strings, adding a column to an existing list, renaming a label, small CSS tweak, "
            "boilerplate following an existing example, a single test from a given pattern. Codex may only "
            "touch `allowed` paths; changes outside them are reported. Claude must review the diff after."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["instructions", "cwd", "allowed", "model", "effort"],
            "properties": {
                "instructions": {"type": "string", "description": "Exact task: files, expected result, example to copy, acceptance criterion."},
                "cwd": {"type": "string", "description": "Absolute project root."},
                "allowed": {"type": "array", "items": {"type": "string"}, "description": "Relative paths Codex may modify."},
                "check": {"type": "string", "description": "Optional command to run afterwards (one test, tsc, lint on a file)."},
                "model": {"type": "string", "description": "REQUIRED. Codex model chosen by Claude for this job (see codex_models / list below)."},
                "effort": {"type": "string", "description": "REQUIRED. Reasoning effort chosen by Claude; must be one the model supports."},
            },
        },
    },
]


def models_text() -> str:
    lines = [f"- {m['slug']}: {m['description']} efforts={m['efforts']}" for m in cd.available_models()]
    return "\n".join(lines) or "(model cache unreadable; call codex_models)"


TOOLS.append({
    "name": "codex_review",
    "description": (
        "Independent read-only review by Codex (another vendor) of the listed files: real bugs and rule "
        "violations at file:line. Works without git. Claude must verify each finding before acting."
    ),
    "inputSchema": {
        "type": "object",
        "required": ["cwd", "files", "focus", "model", "effort"],
        "properties": {
            "cwd": {"type": "string", "description": "Absolute project root."},
            "files": {"type": "array", "items": {"type": "string"}, "description": "Relative files in scope."},
            "focus": {"type": "string", "description": "What to look for (bugs, tenancy, security, docs rules...)."},
            "max_findings": {"type": "integer", "default": 8},
            "model": {"type": "string", "description": "REQUIRED. Codex model chosen by Claude."},
            "effort": {"type": "string", "description": "REQUIRED. Reasoning effort chosen by Claude."},
        },
    },
})

TOOLS.append({
    "name": "codex_models",
    "description": "List the Codex models and reasoning efforts available right now, so Claude can choose per task.",
    "inputSchema": {"type": "object", "properties": {}},
})


def reply(msg_id, result=None, error=None) -> None:
    payload = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def call_tool(name: str, args: dict) -> dict:
    if name == "codex_models":
        result = {"ok": True, "models": cd.available_models()}
    elif name == "codex_review":
        result = cd.run_review(args["cwd"], args.get("files", []), args.get("focus", ""),
                               args.get("model", ""), args.get("effort", ""), args.get("max_findings", 8))
    elif name == "codex_generate_image":
        result = cd.generate_image(
            args["brief"], args["out"], args.get("aspect", "1:1"), args.get("background", "as described"),
            args.get("style", ""), args.get("reference"), args.get("project"),
            args.get("model", ""), args.get("effort", ""),
        )
    elif name == "codex_easy_task":
        result = cd.run_task(args["instructions"], args["cwd"], args.get("allowed", []),
                             args.get("check"), args.get("model", ""), args.get("effort", ""))
    else:
        raise KeyError(name)
    return {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
        "isError": not result.get("ok", False),
    }


def main() -> None:
    # Windows pipes default to cp1252; MCP stdio is UTF-8 (Arabic briefs, em dashes).
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue  # batches/garbage are not used by Claude Code; ignore instead of crashing
        method, msg_id = msg.get("method"), msg.get("id")
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if msg_id is None or method is None:
            continue  # notifications and responses to our (non-existent) requests need no reply
        if method == "initialize":
            reply(msg_id, {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "codex-delegate", "version": "1.0.0"},
            })
        elif method == "tools/list":
            live = models_text()
            tools = [dict(t, description=t["description"] + "\nAvailable Codex models now:\n" + live)
                     if t["name"] != "codex_models" else t for t in TOOLS]
            reply(msg_id, {"tools": tools})
        elif method == "tools/call":
            try:
                reply(msg_id, call_tool(params.get("name", ""), params.get("arguments", {}) or {}))
            except KeyError as exc:
                reply(msg_id, error={"code": -32602, "message": f"Unknown tool or missing argument: {exc}"})
            except BaseException as exc:  # report, never crash the server (incl. SystemExit)
                reply(msg_id, {"content": [{"type": "text", "text": f"codex delegation failed: {exc}"}], "isError": True})
        elif method == "ping":
            reply(msg_id, {})
        else:
            reply(msg_id, error={"code": -32601, "message": f"Method not found: {method}"})


if __name__ == "__main__":
    main()
