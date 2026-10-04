export const meta = {
  name: 'pb-execution-engine',
  description: 'project-brain: implement project-map items one by one - implement, independent verify, one fix round, review - sequential to avoid file conflicts',
  whenToUse: 'Executing a batch of ready project-map items unattended. args: {repo, items[], docs[]}',
  phases: [
    { title: 'Implement', detail: 'one implementer per item, sequential' },
    { title: 'Verify', detail: 'independent verifier; one fix round on failure' },
    { title: 'Review', detail: 'code review of the batch' },
  ],
}

// args: { repo: "C:/path", items: [{id, title, criterion, docs[], role?: "db"|"backend"|"api"|"frontend"|"security"|"docs" (or an array), executor?: "codex", allowed?: ["lang/ar.json"], check?: "php artisan test --filter=X", instructions?: "exact edit"}], docs: [...], codex?: {task:{model,effort}, review:{model,effort}} }
// Codex items still get the independent Claude verifier; a failed Codex attempt escalates to the Claude implementer.
// Items run SEQUENTIALLY on purpose: they share one working tree and often the same files.
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

const REPORT = { type: 'object', required: ['status', 'files', 'commands', 'not_verified'],
  properties: { status: { type: 'string', enum: ['implemented', 'blocked'] }, files: { type: 'array', items: { type: 'string' } },
    commands: { type: 'array', items: { type: 'string' } }, not_verified: { type: 'string' }, blocker: { type: 'string' } } }
const CHECK = { type: 'object', required: ['pass', 'evidence'], properties: { pass: { type: 'boolean' }, evidence: { type: 'string' }, failures: { type: 'string' } } }
const implementer = `Follow ${PB}/agents/pb-implementer.md exactly (rules, return format). Repo: ${A.repo}. Canonical docs: ${(A.docs || []).join(', ')}.`
const verifier = `Follow ${PB}/agents/pb-verifier.md exactly. Repo: ${A.repo}.`

const done = []
for (const it of A.items || []) {
  const tag = it.id || it.title
  let impl = null
  // Codex lane: items marked executor:"codex" (trivial, fully specified, with allowed paths) go to Codex first.
  if (it.executor === 'codex' && CODEX.task && (it.allowed || []).length) {
    const r = await codex('task', { cwd: A.repo, allowed: it.allowed, check: it.check,
      instructions: `${it.title}\nSuccess criterion: ${it.criterion || ''}\n${it.instructions || ''}` }, 'task-' + tag, 'Implement')
    if (r && r.ok) impl = { status: 'implemented', files: r.actually_changed || [], commands: it.check ? [it.check] : [], not_verified: 'pending independent verification', via: 'codex:' + CODEX.task.model }
    else log(`${tag}: codex lane did not finish (${r?.error || (r?.outside_allowed || []).join(', ') || r?.codex_report?.status || 'no result'}) - escalating to Claude implementer`)
  }
  const roles = [].concat(it.role || 'backend')
  if (!impl) impl = await kagent(['implement', ...roles], `${implementer}\nTask ${tag}: ${it.title}\nSuccess criterion: ${it.criterion || 'derive it from the docs before coding'}\nDoc sections: ${(it.docs || []).join(', ')}`,
    { label: 'implement:' + tag, phase: 'Implement', schema: REPORT })
  if (!impl || impl.status === 'blocked') { done.push({ item: tag, status: 'blocked', detail: impl?.blocker || 'no result' }); log(`${tag}: blocked`); continue }
  let check = await kagent(['verify', ...roles], `${verifier}\nTask ${tag}: ${it.title}\nCriterion: ${it.criterion || '(see implementer report)'}\nImplementer report: ${JSON.stringify(impl)}`,
    { label: 'verify:' + tag, phase: 'Verify', schema: CHECK })
  if (check && !check.pass) {
    await kagent(['implement', ...roles], `${implementer}\nFix round for ${tag}. The verifier FAILED it:\n${check.failures || check.evidence}\nFix only what is needed, rerun the checks.`,
      { label: 'fix:' + tag, phase: 'Implement', schema: REPORT })
    check = await kagent(['verify', ...roles], `${verifier}\nRe-verify ${tag}: ${it.title}. Criterion: ${it.criterion || ''}`, { label: 'reverify:' + tag, phase: 'Verify', schema: CHECK })
  }
  const ok = !!check?.pass
  done.push({ item: tag, status: ok ? 'verified' : 'failed', via: impl.via || 'claude', roles, files: impl.files, evidence: check?.evidence, failures: check?.failures })
  log(`${tag}: ${ok ? 'verified' : 'FAILED after one fix round - stopping the batch'}`)
  if (!ok) break // never stack new work on a failing item
}

phase('Review')
const changed = [...new Set(done.flatMap(d => d.files || []))]
const review = changed.length
  ? await child('review-changes.js', { codex: A.codex, lenses: A.reviewLenses, maxVerify: 8, repo: A.repo, scope: 'execution-engine batch: ' + done.map(d => d.item).join(', '), files: changed, docs: A.docs })
  : null

// One fix round for confirmed review findings (same contract as map-loop).
let fixed = []
if (review && (review.kept || []).length) {
  const roles = [...new Set(done.flatMap(d => [].concat(d.roles || [])))]
  const fx = await kagent(['implement', ...(roles.length ? roles : ['backend'])], `${implementer}
The batch review confirmed these findings (confidence >= 80):
${JSON.stringify(review.kept)}
Fix each with the smallest correct change, add a test that fails without the fix, rerun the tests.`, { label: 'fix-review', phase: 'Implement', schema: REPORT })
  const re = await kagent(['verify'], `${verifier}
Confirm each of these findings is fixed and the tests pass: ${JSON.stringify(review.kept)}
Fix report: ${JSON.stringify(fx)}`, { label: 'verify-fixes', phase: 'Verify', schema: CHECK })
  fixed = re && re.pass ? review.kept : []
  log(`review findings ${re && re.pass ? 'fixed and verified' : 'NOT all fixed: keep them in ORPHANS & PENDING'}`)
}
return { agents_used: AGENTS_USED, items: done, review_ran: !!review, review_unverified: review?.unverified || [],
  review_lenses_skipped: review?.lenses_skipped || [], review_fixed: fixed, review_open: (review?.kept || []).filter(f => !fixed.includes(f)) }
