# Operations and monitoring - post-release runbook for a solo founder

Scope: Laravel 12/13 + MySQL 8.4 + Redis, Inertia SSR, Flutter, Electron POS, on a CloudPanel VPS behind Cloudflare. Pair with `deploy-protocol.md` (shipping), `security-protocol.md` (hardening), `quality-gates.md` (evidence), `compliance-payments.md` (breach and legal duties). Shared hosting without a terminal: no Supervisor; use the cron fallback in `backend-architecture.md` sec. 7 and skip the supervisor parts of section 5. Do not duplicate them; this file covers what runs AFTER release.

## 1. Health endpoints

- Laravel ships a health route at `/up` (200 if the app booted, 500 otherwise). Change the path with `health:` in `->withRouting(...)` in `bootstrap/app.php`.
- Laravel dispatches `Illuminate\Foundation\Events\DiagnosingHealth` on each hit. Listener throws an exception = 500. Use it for DB and Redis checks.
- Two endpoints, two purposes:

| Endpoint | Checks | Who calls it | Public? |
|---|---|---|---|
| `/up` (built in) | app boots | external uptime monitor, 1 per site | yes, no data in body |
| `/health/deep` (own) | DB `select 1`, Redis ping, queue heartbeat age, disk free %, SSR reachable | monitor with keyword, plus on-box cron | token header or IP allowlist |

- Queue heartbeat: scheduler job writes `Cache::put('hb:scheduler', now())` every minute; a worker job writes `hb:queue`; deep check fails if older than 5 min. This catches "supervisor alive but worker stuck".

## 2. Uptime monitoring (free options)

| Tool | Free tier (verified) | Note |
|---|---|---|
| UptimeRobot | 50 monitors, 5-min interval, 1 basic status page | Terms (updated 2026-05-26) allow commercial use on every plan, Free included; the 2024 non-commercial clause was removed. Re-read the terms if they change. |
| Sentry Developer plan | includes 1 uptime monitor | enough for the main site only |
| Self-hosted GlitchTip | uptime monitoring included | see section 3 |

- Default setup: 3 external monitors minimum: public site (`/up`), app/API (`/up` or `/health/deep` with keyword), admin or SSR-rendered page (keyword that proves SSR output, not the empty shell).

## 3. Error tracking

Default: Sentry hosted Developer plan for launch (verified: 5k errors/month, 1 user, 50 replays, 5M spans). Move to self-hosted GlitchTip when the quota or the single-user limit hurts or data residency requires it.

| Option | Cost | Ops burden | Decision |
|---|---|---|---|
| Sentry Developer | free, 5k errors/mo | none | start here; set sampling and rate limits so one bug cannot burn the month |
| GlitchTip self-hosted | free, MIT, needs PostgreSQL 14+, Redis/Valkey optional, 512 MB RAM advised | one more service to patch and back up | use when quota is the issue; its SDK compatibility is stated by third parties and by its own pitch (UNVERIFIED on the install page) |

SDK checklist per surface (package names verified from Sentry docs):

| Surface | Package | Must do |
|---|---|---|
| Laravel | `composer require sentry/sentry-laravel`, then `php artisan sentry:publish --dsn=...` | in `bootstrap/app.php`: `->withExceptions(function (Exceptions $exceptions) { \Sentry\Laravel\Integration::handles($exceptions); })`; verify with `php artisan sentry:test`; DSN env var is `SENTRY_LARAVEL_DSN` |
| React (Inertia) | `npm install @sentry/react` | `Sentry.init` once in app entry; React 19 `createRoot` options `onUncaughtError`, `onCaughtError`, `onRecoverableError` with `Sentry.reactErrorHandler`; source maps via `npx @sentry/wizard@latest -i sourcemaps` |
| SSR (Node) | UNKNOWN package choice (UNVERIFIED) | capture SSR render errors separately; confirm in Sentry docs for the Node SDK before adding |
| Flutter | `sentry_flutter` + `sentry_dart_plugin` | `SentryFlutter.init`; upload debug symbols in release builds, mandatory when obfuscating |
| Electron | `npm install @sentry/electron` | init in main (`@sentry/electron/main`) as early as possible and in renderer (`@sentry/electron/renderer`); renderer DSN has no effect, events go through main; set userData path BEFORE init |

