export const meta = {
  name: 'pb-map-loop',
  description: 'project-brain: follow an existing PROJECT_MAP section by section; per section plan items, assign each to a role-skilled agent (or Codex), verify, review, sync the map, then loop to the next section',
  whenToUse: 'An approved project map exists and the owner says go / execute / continue. args: {repo, map, docs[], maxSections?, maxItemsPerSection?, sections?, codex?, baseUrl?, reviewLenses?}',
  phases: [
    { title: 'Plan', detail: 'read the map, list unfinished sections in dependency order' },
    { title: 'Decompose', detail: 'per section: items with role, criterion, executor' },
    { title: 'Build', detail: 'role-skilled implementer (or Codex) per item, sequential' },
    { title: 'Verify', detail: 'independent verifier per item, one fix round' },
    { title: 'Review', detail: 'code review of the section (child workflow), then one fix round for confirmed findings' },
    { title: 'Sync', detail: 'update project map, ORPHANS & PENDING, change log, handoff' },
  ],
}

// args: {
//   repo: "C:/path/to/your-project", map: "docs/project_map.md", docs: ["docs/PRD.md", ...],
//   sections: ["M4", "M5"]        optional: force these sections (else the next unfinished ones in map order)
//   maxSections: 2                sections per run (default 2); run again (or via /loop) to continue
//   maxItemsPerSection: 8         cap per section (default 8); the rest stays in ORPHANS & PENDING
//   codex: { task: {model, effort}, review: {model, effort}, image: {model, effort} }   optional lanes
//   baseUrl: "http://127.0.0.1:8000"   optional: enables a browser UI check for frontend items
//   reviewLenses: ["bugs", "rules"]    optional: lenses for the section review (default bugs, rules, contracts)
// }
// Items run SEQUENTIALLY inside a section (one working tree). The loop stops at the first item that still
// fails after one fix round, so new work is never stacked on a broken base.
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

const MAP = A.map || 'docs/project_map.md'
// Defaults fit the default agent cap (12): 1 section of up to 4 items. Raise them together with maxAgents.
const MAX_SECTIONS = A.maxSections || 1
const MAX_ITEMS = A.maxItemsPerSection || 4
const SYNC_RESERVE = 2  // always keep agents for the section review/sync so built work is recorded
const CTX = `Repository: ${A.repo}. Project map: ${MAP}. Canonical docs: ${(A.docs || []).join(', ') || '(see the map header)'}.`

const SECTIONS = { type: 'object', required: ['sections'], properties: { sections: { type: 'array', items: { type: 'object',
  required: ['id', 'title', 'status', 'why_next'],
  properties: { id: { type: 'string' }, title: { type: 'string' }, status: { type: 'string', enum: ['not_started', 'partial', 'done', 'blocked'] },
    why_next: { type: 'string' }, blocker: { type: 'string' } } } } } }
const ROLE_ENUM = ['db', 'backend', 'api', 'frontend', 'mobile', 'desktop', 'security', 'compliance', 'ops', 'docs', 'assets']
const ITEMS = { type: 'object', required: ['items', 'deferred'], properties: {
  deferred: { type: 'array', items: { type: 'string' } },
  items: { type: 'array', items: { type: 'object',
    required: ['id', 'title', 'roles', 'criterion', 'executor', 'docs'],
    properties: { id: { type: 'string' }, title: { type: 'string' }, roles: { type: 'array', items: { type: 'string', enum: ROLE_ENUM } },
      criterion: { type: 'string' }, executor: { type: 'string', enum: ['claude', 'codex'] }, docs: { type: 'array', items: { type: 'string' } },
      allowed: { type: 'array', items: { type: 'string' } }, check: { type: 'string' }, instructions: { type: 'string' },
      pages: { type: 'array', items: { type: 'string' } },
      brief: { type: 'string' }, out: { type: 'string' }, aspect: { type: 'string' } } } } } }
const REPORT = { type: 'object', required: ['status', 'files', 'commands', 'not_verified'],
  properties: { status: { type: 'string', enum: ['implemented', 'blocked'] }, files: { type: 'array', items: { type: 'string' } },
    commands: { type: 'array', items: { type: 'string' } }, not_verified: { type: 'string' }, blocker: { type: 'string' } } }
