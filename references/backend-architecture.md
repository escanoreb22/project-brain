# Backend architecture (Laravel 12/13 products)

Scope: how to shape and operate the server side of the owner's multi-tenant B2B SaaS. Generic code hygiene, stability-pattern theory, test theory and logging basics live in `engineering-principles.md`; threat modelling in `security-protocol.md`; live deploy steps in `deploy-protocol.md`. This file does not repeat them. Form: "Default: X. Deviate only when Y."

Sources: (Fowler, PoEAA); (Evans, DDD, strategic part); (Vernon, IDDD, ch. 2-3 contexts); (Martin, Clean Architecture, dependency rule); (Nygard, Release It! 2e, stability part); (Newman, Building Microservices 2e, ch. 1 and 3 on monolith-first and modular monolith); (Richards and Ford, Fundamentals of Software Architecture, characteristics and trade-offs); Laravel docs https://laravel.com/docs (queues, horizon, scheduling, octane, context, concurrency, releases).

## 0. Version facts (verified against laravel.com docs, Oct 2026)

- Laravel 12: PHP 8.2-8.5, security fixes until 2027-02-24. Laravel 13: released 2026-03-17, PHP 8.3-8.5, security fixes until 2028-03-17. Check `composer.json` and `php -v` first; the Windows XAMPP PHP is often older than the spec.
- Laravel 13 adds PHP attributes for jobs (`#[Tries]`, `#[Backoff]`, `#[Timeout]`, `#[FailOnTimeout]`), controller `#[Middleware]` / `#[Authorize]`, `Queue::route()`, `Cache::touch()`, `PreventRequestForgery` middleware. Property-style config (`public $tries`) still works; on a 12.x project use properties. Never use a 13-only API without checking the framework version.
- `Context`, `Concurrency`, `Schedule::job()`, `onOneServer()` exist in 12.x. Use the version in the repo as the truth.

## 1. Shape: modular monolith first

- Default: one Laravel app, one deployable, one MySQL schema, split into modules by business capability (Billing, Catalog, Inventory, Identity, Reporting), not by technical layer. Reason: a solo founder cannot pay the operational tax of distribution (Newman, ch. 1; Richards and Ford, ch. on monolith vs distributed trade-offs).
- Deviate to a separate service only when ALL hold: independent scaling or failure isolation is a measured need; a different runtime is required (e.g. a Node renderer); a stable contract exists; the owner approves cost. Candidates seen so far: SSR process, headless-Chrome renderer, Electron POS sync agent. Each is still a process of the same repo unless the owner says otherwise.
- A module = a bounded context (Evans, strategic design): own vocabulary, own tables, own public surface. Same word may mean two things in two modules (Customer in Billing vs CRM); do not force one shared model.
- Public surface rule: other modules call only (a) the module's Action/Service classes in `Public/` (or an interface), (b) its published domain events, (c) read-only query classes. They never touch its Eloquent models for writes and never join across its tables in writes.
- Cross-module reads: allowed through a query class or a DB view; cross-module writes: never directly, only via the other module's action or via an event.
- Foreign keys across modules are allowed in the one DB (integrity beats purity) but the owning module controls deletes; document each in the project map.
- Enforce boundaries mechanically: add an architecture test (Pest `arch()` or PHPStan/deptrac rule) so module B imports from module A only `Modules\A\Public\*` and A's `Events\*` (e.g. `arch()->expect('Modules\Billing')->not->toUse(['Modules\Catalog\Models', 'Modules\Catalog\Actions'])`). A rule that is not checked will rot.
- Clean Architecture subset (Martin): keep the dependency rule only: domain logic must not depend on HTTP, Blade/Inertia or queue classes. Skip ports-and-adapters ceremony, DTO-per-layer mapping and repository-per-model.

## 2. Layering and folder template

Default flow: Route -> Controller (thin) -> FormRequest (validate + authorize) -> Action (one use case) -> Models/domain services -> Resource/Inertia props.

```text
app/
  Http/                      # shared middleware, base classes only
modules/
  Billing/
    Http/{Controllers,Requests,Resources}/
    Actions/                 # CreateInvoice, VoidInvoice (verbs, one public handle())
    Models/                  # Invoice, Payment
    Policies/
    Events/                  # InvoiceIssued (past tense, immutable, ids not models)
    Jobs/  Listeners/
    Queries/                 # read models for other modules and reports
    Public/                  # the only classes other modules may import
    Database/{migrations,factories,seeders}/
    Providers/BillingServiceProvider.php   # routes, policies, event map
    routes.php
tests/{Feature,Unit,Arch}/
```

