#!/usr/bin/env python3
"""Planning completeness checker for the system engineering method (no LLM).

  python plan_check.py [--root DIR] [--docs DIR ...] [--gate data|product|engineering|implementation|production|full|none]

Scans the project's planning docs (docs/ + root files) and reports:
  steps         : the 20 steps of references/system-engineering-method.md section B
  data_gate     : the 35 Data Architecture Gate items (section C)
  gates         : the owner's 4 delivery gates (section G): product, engineering, implementation, production
  traceability  : FR/BR ids that no acceptance test names; FR ids with no work item (project map / backlog)
  advisory      : technical decisions written inside the PRD (PRD = WHAT + WHY; HOW goes to architecture/ADR)
  readiness     : production readiness checklist ticks (a tick counts only with "evidence:" on the line)
Exit 1 when the selected gate fails (default: data). Gates are cumulative: production includes implementation, etc.
It checks presence and IDs, not quality: a reviewer still reads the docs.
Files that still carry the "<!-- pb:template" marker (unfilled scaffolds from assets/production-docs) are ignored.
An item written as "N/A - reason" counts as answered.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DOC_EXTS = {".md", ".yaml", ".yml", ".json", ".txt"}
SKIP = {"node_modules", "vendor", ".git", "graphify-out", "storage", "dist", "build", "public"}
TEMPLATE_MARK = "<!-- pb:template"

# step id -> (label, list of regexes; all must match somewhere in the doc set)
STEPS = {
    "01": ("Product definition", [r"^#+.*(product|overview|vision|problem|goals?)\b"]),
    "02": ("Functional requirements", [r"\bFR-\d+"]),
    "03": ("Business rules", [r"\bBR-\d+"]),
    "04": ("Non-functional requirements (measurable)", [r"\bNFR-\d+[^\n]*\d+\s*(ms|%|s\b|sec|min|minutes|h\b|hours|days|rps|req)"]),
    "05": ("Domain model", [r"domain model", r"\bentit(y|ies)\b"]),
    "06": ("Bounded contexts + data ownership", [r"bounded context|^#+.*contexts?\b", r"\bown(s|er|ership)\b"]),
    "07": ("System architecture", [r"^#+.*architecture"]),
    "08": ("Data model (conceptual/logical)", [r"(conceptual|logical) (data )?model|data architecture"]),
    "09": ("Data dictionary", [r"^\|\s*(field|column)\s*\|.*\|\s*type\s*\|.*null"]),
    "10": ("API contracts + error taxonomy", [r"openapi|^#+.*api", r"\b409\b", r"\b422\b"]),
    "11": ("Auth / RBAC / security", [r"authori[sz]ation matrix|\brbac\b|permission matrix", r"threat model|security"]),
    "12": ("State machines", [r"state machine|transitions?", r"\w+\s*(->|→)\s*\w+|^\|\s*from\s*\|\s*to\s*\|"]),
    "13": ("Events / queues", [r"\b(outbox|queue|event)s?\b"]),
    "14": ("Failure handling", [r"\btimeouts?\b", r"\bretr(y|ies)\b"]),
    "15": ("Testing strategy", [r"^#+.*test"]),
    "16": ("Observability", [r"observability|monitoring|alerts?\b"]),
    "17": ("Deployment", [r"^#+.*deploy"]),
    "18": ("Backup / recovery (RPO/RTO + restore test)", [r"\bRPO\b", r"\bRTO\b", r"restore"]),
    "19": ("Migration strategy", [r"migrations?", r"expand|contract|backfill|backward[- ]compatible"]),
    "20": ("Operations / runbook", [r"runbook|incident"]),
    "ADR": ("Architecture decision records", [r"\bADR-\d+"]),
}

# 35 Data Architecture Gate items -> alias regexes (any one answers it)
GATE = [
    ("01 Domain entities", r"\bentit(y|ies)\b"),
    ("02 Relationships", r"relationships?|\b1:N\b|\bN:N\b|one-to-many|many-to-many"),
    ("03 Ownership", r"\bowner(ship)?\b|owning context"),
    ("04 Cardinality", r"cardinality|expected (rows|volume)|rows? (per|in) (year|month)"),
    ("05 Primary/public IDs", r"public_id|ulid|uuid"),
    ("06 Foreign keys", r"foreign key|\bFK\b"),
    ("07 Nullability", r"nullab|not null"),
    ("08 Uniqueness", r"\bunique\b"),
    ("09 Business invariants", r"invariants?"),
    ("10 Lifecycle/status", r"lifecycle|\bstatus\b"),
    ("11 State transitions", r"transitions?"),
    ("12 Mutable/immutable", r"immutable|append-only"),
    ("13 Deletion strategy", r"soft delete|hard delete|deletion strategy|anonymi[sz]"),
    ("14 Historical snapshots", r"snapshot"),
    ("15 Normalization", r"normali[sz]|\b3NF\b"),
    ("16 Denormalization", r"denormali[sz]"),
    ("17 Access patterns", r"access patterns?"),
    ("18 Indexes", r"\bindex(es)?\b"),
    ("19 Data volume", r"data volume|growth|million|\b\d+\s*[MK]\s*rows"),
    ("20 Transactions", r"transaction boundar|\btransactions?\b"),
    ("21 Concurrency", r"concurrency|for update|optimistic|\bversion\b column|locking"),
    ("22 Idempotency", r"idempoten"),
    ("23 Money representation", r"amount_minor|minor units|\bcents\b|decimal\(\d+,\s*\d+\)"),
    ("24 Date/time strategy", r"\bUTC\b"),
    ("25 Multi-tenancy", r"tenant"),
    ("26 Audit logs", r"audit"),
    ("27 PII classification", r"\bPII\b|confidential|restricted|data classification"),
    ("28 Encryption", r"encrypt|hashed"),
    ("29 Retention", r"retention"),
    ("30 Archiving", r"archiv"),
    ("31 Backup", r"backups?"),
    ("32 RPO/RTO", r"\bRPO\b|\bRTO\b"),
    ("33 Migration strategy", r"expand.{0,20}contract|backfill|migration strategy"),
    ("34 Replication/scaling", r"replica|replication|scaling|read replica"),
    ("35 Reporting/analytics", r"reporting|analytics"),
]

# Owner delivery gates (MASTER_WORKFLOW): extra evidence beyond the 20 steps -> regexes
GATE_EXTRA = {
    "product": [("Out of scope stated", r"out[- ]of[- ]scope|non-goals?")],
    "engineering": [("Architecture drivers ranked", r"architecture drivers?"),
                    ("Critical flows (sync/async, failure points)", r"critical flows?"),
                    ("Consistency model per domain", r"(strong|eventual) consisten"),
                    ("Single points of failure listed", r"single points? of failure|\bSPOFs?\b"),
                    ("Dependency rules between modules", r"dependency (rules|direction)")],
    "implementation": [("Work breakdown / roadmap with exit criteria", r"exit criteria|\bWBS\b|work breakdown"),
                       ("Acceptance tests linked to requirement IDs", r"\bTEST-\d+"),
                       ("Environments (staging)", r"\bstaging\b")],
    "production": [("Incident process", r"incident"), ("Rollback procedure", r"rollback"),
                   ("SLOs", r"\bSLOs?\b")],
}
GATE_STEPS = {
    "product": ["01", "02", "03", "04"],
    "engineering": ["05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "ADR"],
    "implementation": ["15"],
    "production": ["16", "17", "18", "19", "20"],
}
ORDER = ["product", "engineering", "implementation", "production"]


def collect(root: Path, extra: list[str]) -> tuple[dict[str, str], list[str]]:
    bases = [root / d for d in (extra or ["docs"])] + [root]
    texts: dict[str, str] = {}
    unfilled: list[str] = []
    for base in bases:
        if not base.exists():
            continue
        files = [base] if base.is_file() else (
            base.rglob("*") if base != root else [p for p in root.iterdir() if p.is_file()])
        for p in files:
            if p.is_file() and p.suffix.lower() in DOC_EXTS and not any(s in p.parts for s in SKIP) \
                    and p.stat().st_size < 3_000_000:
                rel = p.relative_to(root).as_posix()
                text = p.read_text(encoding="utf-8", errors="replace")
                if TEMPLATE_MARK in text[:400]:
                    unfilled.append(rel)
                else:
                    texts[rel] = text
    return texts, sorted(set(unfilled))


def first_match(texts: dict[str, str], pattern: str) -> str | None:
    rx = re.compile(pattern, re.I | re.M)
    for name, text in texts.items():
        if rx.search(text):
            return name
    return None


def traceability(texts: dict[str, str]) -> dict:
    ids = set()
    for t in texts.values():
        ids.update(re.findall(r"\b(?:FR|BR)-\d+\b", t))
    tested = set()
    for name, t in texts.items():
        if re.search(r"test|acceptance", name, re.I):
            tested.update(re.findall(r"\b(?:FR|BR)-\d+\b", t))
    planned = set()
    for name, t in texts.items():
        if re.search(r"project[_ -]?map|backlog|wbs|roadmap", name, re.I):
            planned.update(re.findall(r"\bFR-\d+\b", t))
    order = lambda s: (s[:2], int(s[3:]))  # noqa: E731
    untested = sorted(ids - tested, key=order)
    unplanned = sorted({i for i in ids if i.startswith("FR")} - planned, key=order)
    return {"requirements": len(ids), "untested": untested[:60], "untested_count": len(untested),
            "fr_without_work_item": unplanned[:60], "fr_without_work_item_count": len(unplanned)}


TECH_IN_PRD = re.compile(r"\b(PostgreSQL|MySQL|MariaDB|Redis|MongoDB|SQLite|GraphQL|REST API|Laravel|Django|Rails|"
                         r"React|Vue|Next\.js|Flutter|create table|varchar|foreign key|migrations?|endpoint)\b", re.I)


def prd_tech_leaks(texts: dict[str, str]) -> list[str]:
    """PRD = WHAT + WHY. Technical decisions in it are advisory findings: move them to architecture/ or an ADR."""
    out = []
    for name, t in texts.items():
        if re.search(r"(^|/)(\d+_)?PRD[^/]*\.md$", name, re.I):
            out += [f"{name}:{i}: {m.group(0)}" for i, line in enumerate(t.splitlines(), 1)
                    for m in [TECH_IN_PRD.search(line)] if m]
    return out[:40]


def readiness(texts: dict[str, str]) -> dict:
    name = next((n for n in texts if re.search(r"production[_ -]?readiness", n, re.I)), None) or \
        next((n for n, t in texts.items() if re.search(r"^#\s*production readiness", t, re.I | re.M)), None)
    if not name:
        return {"file": None, "ticked": 0, "open": 0, "ticked_without_evidence": []}
    lines = texts[name].splitlines()
    boxes = [ln.strip() for ln in lines if re.match(r"\s*[-*]\s*\[[ xX]\]", ln)]
    ticked = [b for b in boxes if re.match(r"[-*]\s*\[[xX]\]", b)]
    no_ev = [b for b in ticked if not re.search(r"evidence\s*:", b, re.I)]
    return {"file": name, "ticked": len(ticked) - len(no_ev), "open": len(boxes) - len(ticked) + len(no_ev),
            "ticked_without_evidence": no_ev[:30]}


def delivery_gates(texts: dict[str, str], steps: dict, missing_gate: list[str], trace: dict, ready: dict) -> dict:
    """The owner's 4 cumulative gates: a gate passes only when it and every earlier gate have nothing missing."""
    gates, blocked = {}, False
    for g in ORDER:
        miss = [f"{s} {steps[s]['step']}" for s in GATE_STEPS[g] if not steps[s]["present"]]
        miss += [label for label, rx in GATE_EXTRA[g] if not first_match(texts, rx)]
        if g == "engineering" and missing_gate:
            miss.append(f"Data Architecture Gate {35 - len(missing_gate)}/35")
        if g == "implementation" and trace["untested_count"]:
            miss.append(f"{trace['untested_count']} FR/BR ids with no acceptance test")
        if g == "implementation" and trace["fr_without_work_item_count"]:
            miss.append(f"{trace['fr_without_work_item_count']} FR ids with no work item (PROJECT_MAP / BACKLOG)")
        if g == "production":
            if not ready["file"]:
                miss.append("production readiness checklist missing")
            elif ready["open"]:
                miss.append(f"readiness checklist: {ready['open']} items open or ticked without evidence")
        gates[g] = {"passed": not miss and not blocked, "missing": miss,
                    **({"blocked_by_earlier_gate": True} if blocked and not miss else {})}
        blocked = blocked or bool(miss)
    return gates


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--docs", nargs="*", default=[], help="Planning doc dirs/files relative to root (default docs/).")
    ap.add_argument("--gate", choices=["data", *ORDER, "full", "none"], default="data")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    texts, unfilled = collect(root, args.docs)
    steps = {}
    for sid, (label, patterns) in STEPS.items():
        evidence = [first_match(texts, p) for p in patterns]
        steps[sid] = {"step": label, "present": all(evidence), "evidence": sorted({e for e in evidence if e})}
    # Gate answers live across the pack (retention in data/, backup in operations/, audit in security/):
    # data-named docs are searched first only so the reported evidence points at them.
    ordered = dict(sorted(texts.items(), key=lambda kv: not re.search(r"data|schema|database|domain", kv[0], re.I)))
    gate = {name: first_match(ordered, rx) for name, rx in GATE}
    missing_gate = [n for n, ev in gate.items() if not ev]
    missing_steps = [f"{sid} {v['step']}" for sid, v in steps.items() if not v["present"]]
    trace = traceability(texts)
    ready = readiness(texts)
    gates = delivery_gates(texts, steps, missing_gate, trace, ready)
    if args.gate == "none":
        failed = False
    elif args.gate == "data":
        failed = bool(missing_gate)
    elif args.gate == "full":
        failed = bool(missing_gate or missing_steps)
    else:
        failed = not gates[args.gate]["passed"]
    print(json.dumps({
        "root": str(root), "docs_scanned": len(texts), "templates_unfilled": unfilled,
        "steps_missing": missing_steps, "data_gate_missing": missing_gate,
        "data_gate_answered": f"{35 - len(missing_gate)}/35",
        "gates": gates, "traceability": trace, "readiness": ready,
        "advisory": {"prd_tech_leaks": prd_tech_leaks(texts)},
        "gate": args.gate, "passed": not failed,
        "steps": steps,
        "next": ("Complete the missing planning artifacts (references/system-engineering-method.md; scaffold: pb.py scaffold-docs) before moving past this gate."
                 if failed else "Selected gate passed on presence; a reviewer still checks the quality of the docs."),
    }, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
