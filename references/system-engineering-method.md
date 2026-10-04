# System engineering method — plan the system, not the tables (owner standard, 2026-10-03)

**Owner rule:** planning never starts with "which tables?" or "which pages?". It starts with what the system does, the rules that must never break, and the data and operations that guarantee them. Every new project or new module goes through the layers below in order; each step produces a named artifact. No migration is written before the **Data Architecture Gate** (section C) passes. `scripts/plan_check.py` verifies the artifacts exist; `workflows/plan-from-prd.js` produces them; `workflows/map-loop.js` refuses database items while the gate fails.

Detail lives in: `planning-playbook.md` (requirements, slicing, ADRs), `db-schema-design.md` (MySQL 8.4 physical rules), `backend-architecture.md` (modules, transactions, outbox), `api-design.md` (contracts), `security-baseline.md` (14 CWE classes + 20 fundamentals), `operations-monitoring.md` (backups, RPO/RTO), `multi-surface-architecture.md` (surfaces).

## A. The 10 layers

1. Product / business definition — 2. Domain modeling — 3. System architecture — 4. Data architecture / database — 5. API & contracts — 6. Security — 7. Reliability & performance — 8. Testing — 9. Deployment & operations — 10. Evolution & change management.

## B. The 20 steps and their artifacts (default location `docs/` in the production docs pack layout of section G; an existing repo layout wins)

| # | Step | Artifact (IDs are mandatory) | Done when |
|---|---|---|---|
| 01 | Product definition | `product/PRD.md` §Product: problem, users/roles, goals, non-goals, success metrics | goals measurable; non-goals explicit |
| 02 | Functional requirements | `product/PRD.md` FR table: `FR-01 Actor can …` | each FR testable, has an actor and acceptance criterion |
| 03 | Business rules | `product/BUSINESS_RULES.md`: `BR-01 X cannot exist without Y` | each BR names where it is enforced (DB constraint / domain / both) |
| 04 | Non-functional requirements | `product/NON_FUNCTIONAL_REQUIREMENTS.md` with numbers: `NFR-01 API P95 < 300 ms`, availability, RPO/RTO, retention, concurrency, auditability, compliance, localization | every NFR has a measurable target and a verification method |
| 05 | Domain model | `domain/DOMAIN_MODEL.md`: entities (real things, not tables), relationships, aggregates | each entity has a one-line meaning and an owner context |
| 06 | Bounded contexts | `domain/BOUNDED_CONTEXTS.md` (context map: owns, publishes, consumes): contexts (Identity, Billing, Catalog, Orders, Inventory, Notifications, Reporting, Audit…) and a **data ownership table** (entity -> owning context; who may write) | every entity has exactly one owner; cross-context access only through the owner's API/events |
| 07 | System architecture | `architecture/SYSTEM_DESIGN.md` (drivers, critical flows, consistency, caching, SPOFs, capacity, 10x plan) + `architecture/ARCHITECTURE.md` (style, module ownership, dependency rules, error model, fitness rules) + diagram: modules, surfaces, sync vs async, external systems | matches the contexts; one deployable unless an ADR says otherwise |
| 08 | Data model | `data/DATA_ARCHITECTURE.md`: conceptual -> logical model, invariants, lifecycles, cardinality | section C checklist answered |
| 09 | Database schema | physical model + **data dictionary** in the same file; migrations only after the gate | every column documented (see section E) |
| 10 | API contracts | `openapi/*.yaml` or `api/API_CONTRACTS.md` before UI work; error taxonomy, pagination, rate limits, idempotency, versioning; `api/WEBHOOKS.md` | each endpoint has input, output, errors (400, 401, 403, 404, 409, 422, 429) |
| 11 | Auth / RBAC / security | `security/SECURITY.md`: authorization matrix + threat model; `security-baseline.md` walk-through | every route/action has a policy row and a negative test planned |
| 12 | State machines | `domain/STATE_MACHINES.md`: states, allowed transitions, who triggers, side effects | forbidden transitions listed (e.g. completed -> draft) |
| 13 | Events / queues | `api/EVENTS.md`: name, producer, consumers, payload, idempotency key, outbox use | every async side effect is idempotent and retry-safe |
| 14 | Failure handling | per external call / job: timeout, retry, backoff, dead letter, compensation | no unbounded retries; compensations defined for multi-step flows |
| 15 | Testing strategy | `testing/TEST_STRATEGY.md` + `testing/ACCEPTANCE_TESTS.md` (Gherkin, `TEST-xxx` names its FR/BR): which tests prove which FR/BR/NFR (traceability), real DB engine | every BR has a test |
| 16 | Observability | `operations/OBSERVABILITY.md`: logs, metrics, traces, alerts, SLOs, audit events | NFR targets are measurable in production |
| 17 | Deployment | `architecture/DEPLOYMENT_ARCHITECTURE.md` + `delivery/CI_CD.md`: environments, pipeline/procedure, config, secrets, rollback | reproducible, rollback defined |
| 18 | Backup / recovery | `operations/BACKUP_RECOVERY.md` (+ `data/RETENTION_POLICY.md`): schedule, retention, PITR (binlog), restore test, RPO/RTO met | a restore was actually tested |
| 19 | Migration strategy | versioned migrations, expand/contract plan for risky changes | no manual production DB edits |
| 20 | Operations | `operations/RUNBOOK.md` + `operations/INCIDENT_RESPONSE.md`: runbook, incident process, ownership | on-call steps written |

