export const meta = {
  name: 'pb-plan-from-prd',
  description: 'project-brain: system engineering plan from a PRD/idea - requirements (FR/BR/NFR), domain and contexts, data architecture gate, contracts, security, operations, ADRs, project map - then a critic with plan_check',
  whenToUse: 'New project or a big new module: PRD/idea then project map. args: {repo, sources[], out}',
  phases: [
    { title: 'Extract', detail: '6 extractors following the 20-step system engineering method' },
    { title: 'Write', detail: 'domain model, data architecture (35-item gate), state machines, ADRs, contracts, project map' },
    { title: 'Critic', detail: 'plan_check + completeness, traceability and scope critic' },
  ],
}

// args: { repo: "C:/path", sources: ["docs/prd.md", "docs/basic-idea.md"], out: "docs/PROJECT_MAP.md" }
const A = args || {}
const PB = '~/.claude/skills/project-brain'

// ---- Knowledge routing (shared snippet; injected into each workflow by build.py) ----
// Every Claude agent in a workflow loads the project-brain skill, then ONLY the files for its role.
const PB_DIR = '~/.claude/skills/project-brain'
const KNOW = {
  planner: ['references/system-engineering-method.md (the 20 steps, data gate, section G delivery gates and docs pack)', 'references/planning-playbook.md', 'references/tracker-protocol.md'],
  surfaces: ['references/multi-surface-architecture.md'],
  db: ['references/system-engineering-method.md (sections C-E: 35-item data gate, MySQL adaptations, data dictionary)', 'references/db-schema-design.md'],
  backend: ['references/backend-architecture.md', 'references/engineering-principles.md', 'references/security-baseline.md (part B + the classes your change touches)'],
  api: ['references/api-design.md', 'references/backend-architecture.md', 'references/security-baseline.md (part B)'],
  frontend: ['references/frontend-system-design.md (incl. Owner UI bar)', 'modules/ui/README.md',
    'modules/ui/apple-hig/routing-index.md (then only the distilled/*.md files for the components you touch)',
    'modules/ui/design-taste-frontend/MODULE.md (pre-flight check section)', 'modules/ui/ui-ux-pro-max/references/ui-ux-rules.md'],
  ui_audit: ['modules/ui/README.md', 'references/frontend-system-design.md (anti-slop checklist, review procedure, Owner UI bar)', 'modules/ui/apple-hig/routing-index.md'],
  security: ['references/security-baseline.md (owner 14 CWE classes + 20 backend fundamentals)', 'modules/review/security-review/README.md', 'modules/review/security-review/LARAVEL_SECURITY.md',
    'modules/review/security-review/agents/security-auditor.md', 'references/security-protocol.md'],
  review: ['modules/review/code-review/README.md', 'references/engineering-principles.md'],
  verify: ['references/quality-gates.md', 'agents/pb-verifier.md'],
  implement: ['agents/pb-implementer.md', 'references/engineering-principles.md'],
  assets: ['references/codex-delegation.md', 'references/frontend-system-design.md (Owner UI bar section)'],
  docs: ['references/planning-playbook.md', 'references/memory-protocol.md'],
  deploy: ['references/deploy-protocol.md', 'references/operations-monitoring.md (release + rollback sections)'],
  mobile: ['references/mobile-flutter.md', 'references/api-design.md (client sections)'],
  desktop: ['references/desktop-electron.md', 'references/multi-surface-architecture.md (offline sync section)'],
  compliance: ['references/compliance-payments.md'],
  ops: ['references/operations-monitoring.md'],
  graph: ['references/operating-protocol.md sec. 1 graphify CLI only (affected/explain/path/query --budget); open modules/brain-graph/BRAIN_GRAPH.md ONLY to build or rebuild a graph'],
}
const WITH_GRAPH = ['planner', 'implement', 'review', 'verify', 'security', 'backend', 'api', 'db', 'frontend', 'mobile', 'desktop']
function skills(roles) {
  const rs = [].concat(roles || [])
  const all = rs.some(r => WITH_GRAPH.includes(r)) ? [...rs, 'graph'] : rs
  const files = ['references/operating-protocol.md (sec. 1 router, sec. 2 anti-hallucination, sec. 3 clean-code, sec. 4 tokens)', ...new Set(all.flatMap(r => KNOW[r] || []))]
  return `SKILL SETUP (do this first):
1. Load the project-brain skill: call the Skill tool with skill "project-brain". If the Skill tool is unavailable, read ${PB_DIR}/SKILL.md sections 1 and 4 instead.
2. Apply its commitments (sec. 1) and execution loop (sec. 4) to your task. The owner profile is ${PB_DIR}/references/owner-profile.md.
3. Read ONLY these files for your role (${[].concat(roles || []).join(', ')}), by relevant section (Grep + offset for long files):
${files.map(f => '   - ' + PB_DIR + '/' + f).join('\n')}
4. Use the router: code_guard.py find / graphify affected|explain|path|query --budget BEFORE opening files; Grep + offset for big files.
5. If you write code: code_guard.py find before creating anything; after, code_guard.py scan --changed <your files> must exit 0; keep functions <= 40 lines and files <= 300.
   Touched translation files: i18n_check.py --changed <files> must exit 0. Before any commit: secret_scan.py --files <files> must exit 0.
   Backend/API code: vuln_scan.py --changed <files> must exit 0, and you walk the 14 CWE classes of references/security-baseline.md for every route/action you touched.
   (code_guard: python ${PB_DIR}/scripts/code_guard.py ; graph: graphify ... from the repo root when graphify-out/ exists)
6. The project's own docs and owner decisions override these defaults; the existing repo layout wins.
7. Role limits: reviewers, verifiers, auditors and planners that were told not to edit must NOT write project files or
   HANDOFF/change-log entries (commitment 10 applies to implementers and sync agents only).
8. Tools you lack: if a needed tool (browser, Skill, MCP) is unavailable, report that check as NOT RUN with the reason;
   never describe a page, file or command output you did not actually obtain.
`
}
// Budget guard: cap on agents per run INCLUDING child workflows (args.maxAgents, default 12 = agentic-workflow.md sec. 7),
// plus the turn's token budget if one is set. Raise maxAgents only when the owner asked for a larger run.
let AGENTS_USED = 0
const MAX_AGENTS = (args && typeof args.maxAgents === 'number') ? args.maxAgents : 12
function spend(label) {
  if (AGENTS_USED >= MAX_AGENTS) { log('budget guard: agent cap ' + MAX_AGENTS + ' reached, skipped ' + label); return false }
  if (budget.total && budget.remaining() < 20000) { log('budget guard: token budget nearly spent, skipped ' + label); return false }
  AGENTS_USED++
  if (AGENTS_USED % 10 === 0) log('budget: ' + AGENTS_USED + '/' + MAX_AGENTS + ' agents used')
  return true
}
// Run a child workflow inside this run's budget; its agents count against the parent cap.
async function child(file, childArgs) {
  const left = MAX_AGENTS - AGENTS_USED
  if (left <= 0) { log('budget guard: no budget left for child ' + file); return null }
  const res = await workflow({ scriptPath: PB_DIR + '/workflows/' + file }, { ...childArgs, maxAgents: left })
  AGENTS_USED += (res && res.agents_used) || 0
  return res
}
const kagent = (roles, prompt, opts) => spend((opts && opts.label) || 'agent')
  ? agent(skills(roles) + '\n' + prompt, opts) : Promise.resolve(null)
