export const meta = {
  name: 'pb-security-audit',
  description: 'project-brain: per-surface adversarial security audit with 2-vote verification of every finding',
  whenToUse: 'Security review/audit of a surface set, or before a release. args: {repo, surfaces[], mode, files?, codex?: {review:{model,effort}}}',
  phases: [
    { title: 'Hunt', detail: 'one hunter per surface x category group' },
    { title: 'Verify', detail: 'two independent refuters per finding' },
  ],
}

// args: { repo: "C:/path", surfaces: ["admin","app","tech","public","api"], mode: "audit" | "change", scope: "optional change description" }
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

// ---- Codex lane (shared snippet; copied into each workflow because scripts cannot import) ----
// args.codex = { task: {model, effort}, review: {model, effort}, image: {model, effort} }
// The orchestrating Claude picks model/effort per lane from `codex_delegate.py models` before launching.
// A lane that is absent means "Claude does this step itself".
const CODEX = (args && args.codex) || {}
const CODEX_PY = '~/.claude/skills/project-brain/scripts/codex_delegate.py'
const CODEX_TMP = '~/.claude/skills/project-brain/.tmp'
function codex(kind, payload, label, phaseName) {
  const choice = CODEX[kind]
  if (!choice || !choice.model || !choice.effort) return Promise.resolve(null)
  if (typeof spend === 'function' && !spend('codex:' + label)) return Promise.resolve(null)
  const spec = { kind, ...payload, model: choice.model, effort: choice.effort }
  const file = CODEX_TMP + '/spec-' + String(label).replace(/[^A-Za-z0-9_-]/g, '_') + '.json'
  return agent(`You are a thin runner for a Codex delegation. Do NOT do the job yourself and do not edit project files.
1. Write this JSON spec, unchanged, as UTF-8 to ${file} with the Write tool:
${JSON.stringify(spec)}
2. Run (Bash, timeout 600000 ms; the spec caps Codex at 540 s): python "${CODEX_PY}" run --spec "${file}"
3. Reply with ONLY the JSON the script printed (no prose, no code fences).`,
    { label: 'codex:' + label, phase: phaseName, model: 'haiku', effort: 'low' })
    .then(text => { try { return JSON.parse(String(text).trim().replace(/^```(json)?|```$/g, '')) } catch (e) { return { ok: false, error: 'unparseable runner output', raw: String(text).slice(0, 500) } } })
}
// ---- end Codex lane ----

const SURFACES = A.surfaces && A.surfaces.length ? A.surfaces : ['all']
const BASE = `Repository: ${A.repo}. Mode: ${A.mode || 'audit'}${A.scope ? ' - change: ' + A.scope : ''}.
Follow ${PB}/references/security-baseline.md (the owner's 14 weakness classes + 20 backend fundamentals) and ${PB}/modules/review/security-review/README.md (confidence >= 8/10, exclusions), ${PB}/modules/review/security-review/LARAVEL_SECURITY.md, the adversarial prompt ${PB}/modules/review/security-review/agents/security-auditor.md, and grep patterns in ${PB}/modules/review/security-review/insecure_patterns.py. Do not modify code.`

const GROUPS = [
  ['access', 'Authorization and privilege (security-baseline.md classes 5, 6, 9, 10): CWE-862 missing authorization, CWE-863 incorrect authorization (ownership, parent/child ids, cross-tenant must be 404), CWE-501 trust boundary violation (request data/mass assignment into the domain, client-sent tenant/role/price), CWE-269 privilege escalation between roles/surfaces'],
  ['auth', 'Authentication and session (classes 7, 8, 11): CWE-306 critical functions without auth (payments, role changes, exports, webhooks without signature), CWE-287 improper authentication (custom tokens, == comparisons, OTP/reset reuse, enumeration, tokens in web storage, JWT alg), CWE-384 session fixation (no regenerate after login/2FA/context switch)'],
  ['injection', 'Injection (classes 1, 2, 3, 4, 12, 14): CWE-78/77 OS and command injection (shell calls, Process with strings, Node exec), CWE-94 code injection (eval, unserialize, dynamic include), CWE-918 SSRF (outbound requests to user URLs, redirects, private IPs), CWE-89 SQL injection (raw SQL, orderBy from request), CWE-79 XSS (dangerouslySetInnerHTML, {!! !!}, href javascript:)'],
  ['backend', 'Backend fundamentals (security-baseline.md part B, all 20) plus CWE-120 in native code paths: endpoint security (every route in a middleware group, no debug/test routes, CSRF), input and API validation (FormRequest per write, contract match, unknown fields rejected), password security (hashing, bcrypt 72-byte limit, reset tokens), JWT if used, logging (no secrets/PII, security events), testing (negative tests exist), database performance (N+1, missing indexes), rate limiting, CORS, env/secrets, sensitive data in responses, error handling/debug, file uploads, DB least privilege, data integrity (ledgers, idempotency, races), production configuration; run python scripts/vuln_scan.py first and verify each hit'],
]
const FINDINGS = { type: 'object', required: ['findings'], properties: { findings: { type: 'array', items: { type: 'object',
  required: ['severity', 'file', 'line', 'title', 'exploit', 'test', 'fix'],
  properties: { severity: { type: 'string', enum: ['critical', 'high', 'medium'] }, file: { type: 'string' }, line: { type: 'integer' },
    title: { type: 'string' }, exploit: { type: 'string' }, test: { type: 'string' }, fix: { type: 'string' } } } } } }