ADRs (`docs/adr/ADR-NNN-*.md`: Context, Decision, Alternatives, Consequences) are written whenever a step makes a structural choice (DB engine, ID strategy, tenancy model, cache, async processing, provider).

## C. Data Architecture Gate — 35 items answered before any migration

Write each answer (or `N/A — reason`) in `DATA_ARCHITECTURE.md`. `plan_check.py` looks for these headings/keywords.

1. Domain entities — 2. Relationships (1:1, 1:N, N:N) — 3. Ownership (owning context per entity) — 4. Cardinality / expected volume (rows now, in 1 year, growth) — 5. Primary and public IDs (owner default: BIGINT PK + `public_id` ULID/UUIDv7; never expose sequential IDs) — 6. Foreign keys — 7. Nullability — 8. Uniqueness (tenant-scoped: `UNIQUE(tenant_id, email)`) — 9. Business invariants -> DB constraints — 10. Lifecycle / status — 11. State transitions — 12. Mutable vs immutable data — 13. Deletion strategy per entity (hard delete, soft delete, archive, deactivate, anonymize; soft delete is never a default) — 14. Historical snapshots (e.g. invoice billing name/address/tax id at issue time) — 15. Normalization (3NF by default) — 16. Denormalization by design (each one justified) — 17. Access patterns (the real reads) — 18. Indexes derived from access patterns — 19. Expected data volume and its consequences (archiving, partitioning, summary tables, read replica) — 20. Transaction boundaries — 21. Concurrency control (optimistic `version`, `SELECT … FOR UPDATE`, atomic conditional updates) — 22. Idempotency (`idempotency_key`, `external_event_id UNIQUE`) — 23. Money representation (`amount_minor BIGINT` + `currency CHAR(3)`, never FLOAT) — 24. Date/time strategy (store UTC; `created_at`, `updated_at`, `occurred_at`, `processed_at`, `scheduled_at`, `effective_at` are different facts) — 25. Multi-tenancy model (owner default: shared DB + `tenant_id`, server-derived, foreign tenant -> 404) — 26. Audit logs (who, what, when, from where, before, after) — 27. PII classification (Public / Internal / Confidential / Restricted) — 28. Encryption (hashed passwords, hashed/encrypted tokens, encrypted casts for sensitive columns; never logged) — 29. Retention per data class (sessions, tokens, audit, temp files, analytics) — 30. Archiving — 31. Backup — 32. RPO / RTO — 33. Migration strategy (expand/contract for renames and type changes) — 34. Replication / scaling — 35. Reporting / analytics strategy (OLTP vs reporting tables/exports).

## D. Method rules (how to fill the gate)

