# Planning playbook: idea -> PRD -> SRS -> PROJECT_MAP -> phases -> task packets

> Order of work: `system-engineering-method.md` (owner standard; §G = delivery gates and the production docs pack in `assets/production-docs/`). This file details requirements, slicing, estimation and ADRs inside that order.

Role: convert approved product evidence into testable requirements, contracts, architecture, and executable task packets. Do not make the PRD a dump of every concern. Owner constraints: `owner-profile.md`. Gates: `quality-gates.md`. Paraphrased from the cited books; official URLs verified where given.

## 1. Pipeline and artifact roles

| Artifact | Answers | Rule |
|---|---|---|
| IDEA / PRD | Why, for whom, what outcome | Goals and non-goals, no implementation. One section per capability. |
| SRS | What the system must do, testably | Numbered requirements + acceptance. Every row traces to a PRD goal. |
| PROJECT_MAP | In what order, and what is wired | `[SYSTEM_FLOW]`, `[ORPHANS & PENDING]`, phases, task ids. |
| Task packet | One reviewable change | Criterion, files, tests, rollback (see `quality-gates.md`). |

Default: do not write a document that no later step reads. Deviate only when the owner asks.

Outputs to maintain: `PRD.md`, `SRS.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`, `API_CONTRACTS.md`, `NON_FUNCTIONAL_REQUIREMENTS.md`, `INTEGRATIONS.md`, `TEST_STRATEGY.md`, `OPERATIONS.md`, `RELEASE_STRATEGY.md`, `PROJECT_MAP.yaml`. (Wiegers & Beatty, Software Requirements, ch. 1-5.)

## 2. Impact mapping: cut scope before writing requirements

Chain: Goal -> Actor -> Impact (behavior change) -> Deliverable (Adzic, Impact Mapping).
- Goal must be measurable (e.g. "cashier closes a shift in under 2 min", "tenant onboarded without owner help").
- Every deliverable must hang off an actor and an impact. A deliverable with no parent is cut or moved to "could".
- Record the map as 4 indented lists in the PRD. No diagrams needed.

## 3. Story map, walking skeleton, vertical slices

(Patton, User Story Mapping, ch. 1-8.)
1. Backbone: list user activities left to right in narrative order (Sign up -> Configure shop -> Sell -> Close shift -> Report). Under each, tasks; under tasks, details sorted by priority.
2. Walking skeleton = thinnest end-to-end path through every backbone activity and every architectural layer. Build it first, even if ugly.
3. Release slices are horizontal cuts across the whole map, not column-by-column.
4. Slice vertically: one slice touches migration + model + service + endpoint + UI + test and ends in observable behavior.
5. Horizontal tasks ("build all models", "build users") are forbidden unless pure infrastructure with a verification command. Split by observable behavior and test cycle.

Project map decomposition: `Epic -> Capability -> Feature -> Workflow -> Task -> Verification`. Order by dependency and risk, not UI navigation. Every task is independently reviewable and carries the mandatory packet from `quality-gates.md`.

Default skeleton for the owner's SaaS stack: tenant creation -> login -> one core record created through the real UI -> one report row -> running on the declared stack (MySQL 8.4) at the URL the owner checks. Do not create a staging environment the project does not already have. Anything missing from this path is added to the skeleton before polishing any feature.

Splitting patterns (apply in order): by workflow step; by role; by business-rule variation; by data variation (one currency/locale first); happy path vs failure path; by interface (API first, UI after) only when the API has its own consumer; by CRUD verb. Never split by layer.

## 4. Appetite and MVP scoping

