# Security baseline — the owner's 14 weakness classes + 20 backend fundamentals

**Owner rule (2026-10-03): this list is mandatory for every backend change and every security review.** Each item gives: where it appears in the owner's stack (Laravel/PHP, Node/Electron, React/Inertia, Flutter), the safe default, the forbidden pattern (machine-checked by `scripts/vuln_scan.py` where possible), and the test that proves the protection. Deeper material: `modules/review/security-review/`, `security-protocol.md`, `backend-architecture.md`, `api-design.md`, `db-schema-design.md`.

How to use: implementers apply the safe defaults; reviewers walk the 14 classes for every changed route/action; `pb.py finish` and the pre-commit gate run `vuln_scan.py --changed`; `workflows/security-audit.js` hunts by these classes.

---

## Part A — Weakness classes (CWE)

| # | Class | CWE |
|---|---|---|
| 1 | OS Command Injection | CWE-78 |
| 2 | Code Injection (the owner's list wrote CWE-78; the correct id is CWE-94) | CWE-94 |
| 3 | Server-Side Request Forgery | CWE-918 |
| 4 | Command Injection (generic: any interpreter/command string) | CWE-77 |
| 5 | Missing Authorization | CWE-862 |
| 6 | Incorrect Authorization | CWE-863 |
| 7 | Missing Authentication for Critical Function | CWE-306 |
| 8 | Improper Authentication | CWE-287 |
| 9 | Trust Boundary Violation | CWE-501 |
| 10 | Improper Privilege Management | CWE-269 |
| 11 | Session Fixation | CWE-384 |
| 12 | SQL Injection | CWE-89 |
| 13 | Buffer Overflow (classic buffer copy) | CWE-120 |
| 14 | Cross-Site Scripting | CWE-79 |

### 1. OS Command Injection (CWE-78) and 4. Command Injection (CWE-77)
- Where: PDF/image tooling, backups (`mysqldump`), git/ffmpeg calls, Electron main process, deploy scripts.
- Default: avoid the shell. Laravel: `Process::run(['mysqldump', '--single-transaction', $db])` (array form, no shell). PHP raw: `proc_open` with an argument array. Node/Electron: `execFile`/`spawn(cmd, args, {shell:false})`. Fixed executable path; user input only as a separate argument, validated against an allowlist (enum, regex, ULID).
- Forbidden: `exec|shell_exec|system|passthru|popen|proc_open|backticks` with interpolated or request data; Node `exec(`/`execSync(` with template strings; `{shell:true}` with user data; building command strings with `.` / `+` / `${}`.
- If a shell is unavoidable: `escapeshellarg` on every argument AND an allowlist; never `escapeshellcmd` alone.
- Test: send `; id`, `&& whoami`, `$(sleep 5)`, `| ls` in the field; assert the call is rejected or the payload is passed as one literal argument.

### 2. Code Injection (CWE-94)
- Where: dynamic evaluation, template engines, deserialization, dynamic `include`, Electron `nodeIntegration`.
- Default: never evaluate user-controlled strings. Blade escapes by default; never compile user templates. Use JSON, never `unserialize()` on untrusted data (use `json_decode`); if a serialized class is unavoidable, `unserialize($x, ['allowed_classes' => false])`.
- Forbidden: `eval(`, `assert(` with strings, `create_function`, `preg_replace` with `/e`, `include/require` of a path built from input, `new Function(`, `setTimeout("string")`, `vm.runInNewContext` with input, `unserialize($request…)`.
- Test: payloads like `${7*7}`, `{{7*7}}`, `phpinfo()` must come back as literal text.

### 3. SSRF (CWE-918)
- Where: "import from URL", webhooks the user configures, link previews, image fetch, PDF rendering of remote URLs (headless Chrome), MaxMind/geo lookups with user URLs.
- Default: allowlist of hosts per feature. Resolve DNS yourself, reject private/loopback/link-local/metadata ranges (127.0.0.0/8, 10/8, 172.16/12, 192.168/16, 169.254/16 incl. 169.254.169.254, ::1, fc00::/7, fe80::/10, 0.0.0.0), then connect to the vetted IP; disable redirects (`Http::withOptions(['allow_redirects' => false])`) or re-validate each hop; only `https` (and `http` only if needed); short timeouts; size cap on the response.
- Headless Chrome PDF: render HTML you built, never navigate to user URLs; block network in the page or route requests through an allowlist.
- Forbidden: `Http::get($request->url)`, `file_get_contents($url)`, `curl` with user URL without validation; following redirects blindly.
- Test: `http://127.0.0.1:…`, `http://169.254.169.254/latest/meta-data/`, `http://[::1]`, a domain that resolves to 10.x, a public URL that redirects to an internal one: all refused.

### 5. Missing Authorization (CWE-862)
- Default: every route/action that reads or changes data goes through a Policy/Gate (`$this->authorize`, `can:` middleware, `Gate::authorize`). Deny by default. Tenant scope derived on the server (never from the request); foreign tenant answers 404.
- Forbidden: controller actions with no policy call or middleware; `Model::find($request->id)` without tenant scope; admin routes outside the admin middleware group; Inertia props exposing data the policy would deny.
- Test: one negative test per tenant-owned route (other tenant's id gives 404) and per role (forbidden role gives 403/404). Keep `authorization_matrix` (role x surface x action) as the source and test it.

### 6. Incorrect Authorization (CWE-863)
- Typical bugs: checking role instead of ownership; checking the parent but not the child (`/companies/{c}/jobs/{j}` where `j` belongs to another company); trusting a client flag (`is_admin`); policy checks that fall through to `true`; caching an authorization result across tenants.
- Default: policies check both role/permission AND ownership of the exact record (scoped route model binding: `->scopeBindings()`); explicit `return false` at the end of every policy method.
- Test: mismatched parent/child ids; staff with partial permissions; suspended/locked accounts.

### 7. Missing Authentication for Critical Function (CWE-306)
- Critical functions: payments/refunds, subscription changes, user/role management, password/email change, data export/deletion, secret/config changes, webhooks that change state, device activation, impersonation.
- Default: all behind `auth` (+ `verified`, + 2FA/step-up for platform staff and destructive actions); webhooks authenticated by signature (HMAC/provider signature) + timestamp tolerance + idempotency; internal endpoints not exposed publicly.
- Forbidden: state-changing route without auth middleware; "secret URL" as the only protection; webhook handler without signature check.
- Test: call every critical route unauthenticated (401/redirect) and with a forged webhook signature (rejected).

### 8. Improper Authentication (CWE-287)
- Default: framework auth only (Sanctum session for SPA, Fortify/Breeze flows, Sanctum tokens for mobile/desktop with abilities + expiry); constant-time comparisons (`hash_equals`); OTP/reset codes single-use, short TTL, hashed at rest, rate limited; account enumeration avoided (same message and timing); MFA for platform staff; Google/OAuth linking only manual with verified email.
- Forbidden: custom token formats, comparing secrets with `==`, logging in by email alone, trusting `X-User-Id` headers, auth tokens in localStorage (owner rule: HttpOnly cookies on web).
- Test: wrong password, reused OTP, expired reset link, brute force throttled, enumeration-neutral responses.

### 9. Trust Boundary Violation (CWE-501)
- Meaning: mixing trusted and untrusted data in the same structure so later code trusts it (e.g. putting request data into the session/`Auth` context, or a client-sent `company_id`/`role` merged into validated data).
- Default: only `$request->validated()` / DTOs cross into the domain; server-derived values (tenant, user, role, prices, totals) are computed server-side and never accepted from the client; IPC from Electron renderer validated in main; data from Codex/LLM output treated as untrusted.
- Forbidden: `$request->all()` into models/sessions, `fill($request->all())`, `$guarded = []` on tenant/money/role fields, prices or totals taken from the client.
- Test: send extra fields (`company_id`, `role`, `price`, `is_admin`) and assert they are ignored.

### 10. Improper Privilege Management (CWE-269)
- Default: least privilege everywhere: role/permission matrix, no implicit super-admin bypass except a single audited platform owner; privilege changes require step-up auth, are audited, and invalidate sessions/tokens; impersonation is explicit, time-boxed, audited and cannot escalate; DB user without DDL in production runtime; queue workers and PHP-FPM not root; Electron app without admin rights.
- Forbidden: users able to edit their own role/permissions; staff creating staff with higher rights; long-lived tokens with all abilities.
- Test: a staff member tries to grant themselves or others a higher role (refused); demoted user's existing token stops working.

### 11. Session Fixation (CWE-384)
- Default: regenerate the session ID on every privilege change: `$request->session()->regenerate()` after login (framework login flows do it; custom flows must), after 2FA success and after context switch (tenant/role selection); `invalidate()` + `regenerateToken()` on logout; cookies `HttpOnly`, `Secure`, `SameSite=Lax` (or `Strict` for admin); no session IDs in URLs.
- Test: capture the session cookie before login; after login it must differ, and the old one must not be authenticated.

### 12. SQL Injection (CWE-89)
- Default: Eloquent/query builder with bindings; `whereRaw/selectRaw/orderByRaw/DB::raw` only with `?` bindings; dynamic column/sort/direction names from an allowlist map (never from the request directly); `LIKE` input escaped for `%` and `_`.
- Forbidden: string interpolation or concatenation inside raw SQL (`"... $var"`, `'...'.$var`), `orderBy($request->sort)` without allowlist, `DB::statement` with input.
- Test: `' OR 1=1 --`, `1; DROP TABLE x`, sort=`id;DROP`, sort=`(SELECT …)`: rejected or harmless; keyset pagination with allowlisted sorts (owner invariant).

### 13. Buffer Overflow (CWE-120)
- Where in this stack: PHP and JS are memory-safe, so the risk sits in native code: PHP extensions (GD/Imagick/exif), Node native addons (`better-sqlite3-multiple-ciphers`, printer drivers), Electron/Chromium, Flutter FFI, and image/PDF parsers fed untrusted files.
- Default: keep runtimes and native deps patched (`composer audit`, `npm audit`, Electron on a supported major); strict upload size limits before parsing; re-encode images in a worker with memory/time limits; validate lengths before Node `Buffer` writes; never `Buffer.allocUnsafe` for data sent out; for FFI/native code, bounds-checked copies only.
- Test: oversized and malformed uploads are rejected before parsing; dependency audit has no known memory-corruption CVEs.

### 14. Cross-Site Scripting (CWE-79)
- Default: React/Inertia escapes by default; Blade `{{ }}`; Content-Security-Policy without `unsafe-inline` scripts (nonces for needed inline); rich text sanitized server-side with an allowlist (HTMLPurifier) before storing or rendering; URLs validated to `http(s)`/`mailto`; SVG uploads refused or sanitized; JSON embedded with `@json`/`Js::from`.
- Forbidden: `dangerouslySetInnerHTML` with unsanitized data, Blade `{!! !!}` with user data, `v-html`, `innerHTML =`, `href={userUrl}` without scheme check, `javascript:` URLs.
- Test: `<script>alert(1)</script>`, `"><img src=x onerror=alert(1)>`, `javascript:alert(1)` in every text field rendered back: shown as text, never executed.

---

## Part B — 20 backend fundamentals (checklist per backend change)

1. **Authentication**: framework flows only; MFA for staff; constant-time checks; short-lived tokens with abilities; HttpOnly cookies on web (items 7, 8, 11).
2. **Authorization**: policy on every action; ownership + role; tenant from the server; foreign tenant 404; deny by default; matrix + negative tests (items 5, 6, 10).
3. **Endpoint security**: every route in a middleware group (auth, verified, tenant, throttle); no debug/test routes in production; route list reviewed (`php artisan route:list`) against the OpenAPI contract; methods restricted; CSRF on cookie-auth state changes.
4. **Input validation**: FormRequest per write endpoint; types, lengths, enums, `exists` scoped to tenant; reject unknown/forbidden fields; normalize (trim, Unicode NFC, phone format) before validation; validate on the server even if the client validates.
5. **Injection protection**: SQL bindings, no shell, no eval, no template compilation of input, header injection guarded (no CR/LF in headers), LDAP/XPath n/a; output encoding per context (items 1, 2, 4, 12, 14).
6. **JWT security** (if a project uses JWT instead of Sanctum): pin the algorithm (no `none`, no alg switching), strong secret/keys from env, validate `exp`, `nbf`, `iss`, `aud`; short access tokens + rotating refresh tokens stored server-side with revocation; never store in localStorage on web; no sensitive data in the payload.
7. **Password security**: `Hash::make` (argon2id preferred, or bcrypt); bcrypt only uses the first 72 bytes, so with bcrypt cap input at 72 bytes (validation + byte-length check, or the hasher's `limit` option) and never let it truncate silently; Laravel rehashes on login by default (`rehash_on_login`), add `Hash::needsRehash` only in custom login flows; rule `Password::min(12)->uncompromised()` (owner default; follow the project spec if it says otherwise); no maximum below 64; no composition rules beyond length + breach check; reset tokens hashed, single-use, short TTL; never log or email passwords.
8. **Rate limiting**: `RateLimiter::for` per route class: login, OTP, reset, signup, search, exports, webhooks, public forms; keyed by user/IP/tenant; `429` with `Retry-After`; lockout/backoff on auth; Cloudflare rules for burst protection.
9. **CORS configuration**: `config/cors.php` with explicit origins (never `*` together with credentials); only needed methods/headers; same-site SPA on the same domain needs no CORS; preflight cached; separate rules for public API if any.
10. **Environment variables**: secrets only in `.env` (never in git, never in DB/settings UI, never in `VITE_*`); `env()` only inside `config/*`; `config:cache` in production; `.env.example` without real values; rotate on exposure.
11. **Sensitive data in response**: API Resources with explicit fields; `$hidden` for secrets/tokens/password hashes/internal flags; no stack traces; no other tenants' data; mask PII where not needed; Inertia shared props minimal; logs and exports follow the same rule.
12. **Error handling**: `APP_DEBUG=false` in production; RFC 9457 problem+json with stable codes for APIs; generic messages to clients, details to logs with request id; handle and report, never swallow; 404 for foreign tenant; custom error pages per surface.
13. **File upload security**: validate `mimes`/`mimetypes` + size + dimensions; store outside `public` (private disk) and serve through signed URLs or authorized controllers; random file names; strip EXIF; re-encode images; refuse executable types and SVG unless sanitized; scan where possible; per-tenant quotas; never trust the client filename or Content-Type.
14. **Database security**: least-privilege DB users (runtime user without DDL/`GRANT`); MySQL bound to localhost/private network (owner open item: MySQL bound to `*` on the VPS); TLS for remote connections; encrypted casts for sensitive columns; backups encrypted and restore-tested; no production data in dev.
15. **Database performance**: indexes for every filter/sort/join (composite indexes leading with tenant id); keyset pagination; `Model::preventLazyLoading()` outside production + eager loading (no N+1); `EXPLAIN` on new heavy queries; avoid `SELECT *` on wide tables; queue heavy work.
16. **Data integrity**: FK, UNIQUE, CHECK and NOT NULL constraints; transactions around multi-row writes; append-only ledgers for money/stock/credits; immutable issued documents with revisions; optimistic locking (`version` + `If-Match`); idempotency keys on retries; atomic sequence numbers.
17. **API validation**: OpenAPI 3.1 contract first; request validation (FormRequest) and response shape (Resources) match the contract; contract tests; versioned paths; consistent error format; reject payloads over size limits.
18. **Logging & monitoring**: structured logs with request id, user id, tenant id; security events logged (logins, failures, permission denials, privilege changes, exports, deletions); never log secrets, tokens, passwords, full card or ID numbers; error tracking + uptime + alerts (`operations-monitoring.md`).
19. **Testing**: feature tests per route on the real DB engine (MySQL 8.4); one negative test per weakness class that applies to the change (unauthenticated, wrong tenant, wrong role, injection payloads, XSS payloads, oversized upload, rate limit); regression test for every fixed vulnerability.
20. **Production configuration**: `APP_ENV=production`, `APP_DEBUG=false`, HTTPS only + HSTS, secure cookies (`SESSION_SECURE_COOKIE=true`), security headers (CSP, X-Content-Type-Options, frame-ancestors, Referrer-Policy), `config:cache`/`route:cache`/`view:cache`, supervised queue workers and SSR, trusted proxies configured for Cloudflare, debug tools (Telescope/Debugbar) off or protected, `composer install --no-dev`.

## Review procedure (per change)

1. List changed routes/actions/commands/uploads/renderers (use `graphify affected` and `code_guard find`).
2. For each, walk the 14 classes; write which apply and the evidence that it is safe (file:line or test name).
3. Run `python scripts/vuln_scan.py --root <repo> --changed <files>`; treat every finding as "prove safe or fix".
4. Walk the 20 fundamentals that the change touches; add the missing negative tests.
5. Record in the change log which classes were checked; any accepted risk goes to the owner (gate).

## Red flags

- A route or action without a policy, or with a policy that ends in `return true`.
- Any raw SQL, shell call, `eval`, `unserialize`, `{!! !!}`, `dangerouslySetInnerHTML` or outbound HTTP to a URL that came from a user.
- Data from the request reaching the domain without `validated()`; prices/tenant/role taken from the client.
- Login or context switch without session regeneration; tokens in localStorage.
- `APP_DEBUG=true`, `*` CORS with credentials, secrets in `VITE_*`, stack traces in responses.
- Uploads stored under `public/` with the client's file name.

## How project-brain uses this

Loaded by the `security` and `backend`/`api` roles (workflows/_knowledge.snippet.js), by `pb-security-reviewer` and `pb-code-reviewer`, and by `workflows/security-audit.js` (one hunter per class group). `scripts/vuln_scan.py` checks the machine-detectable patterns and runs in `pb.py finish` and the git pre-commit gate. Every backend task's done-evidence lists the classes checked.
