# Runtime adapters

Keep `.project-brain/` portable. Runtime-specific configuration may enforce the same contracts but must not become the canonical project memory.

## Codex

- Place a project copy of the skill under `.agents/skills/project-brain/` when repository-local distribution is desired.
- Use `AGENTS.md` for always-on repository facts and boundaries, not for duplicating the full workflow.
- Invoke the skill explicitly for project initialization, planning, implementation, review, resume, and audit.

## Claude Code

- Place the skill under `.claude/skills/project-brain/` or a supported personal skills directory.
- Use `CLAUDE.md` for stable project facts and link to `.project-brain/`.
- Optional custom subagents may specialize by role, but must read and write the same canonical records.
- Use deterministic hooks for formatting, validation, scope checks, secret scanning and stop-time handoff. Hooks must never exfiltrate source, secrets or personal data.

## Portability

If a runtime-specific feature is absent, fall back to the shared skill instructions and CLI. Do not make successful project recovery depend on a private transcript path, proprietary session ID, or hidden auto-memory.

