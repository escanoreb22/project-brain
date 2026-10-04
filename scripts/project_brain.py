#!/usr/bin/env python3
"""Deterministic project-memory utilities for the Project Brain Agent Skill."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
import uuid
from pathlib import Path


PHASES = (
    "idea",
    "requirements",
    "architecture",
    "design",
    "planned",
    "implementing",
    "verifying",
    "release_ready",
    "released",
    "maintenance",
)
APPROVAL_REQUIRED = set(PHASES[1:])
REQUIRED_PATHS = (
    "STATE.yaml",
    "HANDOFF.md",
    "product/PROBLEM_STATEMENT.md",
    "product/PROJECT_IDEA.md",
    "product/FEATURE_CANDIDATES.yaml",
    "product/USERS_AND_ROLES.yaml",
    "product/BUSINESS_RULES.yaml",
    "product/USER_JOURNEYS.yaml",
    "product/ASSUMPTIONS.yaml",
    "product/BLIND_SPOTS.yaml",
    "product/RISKS.yaml",
    "product/SUCCESS_METRICS.yaml",
    "product/OPEN_QUESTIONS.yaml",
    "planning/PRD.md",
    "planning/SRS.md",
    "planning/ARCHITECTURE.md",
    "planning/PROJECT_MAP.yaml",
    "design/DESIGN_SYSTEM.md",
    "design/SCREEN_INVENTORY.yaml",
    "security/SECURITY_PROFILE.yaml",
    "security/THREAT_MODEL.md",
    "tracking/PROJECT_STRUCTURE.yaml",
    "tracking/TRACEABILITY_MATRIX.yaml",
    "tracking/BLOCKERS.yaml",
    "memory/FACTS.jsonl",
    "logs/CHANGES.jsonl",
)
# Lite mode: the repository's own docs/ set is canonical; .project-brain only
# carries execution state, decisions, the change log and the handoff.
LITE_REQUIRED_PATHS = (
    "STATE.yaml",
    "HANDOFF.md",
    "DECISIONS.md",
    "logs/CHANGES.jsonl",
)
SOURCE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cs", ".dart", ".ex", ".exs", ".go", ".java", ".js",
    ".jsx", ".kt", ".kts", ".php", ".py", ".rb", ".rs", ".swift", ".ts", ".tsx",
    ".vue",
}
IGNORED_PARTS = {
    ".git", ".project-brain", ".idea", ".vscode", "build", "coverage", "dist",
    "node_modules", "target", "vendor", ".venv", "venv",
}
SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|pk|rk)[-_][A-Za-z0-9_-]{8,}\b", re.I),
    re.compile(r"\b(?:api[_ -]?key|secret|token|password)\s*[:=]\s*\S+", re.I),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def brain_root(project: Path) -> Path:
    return project.resolve() / ".project-brain"


def parse_flat_yaml(path: Path) -> dict[str, object]:
    data: dict[str, object] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value in {"null", "~"}:
            parsed: object = None
        elif value in {"true", "false"}:
            parsed = value == "true"
        elif value.isdigit():
            parsed = int(value)
        else:
            parsed = value.strip("\"'")
        data[key.strip()] = parsed
    return data


def redact(value: str) -> str:
    result = value
    for pattern in SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def write_if_absent(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def command_init(args: argparse.Namespace) -> int:
    root = brain_root(Path.cwd())
    if root.exists() and not args.force:
        print(f"Project Brain already exists: {root}", file=sys.stderr)
        return 2
    if root.exists():
        shutil.rmtree(root)
    project = args.project_name.strip()
    if not project:
        print("Project name must not be empty.", file=sys.stderr)
        return 2

    if args.lite:
        write_if_absent(
            root / "STATE.yaml",
            "schema_version: 1\n"
            "mode: lite\n"
            f"project: {project}\n"
            "phase: idea\n"
            "phase_approval: pending\n"
            "active_task: null\n"
            f"updated_at: {utc_now()}\n"
            "canonical_docs: []\n"
            "tasks: []\n"
            "blockers: []\n",
        )
        write_if_absent(
            root / "HANDOFF.md",
            f"# {project} handoff\n\n"
            f"## {utc_now()[:10]} — Project Brain initialized (lite)\n\n"
            "Canonical product docs live in the repository docs/ set listed in STATE.yaml.\n",
        )
        write_if_absent(
            root / "DECISIONS.md",
            f"# {project} decisions\n\n"
            "Owner decisions, overrides of the docs, and decisions taken on the owner's behalf.\n"
            "Format: `D-YYYYMMDD-NN` — decision — source (owner / delegated) — docs updated (yes/no).\n",
        )
        write_if_absent(root / "logs" / "CHANGES.jsonl", "")
        print(root)
        return 0

    state = (
        "schema_version: 1\n"
        f"project: {project}\n"
        "phase: idea\n"
        "phase_approval: pending\n"
        "active_role: idea\n"
        "active_task: null\n"
        f"updated_at: {utc_now()}\n"
    )
    write_if_absent(root / "STATE.yaml", state)
    write_if_absent(
        root / "HANDOFF.md",
        f"# {project} handoff\n\n"
        "## Current phase\n\nidea\n\n"
        "## Last verified outcome\n\nProject memory initialized; discovery not yet approved.\n\n"
        "## Next ready task\n\nComplete product discovery and resolve high-impact unknowns.\n\n"
        "## Blockers\n\n- Owner approval for the Idea gate.\n\n"
        "## Verification evidence\n\n- Project Brain initialization completed.\n",
    )
    templates: dict[str, str] = {
        "product/PROBLEM_STATEMENT.md": (
            f"# {project} — Problem statement\n\n"
            "## Problem\n\n"
            "## Affected users\n\n"
            "## Current workaround\n\n"
            "## Desired outcome\n\n"
            "## Why a product, not a feature\n\n"
            "## Evidence class\n\n"
            "<!-- Label each claim: verified | owner_statement | inferred | unknown -->\n"
        ),
        "product/PROJECT_IDEA.md": f"# {project} — Project idea\n\n## Problem\n\n## Users\n\n## Value\n\n## Scope\n\n## Evidence\n",
        "product/FEATURE_CANDIDATES.yaml": "schema_version: 1\ncandidates: []\n# Fields per candidate: name, problem, affected_users, mvp (bool), assumptions, excluded\n",
        "product/USERS_AND_ROLES.yaml": "schema_version: 1\nusers: []\nroles: []\n",
        "product/BUSINESS_RULES.yaml": "schema_version: 1\nrules: []\n",
        "product/USER_JOURNEYS.yaml": "schema_version: 1\njourneys: []\n# Fields per journey: name, actor, trigger, steps, success_outcome, failure_modes\n",
        "product/ASSUMPTIONS.yaml": "schema_version: 1\nassumptions: []\n# Fields: id, statement, evidence_class (verified|owner_statement|inferred|unknown), risk_if_wrong, owner, status\n",
        "product/BLIND_SPOTS.yaml": "schema_version: 1\nblind_spots: []\n",
        "product/RISKS.yaml": "schema_version: 1\nrisks: []\n",
        "product/SUCCESS_METRICS.yaml": "schema_version: 1\nmetrics: []\n# Fields per metric: goal_id, statement, metric_name, baseline, target, measurement_window, instrumentation, owner\n",
        "product/OPEN_QUESTIONS.yaml": "schema_version: 1\nquestions: []\n",
        "planning/PRD.md": f"# {project} — PRD\n\n## Goals\n\n## Non-goals\n\n## Capabilities\n\n## Success metrics\n",
        "planning/SRS.md": f"# {project} — SRS\n\n## Functional requirements\n\n## Non-functional requirements\n",
        "planning/ARCHITECTURE.md": f"# {project} — Architecture\n\n## Context\n\n## Boundaries\n\n## Data\n\n## Failure and recovery\n",
        "planning/PROJECT_MAP.yaml": "schema_version: 1\nepics: []\ntasks: []\n",
        "planning/API_CONTRACTS.md": f"# {project} — API contracts\n",
        "planning/DATA_MODEL.md": f"# {project} — Data model\n",
        "planning/NON_FUNCTIONAL_REQUIREMENTS.md": f"# {project} — Non-functional requirements\n",
        "planning/INTEGRATIONS.md": f"# {project} — Integrations\n",
        "planning/TEST_STRATEGY.md": f"# {project} — Test strategy\n",
        "planning/OPERATIONS.md": f"# {project} — Operations\n",
        "planning/RELEASE_STRATEGY.md": f"# {project} — Release strategy\n",
        "design/DESIGN_SYSTEM.md": f"# {project} — Design system\n\n## Principles\n\n## Tokens\n\n## Components\n",
        "design/INFORMATION_ARCHITECTURE.yaml": "schema_version: 1\nnodes: []\n",
        "design/SCREEN_INVENTORY.yaml": "schema_version: 1\nscreens: []\n",
        "design/USER_FLOWS.md": f"# {project} — User flows\n",
        "design/WIREFRAMES.md": f"# {project} — Wireframes\n",
        "design/COMPONENT_CATALOG.yaml": "schema_version: 1\ncomponents: []\n",
        "design/INTERACTION_RULES.md": f"# {project} — Interaction rules\n",
        "design/CONTENT_GUIDELINES.md": f"# {project} — Content guidelines\n",
        "design/ACCESSIBILITY.md": f"# {project} — Accessibility\n",
        "design/DESIGN_QA.yaml": "schema_version: 1\nchecks: []\n",
        "security/SECURITY_PROFILE.yaml": "schema_version: 1\nlevel: standard\nstandards: []\ncontrols: []\n",
        "security/THREAT_MODEL.md": f"# {project} — Threat model\n\n## Assets\n\n## Trust boundaries\n\n## Threats and controls\n",
        "security/DATA_CLASSIFICATION.yaml": "schema_version: 1\nclasses: []\n",
        "security/TRUST_BOUNDARIES.yaml": "schema_version: 1\nboundaries: []\n",
        "security/ABUSE_CASES.yaml": "schema_version: 1\ncases: []\n",
        "security/SECURITY_REQUIREMENTS.yaml": "schema_version: 1\nrequirements: []\n",
        "security/PRIVACY_MODEL.md": f"# {project} — Privacy model\n",
        "security/DEPENDENCY_POLICY.yaml": "schema_version: 1\nrules: []\n",
        "security/ACCEPTED_RISKS.yaml": "schema_version: 1\nrisks: []\n",
        "tracking/PROJECT_STRUCTURE.yaml": "schema_version: 1\npaths: []\n",
        "tracking/DEPENDENCY_GRAPH.yaml": "schema_version: 1\nnodes: []\nedges: []\n",
        "tracking/TRACEABILITY_MATRIX.yaml": "schema_version: 1\nlinks: []\n",
        "tracking/BLOCKERS.yaml": "schema_version: 1\nblockers: []\n",
        "tracking/DRIFT_REPORT.md": f"# {project} — Drift report\n\nNo drift scan has run.\n",
        "memory/FACTS.jsonl": "",
        "memory/CONSTRAINTS.jsonl": "",
        "memory/CORRECTIONS.jsonl": "",
        "logs/CHANGES.jsonl": "",
    }
    for relative, content in templates.items():
        write_if_absent(root / relative, content)
    for directory in ("decisions", "tasks", "memory/summaries", "security/reviews"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    print(root)
    return 0


def command_validate(_: argparse.Namespace) -> int:
    root = brain_root(Path.cwd())
    errors: list[str] = []
    if not root.is_dir():
        errors.append("Missing .project-brain directory.")
    else:
        state_path = root / "STATE.yaml"
        state = parse_flat_yaml(state_path) if state_path.exists() else {}
        lite = state.get("mode") == "lite"
        for relative in LITE_REQUIRED_PATHS if lite else REQUIRED_PATHS:
            if not (root / relative).exists():
                errors.append(f"Missing required path: {relative}")
        if state_path.exists():
            phase = state.get("phase")
            approval = state.get("phase_approval")
            if phase not in PHASES:
                errors.append(f"Invalid phase: {phase}")
            if not lite and phase in APPROVAL_REQUIRED and approval != "approved":
                errors.append(f"Phase '{phase}' requires explicit approval.")
            if state.get("schema_version") != 1:
                errors.append("Unsupported state schema_version.")
        for relative in ("logs/CHANGES.jsonl", "memory/FACTS.jsonl"):
            path = root / relative
            if path.exists():
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as exc:
                        errors.append(f"Invalid JSONL {relative}:{number}: {exc.msg}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print("VALID: Project Brain memory and state contracts passed.")
    return 0


def command_append_change(args: argparse.Namespace) -> int:
    root = brain_root(Path.cwd())
    if not root.is_dir():
        print("Initialize Project Brain first.", file=sys.stderr)
        return 2
    timestamp = utc_now()
    event = {
        "id": f"CHG-{timestamp[:10].replace('-', '')}-{uuid.uuid4().hex[:8].upper()}",
        "timestamp": timestamp,
        "task": args.task,
        "type": args.type,
        "summary": redact(args.summary),
        "reason": redact(args.reason),
        "files": args.file,
        "requirements": args.requirement,
        "tests": args.test,
        "security_effect": args.security_effect,
        "breaking": args.breaking,
        "rollback": redact(args.rollback),
        "known_issues": [redact(item) for item in args.known_issue],
    }
    path = root / "logs" / "CHANGES.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(event["id"])
    return 0


def command_compact_memory(args: argparse.Namespace) -> int:
    root = brain_root(Path.cwd())
    source = Path(args.input).expanduser().resolve()
    if not root.is_dir() or not source.is_file():
        print("Project memory or input notes missing.", file=sys.stderr)
        return 2
    categories = {
        "DECISION": "decisions",
        "FACT": "facts",
        "CONSTRAINT": "constraints",
        "CORRECTION": "corrections",
        "OPEN": "open_questions",
        "COMPLETED": "completed",
        "BLOCKER": "blockers",
        "NEXT": "next_actions",
    }
    summary: dict[str, object] = {
        "schema_version": 1,
        "created_at": utc_now(),
        "source": source.name,
        **{target: [] for target in categories.values()},
    }
    for raw in source.read_text(encoding="utf-8").splitlines():
        if ":" not in raw:
            continue
        label, value = raw.split(":", 1)
        target = categories.get(label.strip().upper())
        clean = redact(value.strip())
        if target and clean:
            cast = summary[target]
            assert isinstance(cast, list)
            cast.append(clean)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = root / "memory" / "summaries" / f"SESSION-{stamp}.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


def command_validate_task(args: argparse.Namespace) -> int:
    task_path = Path(args.task_file).expanduser().resolve()
    if not task_path.is_file():
        print(f"Task file not found: {task_path}", file=sys.stderr)
        return 2
    import importlib.util
    try:
        raw = task_path.read_text(encoding="utf-8")
        # Minimal YAML extraction: parse key: value pairs to check required fields
        required_fields = {
            "id", "objective", "status", "requirements", "depends_on",
            "allowed_paths", "forbidden_paths", "invariants", "acceptance",
            "tests", "security_checks", "observability", "rollback", "done_evidence",
        }
        present: set[str] = set()
        for line in raw.splitlines():
            stripped = line.strip()
            if ":" in stripped and not stripped.startswith("-"):
                key = stripped.split(":", 1)[0].strip()
                present.add(key)
        missing = required_fields - present
        if missing:
            for field in sorted(missing):
                print(f"ERROR: Task packet missing required field: {field}", file=sys.stderr)
            return 2
        # Validate status value
        valid_statuses = {
            "proposed", "clarified", "ready", "in_progress", "blocked",
            "implemented", "verified", "accepted", "released", "deprecated",
        }
        data = parse_flat_yaml(task_path)
        status = data.get("status")
        if status and status not in valid_statuses:
            print(f"ERROR: Invalid task status: {status}", file=sys.stderr)
            return 2
        task_id = str(data.get("id", ""))
        if task_id and not task_id.startswith("TASK-"):
            print(f"ERROR: Task id must match TASK-* pattern, got: {task_id}", file=sys.stderr)
            return 2
        print(f"VALID: Task packet {task_id or task_path.name} passed all checks.")
        return 0
    except Exception as exc:
        print(f"ERROR: Could not parse task file: {exc}", file=sys.stderr)
        return 2


def mapped_paths(structure: Path) -> set[str]:
    paths: set[str] = set()
    for raw in structure.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        match = re.match(r"-?\s*path:\s*[\"']?([^\"']+?)[\"']?\s*$", stripped)
        if match:
            paths.add(match.group(1).replace("\\", "/").rstrip("/"))
    return paths


def command_check_drift(_: argparse.Namespace) -> int:
    project = Path.cwd().resolve()
    root = brain_root(project)
    structure = root / "tracking" / "PROJECT_STRUCTURE.yaml"
    if not structure.is_file():
        print("Missing project structure map.", file=sys.stderr)
        return 2
    mapped = mapped_paths(structure)
    source_files: list[str] = []
    for path in project.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(project)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        source_files.append(relative.as_posix())
    orphaned = sorted(
        path for path in source_files
        if path not in mapped and not any(path.startswith(entry + "/") for entry in mapped)
    )
    report = root / "tracking" / "DRIFT_REPORT.md"
    lines = ["# Drift report", "", f"Generated: {utc_now()}", ""]
    if orphaned:
        lines.extend(["## Unmapped source files", "", *[f"- `{item}`" for item in orphaned], ""])
        report.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(orphaned))
        return 2
    lines.extend(["No unmapped source files detected.", ""])
    report.write_text("\n".join(lines), encoding="utf-8")
    print("NO_DRIFT: no unmapped source files detected.")
    return 0


def first_list_item(path: Path, key: str) -> str:
    active = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped == f"{key}:":
            active = True
            continue
        if active and stripped.startswith("- "):
            return stripped[2:].strip() or "None"
        if active and stripped and not raw.startswith((" ", "\t")):
            break
    return "None"


def command_handoff(_: argparse.Namespace) -> int:
    root = brain_root(Path.cwd())
    state_path = root / "STATE.yaml"
    if not state_path.is_file():
        print("Initialize Project Brain first.", file=sys.stderr)
        return 2
    state = parse_flat_yaml(state_path)
    if state.get("mode") == "lite":
        # Lite handoffs are hand-written, dated sections; never overwrite them.
        print("Lite mode: append a dated section to HANDOFF.md by hand (state, evidence, open items, next action).")
        return 0
    blockers = first_list_item(root / "tracking" / "BLOCKERS.yaml", "blockers")
    project_map = root / "planning" / "PROJECT_MAP.yaml"
    next_task = first_list_item(project_map, "tasks")
    changes = root / "logs" / "CHANGES.jsonl"
    last_change = "None"
    if changes.exists():
        nonempty = [line for line in changes.read_text(encoding="utf-8").splitlines() if line.strip()]
        if nonempty:
            event = json.loads(nonempty[-1])
            last_change = f"{event.get('id')}: {event.get('summary')}"
    output = root / "HANDOFF.md"
    output.write_text(
        f"# {state.get('project', 'Project')} handoff\n\n"
        f"Generated: {utc_now()}\n\n"
        f"## Current phase\n\n{state.get('phase', 'unknown')} "
        f"(approval: {state.get('phase_approval', 'unknown')})\n\n"
        f"## Active role and task\n\n{state.get('active_role', 'none')} / "
        f"{state.get('active_task') or 'none'}\n\n"
        f"## Last verified outcome\n\n{last_change}\n\n"
        f"## Next ready task\n\n{next_task}\n\n"
        f"## Blockers\n\n{blockers}\n\n"
        "## Verification evidence\n\nRun validation, tests, security checks, and drift checks before resuming.\n",
        encoding="utf-8",
    )
    print(output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize, validate, audit, compact, and hand off Project Brain memory."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create .project-brain in the current project.")
    init.add_argument("--project-name", required=True)
    init.add_argument("--force", action="store_true", help="Replace an existing .project-brain directory.")
    init.add_argument("--lite", action="store_true", help="Minimal state/handoff/decisions/log; repo docs/ stay canonical.")
    init.set_defaults(func=command_init)

    validate = sub.add_parser("validate", help="Validate required memory and state invariants.")
    validate.set_defaults(func=command_validate)

    change = sub.add_parser("append-change", help="Append a redacted JSONL change event.")
    change.add_argument("--task", required=True)
    change.add_argument("--type", required=True, choices=("feat", "fix", "refactor", "docs", "test", "security", "config", "migration", "revert"))
    change.add_argument("--summary", required=True)
    change.add_argument("--reason", required=True)
    change.add_argument("--file", action="append", default=[])
    change.add_argument("--requirement", action="append", default=[])
    change.add_argument("--test", action="append", default=[])
    change.add_argument("--security-effect", choices=("reduced", "neutral", "increased", "unknown"), default="unknown")
    change.add_argument("--breaking", action="store_true")
    change.add_argument("--rollback", default="Not recorded")
    change.add_argument("--known-issue", action="append", default=[])
    change.set_defaults(func=command_append_change)

    compact = sub.add_parser("compact-memory", help="Convert labelled session notes into a redacted JSON summary.")
    compact.add_argument("--input", required=True)
    compact.set_defaults(func=command_compact_memory)

    validate_task = sub.add_parser("validate-task", help="Validate a task packet YAML against required fields and status constraints.")
    validate_task.add_argument("--task-file", required=True, help="Path to a task packet YAML file.")
    validate_task.set_defaults(func=command_validate_task)

    drift = sub.add_parser("check-drift", help="Report source files missing from PROJECT_STRUCTURE.yaml.")
    drift.set_defaults(func=command_check_drift)

    handoff = sub.add_parser("handoff", help="Generate a concise resumable HANDOFF.md.")
    handoff.set_defaults(func=command_handoff)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