const VOTE = { type: 'object', required: ['real', 'reason'], properties: { real: { type: 'boolean' }, reason: { type: 'string' } } }

const jobs = SURFACES.flatMap(s => GROUPS.map(g => ({ surface: s, key: g[0], focus: g[1] })))
// Codex lane: one second-vendor hunter per surface; its findings go through the same 2-vote Claude verification.
if (CODEX.review) SURFACES.forEach(s => jobs.push({ surface: s, key: 'codex', focus: GROUPS.map(g => g[1]).join('; ') }))
function hunt(j) {
  if (j.key !== 'codex') return kagent(['security', 'surfaces'], `${BASE}\nSurface: ${j.surface}. Focus: ${j.focus}. Trace untrusted input to sinks; report at most 5 exploitable findings with a concrete exploit, most severe first.`,
    { label: `hunt:${j.surface}:${j.key}`, phase: 'Hunt', schema: FINDINGS })
  return codex('review', { cwd: A.repo, files: A.files && A.files.length ? A.files : ['(whole repository: focus on the ' + j.surface + ' surface)'], max_findings: 5,
    focus: 'SECURITY ONLY, exploitable issues with a concrete exploit path: ' + j.focus + '. Project rules: foreign tenant then 404, server-derived tenant id, append-only ledgers, no token in web storage, no env() outside config.' },
    'sec-' + j.surface, 'Hunt')
    .then(r => r && r.ok
      ? { findings: (r.report?.findings || []).filter(f => f.severity !== 'low').map(f => ({ severity: f.severity, file: f.file, line: f.line,
          title: f.problem.slice(0, 90), exploit: f.problem, test: 'write a negative test reproducing it', fix: f.fix, source: 'codex' })) }
      : (log('codex security lane failed for ' + j.surface + ': ' + (r?.error || 'no result')), { findings: [] }))
}
const results = await pipeline(
  jobs,
  j => hunt(j),
  (res, j) => parallel((res?.findings || []).map(f => () =>
    parallel([1, 2].map(n => () => kagent(['security'], `${BASE}\nRefuter #${n}: try to prove this finding is NOT exploitable (guarded by middleware/policy/validation, unreachable, test-only). Default real=false if you cannot confirm the exploit path in code.\nFinding: ${JSON.stringify(f)}`,
      { label: `verify:${j.surface}:${f.file.split('/').pop()}:${n}`, phase: 'Verify', schema: VOTE })))
      .then(vs => ({ ...f, surface: j.surface, group: j.key, votes: vs.filter(Boolean).filter(v => v.real).length, reasons: vs.filter(Boolean).map(v => v.reason) })))),
)
const all = results.filter(Boolean).flat().filter(Boolean)
const confirmed = all.filter(f => f.votes === 2)
const disputed = all.filter(f => f.votes === 1)
const unverified = all.filter(f => f.votes === 0 && f.reasons.length < 2)  // refuters skipped (budget) or failed: never drop silently
log(`${all.length} candidates: ${confirmed.length} confirmed, ${disputed.length} disputed, ${unverified.length} unverified`)
return { confirmed, disputed, unverified, agents_used: AGENTS_USED }