(Singer, Shape Up, ch. 3; official: https://basecamp.com/shapeup/1.2-chapter-03.)
- Appetite is a time budget, not an estimate. Fixed time, variable scope. Small batch: 1-2 weeks for a small team; big batch: a full 6-week cycle.
- Default for the solo owner: small batch = 1-3 working days of agent-plus-owner time per slice; big batch = one phase. If the work does not fit, cut scope or split; do not extend.
- A shaped pitch has: problem, appetite, solution sketch (rough, not a design), rabbit holes, no-gos. Write these in the PRD capability section before tasks exist.
- Circuit breaker: when a slice exceeds its appetite, stop, record in `HANDOFF.md`, and re-shape. Do not silently continue.
- MVP = skeleton + the smallest set of slices that lets one real tenant complete the core job and be billed (manually is fine). Everything else is "could".
- MoSCoW tags (must/should/could/won't) mirror `priority` in the requirement contract. "Won't (this release)" is written down so it is not rediscovered as a bug.

## 5. Dependency order (default)

1. Infrastructure: repo, env, one test command, DB engine as declared (MySQL 8.4), queues, deploy target, logging.
2. Identity: users, tenants, roles/permissions, sessions, locale preference.
3. Core domain: the entities and workflows that define the product.
4. Money: pricing, invoices, payments, taxes, stock valuation. Needs identity + core domain first; owner gate applies.
5. Reporting and exports: read models over finished data.
6. Polish: onboarding, empty states, marketing pages, SEO.

Deviate only when risk-first (section 6) forces an earlier spike. Tenancy and authorization are never retrofitted: they ship with the first domain table.

## 6. Risk-first sequencing

- Keep a risk list in PROJECT_MAP: technical (unknown API, hardware, offline sync), business (payment rules), integration (third-party quota), data (migration).
- Each risk gets a spike: a time-boxed task whose output is a decision or a passing/failing test, not production code. Default max 1 day.
- Order: skeleton -> highest-risk spike -> riskiest slice -> the rest. Default high-risk items for this owner: POS hardware and offline sync, payment gateways, Arabic/RTL printing.
- A spike result is recorded as an ADR or a `DECISIONS.md` line.

## 7. Writing testable requirements

(Wiegers & Beatty, Software Requirements, ch. 11, 17; Adzic, Specification by Example, ch. 4-6.)
- Requirement contract: each requirement carries `id` (stable, unique), `type` (functional / business-rule / security / privacy / accessibility / localization / performance / resilience / compliance / migration), `priority` (must / should / could), `actor`, `trigger`, `preconditions`, `rules`, `outcomes`, `failure_cases`, `acceptance` (verifiable criteria), `source` (IDEA ref or owner decision), `owner`, `status`. A vague outcome or unverifiable acceptance criterion means the requirement is not ready.
- Coverage: functional behavior, business rules, security, privacy, accessibility, localization, performance, capacity, availability, resilience, observability, retention, compliance, operations, migration, rollback, deprecation.
- ID scheme: `<DOMAIN>-<NNN>` (e.g. `POS-014`), never reused, never renumbered. Withdrawn ids stay with `status: deprecated`.
- One requirement = one testable statement. The words "and", "or", "etc.", "fast", "easy", "appropriate", "support", "handle" in a rule are red flags.
- Modal verbs per RFC 2119 (https://www.rfc-editor.org/rfc/rfc2119): MUST = mandatory, SHOULD = valid reasons to deviate exist, MAY = optional. Map them to must/should/could.
- Quantify non-functional rules: p95 latency on a named endpoint with N rows, max upload size, retention days. No number, no requirement.
- Acceptance: Given/When/Then, one example per business-rule branch, plus at least one failure example.

```gherkin
Rule: POS-014 A sale cannot be finalized when stock would go negative, unless the tenant allows backorders
  Example: blocked sale
    Given tenant "A" has backorders disabled and product "P1" stock 2
    When the cashier finalizes a sale of 3 x "P1"
    Then the sale is rejected with error "stock.insufficient" and stock stays 2
  Example: tenant isolation
    Given tenant "B" has "P1" stock 10
    When tenant "A" attempts the same sale
    Then tenant "B" stock is still 10
```

Gherkin keywords verified (https://cucumber.io/docs/gherkin/reference/): Feature, Rule, Example/Scenario, Given/When/Then/And/But, Background, Scenario Outline. Rule groups examples under one business rule.

Specification by Example practices to apply: derive scope from goals; use concrete data (named tenants, real amounts, dates); keep examples as living docs and test source; refine examples with edge data before coding; automate only examples with long-term value. Use realistic values, including Arabic names and MAD/EUR amounts.

Mapping to code: each example becomes one Pest/PHPUnit test or Playwright check named `<REQ-ID>: <rule>`. A requirement without a test name is `status: specified`, not `verified`.

## 8. Blind-spot hunt (run per capability before status `ready`)

Record findings as B-numbered decisions (`09_BLIND_SPOTS.md` convention) when the repo uses it.

| Axis | Ask |
|---|---|
| Roles | Owner, admin, staff, support, API client, anonymous, suspended user. Who can NOT do this? |
| States | Draft, pending, active, suspended, cancelled, archived, deleted. Which transitions are legal, who triggers each? |
| Failure | Network drop mid-action, double submit, timeout, third party down, partial success, queue retry, duplicate webhook. |
| Data | Empty, one row, 10k rows, very long text, emoji, Arabic/Latin mix, zero/negative/decimal money, timezone and DST, deleted parent. |
| Abuse | Enumeration, mass assignment, cross-tenant id guess, rate limits, file upload, replay. Hand to `security-protocol.md`. |
| Tenancy | Does every query, cache key, job, file path, and log line carry the tenant? |
| i18n | ar/fr/en strings, RTL layout, number and date format, plural rules, sort order, PDF/receipt fonts. |
| Money | Rounding rule, currency, tax inclusive/exclusive, refunds, audit trail, immutability after close. |
| Ops | Who is alerted, how data is restored, how a bad deploy is rolled back. |
| Lifecycle | Create, edit, delete, restore, export, import, migrate old data. |

Walk the story map once per axis. Each finding becomes a requirement, a task, an explicit "won't", or an `[ORPHANS & PENDING]` row. No finding stays as prose.

## 9. Estimation

(Cohn, Agile Estimating and Planning, ch. 6-10; Brooks, The Mythical Man-Month, ch. 2-3.)
- Default: relative sizing on a coarse scale (S/M/L or 1-2-3-5-8) and ranges, never single-point dates.
- Report as "likely X-Y working days, main risk Z". If Y/X > 3, the task is under-specified: split or spike.
- Calibrate against a completed similar task in the change log, not hope.
- Tasks above 1 day of agent work are split. Tasks that cannot be split get a spike first.
- No invented calendar dates; estimates require known scope, team, capacity, and uncertainty. Give sequence and size.
- Brooks: adding people to a late project delays it; effort and elapsed time are not interchangeable. Applied here: more parallel agents do not shorten work with shared files or unresolved design. Parallelize only independent slices with disjoint file sets.
- Brooks, conceptual integrity: one owner of the data model and API shape. Delegated agents implement the contract; they do not redesign it.
- Brooks, second-system effect: resist "while we are here" additions during rewrites.
- Show risk as an explicit range; do not pad each task.

## 10. Definition of Ready / Done

Ready (task may enter `ready`): requirement id exists; acceptance written; dependencies done; blind-spot axes checked; files and surfaces named; test location known; owner gate flagged; size <= 1 day.

Done (maps to `verified`; `accepted` needs the owner; see `quality-gates.md`): examples executed and passing on the real stack; tests green; UI checked at desktop and phone width in each locale; `[ORPHANS & PENDING]` updated; docs and change log synced; evidence recorded.

INVEST for stories (Cohn/Patton): independent, negotiable, valuable, estimable, small, testable. A story failing "valuable" is infrastructure and is labeled so.

## 11. Traceability

Chain: `GOAL -> REQ -> TASK -> FILES -> TEST -> EVIDENCE -> CHG/ACL -> RELEASE` (the release tag or version that shipped it, logged in the change log and `HANDOFF.md`).

```yaml
- req: POS-014
  task: T-0231
  files: [app/Actions/Sales/FinalizeSale.php, tests/Feature/FinalizeSaleTest.php]
  test: "POS-014: blocked sale"
  evidence: "pest --filter POS-014 -> 3 passed"
  chg: ACL-118
```
- Check with grep: every REQ id appears in at least one test name; every test name citing a REQ id points to a live requirement.
- Orphan requirement (no task) and orphan code (no requirement) are both tracker findings.

## 12. [SYSTEM_FLOW] and [ORPHANS & PENDING]

`[SYSTEM_FLOW]`: the runtime path of data and control as numbered steps with actor, surface, route, table, job, event. One block per flow (sale, signup, payout). Every code line must serve a flow here.

```text
[SYSTEM_FLOW] FLOW-03 Cashier sale
1. Electron POS -> POST /api/v1/sales (idempotency key) [POS-014]
2. FinalizeSale action -> stock decrement (tx) -> sales, sale_items
3. Queue: SendReceipt, SyncToCloud
4. Admin dashboard reads daily_totals
```

`[ORPHANS & PENDING]`: anything built but not wired, wired on one side only, or planned but absent. Row: `id | what | missing side | blocking req | owner`. A row leaves only when both ends work and are verified. Both ends of every cross-surface flow (platform and merchant support, API and UI, POS and cloud) appear in the same flow block; a one-sided flow is an orphan.

## 13. Phases

Default for a new product: P0 skeleton + infrastructure; P1 identity + tenancy; P2 core domain slices 1..n; P3 money; P4 reporting/export; P5 hardening (security review, backup/restore drill, load sanity); P6 release. Each phase has an exit check (a demo script of observable behavior), not a date. Phase exit is a quality gate.

## 14. Decision records and change control

ADR (Nygard, https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions): short noun-phrase title; context; decision in active voice; status (proposed / accepted / deprecated / superseded, with link); consequences including negatives. One to two pages; numbers never reused; superseded records stay. Follow the repo's existing convention (`DECISIONS.md` B-/D- ids, or `docs/adr/NNNN-title.md`); never start a second system.

```markdown
# ADR-0007 Database queue driver for POS sync
Status: accepted (delegated, open to reversal)
Context: this client runs on shared hosting without Redis or Supervisor (fallback in `backend-architecture.md` sec. 7).
Decision: We use the database queue until p95 job wait exceeds 5 s.
Consequences: simpler ops; lower throughput; revisit trigger recorded in OPERATIONS.
```

Write an ADR only when the choice is hard to reverse, spans modules, or records an owner override. Small choices: one line in `DECISIONS.md`.

Change control when the owner overrides docs (precedence in `SKILL.md`):
1. Apply the instruction.
2. Edit every affected doc section in the same change (PRD, SRS id, map, flow).
3. Log date, old rule, new rule, sections touched, decider.
4. If a requirement changes, keep the old id as `deprecated` with a pointer, add a new id, rename tests.
5. Money, auth, tenancy, retention: state the risk once, offer the safe variant, record the conflict.

## 15. Architecture coverage

Cover per project, in the architecture docs:
- system context, trust boundaries, containers/components, ownership, communication, events and queues;
- entity lifecycle, constraints, indexes, tenancy, transactions, consistency, idempotency, deletion and audit;
- API/event/webhook contracts, authentication, authorization, validation, errors, pagination, rate limits, versioning, replay and retries;
- external dependencies, quotas, costs, timeouts, circuit breaking, degraded mode, exit plan;
- environments, configuration, secrets, builds, deployment, scaling, backup, restore, disaster recovery, monitoring and support.

Use the simplest architecture satisfying measured constraints. Record significant choices as decision records with alternatives and consequences (section 14).

## Red flags
- Requirement with no id, no acceptance, or untestable adjectives.
- Task is a layer ("create models") or exceeds 1 day.
- No walking skeleton before feature work; polish before the core flow.
- Single-number dates or estimates; no range or risk.
- Money or permissions built before identity/tenancy exist.
- Flow built on one side only; `[ORPHANS & PENDING]` empty while the map is incomplete.
- Slice overran its appetite with no recorded re-shape.
- Parallel agents editing the same files or redefining the data model.
- Owner override applied in code but not in docs.
- Deliverable with no actor/impact in the impact map (scope creep).
- Capability marked `ready` with blind-spot axes skipped.

## How project-brain uses this
- Load when: writing or revising PRD/SRS/PROJECT_MAP, breaking work into tasks, sizing, resuming a project with unclear order, or handling an owner override of docs. Use `idea-protocol.md` first for new ideas.
- Gates served: requirements -> architecture (ids, acceptance, blind-spot sweep); planned (ready checklist, dependency order); verifying (traceability evidence).
- Domain criteria to cite in requirements and task packets: `compliance-payments.md` (money phase P3, privacy/consent, owner-gate batch), `operations-monitoring.md` (`OPERATIONS.md`, RPO/RTO, P5/P6 exits), `mobile-flutter.md` and `desktop-electron.md` (surface-specific acceptance and release checklists).
- Record: requirements in the repo SRS; flows and orphans in PROJECT_MAP; ADRs/B-ids in the repo decision log; spike results and delegated assumptions in `.project-brain/DECISIONS.md` as `delegated, open to reversal`; phase exits and overruns in `HANDOFF.md`; ids per change in the change log.