Rules:
- Tag every event with `release` (git SHA or version), `environment`, and `tenant_id` (an id, never name or email). Per-tenant filtering is the main value for B2B.
- Set `send_default_pii=false`. Scrub: Authorization, cookies, card data, license keys, SQLCipher keys, POS receipts. Test the scrub with a fake secret.
- `tracesSampleRate` 0.1 or lower in production; replay on error only. The free tier is small.
- Release gate: a deploy is not finished until a deliberately thrown test error shows up in the tracker with a readable (source-mapped) stack.

## 4. Structured logs and rotation

Laravel (verified): default channel is `stack`; `daily` driver rotates; retention via `LOG_DAILY_DAYS` or `days` (default 14); `Log::withContext([...])` / `Log::shareContext([...])` add context; levels follow RFC 5424; a `deprecations` channel exists.

Production defaults:
- `LOG_CHANNEL=stack`, stack = `daily` (+ error tracker handler). `LOG_LEVEL=info` (not debug). `APP_DEBUG=false` always.
- Middleware assigns a request id, calls `Log::shareContext(['request_id'=>..., 'tenant_id'=>..., 'user_id'=>...])`, and returns it in a response header. Show the id on the error page so a customer can quote it.
- Rotation outside Laravel (nginx, php-fpm, supervisor logs, SSR log): use system `logrotate` with `daily`, `rotate 14`, `compress`, `missingok`, `copytruncate` for supervisor-owned files. Verify with `logrotate -d <conf>` (dry run).

## 5. Queue, worker, scheduler and SSR supervision

CloudPanel docs (checked pages) do not document Supervisor or queue workers: treat the supervisor setup as a manual OS-level task (UNVERIFIED how CloudPanel handles it). Confirm that `supervisorctl` exists before writing config.

Laravel supervisor example (from Laravel docs; adapt paths and user):
```ini
[program:site-worker]
process_name=%(program_name)s_%(process_num)02d
command=php /home/SITE_USER/htdocs/SITE/artisan queue:work redis --queue=default --sleep=3 --tries=3 --max-time=3600
user=SITE_USER
autostart=true
autorestart=true
numprocs=2
redirect_stderr=true
stdout_logfile=/home/SITE_USER/logs/worker.log
stopwaitsecs=3600
```
Rules:
- Job `timeout` < connection `retry_after` (Laravel docs), else duplicate runs. Money jobs must be idempotent.
- Every deploy ends with `php artisan queue:restart` (graceful; supervisor respawns). Laravel 12/13 deployment docs also describe `php artisan reload`, which terminates queue workers, Reverb and Octane so the process monitor restarts them; confirm it exists with `php artisan list` before using it.
- Backlog alert: `php artisan queue:monitor redis:default --max=1000` scheduled every minute, notification on threshold.
- Scheduler: one cron line as the site user: `* * * * * cd /home/SITE_USER/htdocs/SITE && php artisan schedule:run >> /dev/null 2>&1`. CloudPanel supports site-user cron via the Cron Jobs tab or `crontab -e` as the site user (verified). Use `->onOneServer()` only if multi-server; use `->withoutOverlapping()` on long jobs.
- Inertia SSR (inertiajs.com SSR docs): Supervisor runs `php artisan inertia:start-ssr`; on deploy run `php artisan inertia:stop-ssr` and Supervisor starts a fresh process with the new bundle; `php artisan inertia:check-ssr` is the health check (deep health and post-deploy). Restart SSR after every frontend build or pages render stale or fail.

## 6. Backups, off-site copy, restore test

CloudPanel remote backups (verified): per-site, backs up vhost and home directory excluding `.ssh`, logs, tmp; stores `backup.tar`; destinations: S3, Wasabi, DO Spaces, Dropbox, Hetzner Storage Box, SFTP, Rclone targets. Whether it includes MySQL data is NOT stated on the checked page (UNVERIFIED), and retention is not stated. Therefore:

Policy (3-2-1 minimum): 3 copies, 2 media, 1 off-provider. The VPS provider's snapshot does not count as off-site.

| What | How | Frequency | Keep |
|---|---|---|---|
| MySQL | own script with `mysqldump --single-transaction --routines --triggers --events --no-tablespaces` (verified options), gzip, encrypt | daily at low traffic, plus before every migration | 7 daily, 4 weekly, 6 monthly |
| Uploaded files (`storage/app`, public uploads) | CloudPanel remote backup or `rclone sync`/`restic` | daily | same |
| `.env` and secrets | encrypted copy in the owner's password manager, never in the repo or plain dump | on change | latest 2 |