- **Invariants live in the database where possible.** Application validation protects the application; constraints protect the data. Map every BR/invariant to `NOT NULL`, `UNIQUE`, `FOREIGN KEY`, `CHECK` (enforced in MySQL 8.0.16+), generated columns or triggers only as last resort; what cannot be a constraint is enforced in one domain service and tested.
- **Referential actions are business decisions.** Deleting a customer never cascades to orders (historical records): `RESTRICT` or archive. `CASCADE` only for true composition (order -> order items while the order is a draft).
- **Lifecycle = state machine.** `status` is an enum backed by a transition table in code (and documented in STATE_MACHINES.md); invalid transitions are rejected and tested.
- **Immutable financial facts.** Money, stock, credits and issued documents are append-only: correct with a reversal or revision record, never an UPDATE.
- **Snapshots on purpose.** Copy values that must reflect "what was true at that time" (invoice party data, prices, tax rates) and document them as denormalization by design.
- **Indexes come from access patterns, not guesses.** List each query (`tenant_id = ? AND status = ? ORDER BY created_at DESC`) and derive the composite index (`(tenant_id, status, created_at)`); verify with `EXPLAIN`.
- **Concurrency is designed, not hoped for.** The "last item bought twice" case is solved by an atomic conditional update (`UPDATE stock SET qty = qty - 1 WHERE id = ? AND qty >= 1`, check affected rows) or `SELECT … FOR UPDATE` inside the transaction, plus idempotency keys for retries.
- **Transaction boundary first, async second.** Decide which steps commit together (order + items + stock reservation + payment record) and which are queued after commit via the outbox.

### MySQL 8.4 adaptations (the owner's engine)

| Generic advice | MySQL 8.4 equivalent |
|---|---|
| Partial index (`WHERE deleted_at IS NULL`) | Not supported: index a generated column (e.g. `active_key` that is NULL when deleted) or include the column in a composite index |
| Materialized view | Not supported: summary table maintained by jobs/events, documented as derived data |
| Native UUID type | `BINARY(16)` with `UUID_TO_BIN(uuid, 1)` for UUIDv1-ordering, or CHAR(26) ULID (owner default via Laravel `ulid()`) |
| Partitioning | Available but restricts FKs: prefer archiving tables + time-based purge jobs |
| Point-in-time recovery | Binary logs + full backups (mysqldump/XtraBackup) and a tested restore |
| ENUM type | Allowed for small fixed sets; prefer VARCHAR + CHECK or a lookup table when values change |

## E. Data dictionary template (one row per important column)

| Field | Meaning | Type | Nullable | Rules |
|---|---|---|---|---|
| `id` | internal identifier | BIGINT UNSIGNED | No | PK, never exposed |
| `public_id` | external identifier | CHAR(26) ULID | No | UNIQUE |
| `tenant_id` | owning tenant | BIGINT UNSIGNED | No | FK tenants, server-derived |
| `status` | lifecycle state | VARCHAR(20) | No | transitions in STATE_MACHINES.md |
| `total_minor` | total amount | BIGINT | No | CHECK (total_minor >= 0) |
| `currency` | ISO 4217 code | CHAR(3) | No | always with an amount |

## F. API contract before the frontend

Each endpoint: method + path, auth, input schema, output schema, errors with stable codes: `400 VALIDATION_ERROR`, `401 UNAUTHORIZED`, `403 FORBIDDEN`, `404 NOT_FOUND` (also foreign tenant), `409 CONFLICT` (state/version/idempotency conflict), `422 BUSINESS_RULE_VIOLATION` (a BR id in the body), `429 RATE_LIMITED`. OpenAPI 3.1 is the default format (`api-design.md`).

## G. Delivery gates and the production docs pack (owner framework, 2026-10-03)

**Order of work:** Idea → Discovery → Product brief → PRD → Business rules → NFR → Domain model → Bounded contexts → Project map → System context → System design → Software architecture → Backend architecture → Database design → API / events / webhooks → Security architecture → Interface specifications → WBS / roadmap → Implementation → Testing → CI/CD → Production readiness review → Release → Observability → Incident / operations → Continuous evolution.

