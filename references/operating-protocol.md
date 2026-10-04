# Operating protocol — how every agent uses the skill set (cheapest correct path first)

Applies to Claude in the main session, every workflow agent and every `pb-*` subagent. Goal: fewer tokens, zero invented facts, zero duplicated code. Tools are tried in the order listed; stop at the first that answers.

Paths: `PB` = this skill's folder (default `~/.claude/skills/project-brain`; workflows and installed agents carry the absolute path that `install.py` writes). CLIs run from the repo root.

## 1. Router — intent → tool/skill

| Intent | 1st (cheap, deterministic) | 2nd | Last resort |
|---|---|---|---|
| Where is X defined? Does it already exist? | `python PB/scripts/code_guard.py find <Name>` | `Grep` for the symbol | — (never guess a path) |
| What uses / depends on X? What breaks if I change X? | `graphify affected "<X>" --depth 2` (needs `graphify-out/`) **and** `Grep` for the symbol name: the graph can miss dynamic/PHP calls, so an empty result is never proof of no consumers | `graphify explain "<X>"` | read the callers |
| How do A and B connect? | `graphify path "A" "B"` | `graphify query "<q>" --budget 800 --context call` | read the 2-3 files on the path |
| Understand an area / onboarding / which doc covers X | `graphify-out/GRAPH_REPORT.md` (god nodes, communities) | `graphify query "<q>" --budget 1500` | read doc sections by heading (Grep + offset) |
| Read a big file | `Grep -n` for the symbol/heading, then `Read` with offset/limit | — | never read >400 lines blind |
| Plan a small part / one task | `references/planning-playbook.md` (slice + criterion) | task packet | — |
| Plan a module / project | `workflows/plan-from-prd.js` | `references/planning-playbook.md` + `multi-surface-architecture.md` | — |
| Write code | §3 below, then the role file (`backend-architecture.md`, `db-schema-design.md`, `api-design.md`, `frontend-system-design.md` + `modules/ui/`) | — | — |
| Check my change for duplication / size | `python PB/scripts/code_guard.py scan --changed <files>` | — | — |
| Translations complete? (ar/fr/en keys, placeholders) | `python PB/scripts/i18n_check.py --changed <files>` (or no args for the whole repo) | — | — |
| Any secret about to leak? | `python PB/scripts/secret_scan.py --files <files to commit>` | `secret_scan.py` (working-tree audit) | — |
| Repo has no git | `python PB/scripts/git_baseline.py --root <repo>` | — | — |
| Is the skill itself healthy? | `python PB/scripts/install.py --check` | — | — |
| Any coding agent (Codex, Cursor, Gemini, Aider): prepare / close a task | `python PB/scripts/pb.py start` / `python PB/scripts/pb.py finish --changed <files>` | — | — |
| Security patterns in my change (owner's 14 CWE classes) | `python PB/scripts/vuln_scan.py --changed <files>` | `references/security-baseline.md` walk-through | — |
| Review | `pb-code-reviewer` (small) / `workflows/review-changes.js` (task or section) | `codex_review` as 2nd vendor | — |
| Security | `pb-security-reviewer` / `workflows/security-audit.js` | `modules/review/security-review/` | — |
| UI check | `pb-ui-auditor` / `workflows/ui-audit.js` | `modules/ui/` | — |
| Images / trivial edits | Codex (`references/codex-delegation.md`) | — | — |
| Version / API fact | the repo's lockfile/manifest | official docs (`research-policy.md`) | — |

Graph freshness: after code changes run `graphify update .` (code only, no LLM, seconds). Docs changes need a semantic rebuild via `modules/brain-graph/BRAIN_GRAPH.md` (`--update`); do it at the end of a docs task, not per edit. If `graphify-out/` is missing, build it with `graphify update .` (code only, seconds, no LLM); if it is older than the files you touch, run the same command. Fall back to `code_guard.py find` + `Grep` only if graphify is unavailable.

## 2. Anti-hallucination rules (absolute)

- Every path, class, function, route, column, config key and package you mention must come from a tool result in this session (`code_guard find`, `graphify`, `Grep`, `Read`, manifest). If not found: write `UNKNOWN`, do not invent.
- Versions come from `composer.lock` / `package-lock.json` / `pubspec.lock`, never memory.
- Before changing a signature, schema, route, event or config key: `graphify affected` (or Grep) to list every consumer; update all of them in the same change.
- "Done" requires executed evidence (tests on the real DB engine, build, browser). Reading code is not evidence.
- When two sources disagree, follow SKILL.md source precedence and report the conflict; never silently pick.

## 3. Clean-code commitments (every code change)

**Before writing**
1. `code_guard.py find <Name>` for every new function/class/component/hook/action you plan to add. Exact hit → reuse or extend it. Similar hit → read it; extend if it is the same responsibility.
2. Find the owning module (graph community or existing folder for that domain). New file only when no existing file owns the responsibility; name it after the responsibility, never `Helper`, `Utils2`, `Manager`, `New*`, `*Copy`, `*Old`.
3. Write the success criterion (SKILL.md §4).

**While writing**
- One responsibility per function/class; a function does one thing at one level of abstraction.
- Size: functions ≤ 40 lines (hard stop 60), files ≤ 300 lines (hard stop 400), parameters ≤ 4 (else an object/DTO). Long code is where hallucination and bugs hide: split by responsibility, not by line count.
- Names say intent (`activateSubscription`, not `doIt`/`handle2`); no abbreviations the domain does not use.
- No duplication: logic used twice moves to its single owner (Action/service/hook/component) and both call sites use it. Same rule for SQL, validation rules, translations and UI pieces.
- Early returns over nesting (max 3 levels). No dead code, commented-out code, placeholders or `TODO`.
- Errors handled where they can be answered; never swallowed. Log with context, never secrets.
- Follow the repo's existing patterns and formatter; do not introduce a second way of doing the same thing.
- Tests next to the behavior: one behavior per test, failure paths included.

**After writing**
1. `code_guard.py scan --changed <files you touched>` must exit 0 (no duplicate files/bodies/names involving your files). Long functions it reports: split them or justify in one line.
2. `graphify update .` if the repo has a graph.
3. Run formatter, linters, type checks, tests (SKILL.md §4).

## 4. Token discipline

- Ask the graph or `code_guard` before opening files; open only the files they point to, and only the relevant range.
- Load only the reference files for your role (`workflows/_knowledge.snippet.js`); never load all modules.
- Large reference files (`design-taste-frontend/MODULE.md`, `BRAIN_GRAPH.md`, Apple HIG): Grep the heading you need, read that section.
- Pass IDs and file:line between agents, not pasted file contents.
- Delegate images and trivial edits to Codex; mechanical runners on the cheapest Claude tier.
- Stop exploring when the question is answered; report `UNKNOWN` rather than reading the whole repo.

## Red flags

- A path or function mentioned without a tool result behind it.
- A new file whose responsibility already exists elsewhere (`code_guard find` would have shown it).
- The same function name or body in two files after your change.
- A function over 60 lines or a file over 400 lines created by your change.
- Reading whole large files or whole doc sets when a graph query or Grep would answer.

## How project-brain uses this

Always loaded: SKILL.md section 0 summarizes it, every workflow agent receives it through `workflows/_knowledge.snippet.js`, and every `pb-*` subagent reads it first. The hooks (`scripts/pb_hooks.py`) enforce its section 3 gates automatically in repositories that contain `.project-brain/`.
