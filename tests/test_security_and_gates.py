"""vuln_scan rules (owner's 14 CWE classes) and the 'only new problems block' hook contract."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
PY = sys.executable

VULNERABLE_PHP = """<?php
class X {
  function a($request) { return shell_exec('ping ' . $request->input('host')); }
  function b($request) { return DB::select("select * from users where id = {$request->id}"); }
  function c($request) { return Http::get($request->input('url')); }
  function d($request) { eval($request->code); }
  function e($request) { return User::create($request->all()); }
  function f($request) { return Post::query()->orderBy($request->input('sort'))->get(); }
  function g($p) { return md5($password); }
}
"""
SAFE_PHP = """<?php
class Y {
  function a($request) { return Process::run(['ping', '-c', '1', $request->validated()['host']]); }
  function b($request) { return DB::select('select * from users where id = ?', [$request->id]); }
  function c() { return Http::post('https://oauth2.googleapis.com/token', ['code' => request('code')]); }
  function e($request) { return User::create($request->validated()); }
  function f($request) { return Post::query()->orderBy(self::SORTS[$request->input('sort')] ?? 'id')->get(); }
}
"""
VULNERABLE_TSX = """export function A({ html, token }: any) {
  localStorage.setItem('auth_token', token);
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}
const r = eval(input);
"""
SAFE_TSX = """export function B() { return page.$eval('#x', (e) => e.textContent); }"""


def run(script, *args, stdin=None):
    p = subprocess.run([PY, str(SCRIPTS / script), *args], input=stdin, capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


class VulnScan(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pbv-"))
        (self.root / "app").mkdir()
        (self.root / "src").mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def scan(self, rel, text):
        (self.root / rel).write_text(text, encoding="utf-8")
        code, out, _ = run("vuln_scan.py", "--root", str(self.root), "--changed", rel)
        return code, json.loads(out)

    def test_detects_owner_classes_in_php(self):
        code, out = self.scan("app/X.php", VULNERABLE_PHP)
        cwes = {f["cwe"] for f in out["findings"] if f["severity"] == "high"}
        self.assertEqual(code, 1)
        for cwe in ("CWE-78", "CWE-89", "CWE-918", "CWE-94", "CWE-501", "CWE-287"):
            self.assertIn(cwe, cwes, f"{cwe} not detected")

    def test_safe_php_is_not_blocked(self):
        code, out = self.scan("app/Y.php", SAFE_PHP)
        self.assertEqual(code, 0, out["findings"])

    def test_detects_js_classes(self):
        code, out = self.scan("src/A.tsx", VULNERABLE_TSX)
        cwes = {f["cwe"] for f in out["findings"]}
        self.assertEqual(code, 1)
        self.assertTrue({"CWE-287", "CWE-79", "CWE-94"} <= cwes)

    def test_playwright_eval_is_not_eval(self):
        code, out = self.scan("src/B.tsx", SAFE_TSX)
        self.assertEqual(code, 0, out["findings"])


class HookOnlyNewProblems(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pbh-"))
        (self.root / ".project-brain").mkdir()
        (self.root / "app").mkdir()
        self.file = self.root / "app" / "Legacy.php"
        self.file.write_text("<?php\nfunction old($request) { eval($request->code); }\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def hook(self, event, file, session="S1"):
        data = {"session_id": session, "cwd": str(self.root), "tool_name": "Edit", "tool_input": {"file_path": str(file)}}
        return run("pb_hooks.py", event, stdin=json.dumps(data))

    def test_pre_existing_problem_does_not_block_an_unrelated_edit(self):
        self.hook("pre-edit", self.file)
        self.file.write_text(self.file.read_text(encoding="utf-8") + "function fine() { return 1; }\n", encoding="utf-8")
        code, _, err = self.hook("post-edit", self.file)
        self.assertEqual(code, 0, err)

    def test_new_problem_blocks(self):
        self.hook("pre-edit", self.file)
        self.file.write_text(self.file.read_text(encoding="utf-8") + "function bad($request) { return shell_exec('x ' . $request->input('h')); }\n", encoding="utf-8")
        code, _, err = self.hook("post-edit", self.file)
        self.assertEqual(code, 2)
        self.assertIn("vuln_scan", err)

    def test_project_brain_files_are_never_locked(self):
        handoff = self.root / ".project-brain" / "HANDOFF.md"
        handoff.write_text("# h\n", encoding="utf-8")
        self.hook("pre-edit", handoff, session="S1")
        _, out, _ = self.hook("pre-edit", handoff, session="S2")
        self.assertEqual(out.strip(), "")


class PbCli(unittest.TestCase):
    def test_start_then_finish_gates(self):
        root = Path(tempfile.mkdtemp(prefix="pbc-"))
        try:
            (root / "src").mkdir()
            body = "export function total(items) {\n  let s = 0;\n  for (const i of items) { s += i.p * i.q; }\n  return s;\n}\n"
            (root / "src" / "a.js").write_text(body, encoding="utf-8")
            code, out, _ = run("pb.py", "start", "--root", str(root), "--name", "T")
            report = json.loads(out)
            self.assertEqual(code, 0)
            self.assertEqual(report["agents_md"], "written")
            self.assertTrue((root / ".project-brain").is_dir())
            (root / "src" / "b.js").write_text(body, encoding="utf-8")
            code, out, _ = run("pb.py", "finish", "--root", str(root), "--changed", "src/b.js")
            self.assertEqual(code, 1)
            self.assertIn("code_guard", json.loads(out)["failed_gates"])
            (root / "src" / "b.js").write_text("export const ok = 1;\n", encoding="utf-8")
            code, out, _ = run("pb.py", "finish", "--root", str(root), "--changed", "src/b.js")
            self.assertEqual(code, 0, out)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
