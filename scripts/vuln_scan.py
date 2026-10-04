#!/usr/bin/env python3
"""Deterministic vulnerability pattern scanner for the owner's 14 weakness classes (no LLM).

  python vuln_scan.py [--root DIR] [--changed FILES...]

Severity: high = a dangerous sink with request/user data on the same line or a construct that is never safe
(eval, md5 passwords, tokens in localStorage, CORS * with credentials) -> exit 1.
review = a sink that must be proven safe by a human/agent (raw SQL with variables, shell calls, innerHTML, ...).
Rules map to references/security-baseline.md. Test and vendor directories are skipped.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKIP = {"node_modules", "vendor", "storage", "dist", "build", "graphify-out", "coverage", "__pycache__", "bootstrap",
        "tests", "test", "__tests__", "spec", "public"}
EXTS = {".php", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".vue", ".dart", ".py"}
USER = r"(\$request|\$_(GET|POST|REQUEST|COOKIE|SERVER)|request\(\)|->input\(|->query\(|req\.(body|query|params)|\$input)"

RULES = [
    # (cwe, severity, languages, pattern, message)
    ("CWE-78", "high", "php", rf"\b(exec|shell_exec|system|passthru|popen|proc_open)\s*\(.*{USER}", "shell call with request data"),
    ("CWE-78", "review", "php", r"\b(shell_exec|system|passthru|popen)\s*\(\s*[\"'][^\"']*\$|\b(exec|shell_exec|system|passthru)\s*\([^)]*\.\s*\$", "shell call built from variables: use Process::run([...]) array form"),
    ("CWE-78", "high", "php", r"^[^'\"]*(=|return|echo)\s*`[^`]*\$[^`]*`", "PHP backtick shell execution with a variable"),
    ("CWE-78", "high", "js", r"(?:(?<![\w.$])|(?<=child_process\.)|(?<=cp\.))(exec|execSync)\s*\(\s*(`[^`]*\$\{|[^)]*\+\s*\w)", "child_process exec with interpolated command: use execFile/spawn with args"),
    ("CWE-78", "high", "php", rf"Process::(run|start|pipe|command)\s*\(\s*(\"[^\"]*{USER}|['\"][^'\"]*['\"]\s*\.\s*{USER})", "Process with a string command runs a shell: use the array form Process::run([...])"),
    ("CWE-78", "review", "php", r"Process::(run|start|pipe|command)\s*\(\s*(\"[^\"]*\$|['\"][^'\"]*['\"]\s*\.)", "Process with a string command built from variables: use the array form"),
    ("CWE-77", "review", "js", r"\bspawn(Sync)?\s*\([^)]*shell\s*:\s*true", "spawn with shell:true"),
    ("CWE-94", "high", "php", r"(?<![\w>$])eval\s*\(|\bcreate_function\s*\(|preg_replace\s*\(\s*['\"][^'\"]*/e['\"]", "dynamic code evaluation"),
    ("CWE-94", "high", "php", rf"\bunserialize\s*\(.*{USER}", "unserialize on user data: use json_decode"),
    ("CWE-94", "review", "php", r"\bunserialize\s*\((?![^)]*allowed_classes)", "unserialize without allowed_classes=false"),
    ("CWE-94", "review", "php", r"\b(include|require)(_once)?\s*\(?\s*\$", "include/require of a variable path"),
    ("CWE-94", "high", "js", r"(?<![\w.$])eval\s*\(|\bnew\s+Function\s*\(|setTimeout\s*\(\s*['\"`]|setInterval\s*\(\s*['\"`]", "dynamic code evaluation"),
    ("CWE-918", "high", "php", rf"(Http::(get|post|put|patch|delete|head)|Http::\w+\([^)]*\)->(get|post|put|patch|delete)|\$(client|http|guzzle)\w*->(get|post|request)|curl_init|file_get_contents|fopen|get_headers)\s*\(\s*(\(string\)\s*)?{USER}", "outbound request to a user-supplied URL: allowlist + private-IP block + no redirects"),
    ("CWE-918", "high", "js", r"\b(fetch|axios\.(get|post|request)|got|request)\s*\(\s*(req\.(body|query|params)|`\$\{req\.)", "outbound request to a user-supplied URL"),
    ("CWE-89", "high", "php", rf"(whereRaw|selectRaw|orderByRaw|havingRaw|groupByRaw|DB::raw|DB::select|DB::statement|DB::unprepared)\s*\(\s*(\"[^\"]*{USER}|['\"][^'\"]*['\"]\s*\.\s*{USER})", "request data inside the raw SQL string: use ? bindings"),
    ("CWE-89", "review", "php", r"(whereRaw|selectRaw|orderByRaw|havingRaw|groupByRaw|DB::raw|DB::select|DB::statement|DB::unprepared|DB::insert|DB::update|DB::delete)\s*\(\s*\"[^\"]*\$", "variable interpolated into raw SQL: prove it comes from an allowlist, else use bindings"),
    ("CWE-89", "review", "php", r"(whereRaw|selectRaw|orderByRaw|havingRaw|DB::raw|DB::select|DB::statement|DB::unprepared)\s*\([^;]*['\"]\s*\.\s*\$", "string concatenation into raw SQL: prove allowlisted, else use bindings"),
    ("CWE-89", "high", "php", rf"(->|::)(orderBy|orderByDesc|groupBy|orderByRaw|whereRaw|selectRaw|havingRaw|groupByRaw)\s*\(\s*{USER}", "request data as column/raw expression: map through an allowlist or bind"),
    ("CWE-89", "high", "php", rf"DB::(raw|select|statement|unprepared)\s*\(\s*{USER}", "request data as the raw SQL: use ? bindings"),
    ("CWE-89", "high", "php", rf"(->query|->exec|->prepare|mysqli_query|mysql_query)\s*\(\s*(\"[^\"]*{USER}|['\"][^'\"]*['\"]\s*\.\s*{USER}|{USER})", "PDO/mysqli query built from request data: use prepared statements with bound parameters"),
    ("CWE-89", "high", "js", r"\.(query|raw|execute)\s*\(\s*`[^`]*\$\{", "template literal in SQL: use parameters"),
    ("CWE-79", "review", "php", r"\{!!\s*(?!\s*(csrf_field|method_field|\$__env|Vite::|vite)).+?!!\}", "unescaped Blade output: only for sanitized HTML"),
    ("CWE-79", "review", "js", r"dangerouslySetInnerHTML\s*=\s*\{\{\s*__html\s*:\s*(?!.*(DOMPurify|sanitize|purify))", "dangerouslySetInnerHTML without sanitization"),
    ("CWE-79", "review", "js", r"\.innerHTML\s*=|\bv-html\s*=|\.outerHTML\s*=|document\.write\s*\(", "raw HTML sink"),
    ("CWE-79", "review", "js", r"href\s*=\s*\{\s*(?!['\"`])[\w.]*(url|link|href)\w*\s*\}", "user URL in href: allow only http(s)/mailto"),
    ("CWE-501", "high", "php", r"(::create|->fill|->update|->forceFill|::firstOrCreate|::updateOrCreate)\s*\(\s*\$request->all\(\)", "request->all() into a model: use validated() / DTO"),
    ("CWE-501", "review", "php", r"\$guarded\s*=\s*\[\s*\]", "$guarded = [] (mass assignment open)"),
    ("CWE-287", "review", "php", r"\$\w*(token|secret|signature|otp|hash|code)\w*\s*(==|!=)\s*[^=]", "secret compared with ==: use hash_equals"),
    ("CWE-287", "high", "php", r"\b(md5|sha1)\s*\(\s*\$\w*pass", "weak password hashing: use Hash::make"),
    ("CWE-287", "high", "js", r"localStorage\.setItem\s*\(\s*['\"`][^'\"`]*\b(token|jwt|access_?token|refresh_?token|auth_?token|session_?id)\b", "auth token in localStorage (owner rule: HttpOnly cookies)"),
    ("CWE-287", "high", "js", r"algorithms?\s*:\s*\[?\s*['\"]none['\"]", "JWT alg none"),
    ("CWE-287", "review", "js", r"jwt\.verify\s*\((?![^)]*algorithms)", "jwt.verify without pinned algorithms"),
    ("CWE-120", "review", "js", r"Buffer\.allocUnsafe|new\s+Buffer\s*\(", "unsafe Buffer allocation"),
    ("CWE-269", "review", "php", r"->(assignRole|givePermissionTo|syncRoles|syncPermissions)\s*\(.*\$request", "role/permission from the request: check the actor may grant it"),
]
STRINGS = re.compile(r"""('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")""")
FILE_RULES = [
    # (cwe, severity, path regex, must-contain regex, must-NOT-contain regex, message)
    ("CWE-384", "review", r"\.php$", r"Auth::(login|loginUsingId|attempt)\s*\(", r"session\(\)->regenerate|->session\(\)->regenerate|regenerate\(\)", "custom login without session regeneration"),
    ("CWE-862", "review", r"Http/Controllers/.*\.php$", r"public function (store|update|destroy|delete|approve|confirm|export)\s*\(", r"authorize|Gate::|->can\(|can:|policy|Policy", "controller write actions with no authorization call in the file"),
    ("CWE-400", "review", r"\.php$", r"Http::(get|post|put|patch|delete|send|withHeaders|withToken|withBasicAuth|acceptJson|asForm|asJson|baseUrl|retry|pool)\s*\(|GuzzleHttp\\Client\b",r"->timeout\s*\(|->connectTimeout\s*\(|['\"](timeout|connect_timeout)['\"]\s*=>", "external HTTP call with no timeout in the file (architecture fitness rule: every external call has a timeout)"),
    ("CORS", "high", r"config/cors\.php$", r"'allowed_origins'\s*=>\s*\[\s*'\*'", r"'supports_credentials'\s*=>\s*false", "CORS * with credentials"),
]


def lang(path: Path) -> str:
    return "php" if path.suffix == ".php" else "js" if path.suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".vue"} else path.suffix


def walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP and not d.startswith(".")]
        for name in filenames:
            path = Path(dirpath, name)
            if path.suffix in EXTS and not name.endswith((".min.js", ".d.ts")):
                yield path


def scan_file(root: Path, path: Path) -> list[dict]:
    rel = path.relative_to(root).as_posix()
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    out = []
    kind = lang(path)
    for no, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("//", "#", "*", "/*")) or len(stripped) > 2000:
            continue
        code_only = STRINGS.sub('""', line) if kind == "js" else line
        for cwe, sev, lng, pattern, msg in RULES:
            subject = code_only if (lng == "js" and cwe == "CWE-94") else line
            if lng == kind and re.search(pattern, subject):
                out.append({"cwe": cwe, "severity": sev, "file": rel, "line": no, "rule": msg, "code": stripped[:160]})
    for cwe, sev, path_re, must, must_not, msg in FILE_RULES:
        if re.search(path_re, rel) and re.search(must, text) and not re.search(must_not, text):
            out.append({"cwe": cwe, "severity": sev, "file": rel, "line": 0, "rule": msg, "code": ""})
    return out


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--changed", nargs="*", default=[])
    ap.add_argument("--exclude", nargs="*", default=[], help="Extra relative dirs to skip (e.g. asstes tools).")
    args = ap.parse_args()
    SKIP.update(e.strip("/").split("/")[-1] for e in args.exclude)
    root = Path(args.root).resolve()
    if args.changed:
        files = [(root / c) for c in args.changed if (root / c).is_file() and (root / c).suffix in EXTS
                 or c.endswith("config/cors.php")]
    else:
        files = list(walk(root))
    findings = [f for p in files for f in scan_file(root, p)]
    high = [f for f in findings if f["severity"] == "high"]
    print(json.dumps({"root": str(root), "files_scanned": len(files), "high": len(high),
                      "review": len(findings) - len(high), "findings": findings[:300],
                      "advice": "high: fix before finishing (references/security-baseline.md). review: prove safe (file:line + test) or fix."
                      if findings else "No pattern findings. Still walk the 14 classes for logic flaws (authorization, trust boundaries)."},
                     ensure_ascii=False, indent=2))
    return 1 if high else 0


if __name__ == "__main__":
    sys.exit(main())