const CHECK = { type: 'object', required: ['pass', 'evidence'], properties: { pass: { type: 'boolean' }, evidence: { type: 'string' }, failures: { type: 'string' } } }

// ---------- Plan: which sections to run ----------
phase('Plan')
const plan = await kagent(['planner', 'graph'], `${CTX}
Read the project map (header, [SYSTEM_FLOW], phases/sections, [ORPHANS & PENDING]) and the latest .project-brain/HANDOFF.md section if present.
Also run: python ${PB}/scripts/plan_check.py --root ${A.repo} --gate none and report data_gate_answered, the first gate in gates that is not passed with its missing list, and templates_unfilled in why_next of the first section.
Compare claimed status with the code where cheap (files exist, tests exist). List ALL sections in the map's dependency order with their real status. A section is a top-level phase/module heading (for example "## M1 - Text utilities" or "Phase 3"); the bullets or numbered items inside it (M1.1, M1.2) are ITEMS of that section, never separate sections.
${A.sections ? 'The owner asked for these sections specifically: ' + A.sections.join(', ') + '.' : ''}
Do not edit files.`, { label: 'plan', phase: 'Plan', schema: SECTIONS })

const queue = (plan?.sections || [])
  .filter(s => A.sections ? A.sections.includes(s.id) : (s.status === 'not_started' || s.status === 'partial'))
  .slice(0, MAX_SECTIONS)
const blockedAhead = (plan?.sections || []).filter(s => s.status === 'blocked')
log(`sections to run now: ${queue.map(s => s.id).join(', ') || 'none'}${blockedAhead.length ? '; blocked: ' + blockedAhead.map(s => s.id).join(', ') : ''}`)

