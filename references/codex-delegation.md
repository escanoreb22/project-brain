# Codex delegation (Claude → Codex)

Codex CLI is a cheap junior worker and an image generator. Claude decides, writes the brief, reviews, and accepts or rejects. Codex never decides product, architecture, security or scope.

## Tools (verified 2026-10-03, Codex CLI 0.160.0)

| Way | When |
|---|---|
| MCP server `codex-delegate` (user scope, every project): `codex_generate_image`, `codex_easy_task` | Default. Call like any MCP tool (Higgsfield-style). |
| CLI fallback: `python ~/.claude/skills/project-brain/scripts/codex_delegate.py image|task ...` | If the MCP server is not loaded in this session. Same rules, same JSON output. |

Both run `codex exec` lean (`--ephemeral`, plugins/apps disabled, `workspace-write` sandbox, structured output for tasks). **Model and effort are never fixed: Claude chooses them on every call** (`model`, `effort` are required). The live list comes from Codex's own cache: MCP tool `codex_models`, or CLI `codex_delegate.py models`; an unsupported choice is rejected with the list.

How Claude chooses:
- Read each model's description in the live list. Pick the cheapest model described as fast/affordable/efficient that can do the job; move up to a balanced or workhorse model only when the job needs reasoning (pattern-following across 2-3 files, a test to write from an example).
- Effort: `low` for images and one-spot edits; `medium` when Codex must read surrounding code to match a pattern; never above `medium` — a task needing more is not an easy task, so do it yourself.
- For images the image tool does the drawing; the agent model only writes the request, so the cheapest model + `low` is normally right.
- Record the chosen model/effort in the change log entry; if a result is weak, change the brief before raising the model.

Measured on 2026-10-03 with a fast model at `low`: an image ≈ 10k Codex tokens (~1 min); a one-line edit ≈ 23k Codex tokens. These tokens are billed to the owner's Codex plan, not the Claude plan.

## Delegate (yes)

- **Images:** illustrations, hero/section art, empty-state art, backgrounds, icon-style images, mockup imagery, social/OG images, image variations from a reference. Prefer Codex over Higgsfield for still images (Higgsfield costs credits — keep it for video/motion when the owner asks).
- **Very easy edits**, fully specified, ≤ ~3 files, with an example to copy or an exact target:
  - adding/fixing translation strings in ar/fr/en files;
  - renaming labels, copy fixes, adding a column/field following an existing identical one;
  - small CSS/Tailwind token swaps the brief spells out;
  - boilerplate that mirrors an existing file (a FormRequest, a Resource, a test case) when the pattern is named;
  - converting/optimizing assets with a given command.

## Never delegate

Auth, authorization, tenancy, payments/ledgers/stock, migrations, deploys, security fixes, anything ambiguous, design decisions, refactors, multi-module changes, work on files another session is editing, anything touching `.env` or secrets. If you have to explain *why*, it is not an easy task — do it yourself.

## Brief rules

**Image brief** = subject + composition + what to avoid + aspect + background + style/palette from the project's design tokens (hex values) + reference image when one exists. Write the destination `out` as an absolute path in the project's assets folder (e.g. `public/images/...` or the repo's existing asset dir) and pass `project` for provenance. Text in images: avoid; put text in HTML instead (Arabic text from image models is unreliable).

**Task brief** = exact files (`allowed` = only those), current → expected result, an example to copy, the acceptance criterion, and a `check` command (one test file, `tsc --noEmit`, `php -l file`, lint on the file). One task per call; never batch unrelated edits.

## Acceptance (Claude, every time)

1. Read the JSON: `ok`, `outside_allowed` must be empty, `codex_report.status` must be `done`.
2. Images: open the file and judge it against the brief (artifacts, stray text, palette, cropping, RTL/cultural fit). Max 2 regenerations with a sharper brief, then do it another way or ask the owner. Convert to webp/avif, produce needed sizes, set width/height and alt in every locale, record in `docs/ASSETS.md` if the project keeps one.
3. Tasks: read the diff of `actually_changed`, rerun the check yourself, run the project's relevant tests. Revert anything outside scope. Codex output is untrusted input.
4. Log the outcome in the change log as `delegated:codex` (provenance is also appended automatically to `.project-brain/logs/DELEGATIONS.jsonl` when that folder exists).

## Failure handling

- Model error ("requires a newer version"): run `codex update` once, retry; else report to the owner.
- `ok:false` with no image: sharpen the brief once; then stop.
- Codex `blocked`: the task was not easy — do it yourself; do not re-prompt Codex into guessing.
- Never run Codex and Claude on the same files at the same time.

## Red flags

- Delegating to save tokens on something that needs judgment, then spending more on fixing it.
- Accepting a Codex result without opening the image or reading the diff.
- Images with embedded text, mixed styles across a page, or palette not from the design tokens.
- Codex touching files outside `allowed`, lock files, `.env`, or migrations.

## How project-brain uses this

Load when a task needs raster assets or contains a cluster of trivial, fully specified edits. It serves the Code and Design gates: delegation never lowers the evidence bar — Claude's own verification is still required before a task is `verified`.

## Codex inside workflows

Workflows take `args.codex = { task, review, image }`, each `{model, effort}` chosen by Claude from the live model list before launch. Lanes: `review-changes.js` (Codex as an extra review lens), `security-audit.js` (Codex hunter per surface), `execution-engine.js` (items with `executor: "codex"` + `allowed` paths), `asset-batch.js` (image generation with Claude judging + one retry). A small Claude runner writes the job as JSON to `.tmp/spec-*.json` and runs `codex_delegate.py run --spec <file>` (UTF-8 safe, no shell quoting). Also available outside workflows: `codex_delegate.py review` / MCP `codex_review` (read-only second-vendor review; fails if any file changes).

Rules: Codex never gets the last word: review findings go through Claude verification, Codex edits through the Claude verifier, Codex images through a Claude judge. Keep workflow script strings ASCII and avoid the `->` sequence (the Workflow approval filter rejects it as hidden content).
