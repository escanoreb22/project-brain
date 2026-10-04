"""Regression tests for project-brain scripts. Run: python -m unittest discover -s tests -v (from the skill dir)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
PY = sys.executable
DUP_FN = ("function totalPrice(items) {\n  let sum = 0;\n  for (const it of items) { sum += it.price * it.qty; }\n"
          "  const tax = sum * 0.2;\n  return Math.round((sum + tax) * 100) / 100;\n}\nmodule.exports = { totalPrice };\n")


def run(script, *args, stdin=None, cwd=None):
    proc = subprocess.run([PY, str(SCRIPTS / script), *args], input=stdin, capture_output=True, text=True,
                          encoding="utf-8", cwd=cwd)
    return proc.returncode, proc.stdout, proc.stderr


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pbt-"))
        (self.root / ".project-brain").mkdir()
        (self.root / "src").mkdir()
        (self.root / "lang").mkdir()
        (self.root / "src" / "a.js").write_text(DUP_FN, encoding="utf-8")
        (self.root / "lang" / "en.json").write_text('{"save":"Save","cancel":"Cancel","hi":"Hi :name"}', encoding="utf-8")
        (self.root / "lang" / "fr.json").write_text('{"save":"Enregistrer","cancel":"Annuler","hi":"Salut"}', encoding="utf-8")
        (self.root / "lang" / "ar.json").write_text('{"save":"حفظ","hi":"مرحبا :name"}', encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def hook(self, event, session="S1", tool="Write", file=None, command=None):
        data = {"session_id": session, "cwd": str(self.root), "tool_name": tool,
                "tool_input": {"file_path": str(file) if file else None, "command": command}}
        return run("pb_hooks.py", event, stdin=json.dumps(data))

    # ---- code_guard ----
    def test_code_guard_find_and_duplicate_gate(self):
        code, out, _ = run("code_guard.py", "find", "totalPrice", "--root", str(self.root))
        self.assertEqual(json.loads(out)["exact"][0]["file"], "src/a.js")
        (self.root / "src" / "b.js").write_text(DUP_FN, encoding="utf-8")
        code, out, _ = run("code_guard.py", "scan", "--root", str(self.root), "--changed", "src/b.js")
        self.assertEqual(code, 1)
        self.assertTrue(json.loads(out)["blocking"])

    def test_code_guard_renamed_copy(self):
        longer = ("function totalPrice(items, rate) {\n  let sum = 0;\n  for (const it of items) {\n    if (!it.active) { continue; }\n"
                  "    sum += it.price * it.qty;\n  }\n  const tax = sum * rate;\n  const total = sum + tax;\n"
                  "  return Math.round(total * 100) / 100;\n}\n")
        (self.root / "src" / "d.js").write_text(longer, encoding="utf-8")
        renamed = longer.replace("totalPrice", "grandTotal").replace("sum", "acc").replace("tax", "vat").replace("total", "result")
        (self.root / "src" / "c.js").write_text(renamed, encoding="utf-8")
        _, out, _ = run("code_guard.py", "scan", "--root", str(self.root), "--changed", "src/c.js")
        self.assertTrue(json.loads(out)["renamed_copies"])

    # ---- i18n ----
    def test_i18n_missing_key_and_placeholder(self):
        code, out, _ = run("i18n_check.py", "--root", str(self.root))
        report = json.loads(out)["problems"][0]
        self.assertEqual(code, 1)
        self.assertIn("cancel", report["missing_keys"]["ar"])
        self.assertTrue(any(p["key"] == "hi" and p["locale"] == "fr" for p in report["placeholder_mismatch"]))

    # ---- secrets ----
    def test_secret_scan_commit_mode_blocks_keys(self):
        (self.root / "id_rsa").write_text("-----BEGIN " + "OPENSSH PRIVATE KEY-----\nabc\n", encoding="utf-8")  # split: no key-shaped literal in the repo
        code, out, _ = run("secret_scan.py", "--root", str(self.root), "--files", "id_rsa")
        self.assertEqual(code, 1)
        code, _, _ = run("secret_scan.py", "--root", str(self.root))
        self.assertEqual(code, 0)  # working-tree audit only informs about local key files

    # ---- hooks ----
    def test_hook_post_edit_feeds_back_duplicates(self):
        (self.root / "src" / "b.js").write_text(DUP_FN, encoding="utf-8")
        code, _, err = self.hook("post-edit", file=self.root / "src" / "b.js")
        self.assertEqual(code, 2)
        self.assertIn("duplication", err)

    def test_hook_post_edit_i18n(self):
        code, _, err = self.hook("post-edit", file=self.root / "lang" / "ar.json")
        self.assertEqual(code, 2)
        self.assertIn("i18n_check", err)

    def test_hook_lock_between_sessions(self):
        target = self.root / "src" / "a.js"
        self.hook("pre-edit", session="S1", tool="Edit", file=target)
        _, out, _ = self.hook("pre-edit", session="S2", tool="Edit", file=target)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
        _, out, _ = self.hook("pre-edit", session="S1", tool="Edit", file=target)
        self.assertEqual(out.strip(), "")

    def test_hook_pre_bash_gate(self):
        _, out, _ = self.hook("pre-bash", tool="Bash", command="git push origin main")
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask")
        _, out, _ = self.hook("pre-bash", tool="Bash", command="npm test")
        self.assertEqual(out.strip(), "")

    def test_hook_stop_requires_handoff(self):
        self.hook("pre-edit", session="S1", tool="Edit", file=self.root / "src" / "a.js")
        _, out, _ = self.hook("stop", session="S1", tool="Stop")
        self.assertEqual(json.loads(out)["decision"], "block")
        time.sleep(0.05)
        (self.root / ".project-brain" / "HANDOFF.md").write_text("# handoff\n", encoding="utf-8")
        _, out, _ = self.hook("stop", session="S1", tool="Stop")
        self.assertEqual(out.strip(), "")

    def test_hooks_ignore_non_project_brain_repos(self):
        shutil.rmtree(self.root / ".project-brain")
        (self.root / "src" / "b.js").write_text(DUP_FN, encoding="utf-8")
        code, _, _ = self.hook("post-edit", file=self.root / "src" / "b.js")
        self.assertEqual(code, 0)

    # ---- project_brain + codex_delegate ----
    def test_project_brain_lite_init_validate(self):
        shutil.rmtree(self.root / ".project-brain")
        self.assertEqual(run("project_brain.py", "init", "--lite", "--project-name", "T", cwd=self.root)[0], 0)
        self.assertEqual(run("project_brain.py", "validate", cwd=self.root)[0], 0)

    def test_codex_delegate_rejects_missing_choice(self):
        sys.path.insert(0, str(SCRIPTS))
        import codex_delegate
        self.assertIn("required", codex_delegate.check_choice("", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
