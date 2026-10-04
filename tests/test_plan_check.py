"""plan_check: the Data Architecture Gate blocks until the 35 items are answered; a complete plan passes."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SCRIPT = SCRIPTS / "plan_check.py"

COMPLETE_DATA = """# Data architecture
## Conceptual model
Domain entities: Customer, Order, OrderItem. Relationships: Customer 1:N Order. Ownership: Orders context owns orders.
Cardinality: 10M rows per year of orders. Data volume growth handled by archiving.
## Logical model
Keys: BIGINT id + public_id ULID. Foreign keys with RESTRICT. Nullability: NOT NULL by default. Uniqueness: UNIQUE(tenant_id, email).
Business invariants as CHECK constraints. Lifecycle/status with transitions in STATE_MACHINES.md. Payments are immutable (append-only).
Deletion strategy: soft delete for employees, hard delete for tokens, anonymize PII. Historical snapshot of billing data on invoices.
Normalization to 3NF; denormalization by design for invoice snapshot. Access patterns listed; indexes derived from them.
Transaction boundaries: order + items + stock. Concurrency: SELECT ... FOR UPDATE and optimistic version column. Idempotency keys.
Money: amount_minor + currency. Time: UTC. Multi-tenancy: shared DB + tenant_id. Audit log with before/after.
PII classification: Public, Internal, Confidential, Restricted. Encryption: passwords hashed, tokens encrypted. Retention policy per class.
Archiving monthly. Backups daily with binlogs. RPO 5 min, RTO 30 min. Migration strategy: expand/contract with backfill.
Replication: read replica later. Reporting: summary tables for analytics.
| Field | Meaning | Type | Nullable | Rules |
|---|---|---|---|---|
| id | internal id | bigint | No | PK |
"""


def run(root, gate="data"):
    p = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--gate", gate], capture_output=True, text=True, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


class PlanCheck(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pbplan-"))
        (self.root / "docs" / "architecture").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_empty_plan_fails_the_data_gate(self):
        (self.root / "docs" / "PRD.md").write_text("# Product\nFR-01 User can create an order\n", encoding="utf-8")
        code, out = run(self.root)
        self.assertEqual(code, 1)
        self.assertIn("17 Access patterns", out["data_gate_missing"])

    def test_complete_data_architecture_passes(self):
        (self.root / "docs" / "architecture" / "DATA_ARCHITECTURE.md").write_text(COMPLETE_DATA, encoding="utf-8")
        code, out = run(self.root)
        self.assertEqual(code, 0, out["data_gate_missing"])
        self.assertEqual(out["data_gate_answered"], "35/35")

    def test_measurable_nfr_required(self):
        (self.root / "docs" / "PRD.md").write_text("# Product\nNFR-01 The API must be fast\n", encoding="utf-8")
        _, out = run(self.root, gate="none")
        self.assertIn("04 Non-functional requirements (measurable)", out["steps_missing"])
        (self.root / "docs" / "PRD.md").write_text("# Product\nNFR-01 API P95 < 300 ms\n", encoding="utf-8")
        _, out = run(self.root, gate="none")
        self.assertNotIn("04 Non-functional requirements (measurable)", out["steps_missing"])



def pb(root, *args):
    p = subprocess.run([sys.executable, str(SCRIPTS / "pb.py"), *args, "--root", str(root)], capture_output=True, text=True, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


class DeliveryGates(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pbgates-"))
        (self.root / "docs").mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, text):
        p = self.root / "docs" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def test_scaffold_never_overwrites_and_templates_never_pass(self):
        self.write("PRD.md", "# Product\noriginal text\n")
        code, out = pb(self.root, "scaffold-docs")
        self.assertEqual(code, 0)
        self.assertIn("product/PRD.md", out["kept_existing"])
        self.assertEqual((self.root / "docs" / "PRD.md").read_text(encoding="utf-8"), "# Product\noriginal text\n")
        self.assertFalse((self.root / "docs" / "product" / "PRD.md").exists())
        self.assertTrue((self.root / "docs" / "data" / "DATA_ARCHITECTURE.md").exists())
        code, res = run(self.root)  # scaffolds full of gate keywords must not answer the gate
        self.assertEqual(code, 1)
        self.assertEqual(res["data_gate_answered"], "0/35")
        self.assertIn("docs/data/DATA_ARCHITECTURE.md", res["templates_unfilled"])

    def test_traceability_lists_untested_requirements(self):
        self.write("product/PRD.md", "# Product\n| FR-01 | a |\n| FR-02 | b |\n")
        self.write("product/BUSINESS_RULES.md", "| BR-01 | rule |\n")
        self.write("testing/ACCEPTANCE_TESTS.md", "### TEST-001\n**Requirement:** FR-01 / BR-01\n")
        _, res = run(self.root, gate="none")
        self.assertEqual(res["traceability"]["untested"], ["FR-02"])

    def test_readiness_tick_needs_evidence_and_gates_are_cumulative(self):
        self.write("release/CHECKLIST_PRODUCTION_READINESS.md",
                   "# Production Readiness Checklist\n- [x] Rate limits - evidence: tests/Feature/RateLimitTest.php\n- [x] Backups\n- [ ] Runbook\n")
        code, res = run(self.root, gate="production")
        self.assertEqual(code, 1)
        self.assertEqual(res["readiness"]["ticked"], 1)
        self.assertEqual(res["readiness"]["open"], 2)
        self.assertEqual(res["readiness"]["ticked_without_evidence"], ["- [x] Backups"])
        self.assertFalse(res["gates"]["product"]["passed"])
        self.assertFalse(res["gates"]["production"]["passed"])


class TimeoutFitnessRule(unittest.TestCase):
    def test_external_http_call_without_timeout_is_flagged(self):
        root = Path(tempfile.mkdtemp(prefix="pbhttp-"))
        try:
            (root / "app").mkdir()
            (root / "app" / "A.php").write_text("<?php\n$r = Http::acceptJson()->get($url);\n", encoding="utf-8")
            (root / "app" / "B.php").write_text("<?php\n$r = Http::acceptJson()->timeout(5)->get($url);\n", encoding="utf-8")
            p = subprocess.run([sys.executable, str(SCRIPTS / "vuln_scan.py"), "--root", str(root)], capture_output=True, text=True, encoding="utf-8")
            files = [f["file"] for f in json.loads(p.stdout)["findings"] if f["cwe"] == "CWE-400"]
            self.assertEqual([Path(f).name for f in files], ["A.php"])
            self.assertEqual(p.returncode, 0)  # review severity: prove safe, does not block
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