// ---- end knowledge ----
const SRC = `Repository: ${A.repo}. Source documents (canonical, never contradict them): ${(A.sources || []).join(', ')}.`
const METHOD = `${PB}/references/system-engineering-method.md`
const DIMS = [
  ['requirements', ['planner'], `Steps 01-04 of ${METHOD}: product definition; FR-xx (actor, acceptance criterion); BR-xx business rules (each says where it is enforced: DB constraint, domain, or both); NFR-xx with measurable targets (latency P95, availability, RPO/RTO, retention, concurrency, auditability, compliance, localization). Only what the sources state or clearly imply; anything else is a PROPOSAL.`],
  ['domain', ['planner', 'surfaces'], `Steps 05-07 and 12 of ${METHOD}: domain entities (real things, not tables) with one-line meaning, relationships, aggregates; bounded contexts and a data ownership table (entity, owning context, who may write); surfaces and system architecture (modules, sync vs async, external systems); lifecycles as state machines (states, allowed and forbidden transitions, trigger, side effects).`],
  ['data', ['planner', 'db'], `Steps 08-09 and the 35-item Data Architecture Gate (section C) of ${METHOD}: conceptual then logical model, invariants mapped to DB constraints, keys (BIGINT PK + public_id ULID), FKs and referential actions as business decisions, nullability, tenant-scoped uniqueness, mutable vs immutable, deletion strategy per entity, historical snapshots, normalization and justified denormalization, access patterns and the indexes derived from them, cardinality/volume, transaction boundaries, concurrency control, idempotency, money (amount_minor + currency), UTC time fields, multi-tenancy, audit, PII classification, encryption, retention, archiving, backup, RPO/RTO, migration strategy, scaling, reporting. Use the MySQL 8.4 adaptations. Answer EVERY item (or N/A with reason). Include a data dictionary table (Field | Meaning | Type | Nullable | Rules).`],
  ['contracts', ['planner', 'api', 'security'], `Steps 10-11 of ${METHOD}: API contract per endpoint (input, output, errors 400/401/403/404/409/422/429 with stable codes, 422 carries the BR id), authorization matrix (role x surface x action), threat model per surface walking the 14 CWE classes and 20 backend fundamentals of ${PB}/references/security-baseline.md.`],
  ['operations', ['planner', 'ops'], `Steps 13-20 of ${METHOD}: events/queues (producer, consumers, idempotency key, outbox), failure handling per external call/job (timeout, retry, backoff, dead letter, compensation), testing strategy with traceability (every BR has a test), observability, deployment, backup/recovery with RPO/RTO and a restore test, migration strategy (expand/contract), operations runbook. List the ADRs needed (Context, Decision, Alternatives, Consequences).`],
  ['blindspots', ['planner'], `Contradictions, gaps, missing states/roles/failure paths, abuse cases, business-logic risks in the sources. Report them; do not resolve product questions yourself - propose a default for each.`],
]
const parts = await parallel(DIMS.map(([k, roles, d]) => () =>
  kagent(roles, `${SRC}\nProduce dimension "${k}": ${d}\nReturn compact Markdown with IDs. Do not write files.`, { label: 'extract:' + k, phase: 'Extract' })))
