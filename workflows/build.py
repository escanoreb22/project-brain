"""Inject the shared snippets into every workflow and validate them.

Each workflow marks where snippets go with:
  //@@KNOWLEDGE@@   ... replaced by _knowledge.snippet.js
  //@@CODEX@@       ... replaced by _codex-lane.snippet.js
Previously injected blocks (between '// ---- X' and '// ---- end X ----') are refreshed in place.
Run after editing a snippet:  python build.py
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNIPPETS = {
    "KNOWLEDGE": ("// ---- Knowledge routing", "// ---- end knowledge ----", HERE / "_knowledge.snippet.js"),
    "CODEX": ("// ---- Codex lane", "// ---- end Codex lane ----", HERE / "_codex-lane.snippet.js"),
}
FORBIDDEN = ("->",)  # the Workflow approval filter rejects scripts containing it
PB_POSIX = HERE.parent.as_posix()  # this skill's real location on THIS machine (portability)
PB_PATH = re.compile(r"[A-Za-z]:/[^'\"`\s]*?/\.claude/skills/project-brain|/(?:home|Users)/[^'\"`\s]*?/\.claude/skills/project-brain"
                     r"|~/\.claude/skills/project-brain")  # ~ form = the public copy before install


def localize(text: str) -> str:
    return PB_PATH.sub(PB_POSIX, text)


def refresh(text: str) -> str:
    for key, (start, end, path) in SNIPPETS.items():
        body = path.read_text(encoding="utf-8").strip()
        marker = f"//@@{key}@@"
        if marker in text:
            text = text.replace(marker, body)
        elif start in text and end in text:
            i, j = text.index(start), text.index(end) + len(end)
            text = text[:i] + body + text[j:]
    return text


def main() -> int:
    for snippet in HERE.glob("_*.snippet.js"):
        snippet.write_text(localize(snippet.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")
    bad = 0
    for wf in sorted(HERE.glob("*.js")):
        if wf.name.startswith("_"):
            continue
        text = localize(refresh(wf.read_text(encoding="utf-8")))
        wf.write_text(text, encoding="utf-8", newline="\n")
        problems = [f for f in FORBIDDEN if f in text]
        problems += [f"non-ASCII U+{ord(c):04X}" for c in sorted(set(text)) if ord(c) > 126]
        problems += [f"control 0x{ord(c):02X}" for c in sorted(set(text)) if ord(c) < 32 and c not in "\n\t"]
        status = "OK" if not problems else "FIX: " + ", ".join(problems)
        bad += bool(problems)
        print(f"{wf.name}: {status}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