Script rules:
- `set -euo pipefail`; credentials from a `~/.my.cnf` with mode 600, never on the command line.
- Dump then check: non-zero size, gzip -t, and row count sanity on 2 key tables. Write a result log line and ping the heartbeat URL only on success.
- Encrypt before upload (`age` or `gpg`; key stored off the server). Unencrypted tenant data off-site is a breach risk.

Monthly RESTORE TEST (mandatory, 30 minutes, owner or agent, on a scratch DB, never on production):
1. Download the latest off-site backup to a scratch machine; decrypt with the off-box key.
2. `mysql` create scratch DB `restore_test`; import the dump on MySQL 8.4 (same major as prod).
3. Run: row counts of 5 key tables vs production (within the backup window), `CHECK TABLE` on the largest, one tenant-scoped query, Laravel `php artisan migrate:status` against it.
4. Open the app against the scratch DB and files; log in; load one invoice or POS sale and one uploaded file.
5. Record in `.project-brain/` ops log: date, backup age, restore time (RTO measured), data loss window (RPO measured), pass/fail. A failed test is a P2 incident.
6. Delete the scratch DB and the downloaded files.

## 7. Cloudflare settings that matter

Verified facts: Cloudflare does not cache HTML or JSON by default; it skips caching on `private`, `no-store`, `no-cache`, `max-age=0` or a `Set-Cookie`; default cached types are static assets (images, JS, CSS, etc.); Cache Rules are available on all plans (Free: 10 rules) and need proxied (orange cloud) DNS; Cloudflare ignores `Vary` by default except `Accept-Encoding`.

Rules:
- Do NOT add a "cache everything" rule on a dynamic host. Inertia serves HTML and JSON from the same URL depending on the `X-Inertia` header; since `Vary` is ignored, a cached HTML page can be served to an Inertia XHR (or the reverse) and break navigation or leak a logged-in page.
- Rule order (first, explicit bypass): `starts_with(http.request.uri.path, "/api")` OR path in (`/up`, `/health`, `/login`, `/logout`, `/admin`, `/app`, `/broadcasting`, `/livewire` if used) OR header `X-Inertia` present OR cookie `laravel_session` present -> Bypass cache. Then allow static: `/build/*` (Vite hashed assets) -> Eligible, Edge TTL 1 year (hashed names make this safe), Browser TTL 1 year.
- SSL/TLS mode: Full (strict) with an origin certificate. Never Flexible. Always Use HTTPS on. Minimum TLS 1.2. HSTS only after confirming all subdomains serve HTTPS.
- Real client IP: behind Cloudflare, Laravel sees Cloudflare IPs. Configure trusted proxies (`trustProxies`) for Cloudflare ranges and use `CF-Connecting-IP`, otherwise rate limits and audit logs are wrong (same rule in `api-design.md` sec. 14). Lock the origin firewall to Cloudflare IP ranges so attackers cannot hit the VPS IP directly.
- WAF basics (verified): Free plan has the Cloudflare Free Managed Ruleset (high-impact vulnerabilities); Pro and above add Cloudflare Managed and OWASP Core rulesets. Cloudflare docs say the Free Managed Ruleset is deployed by default on Free plans; confirm it is still enabled in the dashboard.
- Free rate limiting (verified): 1 rule, 10-second period and timeout, match on Path and Verified Bot only, per IP. Use it on `/login` and `/api/*/auth` as a coarse shield; keep Laravel `RateLimiter` as the precise per-user and per-tenant limit.

## 8. Performance budgets and automated audits

Budgets (Core Web Vitals "good", verified, measured at p75): LCP <= 2.5 s, INP <= 200 ms, CLS <= 0.1. Add own budgets: Lighthouse performance >= 90 on public pages (mobile profile), initial JS on public pages <= 170 KB gzip (same default as `frontend-system-design.md` sec. 11), API p95 <= 500 ms for list endpoints.

Lighthouse CLI (verified flags; requires Node 22 LTS or later per the repo README):
```bash
npx lighthouse https://example.com/fr --output json --output-path ./.tmp/lh-fr.json --chrome-flags="--headless" --only-categories=performance,accessibility,seo,best-practices
npx lighthouse https://example.com/ --preset=desktop --output json --output html --output-path ./.tmp/lh-desktop
```

