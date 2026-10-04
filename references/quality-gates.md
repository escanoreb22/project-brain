# Quality gates

Apply the gate whose exit changes project or task state. Evidence must be a file, command result, test, reviewed artifact, or explicit owner decision.

| Gate | Required evidence | Stop when |
|---|---|---|
| Idea | `PROBLEM_STATEMENT.md`, actors, journeys, business rules, feature candidates, assumptions, risks, success metrics with baselines | high-impact unknown, undefined user role, goal without metric, or contradictory owner statement |
| Requirements | uniquely identified testable requirements with all fields, NFR budgets, traceability | vague outcome, missing actor, unverifiable acceptance criterion |
| Architecture | boundaries, data ownership, contracts, failures, deployment, rollback | critical dependency, trust boundary, or disaster-recovery path unresolved |
| Design | IA, screen/state inventory for all scenarios, component rules, content, accessibility | primary flow, error/recovery state, or accessibility target missing |
| Ready | complete task packet (all mandatory fields), dependencies satisfied, no concurrent file ownership conflict | blocker, unstated migration, missing acceptance test, or scope conflict |
| Code | scoped diff, no placeholders, versions verified against manifests, tests added | invented API, unrelated edit, unexplained dependency, forbidden path touched |
| Security | threat controls verified, secrets clean, authorization and abuse tested per profile level | critical/high risk unmitigated or unaccepted by owner |
| Verification | formatter/lint/type/tests/build/runtime checks appropriate to change | output has errors, warnings that affect correctness, or untested failure path |
| Drift | requirement↔task↔file↔test traceability complete, `DRIFT_REPORT.md` updated, structure record matches actual repo | orphan behavior, stale contract, undocumented public surface, task status inconsistency |
| Acceptance | owner or delegated product authority accepts observable outcome against success metrics | implementation evidence does not demonstrate user result |
| Release | migration/rollback verified, monitoring/alerts active, runbook drafted, backup/restore as applicable | rollback impossible or production authorization absent |

## Mandatory task packet

Require `id`, `objective`, `status`, `requirements`, `depends_on`, `allowed_paths`, `forbidden_paths`, `invariants`, `acceptance`, `tests`, `security_checks`, `observability`, `rollback`, and `done_evidence`.

## Red flags

Stop and correct course when the agent says or implies:

- “It should work” without execution evidence.
- “Tests pass” when only a subset unrelated to the risk ran.
- “Best practice” without project constraints or source.
- “Latest” without a dated official source.
- “Complete” while blockers, TODOs, placeholders, skipped checks, or drift remain.
- “Safe” without assets, threats, controls, and residual risk.

