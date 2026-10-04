"""Precision regressions found by the re-verification pass (false blocks and missed patterns)."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def scan(rel, text, script="vuln_scan.py", extra=()):
    root = Path(tempfile.mkdtemp(prefix="pbp-"))
    try:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
        args = ["--root", str(root), *extra]
        if script == "vuln_scan.py":
            args += ["--changed", rel]
        p = subprocess.run([sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True, encoding="utf-8")
        return p.returncode, json.loads(p.stdout)
    finally:
        shutil.rmtree(root, ignore_errors=True)


class Precision(unittest.TestCase):
    def test_regexp_exec_is_not_command_injection(self):
        code, out = scan("src/a.ts", "const m = /x(\\d+)/.exec(a + b);\nconst n = re.exec(`${a}`);\n")
        self.assertEqual(code, 0, out["findings"])

    def test_eval_in_string_and_author_key_not_flagged(self):
        code, out = scan("src/b.ts", "const s = 'please do not eval(x)';\nlocalStorage.setItem('author', name);\n")
        self.assertEqual(code, 0, out["findings"])

    def test_service_calls_with_request_are_not_ssrf(self):
        code, out = scan("app/S.php", "<?php\n$x = $this->cache->get($request->input('k'));\n$y = $repo->post($request->validated());\n")
        self.assertEqual(code, 0, out["findings"])

    def test_missed_patterns_now_detected(self):
        php = ("<?php\n"
               "$a = Process::run(\"git log \" . $request->input('b'));\n"
               "$b = DB::raw($request->input('expr'));\n"
               "$c = User::orderBy($request->input('sort'))->get();\n"
               "$d = $pdo->query(\"select * from t where id = $request->id\");\n")
        code, out = scan("app/M.php", php)
        cwes = [f["cwe"] for f in out["findings"] if f["severity"] == "high"]
        self.assertEqual(code, 1)
        self.assertGreaterEqual(cwes.count("CWE-89"), 3, out["findings"])
        self.assertIn("CWE-78", cwes)

    def test_i18n_i18next_plural_suffix_and_urls(self):
        root = Path(tempfile.mkdtemp(prefix="pbi-"))
        try:
            (root / "locales" / "en").mkdir(parents=True)
            (root / "locales" / "ar").mkdir(parents=True)
            (root / "locales" / "en" / "c.json").write_text('{"item_one":"1 item","item_other":"{{count}} items","url":"see https://x.y"}', encoding="utf-8")
            (root / "locales" / "ar" / "c.json").write_text('{"item_zero":"لا","item_one":"واحد","item_two":"اثنان","item_few":"{{count}}","item_many":"{{count}}","item_other":"{{count}}","url":"انظر https://x.y"}', encoding="utf-8")
            p = subprocess.run([sys.executable, str(SCRIPTS / "i18n_check.py"), "--root", str(root)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(p.returncode, 0, p.stdout)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_empty_vite_placeholder_in_example_not_blocked(self):
        root = Path(tempfile.mkdtemp(prefix="pbs-"))
        try:
            (root / ".env.example").write_text("VITE_APP_TOKEN=\nAPP_NAME=demo\n", encoding="utf-8")
            p = subprocess.run([sys.executable, str(SCRIPTS / "secret_scan.py"), "--root", str(root), "--files", ".env.example"],
                               capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(p.returncode, 0, p.stdout)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