axe CLI (verified flags):
```bash
npx @axe-core/cli https://example.com/ar --tags wcag2a,wcag2aa --exit --save ./.tmp/axe-ar.json
npx @axe-core/cli https://example.com/fr https://example.com/en --tags wcag2a,wcag2aa --exit
```
`--exit` returns a failing code on violations (CI-friendly). It needs a Chrome driver; use `--chromedriver-path` if versions mismatch. For logged-in pages use Playwright with `@axe-core/playwright` instead (UNVERIFIED here, confirm package docs).

Regression rule: a release that drops any budget by more than 5 points or breaks a Core Web Vital threshold is held unless the owner accepts it (gate).

## 9. Secret rotation

| Secret | Rotate | Trigger events | Notes |
|---|---|---|---|
| `APP_KEY` | only on compromise | leak | a bare change logs everyone out and makes encrypted values unreadable; put the old key in `APP_PREVIOUS_KEYS` (comma list; Laravel tries the current key, then previous ones), re-encrypt stored values, then drop the old key (laravel.com/docs/12.x/encryption) |
| DB password, Redis password | 12 months | staff or contractor exit, leak | update `.env`, `php artisan config:cache`, restart workers and SSR |
| Stripe keys and webhook secret | on leak or yearly | leak, repo exposure | use restricted keys; roll in dashboard, deploy, then revoke old |
| Cloudflare API tokens | 6-12 months | leak | scope tokens to one zone and minimal permissions |
| Backup encryption key | never silently | loss = unrecoverable | keep two offline copies; test decrypt monthly in the restore test |
| SQLCipher key (Electron POS) | per policy in `desktop-electron.md` | device loss | key change requires re-encrypt migration; gate |
| SSH keys, deploy keys | yearly | laptop loss | one key per person and machine |

Procedure: create new, deploy new, verify, revoke old, log date in the ops log (no values). A pasted secret in chat = remind the owner once to rotate. Never commit `.env`. Run a secret scan (`gitleaks` or equivalent) before release; any hit = rotate, not just delete.

## 10. Incident runbook

Severity: P1 = site or POS sync down, data loss or exposure, payments broken. P2 = major feature broken, degraded. P3 = minor, workaround exists.

1. Detect: alert from monitor or error tracker or customer. Open an incident note immediately: time (UTC), who noticed, symptom.
2. Triage (5 min): is it the edge (Cloudflare status), the VPS (disk, RAM, CPU, `systemctl`), the app (`/up`, error tracker), a dependency (DB, Redis, Stripe), or the last deploy? Check "what changed in the last 24 h" first (deploys, Cloudflare edits, cert expiry, cron).
3. Mitigate before fixing: rollback (section 11), restart workers/SSR, enable maintenance mode `php artisan down --secret=...` (check flags with `php artisan down --help`), disable the failing feature flag, block abusive IP in Cloudflare, free disk. Mitigation is reversible; root-cause fixes wait.
4. Communicate: status page update within 15 min for P1 (what is affected, next update time). Per-tenant email only if their data or money is affected. Legal: personal data exposure follows the breach runbook in `compliance-payments.md` sec. 3 (GDPR art. 33: authority notice within 72 h of awareness where feasible; Law 09-08 duties UNVERIFIED there). Notifications are an owner gate.
5. Resolve and verify: run the failing user flow in the real browser, check the queue, check the error rate for 30 min.
6. Postmortem within 3 days for P1/P2, blameless, saved in `.project-brain/incidents/YYYY-MM-DD-slug.md`.

Postmortem template:
```
# Incident YYYY-MM-DD - title
Severity: P? | Duration: start-end (UTC) | Detected by: monitor/user/self
Impact: who, how many tenants, money or data affected
Timeline (UTC): hh:mm event ...
Root cause: one paragraph, technical
Why detection was late or early: ...
What worked / what did not: ...
Actions: [owner, due date, ticket id] (at least one prevents recurrence, one improves detection)
Customer communication sent: yes/no, link
```

Agent behavior in an incident: gather facts read-only first; do not run destructive commands (drop, truncate, delete, force push) without the owner's yes; production changes follow `deploy-protocol.md` gates. Report in Arabic, short.

## 11. Release cadence and rollback

