# Deploy protocol (live updates)

Use when the owner says "حدث المشروع" / "update the live site" / "deploy". Read the project's own runbook and memory first (VPS access, paths, procedure); they override this generic list.

## Before

1. Diff incoming code against live (dry-run sync, excluding storage, caches, build output, vendor, node_modules, `.env`, verification files such as `public/google*.html`).
2. Classify every change:
   - **safe** — code/UI/text/assets, additive migrations, config already present;
   - **risky** — destructive or locking migrations, server/runtime changes (SSR, workers, PHP version), security headers/CSP, service workers/PWA, cache or CDN rules, deletions, auth/session changes, anything touching money or tenant data.
3. Audit SEO on live and incoming (titles, canonical, hreflang/locale routes, sitemap, robots, structured data) when the project has public pages.
4. Deploy the safe set. Present each risky item to the owner as a one-line question with a recommended answer and **wait**. Never push a risky item on judgment alone.

## During

Backup DB → maintenance mode → sync with correct ownership → install deps only if lockfiles changed → build → migrate → optimize/cache → restart queues/workers → restart SSR if the project uses it (a stale SSR bundle causes hydration errors everywhere) → back up.

## After

- Verify through the public domain (cache-busting query) the exact pages changed, plus login, one critical flow and the console for errors.
- Confirm every asset the owner expects is live (a missing favicon was once noticed by the owner, not by the agent).
- Record the deploy in the change log with what shipped, what was held back and why.