const sectionResults = []
let stop = false
for (const sec of queue) {
  if (stop) break
  // ---------- Decompose ----------
  const dec = await kagent(['planner', 'surfaces'], `${CTX}
Section ${sec.id}: ${sec.title}.
Decompose ONLY this section into implementable items in dependency order, at most ${MAX_ITEMS} (put the rest in "deferred" with one line each).
For each item give: roles (which skills it needs: db, backend, api, frontend, mobile, desktop, security, compliance (money/privacy/legal), ops, docs, assets), a testable success criterion, the doc sections it implements,
executor "codex" ONLY for trivial fully specified edits (strings/translations, a field copied from an identical one, CSS token swap) with exact "allowed" paths, "check" and "instructions"; otherwise "claude".
Frontend items: list the "pages" (paths) to check in the browser. Asset items (role assets): give "brief", absolute "out" path and "aspect".
Data Architecture Gate: run python ${PB}/scripts/plan_check.py --root ${A.repo}. If it fails, do NOT schedule migration/schema items; schedule first a docs item (roles: docs, db) that completes the missing gate items in the repo's data architecture doc (docs/data/DATA_ARCHITECTURE.md by default; references/system-engineering-method.md).
Release and production deploy items: schedule them only when python ${PB}/scripts/plan_check.py --root ${A.repo} --gate production passes; otherwise schedule a readiness item that produces the missing evidence (tests, restore test, alerts, runbook) and ticks the checklist lines with evidence only after the evidence exists.
Never invent scope beyond the map and docs. Do not edit files.`, { label: 'decompose:' + sec.id, phase: 'Decompose', schema: ITEMS })

  const items = dec?.items || []
  const done = []
  for (const it of items) {
    const tag = sec.id + '/' + it.id
    if (MAX_AGENTS - AGENTS_USED <= SYNC_RESERVE) {
      done.push({ item: tag, status: 'budget_exhausted', detail: 'not started: agent budget reserved for sync' })
      continue
    }
    const roles = (it.roles && it.roles.length ? it.roles : ['backend'])
    let impl = null
    let codexLeftovers = []

    // Assets go to the Codex image lane when configured.
    if (roles.includes('assets') && CODEX.image && it.brief && it.out) {
      const r = await codex('image', { brief: it.brief, out: it.out, aspect: it.aspect || '1:1', project: A.repo }, 'img-' + tag, 'Build')
      if (r && r.ok) impl = { status: 'implemented', files: [r.path], commands: [], not_verified: 'image needs judging', via: 'codex-image' }
    }
    // Trivial items go to the Codex task lane when configured.
    if (!impl && it.executor === 'codex' && CODEX.task && (it.allowed || []).length) {
      const r = await codex('task', { cwd: A.repo, allowed: it.allowed, check: it.check,
        instructions: `${it.title}\nSuccess criterion: ${it.criterion}\n${it.instructions || ''}` }, 'task-' + tag, 'Build')
      if (r && r.ok) impl = { status: 'implemented', files: r.actually_changed || [], commands: it.check ? [it.check] : [], not_verified: 'pending verification', via: 'codex:' + CODEX.task.model }
      else { codexLeftovers = (r && r.actually_changed) || []; log(`${tag}: codex lane did not finish, escalating to Claude`) }
    }
    // Everything else (and every Codex failure) goes to a role-skilled Claude implementer.
    if (!impl) impl = await kagent(['implement', ...roles], `${CTX}
Implement item ${tag}: ${it.title}
Success criterion: ${it.criterion}
${codexLeftovers.length ? 'A failed Codex attempt may have left edits in: ' + codexLeftovers.join(', ') + ' - review them first and revert anything wrong.' : ''}
Doc sections: ${(it.docs || []).join(', ')}
Follow ${PB}/agents/pb-implementer.md (rules and return format). Update the project map entry and the change log for this item in the same change.`,
      { label: 'build:' + tag, phase: 'Build', schema: REPORT })
    if (!impl && AGENTS_USED >= MAX_AGENTS) { done.push({ item: tag, status: 'budget_exhausted', detail: 'agent cap reached' }); continue }
    if (!impl || impl.status === 'blocked') { done.push({ item: tag, status: 'blocked', detail: impl?.blocker || 'implementer returned nothing' }); log(`${tag}: blocked`); continue }

    const verifyPrompt = (extra) => `${CTX}
Verify item ${tag}: ${it.title}
Criterion: ${it.criterion}
Implementer report: ${JSON.stringify(impl)}
${roles.includes('frontend') && A.baseUrl ? 'Also open these pages in the real browser at 1440 and 390 width in every locale: ' + (it.pages || []).map(p => A.baseUrl + p).join(', ') : ''}
${roles.includes('assets') ? 'Open the produced image(s) with the Read tool and judge them against the brief and the owner UI bar.' : ''}
${extra || ''}
Follow ${PB}/agents/pb-verifier.md. Never edit code.`
    let check = await kagent(['verify', ...roles, ...(roles.includes('frontend') ? ['ui_audit'] : [])], verifyPrompt(),
      { label: 'verify:' + tag, phase: 'Verify', schema: CHECK })
    if (check && !check.pass) {
      await kagent(['implement', ...roles], `${CTX}\nFix round for ${tag}. The verifier FAILED it:\n${check.failures || check.evidence}\nFix only what is needed and rerun the checks. Follow ${PB}/agents/pb-implementer.md.`,
        { label: 'fix:' + tag, phase: 'Build', schema: REPORT })
      check = await kagent(['verify', ...roles], verifyPrompt('This is the re-verification after a fix round.'), { label: 'reverify:' + tag, phase: 'Verify', schema: CHECK })
    }
    const ok = !!check?.pass
    done.push({ item: tag, status: ok ? 'verified' : 'failed', via: impl.via || 'claude', roles, files: impl.files, evidence: check?.evidence, failures: check?.failures })
    log(`${tag}: ${ok ? 'verified' : 'FAILED after one fix round, stopping the loop'}`)
    if (!ok) { stop = true; break }
  }

  // ---------- Review the section ----------
  const files = [...new Set(done.flatMap(d => d.files || []))]
  let review = null
  if (files.length) {
    review = await child('review-changes.js', {
      repo: A.repo, scope: `section ${sec.id} (${sec.title})`, files, docs: A.docs,
      lenses: A.reviewLenses || ['bugs', 'rules', 'contracts'], maxVerify: 8, codex: A.codex })
  }

  // ---------- Fix confirmed review findings (one round) ----------
  let fixed = []
  if (review && (review.kept || []).length && !stop) {
    const fx = await kagent(['implement', ...new Set(done.flatMap(d => d.roles || []))], `${CTX}
Section ${sec.id} review confirmed these findings (confidence >= 80):
${JSON.stringify(review.kept)}
Fix each one with the smallest correct change, add a test that fails without the fix, rerun the section's tests. Follow ${PB}/agents/pb-implementer.md.
Return which findings you fixed (by file:line) and the test results.`, { label: 'fix-review:' + sec.id, phase: 'Build', schema: REPORT })
    const re = await kagent(['verify'], `${CTX}
Confirm that each of these review findings is now fixed and the section tests pass: ${JSON.stringify(review.kept)}
Fix report: ${JSON.stringify(fx)}
Follow ${PB}/agents/pb-verifier.md. Never edit code.`, { label: 'verify-fixes:' + sec.id, phase: 'Verify', schema: CHECK })
    fixed = re && re.pass ? review.kept : []
    log(`${sec.id}: review findings ${re && re.pass ? 'fixed and verified' : 'NOT all fixed, kept in ORPHANS & PENDING'}`)
  }
  const openFindings = (review?.kept || []).filter(f => !fixed.includes(f))
  const unverifiedFindings = review?.unverified || []
  const reviewed = !files.length || (!!review && !(review.lenses_skipped || []).length)

  // ---------- Sync the map ----------
  const sync = await kagent(['docs', 'planner'], `${CTX}
Section ${sec.id} results: ${JSON.stringify(done)}
Deferred items: ${JSON.stringify(dec?.deferred || [])}
Review findings fixed and verified: ${JSON.stringify(fixed)}
Review findings (confidence >= 80) still open: ${JSON.stringify(openFindings)}
Review findings NOT verified (keep them in ORPHANS & PENDING as 'to verify'): ${JSON.stringify(unverifiedFindings)}
${reviewed ? '' : 'The section review did NOT run completely (budget): record "review pending" in ORPHANS & PENDING.'}
Items not started because of the agent budget: ${JSON.stringify(done.filter(d => d.status === 'budget_exhausted').map(d => d.item))}
Update ${MAP}: mark verified items done, keep failed/blocked/deferred items and every open review finding in [ORPHANS & PENDING] (remove entries only when complete),
append one change-log entry for the section, and add a dated section to .project-brain/HANDOFF.md (done, verified with commands, not verified, open findings, next action).
If graphify-out/ exists in the repo, run "graphify update ." from the repo root to refresh the code graph. Do not touch code. Return a 5-line summary.`, { label: 'sync:' + sec.id, phase: 'Sync' })

  sectionResults.push({ section: sec.id, items: done, deferred: dec?.deferred || [], review_fixed: fixed, review_open: openFindings,
    review_unverified: unverifiedFindings, reviewed, synced: !!sync, sync })
}

