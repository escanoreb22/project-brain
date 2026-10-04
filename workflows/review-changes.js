export const meta = {
  name: 'pb-review-changes',
  description: 'project-brain: multi-lens review of a local change set, adversarially verified, findings >= 80 confidence',
  whenToUse: 'After implementing a task, before claiming done. args: {repo, scope, files?, docs?, lenses?, maxVerify?, codex?: {review:{model,effort}}}',
  phases: [
    { title: 'Review', detail: 'independent lenses on the change set' },
    { title: 'Verify', detail: 'refute each finding; keep confidence >= 80' },
  ],
}

// args: { repo: "C:/path/to/repo", scope: "what changed / task id", files: ["rel/path", ...] (optional; else git diff or latest change-log entries), docs: ["docs/..."] }
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

const SCOPE = `Repository: ${A.repo}
Change under review: ${A.scope || 'latest task'}
Files: ${(A.files || []).join(', ') || 'use `git diff` if it is a git repo; otherwise the files named in the latest change-log entries (AGENT_CHANGELOG.md / .project-brain logs) for this task'}
Governing docs: ${(A.docs || []).join(', ') || 'the project docs sections the change touches + CLAUDE.md files'}
Method and false-positive list: ${PB}/modules/review/code-review/README.md. Read only the change and the context needed.`

const FINDINGS = {
  type: 'object', required: ['findings'],
  properties: { findings: { type: 'array', items: { type: 'object',
    required: ['file', 'line', 'severity', 'problem', 'fix'],
    properties: { file: { type: 'string' }, line: { type: 'integer' }, severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
      problem: { type: 'string' }, fix: { type: 'string' } } } } },
}
const VERDICT = { type: 'object', required: ['confidence', 'reason'],
  properties: { confidence: { type: 'integer', minimum: 0, maximum: 100 }, reason: { type: 'string' } } }

const LENSES = [
  ['rules', 'Rules/doc adherence: CLAUDE.md, PRD/spec sections, project invariants (tenancy 404, ledgers append-only, immutable documents, authz), ' + PB + '/references/engineering-principles.md.'],
  ['bugs', 'Real bugs in the changed lines: logic, edge cases, races, N+1, wrong status codes, broken redirects, missing locale strings.'],
  ['failures', 'Silent failures and error handling. Use the prompt in ' + PB + '/modules/review/code-review/agents/silent-failure-hunter.md.'],
  ['tests', 'Do tests prove behavior and failure paths on the real DB engine? Use ' + PB + '/modules/review/code-review/agents/pr-test-analyzer.md.'],
  ['contracts', 'Types, API shape, DB schema of the change: ' + PB + '/references/api-design.md and db-schema-design.md; ' + PB + '/modules/review/code-review/agents/type-design-analyzer.md.'],
  ['simplicity', 'Duplication and needless complexity. FIRST run: python ' + PB + '/scripts/code_guard.py scan --root ' + A.repo + ' --changed ' + (A.files || []).join(' ') + ' and report every duplicate file/body/name and every function over 60 lines it lists as findings. Then ' + PB + '/modules/review/code-review/agents/code-simplifier.md; only flag what clearly should be simpler.'],
]

const LENS_ROLES = { rules: ['review', 'planner'], bugs: ['review', 'backend'], failures: ['review', 'backend'], tests: ['review', 'verify'], contracts: ['review', 'api', 'db'], simplicity: ['review'] }
// Lenses: all 6 by default; pass args.lenses (e.g. ["bugs","rules"]) for a small change.
const ACTIVE = A.lenses && A.lenses.length ? LENSES.filter(l => A.lenses.includes(l[0])) : LENSES
const MAX_VERIFY = A.maxVerify || 12

// Barrier on purpose: lenses overlap, so dedupe ALL findings before paying for verification.
const lensesSkipped = []
const lensJobs = ACTIVE.map(([key, focus]) => () =>
  kagent(LENS_ROLES[key] || ['review'], `${SCOPE}

Your lens: ${focus}
Return at most 5 findings you can point to at file:line, most important first. Do not edit files.`,
    { label: 'review:' + key, phase: 'Review', schema: FINDINGS })
    .then(r => { if (!r) { lensesSkipped.push(key); return [] } return (r.findings || []).map(f => ({ ...f, lens: key })) }))
// Codex lane: an independent second-vendor reviewer (needs an explicit file list).
if (CODEX.review && (A.files || []).length) {
  lensJobs.push(() => codex('review', { cwd: A.repo, files: A.files, max_findings: 8,
    focus: 'real bugs, rule/doc violations, silent failures, contract/schema problems, needless complexity' + (A.docs ? '; governing docs: ' + A.docs.join(', ') : '') },
    'review', 'Review')
    .then(r => { if (!r || !r.ok) { log('codex review lane failed: ' + (r?.error || 'no result')); return [] }
      return (r.report?.findings || []).map(f => ({ ...f, lens: 'codex' })) }))
} else if (CODEX.review) log('codex review lane skipped: pass args.files')

// Barrier on purpose: lenses overlap, so dedupe ALL findings before paying for verification.
const raw = (await parallel(lensJobs)).filter(Boolean).flat()

const RANK = { critical: 0, high: 1, medium: 2, low: 3 }
const unique = []
for (const f of raw.sort((a, b) => RANK[a.severity] - RANK[b.severity])) {
  const dup = unique.find(u => u.file === f.file && Math.abs(u.line - f.line) <= 5)
  if (dup) { dup.lens += '+' + f.lens; continue }
  unique.push(f)
}
const toVerify = unique.slice(0, MAX_VERIFY)
if (unique.length > MAX_VERIFY) log(`verifying top ${MAX_VERIFY} of ${unique.length} unique findings; ${unique.length - MAX_VERIFY} lower-severity ones returned unverified`)

const verified = await parallel(toVerify.map(f => () =>
  kagent(['review'], `${SCOPE}

Try to REFUTE this finding. Read the code yourself. Score 0-100 how confident you are it is a real, in-scope issue (pre-existing, unchanged lines, linter territory, pedantry => low).
Finding: ${JSON.stringify(f)}`,
    { label: 'verify:' + f.file.split('/').pop() + ':' + f.line, phase: 'Verify', schema: VERDICT })
    .then(v => v ? ({ ...f, confidence: v.confidence ?? 0, verdict: v.reason }) : ({ ...f, confidence: null, verdict: 'not verified (budget/agent unavailable)' }))))
const notVerified = verified.filter(f => f && f.confidence === null)
const all = verified.filter(f => f && f.confidence !== null)
const kept = all.filter(f => f.confidence >= 80)
log(`${raw.length} raw, ${unique.length} unique, ${kept.length} kept (>= 80)`)
return { kept, dropped: all.length - kept.length, unverified: [...notVerified, ...unique.slice(MAX_VERIFY)], lenses_skipped: lensesSkipped, agents_used: AGENTS_USED }
