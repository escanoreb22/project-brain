# Optional modules

The author's private copy bundles third-party skills here. They are **not redistributed** in the public repository because their licenses either do not allow it or are not documented in the copies. project-brain works without them: when a `modules/...` path in `SKILL.md` is missing, the agent uses the matching `references/` file instead.

To add one, install it from its source into the folder shown, then run `python scripts/install.py`.

| Folder | Gives | Source |
|---|---|---|
| `modules/ui/apple-hig/` | Apple Human Interface Guidelines, distilled per component | https://github.com/justinwetch/HIGAgentSkills |
| `modules/ui/frontend-design/` | Distinctive visual direction for new UI | Anthropic's `frontend-design` skill/plugin (check its license before copying) |
| `modules/ui/design-taste-frontend/` | Anti-"AI slop" landing pages and redesigns | the "taste skill" (tasteskill) — search its repository and license |
| `modules/ui/ui-ux-pro-max/` | Compact UI/UX rules | the "ui-ux-pro-max" skill — search its repository and license |
| `modules/review/code-review/` | Code review method + specialist reviewers | Anthropic Claude Code plugins `code-review`, `pr-review-toolkit` (https://github.com/anthropics/claude-code) |
| `modules/review/security-review/` | Security review method, insecure-pattern list | Claude Code `/security-review` and the `security-guidance` plugin |
| `modules/brain-graph/` | Knowledge graph of docs and code | graphify (`pip install graphifyy`); the `graphify` CLI alone is enough for project-brain's scripts |