**What each document answers:** Product brief = what is the idea · PRD = what the product must do and why · Business rules = what must never break · Domain model = the real concepts · Project map = the parts and how they connect · System design = how the whole system works · Architecture = how code and components are organized · Backend architecture = how operations and rules execute · Database design = how the truth is stored · API design = how systems talk · Security = how system and data are protected · Operations = how it runs and is watched in production · Testing = how we prove it is correct · ADR = why the important technical decisions were made.

**Pack:** `assets/production-docs/` (scaffold into a repo with `python scripts/pb.py scaffold-docs --root <repo>`; never overwrites; a doc with the same file name anywhere in `docs/` wins). Layout: `PROJECT_MAP.md` (index + traceability), `product/` (PRODUCT_BRIEF, PRD with 23 sections, BUSINESS_RULES, NON_FUNCTIONAL_REQUIREMENTS, ROADMAP), `domain/` (DOMAIN_MODEL, BOUNDED_CONTEXTS, STATE_MACHINES), `architecture/` (SYSTEM_CONTEXT, SYSTEM_DESIGN, ARCHITECTURE, BACKEND_ARCHITECTURE, DEPLOYMENT_ARCHITECTURE), `interfaces/INTERFACE_SPEC.md` (copy per application), `data/` (DATA_ARCHITECTURE, RETENTION_POLICY), `api/` (API_CONTRACTS, EVENTS, WEBHOOKS), `security/SECURITY.md`, `operations/` (OBSERVABILITY, BACKUP_RECOVERY, INCIDENT_RESPONSE, RUNBOOK), `delivery/` (CI_CD, BACKLOG with WBS and Epic/Feature/Story/Task), `testing/` (TEST_STRATEGY, ACCEPTANCE_TESTS), `release/CHECKLIST_PRODUCTION_READINESS.md`, `adr/`. Each scaffold starts with a `<!-- pb:template` line: delete it only when the file holds project facts or `N/A - reason`; `plan_check` ignores files that still carry it, so an empty template can never pass a gate.

**Gates** (`python scripts/plan_check.py --root <repo> --gate <name>`, cumulative: a later gate fails while an earlier one fails):

| Gate | Passes when | Blocks |
|---|---|---|
| 1 Product ready | steps 01-04, out of scope stated; requirements testable; business rules explicit | domain/architecture work |
| 2 Engineering ready | steps 05-14 + ADRs, Data Architecture Gate 35/35, architecture drivers ranked, critical flows, consistency model per domain, SPOFs, dependency rules | migrations (the data gate alone already blocks them) and module code |
| 3 Implementation ready | testing strategy, WBS/roadmap with exit criteria, `TEST-xxx` acceptance tests, every FR/BR id named by a test, every FR id in a work item (project map / backlog), staging environment | starting a release's implementation |
| 4 Production ready | steps 16-20, incident process, rollback, SLOs, and every item of `release/CHECKLIST_PRODUCTION_READINESS.md` ticked **with `evidence:` on the line** (a bare tick counts as open) | the first production release and any release that changes money, auth, tenancy or data shape |

Gate 4 is evidence, not intent: tick a checklist item only after the command, test, file or screenshot exists, and name it. An agent that ticks without evidence is hallucinating; `plan_check` reports it under `readiness.ticked_without_evidence`.

**Webhooks** (both directions): inbound = verify signature → persist event (unique provider event id) → respond fast → queue → process idempotently, tolerating duplicates and out-of-order delivery; outbound = signed, delivery ids, retry schedule, max attempts, dead-letter state, customer-visible delivery log.

**Retention:** a matrix per data category (sessions, audit logs, financial records, PII) with retention, archive, delete/anonymize and reason; deletion workflow (trigger, grace period, legal hold, anonymization, backup expiry) and a check that the retention jobs really run.

**Incidents:** SEV-1/2/3; detect → triage → contain → mitigate → recover → review; roles (commander, tech lead, comms, scribe); postmortem without blame (what happened, why, why it was not caught, actions with owners and dates).

**Load tests** (before gate 4 for public or high-volume systems): baseline, peak, spike, soak, stress; migration tests on production-like volume.

## I. Document roles, boundaries and traceability