if (!plan) return { error: 'plan agent returned nothing (budget or failure): nothing was run', agents_used: AGENTS_USED }
// A section is finished only when it was decomposed and every item is verified with no open review finding.
const finished = id => sectionResults.some(r => r.section === id && r.items.length > 0
  && r.items.every(i => i.status === 'verified') && r.review_open.length === 0 && r.review_unverified.length === 0
  && r.deferred.length === 0 && r.reviewed && r.synced)
const budgetStopped = sectionResults.some(r => r.items.some(i => i.status === 'budget_exhausted') || !r.reviewed || !r.synced)
const remaining = (plan.sections || []).filter(s => s.status !== 'done').map(s => s.id).filter(id => !finished(id))
const ownerQuestions = sectionResults.flatMap(r => r.items.filter(i => i.status === 'blocked').map(i => ({ item: i.item, question: i.detail })))
return {
  ran: sectionResults,
  stopped_on_failure: stop,
  owner_questions: ownerQuestions,
  remaining_sections: remaining,
  agents_used: AGENTS_USED,
  next: stop ? 'Fix the failed item (see failures) before looping again.'
    : ownerQuestions.length ? 'Ask the owner the owner_questions (one batch, with recommended defaults) before relaunching.'
    : budgetStopped ? 'Agent budget ran out: relaunch (or pass a larger maxAgents if the owner asked for a bigger run).'
    : remaining.length ? `Run pb-map-loop again (or /loop it) to continue with: ${remaining.slice(0, MAX_SECTIONS).join(', ')}`
    : 'Map complete: run security-audit.js and ui-audit.js before release.',
}
