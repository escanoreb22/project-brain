export const meta = {
  name: 'pb-asset-batch',
  description: 'project-brain: generate a batch of raster assets with Codex (model/effort chosen by Claude), judge each image, regenerate once with a sharper brief',
  whenToUse: 'A page/section needs several images (hero, illustrations, empty states, OG images). args: {repo, assets[], style, codex:{image:{model,effort}}}',
  phases: [
    { title: 'Generate', detail: 'one Codex image job per asset, in parallel' },
    { title: 'Judge', detail: 'Claude opens each image and accepts or sharpens the brief' },
  ],
}

// args: { repo: "C:/path", style: "flat vector, primary #0D5A40, canvas #EEF1F0, no text",
//         assets: [{ id: "hero", brief: "...", out: "C:/path/public/images/hero.png", aspect: "16:9", background: "flat #EEF1F0", reference: "optional C:/.../ref.png" }],
//         codex: { image: { model, effort } } }
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

if (!CODEX.image) return { error: 'args.codex.image {model, effort} is required: choose them from `codex_delegate.py models`.' }

const JUDGE = { type: 'object', required: ['accept', 'issues', 'better_brief'],
  properties: { accept: { type: 'boolean' }, issues: { type: 'string' }, better_brief: { type: 'string' } } }
const judgeOf = (a, path, tag) => kagent(['assets', 'ui_audit'], `Open the image ${path} with the Read tool and judge it against the brief and the owner's UI bar (${PB}/references/frontend-system-design.md, section "Owner's UI bar").
Brief: ${a.brief}
Style: ${A.style || ''}
Aspect: ${a.aspect || '1:1'}
Reject for: stray text or letters, AI artifacts, wrong palette/background/aspect, cluttered or cheap look, culturally off content.
If rejecting, write a sharper brief that fixes the issues.`, { label: 'judge:' + tag, phase: 'Judge', schema: JUDGE })
const imageJob = (a, brief, tag) => codex('image', { brief, out: a.out, aspect: a.aspect || '1:1', background: a.background || 'as described',
  style: A.style || '', reference: a.reference, project: A.repo }, 'img-' + tag, 'Generate')

const results = await pipeline(
  A.assets || [],
  a => imageJob(a, a.brief, a.id),
  async (r, a) => {
    if (!r || !r.ok) return { id: a.id, ok: false, error: r?.error || 'no image' }
    let final = r
    let verdict = await judgeOf(a, r.path, a.id)
    if (verdict && !verdict.accept && verdict.better_brief) {
      const again = await imageJob(a, verdict.better_brief, a.id + '-retry')
      if (again && again.ok) { final = again; verdict = await judgeOf({ ...a, brief: verdict.better_brief }, again.path, a.id + '-retry') }
    }
    return { id: a.id, ok: !!verdict?.accept, path: final.path, codex_tokens: final.codex_tokens, issues: verdict?.issues }
  },
)
const done = results.filter(Boolean)
log(`${done.filter(r => r.ok).length}/${done.length} assets accepted`)
return { agents_used: AGENTS_USED, assets: done, next: 'Convert accepted PNGs to webp/avif, add sizes, width/height and alt text in every locale; record in docs/ASSETS.md if the project keeps one.' }
