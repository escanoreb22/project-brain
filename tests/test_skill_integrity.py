"""Static integrity checks for the skill itself (no network, no LLM).

Catches the skill's own hallucination risks: references to files that do not exist, workflows that were not
rebuilt, forbidden characters, reference files missing their mandatory sections, installed agents out of sync.
"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
DEPRECATED = {"planner-protocol.md", "coder-protocol.md", "designer-protocol.md"}
REF_PATTERN = re.compile(r"(?<![\w/.-])((?:references|scripts|workflows|modules|agents|assets|schemas|tests)/[\w./-]+\.(?:md|py|js|yaml|json|txt))")
TEXT_FILES = [p for p in SKILL.rglob("*") if p.suffix in {".md", ".js", ".py"} and ".git" not in p.parts
              and "apple-hig" not in p.parts and "brain-graph" not in p.parts and "code-review" not in p.parts
              and p.name not in DEPRECATED]


def mentioned_paths():
    for f in TEXT_FILES:
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in REF_PATTERN.finditer(text):
            yield f, m.group(1).rstrip(".")


class SkillIntegrity(unittest.TestCase):
    def test_every_mentioned_skill_path_exists(self):
        optional = lambda p: p.startswith("modules/") and not (SKILL / "/".join(p.split("/")[:2])).exists()
        missing = sorted({(f.relative_to(SKILL).as_posix(), p) for f, p in mentioned_paths()
                          if not (SKILL / p).exists() and not (f.parent / p).exists() and "<" not in p and "*" not in p
                          and not optional(p)})  # bundled modules are optional (public copy ships without them)
        self.assertEqual(missing, [], f"files referenced but missing: {missing}")

    def test_no_live_links_to_deprecated_references(self):
        bad = sorted({f.relative_to(SKILL).as_posix() for f, p in mentioned_paths() if Path(p).name in DEPRECATED})
        self.assertEqual(bad, [], f"still pointing at merged references: {bad}")

    def test_references_have_mandatory_sections(self):
        exempt = DEPRECATED | {"owner-profile.md", "runtime-adapters.md", "research-policy.md", "memory-protocol.md",
                               "tracker-protocol.md", "quality-gates.md", "security-protocol.md", "idea-protocol.md",
                               "deploy-protocol.md"}
        lacking = [p.name for p in (SKILL / "references").glob("*.md") if p.name not in exempt and not (
            "## Red flags" in (t := p.read_text(encoding="utf-8")) and "## How project-brain uses this" in t)]
        self.assertEqual(lacking, [], f"references missing Red flags / How project-brain uses this: {lacking}")

    def test_workflows_built_and_clean(self):
        res = subprocess.run([sys.executable, str(SKILL / "workflows" / "build.py")], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stdout)
        for wf in (SKILL / "workflows").glob("[a-z]*.js"):
            text = wf.read_text(encoding="utf-8")
            self.assertNotIn("//@@", text, f"{wf.name}: unexpanded snippet marker")
            self.assertTrue(text.startswith("export const meta"), f"{wf.name}: meta must come first")
            self.assertIn("function spend(", text, f"{wf.name}: budget guard missing")

    def test_workflow_syntax(self):
        node = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if node.returncode != 0:
            self.skipTest("node not installed")
        checker = ("const s=require('fs').readFileSync(process.argv[1],'utf8').replace(/^export const meta/m,'const meta');"
                   "new (Object.getPrototypeOf(async function(){}).constructor)('args','agent','parallel','pipeline','phase','log','workflow','budget',s)")
        for wf in (SKILL / "workflows").glob("[a-z]*.js"):
            res = subprocess.run(["node", "-e", checker, str(wf)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"{wf.name}: {res.stderr[-300:]}")

    def test_skill_frontmatter(self):
        head = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        self.assertIn("name: project-brain", head)
        desc = re.search(r"description: (.+)", head).group(1)
        self.assertLess(len(desc), 1536, "description over the listing cap")

    def test_installed_agents_in_sync(self):
        installed = Path.home() / ".claude" / "agents"
        if not any(installed.glob("pb-*.md")):
            self.skipTest("agents not installed on this machine (run scripts/install.py)")
        for src in (SKILL / "agents").glob("pb-*.md"):
            dst = installed / src.name
            self.assertTrue(dst.exists(), f"{src.name} not installed: run scripts/install.py")
            norm = lambda s: re.sub(r"\S*/\.claude/skills/project-brain", "PB", s)
            self.assertEqual(norm(src.read_text(encoding="utf-8")), norm(dst.read_text(encoding="utf-8")),
                             f"{src.name} differs from the installed copy: run scripts/install.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)