- Every release has: version/tag, changelog entry, migration list, rollback note, post-deploy checks (health, error tracker release visible, one smoke flow per surface).
- Expand/contract migrations only (see `db-schema-design.md`): a code rollback must work against the already-migrated schema. Never ship a migration that makes the previous release crash.
- Rollback ladder (try in order): (1) feature flag off; (2) redeploy the previous tag/build with the `deploy-protocol.md` steps (keep the previous build ZIP or tag ready; use a symlink switch only if the project already deploys into release directories); (3) restore DB from the pre-deploy dump (data loss since deploy; owner gate); never `migrate:rollback` blindly in production on data-bearing tables.
- After rollback: `php artisan optimize`, `php artisan queue:restart`, restart SSR, purge Cloudflare cache for changed assets, confirm via the public domain.

## 12. Weekly ops checklist (15 minutes, same day each week)

- [ ] Uptime monitors green; review last 7 days incident list and response times.
- [ ] Error tracker: triage new and regressed issues; resolve or ticket; check quota use.
- [ ] `supervisorctl status`; `php artisan queue:failed`; queue backlog near zero; scheduler heartbeat fresh.
- [ ] Backup jobs: last success time < 26 h for DB, files; off-site copy visible; heartbeat green.
- [ ] Disk (< 80%), RAM, swap, load; log directory size; Redis memory.
- [ ] Lighthouse + axe run on public pages (all locales); compare with budgets.
- [ ] Monthly (first week): RESTORE TEST, alert-channel test, secret and access review (who has SSH, Cloudflare, Sentry access).
- [ ] Log findings in the ops log; open tasks for anything red.

## Red flags

- Backups exist but no restore was ever tested, or the only copy lives on the same VPS or provider account.
- "Cache everything" or a long HTML cache on a host that serves Inertia, `/api`, or logged-in pages.
- `APP_DEBUG=true`, `LOG_LEVEL=debug`, or secrets/PII in logs and error events.
- Workers not supervised, not restarted after deploy, or running as root; SSR not restarted after a frontend build.
- Alerts that go only to email nobody reads; a single monitor behind the same Cloudflare zone.
- Uptime or error-tracking tool terms and quotas not re-checked before launch.
- Stripe webhook or POS sync path blocked by WAF, Bot Fight Mode or rate limit (found by customers, not by tests).
- Migration not backward compatible with the previous release (no rollback possible).
- Incident fixed without a postmortem action that improves detection.
- Any fact in this file used without checking the installed version (Laravel, Sentry SDK, supervisor, MySQL) in the lockfile or on the server.

## How project-brain uses this

- Deploy playbook (3.10): after `deploy-protocol.md` steps, run section 11 post-deploy checks and the section 5 worker/SSR restart; do not report "deployed" without health and error-tracker evidence.
- New project / PRD (3.1): add "operations" requirements to the PRD (uptime target, RPO/RTO, backup retention, monitoring owner) so they reach `PROJECT_MAP`; unwired items go to `[ORPHANS & PENDING]`.
- Backend work (3.7): health endpoint, request-id middleware, log context, idempotent jobs come from sections 1, 4, 5.
- Gates (`SKILL.md` section 5): restore from backup, rollback with data loss, Cloudflare WAF changes that block traffic, secret rotation affecting live clients, and legal notifications require the owner's yes.
- Sources (official unless noted): https://laravel.com/docs/12.x/deployment , https://inertiajs.com/docs/v2/advanced/server-side-rendering , https://uptimerobot.com/terms/ , https://developers.cloudflare.com/waf/get-started/ , https://laravel.com/docs/12.x/queues , https://laravel.com/docs/12.x/logging , https://docs.sentry.io/platforms/php/guides/laravel/ , https://docs.sentry.io/platforms/javascript/guides/react/ , https://docs.sentry.io/platforms/dart/guides/flutter/ , https://docs.sentry.io/platforms/javascript/guides/electron/ , https://sentry.io/pricing/ , https://uptimerobot.com/pricing/ , https://glitchtip.com/documentation/install , https://www.cloudpanel.io/docs/v2/admin-area/backups/ , https://www.cloudpanel.io/docs/v2/frontend-area/cron-jobs/ , https://developers.cloudflare.com/cache/concepts/default-cache-behavior/ , https://developers.cloudflare.com/cache/how-to/cache-rules/ , https://developers.cloudflare.com/cache/concepts/cache-control/ , https://developers.cloudflare.com/waf/managed-rules/ , https://developers.cloudflare.com/waf/rate-limiting-rules/ , https://developers.cloudflare.com/waf/custom-rules/skip/ , https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html , https://github.com/GoogleChrome/lighthouse , https://github.com/dequelabs/axe-core-npm/blob/develop/packages/cli/README.md , https://web.dev/articles/vitals