- Existing repo layout wins: never restructure a running app into `modules/` without an owner decision; apply the rules inside the current folders.
- Small project (< 8 models): skip `modules/`, use `app/Actions`, `app/Models` and still keep domain folders. Introduce modules at the second bounded context, not before.
- Controller: map request -> action input -> response. No queries beyond route-model binding, no business rules, no `DB::transaction`.
- FormRequest: `rules()` for shape, `authorize()` calls a Policy. Business rules that need the DB belong in the Action.
- Action: one use case, one public method, constructor-injected deps, returns a model or value object, owns the transaction. Services only for logic shared by several actions. Repository only when a second data source exists (PoEAA: Eloquent already is Active Record; do not wrap it by reflex); a query reused 3+ times becomes a model scope or a `Queries/` class.
- Fat model is not a goal: models hold relations, casts, scopes, small invariants; workflows live in actions.

```php
final class IssueInvoice
{
    public function __construct(private InvoiceNumbers $numbers) {}

    public function handle(Tenant $tenant, User $actor, IssueInvoiceData $in): Invoice
    {
        return DB::transaction(function () use ($tenant, $actor, $in) {
            $invoice = Invoice::query()->whereBelongsTo($tenant)->lockForUpdate()
                ->findOrFail($in->invoiceId);              // foreign tenant -> 404
            throw_if($invoice->status !== InvoiceStatus::Draft, DomainException::class);
            $invoice->update(['status' => InvoiceStatus::Issued,
                'number' => $this->numbers->next($tenant), 'issued_by' => $actor->id]);
            InvoiceIssued::dispatch($invoice->id, $tenant->id); // event implements ShouldDispatchAfterCommit
            return $invoice;
        });
    }
}
```

## 3. Authorization and tenancy

- Default: Policy per model, registered in the module provider; `FormRequest::authorize()` or `$this->authorize()` in controllers; Gates only for non-model abilities. Every route group has `auth` + tenant middleware; check with `php artisan route:list` that no tenant route is public by accident.
- Tenant id is server-derived (session user, subdomain resolved server-side, or token claim). Never read `tenant_id` from request input. Mass assignment: `$fillable` excludes `tenant_id`, `role`, `is_admin`.
- Single-DB tenancy default: `tenant_id` on every tenant table + composite indexes starting with `tenant_id`, a global scope trait (`BelongsToTenant`) that applies the scope and sets `tenant_id` on create. Scopes do not apply to raw `DB::table()`, `withoutGlobalScopes()`, jobs without context, or `Model::insert()`: grep for these in review.
- Foreign-tenant record -> 404, not 403 (do not leak existence). Route-model binding must resolve through the scoped query, so a wrong-tenant id never loads.
- Queued jobs and listeners carry `tenant_id` explicitly (constructor arg) and re-establish tenant context in `handle()`. A job that relies on ambient auth state is a defect.
- Required tests per tenant-owned endpoint: tenant A cannot read/update/delete tenant B's record (expects 404), list endpoints never return B's rows, and a cross-tenant id inside a nested payload is rejected.
- Deviate to DB-per-tenant only for hard isolation or per-tenant restore requirements; it costs migrations fan-out and connection management. Owner decision (tenancy gate).

## 4. Transactions and consistency

- Default: one Action = one local DB transaction around the aggregate it changes. Keep the transaction short: no HTTP calls, no PDF render, no mail inside it.
- Consistency boundary = aggregate (Evans/Vernon): change one aggregate per transaction; reference other aggregates by id; reach eventual consistency between aggregates with events/jobs.
- Money, stock, counters: `lockForUpdate()` inside a transaction, or an atomic SQL update (`update ... set qty = qty - ? where qty >= ?` and check affected rows). Store money as integer minor units + currency. InnoDB (MySQL 8.4) default isolation is REPEATABLE READ; do not assume read-after-lock without locking.
- Unique constraints are the final idempotency guard (e.g. `idempotency_keys` unique `(tenant_id, user_id, key)` per `db-schema-design.md` sec. 9, unique `(tenant_id, number)`); catch the duplicate-key error and return the original result.
- Jobs that read the committed row: `->afterCommit()` on dispatch or `after_commit => true` on the queue connection (verified in queues doc). Events: implement `ShouldDispatchAfterCommit` on the event class (event dispatch is not chainable with `afterCommit()`); queued listeners can also implement `ShouldQueueAfterCommit`. Otherwise the worker may run before the commit and not find the row.
- Deadlock handling: `DB::transaction($cb, 3)` retries deadlocks; the callback must be safe to re-run.