const bundle = DIMS.map(([k], i) => `## ${k}\n${parts[i] || '(missing: agent skipped or failed - the critic must list this as a gap)'}`).join('\n\n')

phase('Write')
const out = A.out || 'docs/PROJECT_MAP.md'
await kagent(['planner', 'surfaces', 'db'], `${SRC}\nFollow ${METHOD}. Using the material below, write or update (controlled technical English, existing repo layout wins, never overwrite the owner's source documents):
First run: python ${PB}/scripts/pb.py scaffold-docs --root ${A.repo} (production docs pack, section G of the method; it never overwrites and keeps existing docs with the same name). Fill the scaffolds in place; when a file holds project facts or "N/A - reason" for every section, delete its first "<!-- pb:template" line (plan_check ignores files that still carry it). If the repo already has an equivalent doc, update that one instead of the scaffold and delete the unused scaffold.
- docs/product/BUSINESS_RULES.md and docs/product/NON_FUNCTIONAL_REQUIREMENTS.md (BR-xx with enforcement point and test; NFR-xx with a number and a verification method)
- requirement IDs: FR tables go in docs/product/PRD.md only if the PRD is agent-maintained; if the PRD is an owner source, keep it verbatim and write the FR table in docs/product/REQUIREMENTS.md
- docs/domain/DOMAIN_MODEL.md, docs/domain/BOUNDED_CONTEXTS.md (context map, data ownership), docs/domain/STATE_MACHINES.md
- docs/architecture/SYSTEM_DESIGN.md (ranked drivers, constraints, critical flows with transaction boundary and failure points, consistency per domain, caching, concurrency, resilience, capacity, SPOFs, 10x plan), docs/architecture/ARCHITECTURE.md (style with ADR, module ownership, dependency rules, error model, fitness rules), docs/architecture/DEPLOYMENT_ARCHITECTURE.md
- docs/data/DATA_ARCHITECTURE.md (conceptual + logical model, all 35 gate items answered or N/A with reason, access patterns and the indexes derived from them, data dictionary), docs/data/RETENTION_POLICY.md
- the API contract (docs/openapi/*.yaml if the repo uses OpenAPI, else docs/api/API_CONTRACTS.md) with the error taxonomy, pagination, rate limits, idempotency, versioning; docs/api/EVENTS.md; docs/api/WEBHOOKS.md when providers or customers exchange webhooks
- docs/security/SECURITY.md (threat model, authorization matrix, 14 CWE walk-through)
- docs/operations/OBSERVABILITY.md, BACKUP_RECOVERY.md, INCIDENT_RESPONSE.md, RUNBOOK.md; docs/delivery/CI_CD.md
- docs/testing/TEST_STRATEGY.md and docs/testing/ACCEPTANCE_TESTS.md (TEST-xxx in Gherkin, each naming its FR/BR ids; every FR and BR has at least one)
- docs/product/ROADMAP.md (releases with objective, included and excluded capabilities, dependencies, risks, exit criteria)
- docs/adr/ADR-NNN-*.md for each structural decision (Context, Decision, Alternatives, Consequences)
- leave docs/release/CHECKLIST_PRODUCTION_READINESS.md unticked: items are ticked only later, with evidence
- ${out}: header (status, stack, source precedence), [SYSTEM_FLOW], surfaces map, phases in dependency order (planning artifacts first, then infra, identity, core domain, money, reporting, polish) with tasks (id, objective, requirement IDs, criterion, files/areas, tests), decisions needed from the owner (with recommended defaults), [ORPHANS & PENDING].
Scope rule: anything NOT in the source documents goes ONLY into a 'Proposed (needs owner approval)' table with a recommended default; never schedule it and never give it a requirement ID until the owner approves.
Material:\n${bundle}`, { label: 'write-artifacts', phase: 'Write' })

phase('Critic')
const critic = await kagent(['planner', 'db'], `${SRC}\nRun: python ${PB}/scripts/plan_check.py --root ${A.repo} --gate implementation (gates product, engineering, implementation; production is checked at release time)
Then read the sources and the written artifacts. Completeness critic for ${METHOD}:
1. every step 01-20 has its artifact; no scaffold still carries its template line while it is treated as done; every FR/BR id is named by an acceptance test; every one of the 35 Data Architecture Gate items is answered (or N/A with a reason); every BR is mapped to a DB constraint or a named domain service and has a planned test; every NFR has a number and a verification method; every entity has exactly one owning context;
2. every source requirement, rule, condition or screen is present (nothing weakened), every task has a testable criterion, dependency order is right (no migration task scheduled before the data gate items it needs);
3. scope creep: anything not traceable to the sources moves to 'Proposed (needs owner approval)'.
Fix the artifacts directly, rerun plan_check until it passes or only owner decisions remain, then return: plan_check result, the fixes you made, and what needs the owner.`,
  { label: 'critic', phase: 'Critic' })
return { critic, agents_used: AGENTS_USED }
