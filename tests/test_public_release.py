"""Public release safety: the export leaves out personal and third-party content, the uninstall removes only
project-brain's own entries, and plan_check flags HOW inside a PRD and FRs with no work item."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"


def export(out, *private):
    p = subprocess.run([sys.executable, str(SCRIPTS / "export_public.py"), "--out", str(out), "--skip-tests",
                        "--private", *private], capture_output=True, text=True, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


@unittest.skipUnless((SKILL / "public").is_dir() and (SKILL / ".git").exists(), "only in the author's source copy")
class Export(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pbexport-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_clean_copy_without_personal_or_third_party_files(self):
        out = self.tmp / "a"
        code, rep = export(out)
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["leaks"], [])
        self.assertEqual((out / "references" / "owner-profile.md").read_text(encoding="utf-8"),
                         (SKILL / "public" / "references" / "owner-profile.md").read_text(encoding="utf-8"))
        self.assertFalse((out / "modules" / "ui").exists())
        self.assertTrue((out / "LICENSE").exists() and (out / "README.md").exists())
        self.assertNotIn(".claude/skills/project-brain", "".join(
            l for l in (out / "agents" / "pb-verifier.md").read_text(encoding="utf-8").splitlines() if ":/" in l))

    def test_private_marker_blocks_the_export(self):
        code, rep = export(self.tmp / "b", "Laravel")
        self.assertEqual(code, 1)
        self.assertTrue(rep["leaks"])

    def test_refuses_non_empty_folder(self):
        (self.tmp / "c").mkdir()
        (self.tmp / "c" / "x.txt").write_text("x", encoding="utf-8")
        code, rep = export(self.tmp / "c")
        self.assertEqual(code, 1)
        self.assertIn("not empty", rep["error"])


class Uninstall(unittest.TestCase):
    def test_removes_only_project_brain_entries(self):
        spec = importlib.util.spec_from_file_location("pb_install", SCRIPTS / "install.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        home = Path(tempfile.mkdtemp(prefix="pbhome-"))
        try:
            (home / "agents").mkdir()
            (home / "agents" / "pb-verifier.md").write_text("x", encoding="utf-8")
            (home / "agents" / "mine.md").write_text("x", encoding="utf-8")
            settings = {"model": "opus", "hooks": {"PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "python", "args": ["/x/pb_hooks.py", "pre-bash"]},
                                              {"type": "command", "command": "echo mine"}]}],
                "Stop": [{"hooks": [{"type": "command", "command": "python", "args": ["/x/pb_hooks.py", "stop"]}]}]}}
            (home / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
            with mock.patch.object(mod, "HOME_CLAUDE", home), mock.patch("shutil.which", return_value=None):
                rep = mod.uninstall()
            after = json.loads((home / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(after["model"], "opus")
            self.assertEqual(after["hooks"], {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}]})
            self.assertEqual(rep["agents_removed"], ["pb-verifier.md"])
            self.assertTrue((home / "agents" / "mine.md").exists())
            self.assertTrue(list(home.glob("settings.json.bak-*")))
        finally:
            shutil.rmtree(home, ignore_errors=True)


class PrdBoundaries(unittest.TestCase):
    def test_tech_in_prd_and_fr_without_work_item(self):
        root = Path(tempfile.mkdtemp(prefix="pbprd-"))
        try:
            (root / "docs" / "product").mkdir(parents=True)
            (root / "docs" / "product" / "PRD.md").write_text(
                "# Product\n| FR-001 | Owner can create a branch |\n| FR-002 | Store orders in MySQL |\n", encoding="utf-8")
            (root / "docs" / "PROJECT_MAP.md").write_text("# Map\n| T1 | FR-001 |\n", encoding="utf-8")
            p = subprocess.run([sys.executable, str(SCRIPTS / "plan_check.py"), "--root", str(root), "--gate", "none"],
                               capture_output=True, text=True, encoding="utf-8")
            res = json.loads(p.stdout)
            self.assertEqual(res["traceability"]["fr_without_work_item"], ["FR-002"])
            self.assertTrue(any("MySQL" in x for x in res["advisory"]["prd_tech_leaks"]))
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