## 5. Events, outbox, side effects

- Default: Laravel events for in-process decoupling inside and between modules (listener reacts to `InvoiceIssued`). Events carry ids and primitives, are past-tense, and are dispatched after commit.
- Queued listeners for anything slow or external (mail, push, webhooks, PDF, third-party API).
- Use the transactional outbox only when losing a side effect is unacceptable (payment webhooks to others, accounting sync, stock sync to POS): in the same transaction insert an `outbox` row (columns in `db-schema-design.md` sec. 9); a scheduled/looping dispatcher drains rows `where processed_at is null and available_at <= now()` with `FOR UPDATE SKIP LOCKED` (MySQL 8) and marks them; consumers are idempotent (Fowler/Newman: at-least-once delivery means duplicates).
- Do not build an outbox for mail or notifications; a failed job + retry + alert is enough.
- No event sourcing, no CQRS buses, no saga framework unless the PRD names a concrete need (YAGNI; owner hates over-engineering).

## 6. Queues, Horizon, retries, idempotency

- Default: Redis queue connection. Horizon when the project has >1 queue or needs metrics/alerts (Horizon requires Redis, is not compatible with Redis Cluster, reserves a Redis connection named `horizon`); plain `queue:work` under Supervisor otherwise.
- Queues by workload, not by module: `default`, `notifications`, `reports` (PDF/exports, low concurrency), `integrations` (third parties, rate-limited). Priority across queues in Horizon needs separate supervisors; `auto` balance does not honor list order.
- Every job declares: `tries`, `backoff` (array, e.g. `[10, 60, 300]`), `timeout`, and `failed()` handling. Without `tries` a job runs once.
- `timeout` < `retry_after` (queue config) with a few seconds margin; Horizon `timeout` > any job timeout. Wrong order = duplicate execution. `timeout` needs the pcntl extension (Linux; not on Windows dev).
- Middleware set: `WithoutOverlapping($key)` for per-entity serialization, `RateLimited('provider')` for API quotas, `ThrottlesExceptions` for flaky third parties. These consume attempts, so raise `tries` or use `retryUntil()`.
- Idempotent jobs: key the work on a business id, check state first ("already sent/paid/rendered" -> return), use unique constraints; `ShouldBeUnique` dedups queueing only, it is not a correctness guard.
- Serialize ids, not heavy models; re-load inside `handle()` (stale data) and handle "model deleted" (`$deleteWhenMissingModels`).
- Chains for ordered steps, batches for fan-out with progress; always `catch`/`failed` hooks; never an unbounded self-redispatch loop.
- Context facade: add `request_id`, `tenant_id`, `user_id` in middleware; they flow into queued jobs and every log line automatically. Use hidden context for non-loggable data.
- Deploy: `php artisan horizon:terminate` (or `queue:restart`) after every release or workers run old code. Supervisor `stopwaitsecs` > longest job. Failed jobs table + alert on count > 0.
- Concurrency facade (`Concurrency::run`) is for CLI/report fan-out with the `process` driver; `fork` is CLI-only. Do not use it to avoid proper queues in request paths.

## 7. Scheduler and shared-hosting fallback

- Default: define everything in `routes/console.php`; one cron entry `* * * * * cd /app && php artisan schedule:run`. Prefer `Schedule::job(new X)` so work runs on queues and the scheduler stays fast.
- Every scheduled task: `->withoutOverlapping(n)` (default lock is 24 h, set a sane n), `->onOneServer()` if more than one server (needs redis/database/memcached cache; named closures), `->onFailure()` alert, a heartbeat `pingOnSuccess()` to an uptime monitor. Avoid timezone schedules around DST; keep app timezone UTC.
- Sub-minute tasks: dispatch jobs only; add `php artisan schedule:interrupt` to the deploy script.
- Shared hosting without terminal or supervisor: cron every minute runs `schedule:run`, and the queue runs as `Schedule::command('queue:work --stop-when-empty --max-time=55')->everyMinute()->withoutOverlapping()`. Database queue driver there (no Redis). Deliver a pre-built ZIP (vendor + built assets). Document the limits in `.project-brain/DECISIONS.md`.

