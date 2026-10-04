# Memory protocol

The repository memory is the cross-runtime source. Runtime auto-memory and conversation history are optional inputs, never the sole source of truth.

## Persist

- facts with evidence and confidence;
- owner decisions and rejected alternatives;
- constraints, invariants, corrections, risks, blockers;
- task transitions and verification evidence;
- concise session summaries and next action.

Do not persist hidden reasoning, raw secrets, credentials, access tokens, unnecessary personal data, large command output, copied documentation, or speculative facts presented as truth.

## Layers

| Layer | Location | Load policy |
|---|---|---|
| Current | `STATE.yaml`, `HANDOFF.md` | every resume |
| Canonical | product/planning/design/security/tracking | only role-relevant files |
| Decisions | `decisions/*.md` | referenced decision only |
| Working | in-session notes, open questions, temp assumptions | discard after compaction; never persist raw |
| Events | `logs/*.jsonl` | search/filter; do not load wholesale |
| Episodes | `memory/summaries/*.json` | latest relevant summaries |
| Raw transcript | outside active memory | optional; compact before use |

The repository files are the cross-runtime shared memory. Runtime auto-memory and conversation history are optional inputs. When a Subagent or secondary runtime resumes work, it must read repository files, not rely on a session transcript it cannot access.

## Source precedence

When sources conflict, resolve in this order:
1. Current explicit owner instruction.
2. Accepted decision record.
3. Approved requirements and contracts.
4. Verified source code, migrations, configuration, and tests.
5. Current project-memory records.
6. Change logs and session summaries.
7. Old conversation text.
8. Agent inference.

Do not silently choose between conflicting authoritative sources. Record drift and ask the owner when product behavior, money, law, privacy, destructive operations, or security posture would change.

## Compaction

Convert session notes into `decisions`, `facts`, `constraints`, `corrections`, `open_questions`, `completed`, `blockers`, and `next_actions`. Every item needs explicit wording; uncertain items remain unknown. A correction supersedes the old fact but never erases audit history.

## Resume

Validate memory, read handoff, inspect actual repository state and Git diff, then compare the claimed last task with files and tests. If memory is stale, record drift before continuing. Generate a new handoff whenever work stops, succeeds, fails, or is blocked.

