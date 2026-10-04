# Agentic workflow — how Claude runs a long project

Rules for Claude itself: memory, goals, loops, delegation, verification. Complements `memory-protocol.md` (record layers), `engineering-principles.md` sec. 13-16 (per-task execution, formerly `engineering-principles.md`), `quality-gates.md` (gate evidence), `runtime-adapters.md` (Codex/Claude adapters). Do not duplicate them; apply them with the rules below.

## 1. Principles (sources)

- Default: simplest structure that works. Add agents, loops or subagents only when they measurably improve the result (Anthropic, "Building effective agents": https://www.anthropic.com/engineering/building-effective-agents).
- Pattern choice: fixed steps -> prompt chain (implement -> verify -> sync). Distinct categories -> routing (model/tool per task type). Independent slices -> parallel sections. Unknown subtasks -> orchestrator + workers. Clear pass/fail criteria -> evaluator/optimizer loop.
- Every autonomous loop has a stop condition and an iteration cap. No cap, no loop.
- Appetite before estimate (Singer, Shape Up, "Set Boundaries"): decide how much time/tokens the item deserves, then cut scope to fit. Never stretch the appetite silently; hammer scope instead.
- Tracer bullet first (Hunt/Thomas, The Pragmatic Programmer, "Tracer Bullets"): one thin slice through every layer (route -> controller -> DB -> UI) that runs end to end, then widen. Prefer it over layer-by-layer builds.
- Small batches (Forsgren/Humble/Kim, Accelerate, delivery-practice chapters): small, reversible, verified increments beat big unattended drops. This matches the owner's "things broke while unattended" complaint.
- Next-action discipline (Allen, Getting Things Done, "Organizing"): every open item in memory names one concrete next physical action, not a topic.

## 2. Memory layers

| Layer | Where | Holds | Rule |
|---|---|---|---|
| Context window | the session | files read, outputs, reasoning | Scarce; quality drops as it fills. Never the only copy of anything. |
| CLAUDE.md / AGENTS.md | repo root, `~/.claude/` | stable instructions, commands, gotchas | Target under 200 lines; rules, not state. Advisory only. |
| Auto-memory | `~/.claude/projects/<repo>/memory/` (shared across worktrees of one repo) | learned preferences, corrections | `MEMORY.md` loads only its first 200 lines / 25 KB: one line per entry, detail in topic files. |
| `.project-brain/` | repo | STATE, HANDOFF, DECISIONS, change log | Cross-runtime source of truth (Codex, Claude, other sessions). |
| Repo docs | `docs/` | PRD, PROJECT_MAP, specs | Canonical; never copy into memory, reference by id. |

Sources: https://code.claude.com/docs/en/memory , https://code.claude.com/docs/en/best-practices (fetched 2026-10).

- Default: write state to `.project-brain/` first; mirror only durable cross-session facts to auto-memory. Deviate only for personal preferences that apply to every repo (user-level CLAUDE.md).
- Rules that must always hold go into hooks or tests, not prose. CLAUDE.md is advice; a PreToolUse or Stop hook is enforcement.
- Subagents start with no history and no prior reads; they get CLAUDE.md plus the delegation message. Put everything they need in the prompt or a file path.
- Compaction loses detail. Before a long step ends or context is large, write to HANDOFF: modified files, test commands, open decisions, next action. Tell compaction what to keep (modified files, test commands).
- Use `/clear` between unrelated tasks. After two failed corrections on one issue, clear and restart with a sharper prompt that carries what was learned.
- Never store secrets, chain-of-thought or raw logs. Store conclusions with evidence pointers.

## 3. Goals and success criteria

- Every work item starts with one measurable end state and the check that proves it. Form: `<observable result> verified by <command/URL/screenshot>, without changing <invariant>`.
- Good: "`php artisan test --filter=Invoice` exits 0 on MySQL 8.4; `/ar/invoices` renders RTL at 390 px; no file outside `app/Invoices/` and `resources/js/invoices/` changed."
- Bad: "make invoices better", "works well", "clean code".
- For unattended runs use `/goal <condition>`: a separate evaluator re-checks after each turn and judges only what appears in the transcript, so make Claude print the evidence. Always add a bound ("or stop after N turns") (https://code.claude.com/docs/en/goal).
- A condition must be falsifiable by output Claude can show: exit code, test summary, HTTP status, screenshot path, row count.
- Size to appetite: one goal = one task packet. A multi-task phase is a list of goals, not one goal.
- If a criterion cannot be checked on this machine (needs production, a device, a paid service), say so in the criterion and mark that part `not verified`.

## 4. Task sizing

- Default: one task = one reviewable diff, at most ~8 files, one concern, one session. Larger -> split by vertical slice (tracer-bullet order), not by layer.
- A task is `ready` only with: id, criterion, allowed paths, dependencies, verification command, rollback. Otherwise it is a note.
- Order: riskiest unknown first (spike or tracer bullet), then core flow, then edges, then polish. Money, auth and tenancy slices get their own task and an owner gate.
- Split when: the diff touches more than one surface (API + web + mobile) without a merged shared contract; the check needs more than one environment; two sessions would edit the same files.
- Do not split when the pieces cannot be verified alone (half a migration, unwired component). Keep them in one task, or park the unwired part in `[ORPHANS & PENDING]`.
- Scope hammering: when a task overruns, cut the feature, never the verification. Record cut items as `deferred` with a reason.

## 5. Loop patterns

Core loop (SKILL.md section 4): criterion -> smallest change -> verify -> sync memory -> next item.

| Loop | Use when | Stop when |
|---|---|---|
| Implement -> verify -> sync | every task | check passes AND docs/map/changelog updated |
| Fix loop (red -> green) | failing test or build | green; or 3 attempts without new information -> stop, summarize, change method |
| Loop-until-dry | audits, bug hunts, migrating N call sites | a full pass finds zero new items; or cap reached (default 3 passes) |
| `/loop <interval> <prompt>` | polling deploys, CI, PR comments | condition seen or user stops; recurring jobs expire after 7 days |
| `/loop <prompt>` (self-paced) | work with variable wait | Claude ends it when complete; wake-up chosen 1-60 min |
| `/goal <condition>` | long unattended implementation | evaluator says met/impossible, or turn-cap clause |
| Stop hook | a check that must gate every turn end | script exits clean |

- Verified: `/loop` runs only in an open, idle session; `/loop` and `/goal` are session-scoped (https://code.claude.com/docs/en/scheduled-tasks). For jobs that must survive a closed machine use routines or cron on the VPS, not `/loop`.
- Never loop on "improve" or "polish". A loop needs a test, a count or a diff-size budget.
- Diminishing returns: if two consecutive passes change less than they cost, stop and report. A reviewer told to find gaps always finds some; accept only findings that affect correctness or a stated requirement (best-practices page, adversarial review section).
- Research converges or stops: after 2 rounds with no usable result, change source or method; do not add rounds.
- Long waits (build, deploy, queue): prefer Monitor/background command output over polling prompts.

## 6. Subagents: parallel vs sequential

- Parallel only for independent slices: different files, no shared output, no ordering. Read-only research and review parallelize freely; edits do not.
- Sequential when step B needs A's output, when both edit the same files, or when the slice is under ~10 minutes of work (spawn cost exceeds gain).
- Use a subagent to keep exploration out of the main context: "investigate X, return findings with file paths". Ask for a short structured return (paths, line refs, verdict), not a transcript.
- Brief template: goal, exact paths, constraints (read-only or allowed paths), output format, what NOT to do. A subagent sees none of this conversation.
- Never delegate understanding: Claude reads the result, spot-checks key claims against files, then decides.
- Writer/reviewer split: the reviewer runs in fresh context against the diff and the criterion, not the implementer's reasoning. For security-sensitive diffs use a different model or tool (Codex).
- Platform facts (https://code.claude.com/docs/en/sub-agents, fetched 2026-10): subagent frontmatter supports `model`, `tools`, `isolation: worktree`, `maxTurns`; default nesting depth 3; default cap 20 concurrent; background subagents cannot call the Agent or Workflow tools. These are ceilings, not targets.

## 7. Fan-out budget (assume a limited plan unless owner-profile.md says otherwise)

- Default fan-out: 1-4 agents. Cap: 12 agents per run, child workflows included (the workflows enforce it through `maxAgents`, default 12). Never hundreds: fleets of hundreds of agents and multi-million-token research runs have burned whole plan budgets with no result.
- Above 12 only when the owner asked for that scale (e.g. a 30-40 agent research fleet, or map-loop over several sections): state "N agents x ~M tokens, purpose" in one line, set `maxAgents` explicitly, then run.
- Fan-out is for breadth that is truly independent (per-module audit, per-locale review). Not for depth, not for "more eyes" on a small diff.
- Pilot on 1-3 items, inspect output, fix the prompt, then scale. Put a budget line in each prompt ("stop after N tool calls").
- Prefer cheap tools first: Grep/Glob, `rg`, the graphify graph, scripts. An agent is the last resort for a search a script can do.
- Workflow tool (scripted fan-out): same caps; size the item list in the script before running, print the count, run a pilot item first.
- Log any run over 4 agents (agents, model, purpose, outcome) in the change log.

## 8. Model routing

| Work | Tier | Notes |
|---|---|---|
| Architecture, security, money/tenancy review, hard debugging, spec conflicts | strongest (opus-class), high effort | Few calls, high value. |
| Writing code and docs, normal refactors, tests | mid (sonnet-class), medium effort | Default. |
| Mechanical: renames, formatting, file listing, log triage, locale-key checks, bulk edits | cheapest (haiku-class) or a script | Verify with tests, not trust. |
| Independent second opinion | Codex (other vendor) | See section 10. |

- Set `model:` in custom subagent frontmatter; do not inherit the main model for mechanical agents.
- Escalate tier only after a cheaper attempt fails a concrete check, except security/money, where start strong.
- Effort: default medium; high only for money, auth, tenancy, migrations on live data.

## 9. Worktrees and concurrent sessions

- Parallel edits need isolation: `claude --worktree <name>` (repo needs at least one commit) or subagent `isolation: worktree`. Review each diff before merging; no blind auto-merge (https://code.claude.com/docs/en/common-workflows).
- Non-git projects (common for the owner): no worktrees. Run edit tasks sequentially, or give each session disjoint `allowed_paths` and record ownership in `.project-brain/` (task id -> paths -> session).
- Before editing: list recently modified files (`ls -lt` / `git status`), read the tail of the change log and HANDOFF. A file changed recently by something other than you belongs to another session: re-read it fully before editing; never overwrite from stale context.
- Take the next free task id across all tracks; append to the change log, never rewrite it.
- Shared hot files (routes, migrations dir, translations, project map, `package.json`, lockfiles): one owner at a time. Check `database/migrations` immediately before creating a migration so timestamps and tables do not collide.
- Auto-memory is shared by worktrees of one repo: one fact per file; do not rewrite entries you did not create.
- Ask the owner only when two sessions need the same file for contradictory goals; otherwise finish your disjoint slice.

## 10. Delegation to Codex CLI and other tools (this machine)

Codex CLI 0.160.0 (updated 2026-10-03; default model works again). All delegation rules, the MCP tools (`codex-delegate`: `codex_generate_image`, `codex_easy_task`), the CLI fallback, costs and the acceptance procedure are in `codex-delegation.md` — load it instead of calling `codex exec` by hand.

Other tools: Higgsfield MCP (video/motion; costs credits — ask before large spend; prefer Codex for still images); codex plugin (`codex:rescue` skill, `codex:codex-rescue` agent) for a second-opinion diagnosis of a stuck bug; `codex exec review --uncommitted` for an independent review of a diff (add `-c sandbox_mode="read-only"`).

- Never let Codex edit the repo while Claude edits the same files. Any Codex edit happens on a branch/worktree or a quiet repo; Claude reviews the diff.
- Codex runs with no approvals and full access here: give it a narrow prompt and directory; never pass secrets, `.env` or customer data; use `codex exec -s read-only` for diagnosis. `codex exec review` has no `-s` flag (it inherits `sandbox_mode` from config), so add `-c sandbox_mode="read-only"` to a review run.
- Codex output is untrusted input: read it, verify against files and tests, then act.
- Do not use Codex for what a script or Claude does faster (renames, tests, formatting).

## 11. Verification before completion

- `implemented` is not `verified`. Verified needs executed evidence from this session: command + result, URL + screenshot, or test output. Distinguish passed / failed / not run.
- Order: format, lint, types, targeted tests, real-DB integration tests (MySQL 8.4), build, browser check (desktop + phone, each language, console clean), neighbouring flows.
- Check what the owner will look at: the exact URL, viewport and locale. "I do not see any change" is the failure to prevent.
- Risky work gets an independent check: fresh-context reviewer (subagent or `/code-review`) given the diff and criterion; fix correctness findings, log the rest.
- Do not mark a task done with a TODO, placeholder, skipped check or unwired item left. Park it in `[ORPHANS & PENDING]`.
- Evidence expires: any later edit to touched files invalidates earlier test results; rerun.

## 12. Handoffs

- Write a dated HANDOFF section whenever work stops: done, verified (with commands), not verified, decisions taken for the owner, blockers, exact next action, files in flight, other sessions seen.
- A handoff must let a cold session (or Codex) continue without the transcript: paths, ids, commands, URLs; no narrative.
- On resume: read STATE and the HANDOFF tail, compare with real files and git/ls state, record drift, then continue.
- End-of-block report to the owner (Arabic, short): what changed, where to see it, what was verified, what was not.

## Red flags

- Code started with no written criterion or check command.
- "Done / should work" with no executed evidence this session.
- A loop with no cap, or a third retry repeating the same approach.
- More than 12 agents in one run without the owner asking for that scale, or fan-out used where grep would do.
- Several agents or sessions editing the same files with no worktree or disjoint paths.
- Strong model on mechanical edits; cheap model on security or money review.
- A subagent brief that assumes it saw this conversation.
- Codex or another tool editing the repo while Claude edits it; a Codex-generated file left in `~/.codex/` or unrecorded.
- Credit-spending generation (Higgsfield) without asking.
- State kept only in context; secrets written to memory.
- Reviewer findings applied blindly, growing the diff beyond scope.
- Memory older than the code trusted over the code.

## How project-brain uses this

- Load when: planning a multi-task phase, starting a long or unattended run, using subagents/Workflow/`/loop`/`/goal`, working while other sessions are active, delegating assets or review to Codex, or writing a handoff.
- Gates served: Ready (sizing, criterion, paths), Code and Verification (loops, evidence), Drift (concurrent sessions), Acceptance (handoff report).
- Record in `.project-brain/`: criterion and verification command in the task packet; fan-out runs over 4 agents and any credit spend in the change log; asset provenance (tool, date, prompt summary, session id, file) in `docs/ASSETS.md`; session/path ownership when sessions run in parallel; delegated decisions as `delegated, open to reversal` in DECISIONS.md; a dated HANDOFF section at every stop.