## 8. Caching and storage

- Redis for cache, locks, sessions, rate limiters, queue. Use separate Redis DB numbers or key prefix per app; never share a prefix between staging and production.
- Cache keys always include `tenant_id` (and locale if output is localized). Default TTL on everything; no forever keys except versioned config.
- Invalidation rule: the Action that changes data busts the keys (or bumps a version key) in the same code path, after commit. If you cannot name who invalidates a key, do not cache it. `Cache::remember` + short TTL for expensive reads; `Cache::lock` for stampede control; tags only on Redis.
- Never cache authorization decisions across users; never cache per-user data under a shared key.
- Files: `Storage` disks only, never raw paths. Local `private` disk first; move to S3-compatible (S3/R2) by env switch with no code change. Store `disk, path, size, mime, sha256` in DB; tenant-prefixed paths `tenants/{id}/...`; private files served via controller with policy check or short-lived signed URLs. Validate uploads by content type, size, extension allow-list; randomize stored names; run image/PDF processing in a queued job.

## 9. PDF, notifications, external calls

- PDF: render a dedicated print Blade/Inertia-free HTML route (signed, tenant-scoped) or raw HTML, convert with Browsershot (Puppeteer + headless Chrome) inside a queued job on the low-concurrency `reports` queue. Store the result on the file disk, then notify. Never render in the request cycle. Never pass user-supplied URLs or unsanitized HTML to Chrome (SSRF/local file read); set a job `timeout`, `setChromePath`/`setNodeBinary` from config, not hard-coded in `.env` (owner rule). Browsershot v4 needs Node 22+ and Puppeteer 23+ (spatie docs). For Arabic/RTL, embed fonts in the HTML and test a real Arabic document.
- Notifications: Laravel Notifications, `ShouldQueue`, channel per need (mail, database, push via FCM/APNs provider). Locale comes from the recipient (`HasLocalePreference`), not the actor. Store a database notification for anything the user must not miss. Mail through a transactional provider; set SPF/DKIM/DMARC.
- Third-party calls: wrapper class per provider, `Http::timeout(5)->connectTimeout(3)->retry(...)` only for idempotent calls, a clear exception type, and fakeable in tests (`Http::fake`). Webhooks in: verify signature + timestamp, store raw event, return 2xx fast, process in a job, dedupe by event id.

## 10. Config, secrets, observability

- `env()` only inside `config/*.php`; app code uses `config()`. Production runs `config:cache`, so `env()` elsewhere returns null. Add a test or grep gate for `env(` outside config.
- Secrets live in server `.env` (or secret store), are never committed, logged, or written to `.project-brain/`. One `.env.example` listing every key with a harmless value. Per-environment keys; rotate after the owner pastes any in chat.
- Octane (FrankenPHP/Swoole/RoadRunner) is optional. If used: no static state, no container/request/config injected into singletons, run `octane:reload` on deploy (Laravel octane doc). Default: PHP-FPM; adopt Octane only after a measured bottleneck.
- Logging: JSON/structured channel, `request_id` + `tenant_id` + `user_id` via Context, no PII/tokens in logs, one log line per failed job with job class and id. Error tracking (Sentry/Nightwatch/Flare) on production.
- Health: `/up` (framework) for liveness; a protected `/health` checks DB, Redis, queue heartbeat (last scheduler run, Horizon status), disk space. Monitor from outside the VPS.
- Rate limiting: named limiters in `AppServiceProvider` (`login` per email+IP, `api` per user/tenant, `webhooks` per source). Behind Cloudflare, trust proxies and use the real client IP header or all users share one limit.
- Stability (Nygard): every outbound call has connect and total timeouts; retries have backoff + jitter and a cap; use a circuit breaker (cache-backed failure counter, fail fast for N seconds) for non-critical providers; bulkhead by queue (slow provider cannot starve `default`); degrade features instead of failing the whole request. Details in `engineering-principles.md` section 6.

## 11. Backend testing pyramid

