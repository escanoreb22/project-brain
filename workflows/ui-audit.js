export const meta = {
  name: 'pb-ui-audit',
  description: 'project-brain: real-browser UI/UX audit per page (widths x locales) against design system, owner bar, HIG and anti-slop checklist',
  whenToUse: 'UI complaints ("AI slop", bad UX), before shipping a surface, after a redesign. args: {repo, baseUrl, pages[], locales[]}',
  phases: [
    { title: 'Audit', detail: 'one auditor per page' },
    { title: 'Consolidate', detail: 'dedupe into system-level fixes' },
  ],
}

// args: { repo: "C:/path", baseUrl: "http://127.0.0.1:8000", pages: ["/admin/dashboard", ...], locales: ["fr","ar","en"], login: "how to log in (dev seed accounts, no real credentials)" }
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
const RULES = `Rules: ${PB}/modules/ui/README.md (precedence, procedure); ${PB}/references/frontend-system-design.md (sec. 15 anti-slop checklist, sec. 16 review procedure), including the Owner UI bar section; relevant files via ${PB}/modules/ui/apple-hig/routing-index.md; the project's own design system docs in ${A.repo}.`
const PAGE = { type: 'object', required: ['page', 'issues'], properties: { page: { type: 'string' }, issues: { type: 'array', items: { type: 'object',
  required: ['impact', 'where', 'evidence', 'rule', 'fix'],
  properties: { impact: { type: 'string', enum: ['high', 'medium', 'low'] }, where: { type: 'string' }, evidence: { type: 'string' }, rule: { type: 'string' }, fix: { type: 'string' } } } } } }

// Sequential on purpose: the browser pane, viewport, locale and login cookies are shared between agents.
const pages = []
for (const p of A.pages || []) pages.push(await kagent(['ui_audit', 'frontend'], `Audit ${A.baseUrl}${p} in the real browser (load browser tools via ToolSearch, e.g. "Claude_Browser"). Login: ${A.login || 'use the project dev seed accounts documented in the repo'}.
Check widths 1440, 768, 390; locales ${(A.locales || ['default']).join(', ')} including RTL; console errors; component states; forms (local/dev only).
${RULES}
Do not edit code. Never propose new sections or features. Return concrete issues with evidence and exact fixes.`,
    { label: 'audit:' + p, phase: 'Audit', schema: PAGE }))
const found = pages.filter(Boolean)
const notAudited = (A.pages || []).filter((p, i) => !pages[i])
phase('Consolidate')
const plan = await kagent(['ui_audit', 'frontend'], `Here are per-page UI audit results for ${A.repo}:\n${JSON.stringify(found)}\n\n${RULES}\nMerge duplicates into SYSTEM-level fixes (tokens, shared components, layout shells) first, then page-specific fixes. Order by impact. For each: files/components likely involved, the fix, pages it resolves. Return Markdown.`,
  { label: 'consolidate', phase: 'Consolidate' })
return { pages: found, not_audited: notAudited, plan, agents_used: AGENTS_USED }