| Document | Answers | Never contains | Primary owner (one person may hold several roles) |
|---|---|---|---|
| Product brief | What is the idea? | features list, tech | product |
| PRD (23 sections, `product/PRD.md`) | What must the product do, for whom, and why? Goals, non-goals, actors, journeys, FR, edge cases, roles, success metrics, release scope, open questions | HOW: DB engine, tables, Redis, REST, frameworks | product |
| Business rules | What must always be respected? | UI wording | product + tech lead |
| Domain model | What concepts does the business contain? | tables | architect + product + tech lead |
| Project map | What does the whole project contain, where, why, how it connects, status? (an index, not a copy) | duplicated content of other docs | tech lead |
| System context / system design | How does the overall system work? | code layout | architect |
| Architecture / backend architecture | How is the software organized; how do rules execute? | product decisions | backend lead |
| Database design | How is persistent truth modeled? | | backend / data |
| API design | How do clients and systems communicate? | | backend lead |
| Interface spec (one per application) | How does each application behave (screens by journey, states, roles)? | | product designer |
| WBS / backlog | What work must engineers execute? (Epic, Feature, Story, Task) | architecture | tech lead |
| Roadmap | In what order do we deliver it? | architecture | product |
| ADR | Why did we make an important technical decision? | | the engineer deciding |
| Runbooks / operations | How do we operate it in production? | | ops |

**PRD = WHAT + WHY; architecture = HOW.** "Users are notified when an order changes" is a PRD line; "OrderStatusChanged event, queue, notification worker, push/email" is architecture. `plan_check` lists technical words found in the PRD under `advisory.prd_tech_leaks`: move them to architecture/ or an ADR.

**Flow:** Discovery, then Product brief, then PRD, then domain model, then project map, then system design and architecture, then database and API design, then UX/UI, then engineering plan and backlog, then implementation, QA, release, monitoring. After the domain model three tracks run in parallel: UX/UI, architecture, API/data design. A PRD never goes straight to code.

**Traceability chain** (kept in the project map's traceability table): `FR-021 refund a payment` to `BR-014 a captured payment is refunded once` to `POST /payments/{id}/refund` to `RefundPaymentAction` to table `payment_refunds` to event `PaymentRefunded` to tests `PAY-REFUND-001/002` to the work item. `plan_check` reports FR/BR ids with no acceptance test and FR ids with no work item; gate 3 fails on either.

## H. Architecture fitness rules (checked in review; the timeout rule also by `vuln_scan.py`, CWE-400)

No business logic in controllers · no cross-context DB writes (only through the owner context's contract) · every external call has a timeout (and bounded retries with backoff) · jobs are idempotent · critical actions are audited · the domain never depends on the framework or directly on a provider (payment provider, Redis, HTTP): ports inward, adapters outward · error model maps domain → application → transport errors in one place.

## Red flags

- Migrations or controllers written before FR/BR/NFR, the domain model and the Data Architecture Gate exist.
- A table whose owner context is unknown, or two contexts writing the same table.
- A business rule enforced only in a controller or only in the UI.
- `status` strings without a documented transition table; `deleted_at` on every table by default; `ON DELETE CASCADE` on historical records.
- Indexes added "just in case"; no access pattern list; no volume estimate for high-growth tables.
- FLOAT money, local-time timestamps, global UNIQUE on tenant data, sequential IDs in URLs.
- No RPO/RTO, no restore test, manual production schema changes, renames without expand/contract.
- Structural decisions with no ADR.
- Readiness checklist ticked without evidence; templates left with their `<!-- pb:template` line and treated as done.
- An external HTTP call without a timeout; a webhook processed before its signature is verified or without a stored event id.

## How project-brain uses this

Loaded by the `planner`, `db` and `api` roles (`workflows/_knowledge.snippet.js`) and by playbooks 3.1 (new project), 3.6 (database) and 3.7 (backend/API). `workflows/plan-from-prd.js` produces the artifacts of section B and answers section C; its critic checks every step and all 35 gate items. `python scripts/plan_check.py --root <repo>` verifies the artifacts deterministically; `workflows/map-loop.js` runs it and refuses database/migration items until the data gate passes, scheduling the missing planning item first.