- Base: many unit tests for pure logic (money math, state machines, calculators). Middle: feature tests through HTTP + FormRequest + Action on the REAL MySQL 8.4 database (never SQLite/MariaDB; owner rule), `RefreshDatabase` or transaction wrapping, factories per module. Top: few end-to-end flows (checkout, invoice to PDF, login) and the arch tests.
- Mandatory per feature: authz matrix (guest 401, wrong role 403, wrong tenant 404), validation errors, happy path, one idempotency/replay case for money or webhooks, queue assertions (`Queue::fake`, `Event::fake` scoped) plus one test that actually runs the job synchronously.
- Run the same commands CI/production use: `php artisan test`, Pint, PHPStan/Larastan level the repo uses, `composer audit`. Report passed/failed/not-run (see `quality-gates.md`).

## 12. Deployment shape (CloudPanel VPS behind Cloudflare)

- One site per app in CloudPanel (PHP-FPM, Nginx), MySQL 8.4, Redis, Supervisor programs: `horizon` (or `queue:work`), `ssr` (`php artisan inertia:start-ssr` or the node SSR bundle), cron `schedule:run`. Headless Chrome/Node installed on the same host for Browsershot.
- Release order: backup DB -> maintenance mode -> sync -> `composer install --no-dev -o` if lock changed -> build assets -> `migrate --force` -> `config:cache route:cache view:cache event:cache` -> `horizon:terminate`/`queue:restart` -> restart SSR -> `schedule:interrupt` -> up. Migrations must be backward compatible with the previous code for one release (expand, then contract). Full procedure in `deploy-protocol.md`.
- Cloudflare: origin accepts only Cloudflare IPs if possible, SSL mode Full (strict), `TrustProxies` set, never cache authenticated HTML, `/api/*` or Inertia responses (any request with `X-Inertia`); cache rules only for static assets and public pages. Add no Cloudflare rule, DNS record or host the owner did not request.
- Resources: size `maxProcesses` to RAM; Chrome plus workers plus MySQL on one small VPS will OOM. Set limits per queue and watch memory.

## Red flags

- Business logic in controllers, Blade/Inertia props closures, or model events with side effects (mail, HTTP) .
- `tenant_id` read from request, missing global scope, `withoutGlobalScopes()` or raw `DB::table()` on tenant data, 403 for foreign tenant.
- Module A writes module B's tables or imports `B\Internal`; shared "God" `Helpers`/`Utils`/`Service` class.
- Job without `tries`/`backoff`/`timeout`; `timeout >= retry_after`; job dispatched inside a transaction without `afterCommit`; non-idempotent job on a retrying queue.
- HTTP call, PDF render or mail send inside a DB transaction or in the request cycle.
- `env()` outside config; secrets in repo, logs or memory files; hard-coded binary paths in `.env`.
- Cache key without tenant/locale; cache with no TTL and no named invalidator.
- Workers not restarted after deploy; SSR stale after build; scheduler task without overlap protection.
- Microservice, event bus, CQRS, outbox or repository-per-model introduced with no PRD requirement.
- Tests on SQLite, or only happy-path tests, or authz matrix missing.
- Octane enabled with singletons holding request/container state.

## How project-brain uses this

- Load when: designing architecture or module boundaries; adding a queue/job/scheduler task, webhook, file upload, PDF/export, notification, cache layer or integration; touching tenancy or transactions; preparing a deploy shape. Pair with `db-schema-design.md` (tables, outbox, idempotency keys), `api-design.md` (endpoints) and `multi-surface-architecture.md` (several interfaces).
- Gates served: architecture gate before `implementing` (module map, tenancy mode, queue/scheduler inventory); security gate (tenancy, authz matrix, uploads, secrets); verification gate (real-MySQL feature tests, arch tests, worker/SSR restart evidence).
- Record in `docs/` (canonical, not `.project-brain/`): module list with owners and public surface in PROJECT_MAP; per-job table (queue, tries, backoff, timeout, idempotency key); scheduler inventory; cache keys and invalidators; outbox yes/no; storage disk plan; deployment processes.
- Record in `.project-brain/DECISIONS.md`: tenancy mode, outbox/Horizon/Octane choices, shared-hosting fallback, any deviation from a default above as `delegated, open to reversal`. Put unwired jobs, listeners or schedules in `[ORPHANS & PENDING]` until verified end to end.
