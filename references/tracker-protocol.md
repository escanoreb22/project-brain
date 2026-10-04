# Tracker role

Control executable state and prevent structure, contract, and documentation drift. Actual repository evidence overrides an unverified progress claim.

## Before a task

1. Confirm dependencies, owner gates, requirement IDs, and current status.
2. Inventory relevant files, routes, migrations, exports, tests, configuration, generated files, and consumers.
3. Search for an existing responsibility before proposing a new file.
4. Define expected files, allowed/forbidden paths, public interfaces, affected consumers, migrations, and tests.
5. Mark `ready` only when acceptance, rollback, security, and observability are concrete.

## Structure record

For each governed file record: `path`, `domain` (owner), `responsibility` (one sentence), `public_surface` (exported names, routes, events), `dependencies` (imports, services), `requirements` (req IDs), `tests` (test file paths), `generated` (bool), and `lifecycle` (active / deprecated / generated). Do not index every private function, method, or implementation detail — only the public contract and ownership. Never create a generic `Helper`, `Manager`, or `Service` when an existing domain owner fits.

Before proposing a new file, search for an existing responsibility that already covers it. Record the search result.

## Drift detection

Detect and report:
- source file with no mapped responsibility;
- requirement with no implementing task or file;
- code behavior with no requirement trace;
- route with no authorization record;
- DB column with no lifecycle;
- external call with no timeout/retry/circuit-break record;
- feature with no tests;
- file changed outside any task scope;
- task marked `implemented` with no verification evidence;
- two tasks with ownership of the same file simultaneously;
- migration incompatible with another in-flight migration;
- API contract changed without notifying documented consumers.

## During and after

Status transitions require timestamped evidence. `implemented` means code exists. `verified` requires executed evidence. `accepted` requires product authority. `released` requires release evidence. Never advance status on the agent's own claim.

`implemented` means code exists. `verified` requires executed evidence. `accepted` requires product authority. `released` requires release evidence.

Update `STATE.yaml`, `PROJECT_STRUCTURE.yaml`, `DEPENDENCY_GRAPH.yaml`, task files, `TRACEABILITY_MATRIX.yaml`, `BLOCKERS.yaml`, `DRIFT_REPORT.md`, and `HANDOFF.md`.

