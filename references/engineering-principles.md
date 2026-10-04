# Engineering principles (code level)

Rules for writing, changing and reviewing code, including the coder role (preflight, anti-hallucination, execution, verification order, handoff; formerly `engineering-principles.md`, merged here). Implement one ready task packet at a time; the objective is the smallest clear, correct, secure, observable, testable, maintainable change, not the fewest lines and not a long impressive diff. Architecture/API/DB/UI rules live in `backend-architecture.md`, `api-design.md`, `db-schema-design.md`, `frontend-system-design.md`, `multi-surface-architecture.md` and `security-protocol.md`.

Sources: Ousterhout, *A Philosophy of Software Design* (APoSD); Martin, *Clean Code* (CC); Hunt & Thomas, *The Pragmatic Programmer* (PP); Fowler, *Refactoring* 2e; Feathers, *Working Effectively with Legacy Code* (WELC); McConnell, *Code Complete* 2e (CC2); Freeman & Pryce, *GOOS*; Nygard, *Release It!*; Metz, "The Wrong Abstraction". Paraphrased, not quoted.

## 0. Conflict order
1. Owner profile and docs (`SKILL.md` precedence) beat every rule below.
2. Where Clean Code and Ousterhout conflict, follow Ousterhout (APoSD ch. 9, 10, 12). Contested CC points: tiny 2-5 line functions everywhere, "comments are failure", "one level of abstraction" taken to extremes, excessive extraction that forces readers to jump between files. Keep from CC: intention-revealing names, no duplicated logic, tests as design feedback.
3. Existing project convention beats a "better" rule. Match the repo's style; propose changes via `DECISIONS.md`, do not apply them in a feature diff.

## 1. Naming
- Default: name states what the thing is or does in domain words from the PRD glossary. Deviate only for established framework terms.
- One concept = one word across PHP, TS, Dart, DB and UI (e.g. `tenant`/`tenant_id` by default, or the repo's existing word, never `tenant`/`account`/`company` mixed). Check the glossary before inventing a term.
- Booleans read as predicates (`isPaid`, `hasStock`, `canRefund`); never `flag`, `data`, `info`, `manager`, `helper`, `util`, `process`, `handle` as the only meaningful word (CC2 ch. 11).
- Name length proportional to scope: `$i` in a 3-line loop is fine; a class-wide field needs a full name.
- A name you cannot choose easily signals a muddled design (APoSD ch. 14); fix the design, not the name.
- Units and currency in names or types: `amountMinor` (int cents), `timeoutSeconds`, never bare `amount`/`timeout` where ambiguity exists. Money: integer minor units or a Money value object; never float.

## 2. Functions and modules
- Default: a function does one thing at one level, readable top to bottom without scrolling. Length is a smell, not a rule; split only when the pieces have a clean name and a clean contract (APoSD ch. 9: split only if each part is independent).
- Prefer deep modules: small public surface, substantial behavior behind it (APoSD ch. 4). A class with ten one-line pass-through methods is shallow; merge or delete it.
- Red flag: pass-through method/variable, wrapper that only renames, "Manager"/"Service" that holds no rule of its own.
- Parameters: 0-3 positional. More than 3, or two booleans, means a value object / DTO / named arguments (PHP 8 named args, TS options object, Dart named params).
- No boolean flag parameters that switch behavior; split into two functions or pass an enum.
- Return early for guards; max nesting depth 3. Replace nested conditionals with guard clauses before extracting.
- Command-query separation: a function either returns a value or changes state, not both, unless atomic by nature (`save()` returning the model is fine).
- Pull complexity downward: the module absorbs awkward cases so callers stay simple (APoSD ch. 8). Do not push config options onto callers to avoid deciding a default.
- Define errors out of existence where honest (idempotent delete, empty collection returns empty, `firstOrCreate`), but never hide a real failure (APoSD ch. 10).
- Comments: explain why, invariants, units, non-obvious constraints and interface contracts. Never restate the code. Write the interface comment before the body for any new public class (APoSD ch. 12, 15). No commented-out code.

## 3. Cohesion, coupling, layering
- Default Laravel layering: Controller/FormRequest (HTTP only) -> Action or Service class (business rule, one verb) -> Eloquent model (persistence, scopes, casts, relations). Rules never live in controllers, Blade/Inertia props, or React components.
- Information hiding: a design decision (table layout, third-party payload shape, pricing rule) lives in one module. If changing one decision touches 5 files, the boundary is wrong (APoSD ch. 5; PP topic "Orthogonality").
- Depend on direction: UI -> application -> domain; never the reverse. Domain code does not import `Illuminate\Http`, `Request`, React, or Flutter widgets.
- Law of Demeter: avoid `$order->customer->tenant->plan->limit`; add a method on the owner that answers the question (PP "Tell, Don't Ask").
- Wrap third-party SDKs (payment, SMS, Codex/AI, storage) behind one app-owned interface and one adapter; tests fake the interface (GOOS "only mock types you own").
- Multi-tenant: tenant scoping is enforced in one place (global scope / policy / middleware), not repeated in each query. Test the scope itself.
- Circular dependency between modules: stop, introduce a third module or merge. Check with Pest arch tests (below).

## 4. Abstraction, YAGNI, DRY
- Default: write the concrete code first. Extract on the third real occurrence (rule of three), and only if the occurrences change for the same reason. (Fowler, *Refactoring*, "Duplicated Code"; Metz.)
- Duplication is cheaper than the wrong abstraction. When a shared function grows boolean params/conditionals to satisfy callers, inline it back into each caller and re-extract the real shape (Metz).
- DRY is about knowledge, not text: one source for a business rule, a constant, a schema, a permission list (PP topic 9). Two similar-looking pieces with different reasons to change stay separate.
- YAGNI: no interface with one implementation (except the third-party adapter case above), no config flag nobody sets, no event/listener where a method call works, no repository layer over Eloquent unless a second data source exists, no generic base class for two users.
- Speculative generality red flags (Fowler "Speculative Generality"): unused parameter, abstract class with one child, hook "for future", plugin system, factory of one product.
- Prefer composition and plain functions over inheritance. Inheritance only for true is-a with the framework (Model, FormRequest, Notification).
- Use the platform before a library: `Collection`/`Str`/`Arr`, `Carbon`, PHP 8.4 features (property hooks, asymmetric visibility `public private(set)`, `new` without parentheses) (php.net/releases/8.4), TS built-ins, Dart core.

## 5. Error handling
- Fail fast at the boundary: validate in FormRequest / zod / Dart model parsing, then trust typed values inside.
- Exceptions for exceptional states; domain-meaningful exception classes (`InsufficientStock`) carrying context, caught only where recovery or translation to HTTP/UI happens. Never `catch (\Throwable) {}` empty; never catch just to log and continue silently.
- Do not return `null`/`false` to signal failure from functions whose callers will forget to check; throw, or return a typed result.
- Translate at layer borders: DB/HTTP-client exceptions become domain exceptions; domain exceptions become HTTP status + stable error code + localized message (ar/fr/en). Never leak SQL, stack traces or vendor messages to users.
- Cleanup guaranteed: `DB::transaction()` for multi-write invariants, `finally` for resources, Dart `try/finally`, React effect cleanup.
- Transactions + side effects: dispatch queued jobs/events after commit (`afterCommit()` on the job or `after_commit` on the queue connection) (laravel.com/docs/12.x/queues).
- TypeScript: no `any`, no non-null `!` to silence errors, no `as` casts on external data; parse unknown data at the edge. Dart: no `!` on nullable API data without a check; handle `Future` errors.

## 6. Stability patterns for anything that calls out or runs async (Nygard, Release It!)
| Situation | Default |
|---|---|
| Any outbound HTTP/SMS/payment/AI call | Explicit timeout (`Http::timeout(5)->connectTimeout(3)`), never default-infinite |
| Transient failure | Retry with exponential backoff + jitter, max 3, only if the call is idempotent |
| Repeated failure of a dependency | Circuit breaker or fast "unavailable" path; show degraded UI instead of hanging |
| Queue job | `$tries`, `$backoff = [10,60,300]`, `$timeout` below `retry_after`, `failed()` handler, idempotency key or `ShouldBeUnique`/`WithoutOverlapping` for shared resources |
| Unbounded input | Cap list sizes, page every list, limit upload size, rate-limit (`RateLimiter`/`throttle`) |
| Shared resource | Bulkhead: separate queue/connection for slow or non-critical work (reports, emails) vs payments/POS |
| Webhook / retried request | Idempotent handler keyed by event id |
| Cache/Redis down | Core flow still works from the DB; cache is an optimization |
- Offline POS/Flutter: every write has a client-generated idempotency key; sync retries cannot double-charge.

## 7. Testing strategy
- Default: test behavior through the public interface, not private methods or call order. A refactor that keeps behavior must not break tests (GOOS; Fowler "Self-Testing Code").
- Pyramid (Flutter docs, docs.flutter.dev/testing/overview use the same split): many unit tests for rules, a moderate number of integration/feature tests (HTTP -> DB), few end-to-end/browser tests for critical journeys (login, checkout, payment, tenant isolation).
- Laravel (Pest preferred if the repo already uses it, else PHPUnit; follow the repo): feature tests through HTTP on the real DB engine (MySQL 8.4 per owner profile; never SQLite). `RefreshDatabase` or `LazilyRefreshDatabase`. Call `Http::preventStrayRequests()` in the base setup so unfaked external calls fail the test. Fake only at your adapter boundary (`Http::fake`, `Queue::fake`, `Mail::fake`, `Event::fake`), never fake the DB or your own Actions.
- Pest `arch()` tests enforce structure cheaply: `arch()->expect('App\Actions')->not->toUse('Illuminate\Http')` (module apps: each `Modules\*\Actions` namespace; boundary rules in `backend-architecture.md` sec. 1), `->toUseStrictTypes()`, `->not->toUse(['dd','dump','die'])` (pestphp.com/docs/arch-testing).
- Eloquent strictness in non-production: `Model::shouldBeStrict(! app()->isProduction())` (lazy-loading, silent attribute discard, missing attribute) catches N+1 and typos in tests (laravel.com/docs/12.x/eloquent).
- React: Vitest + Testing Library; query by role/label/text like a user, `userEvent` not `fireEvent`, `await` interactions; no assertions on internal state, hooks internals or snapshots of large trees. Mock network at the fetch boundary (MSW) not the component.
- Flutter: unit tests for logic, widget tests for screens/states (loading/empty/error/data), `integration_test` only for critical flows. Golden tests only for stable, design-system widgets.
- Test names state the rule: `it('rejects refund above captured amount')`. One behavior per test; arrange-act-assert; no logic (loops/ifs) in tests.
- Every bug fix starts with a failing regression test (PP "Test to Code"). Every authz/tenancy rule gets a negative test (other tenant, other role, guest).
- Edge checklist (CC2 ch. 22): empty, one, many, boundary +-1, null/missing, duplicate, wrong type, Unicode/RTL/Arabic text, timezone/DST, concurrent double-submit, partial failure.
- Flaky test = defect: fix or delete; never retry-until-green or `sleep`. Freeze time (`Carbon::setTestNow`, fake timers).
- Coverage number is not evidence; mutation of the rule (break it, see the test fail) is. Before claiming a test protects a rule, break the rule once and watch it fail.
- Test-double order: real object > fake > stub > mock. Mock only to verify an outbound interaction that is itself the requirement (e.g. "email sent").

## 8. Refactoring safely (Fowler, Feathers)
- Precondition: green tests covering the behavior you will move. No tests -> add characterization tests first (section 9). Refactor and feature change never share a commit/step.
- Small steps, run tests after each: rename, extract function, inline, move, extract class, replace conditional with polymorphism/map, introduce parameter object. Stop the moment tests are red and revert the last step rather than debug forward.
- Scope: only inside the task's `allowed_paths`; unrelated mess is reported, not fixed (owner dislikes unattended breakage).
- Rename/move across files: grep all consumers (PHP, Blade, TS, routes, config strings, migrations, docs) and let `tsc`, PHPStan, `dart analyze` confirm zero dangling references.
- Public contracts (route names, JSON fields, event names, DB columns, translation keys, queue payloads) are not refactorable without a migration path: add new, dual-read, then remove (expand/contract).
- Delete dead code you created; before deleting older code, trace callers incl. dynamic ones (`route('x')`, string class names, `config()`, `Gate::define`, translation keys).

## 9. Legacy and unfamiliar code (Feathers)
Default flow: identify change point -> find test points/seams -> break dependencies minimally -> write characterization tests -> change -> refactor.
- Characterization test: call the code, record what it actually returns today (even if odd), assert exactly that; label it `characterization`. It documents behavior, not correctness. Do not "fix" the behavior in the same step.
- Seams to cut dependencies with minimal edits: extract method then override in a test subclass; inject the collaborator via constructor (default to the current concrete); wrap a static/facade call in a tiny method; for PHP use `app()->bind`/container swaps; TS `vi.mock` at module boundary; Dart constructor injection.
- Sprout method/class: new logic goes into a new tested function called from the old one. Wrap method: rename old, new method adds behavior then calls it. Use when the surrounding code is untestable.
- Edit-and-pray is banned: if a change cannot be covered by any check, say so, shrink the change, and record the risk.
- Strangler: for rewrites of a module, route new behavior through the new code behind one entry point and retire the old per slice; no big-bang rewrite (owner: scoped and reversible).
- Unknown behavior in old code: ask the owner or read logs/DB data; record `UNKNOWN` per section 14.

## 10. Dependencies and tooling hygiene
- Default: no new package. If needed: check manifest first, maintained (recent release), license, weekly downloads/community, transitive size, security advisories (`composer audit`, `npm audit`, `dart pub outdated`), and that the framework cannot already do it. Record in `DECISIONS.md`.
- Pin by lockfile; commit `composer.lock`, `package-lock.json`/`pnpm-lock.yaml`, `pubspec.lock` (apps). Upgrade one major at a time, in its own task.
- PHP toolchain: Laravel Pint for style (`vendor/bin/pint --test` in CI; presets laravel/per/psr12/symfony/empty, laravel.com/docs/pint), Larastan/PHPStan for types (levels 0-10; level 9 is strict about explicit `mixed`, level 10 also reports implicit `mixed` from missing types, phpstan.org/user-guide/rule-levels). Default: if a baseline exists, never raise the baseline count; new code at the repo's current level; a new project starts at 6+ and rises. Fix errors, do not add `@phpstan-ignore` without a reason comment.
- TS toolchain: `tsc --noEmit` with `strict: true`, ESLint (+ `react-hooks` rules), Prettier or the repo formatter, Vitest. Dart: `dart analyze` with `flutter_lints`/stricter options, `dart format`, `flutter test`.
- `declare(strict_types=1);` in new PHP files unless the repo does not use it; typed properties, return types, `readonly` value objects, enums over string constants.
- Config via `config()` only (never `env()` outside config files, or `config:cache` breaks it).

## 11. Logging and observability
- Log events with context, not prose: `Log::info('refund.created', ['tenant_id'=>$t,'order_id'=>$o,'amount_minor'=>$a])`. Add request/tenant/user ids once via `Log::shareContext()` / `withContext()` in middleware (laravel.com/docs/12.x/logging).
- Levels: `error` = a human must look; `warning` = degraded but handled; `info` = business milestone; `debug` = off in production. Never log expected user mistakes (validation failures) as errors.
- One log per failure at the layer that handles it; do not log-and-rethrow through every layer (duplicate noise).
- Never log secrets, tokens, passwords, full card data, OTPs, or full personal data; redact (see `security-protocol.md`).
- Instrument what you cannot see otherwise: queue failures (`failed()`), webhook processing, payment state changes, sync conflicts, slow queries, scheduled-task heartbeat.
- Each user-facing failure maps to an id the user can quote and the log can find (correlation/request id in the error UI).
- Frontend: report unhandled errors and failed API calls to the chosen collector with the same ids; never `console.log` leftovers in committed code.

## 12. Code review checklist (self-review before handoff)
1. Does the diff do exactly the task and nothing else (`allowed_paths`, no bonus features)?
2. Is there a behavioral test that fails without the change? Did I run it and see the output?
3. Interface: is it simple to use correctly and hard to misuse? Any shallow wrapper or pass-through added?
4. Names consistent with the glossary; no `data/helper/util/manager`.
5. Error paths: timeouts, null/empty, partial failure, double submit, retry, permission denied, other tenant.
6. Data: N+1, missing index for new filter/sort, unbounded query, transaction boundary, migration reversible/expand-contract.
7. Concurrency: race on read-modify-write (use atomic update, `lockForUpdate`, unique constraint); jobs idempotent.
8. Security touchpoints: authz at the policy layer, mass assignment, output escaping, uploads, secrets.
9. i18n/RTL: no hard-coded strings; logical CSS properties; all locales have keys.
10. Dead code, debug output, commented code, stray `TODO`, unused imports removed (own mess only).
11. Tooling output pasted accurately: pint, phpstan, tests, tsc, eslint, vitest, dart analyze, build.
12. Docs/project map/change log updated per `SKILL.md` execution loop.

## 13. Preflight (before the first edit)
- Read current state, task packet, linked requirement/contracts, mapped structure, relevant decision records and the current diff. Inspect actual files and manifests.
- Verify expected APIs and installed versions locally; use official version-matched documentation when the API is unstable.
- Stop for: missing acceptance criteria, unsafe permissions, unrelated dirty changes that overlap the task, unresolved high-risk assumptions.

## 14. Anti-hallucination rules
Absolute; violating any one invalidates the step.
- Never claim a file exists without reading it from the file system.
- Never invent a function, method, class, event or package name.
- Never assume a framework or package version without checking the manifest or lockfile.
- Never add a dependency without verifying it exists, is maintained, is licensed compatibly and is absent from the manifest (section 10).
- Never change a function signature, schema, event, route or configuration key without first identifying every consumer.
- Never declare success from reading code; require executed test or runtime evidence.
- Never substitute a placeholder, stub or TODO comment for a real implementation.
- Never delete code without tracing every caller and confirming none remain in scope.
- Never modify a file outside the task's `allowed_paths`.
- When a fact is unknown: record `UNKNOWN`, stop, and ask the owner rather than guessing.

## 15. Execution order
1. Establish a failing behavioral test or reproducible check.
2. Implement the minimum change to pass.
3. Refactor only inside task scope while preserving behavior (section 8).
4. Evaluate performance and concurrency when the path is hot, shared, retried, financial or asynchronous.
(Error handling, observability, consumer inspection and dependencies follow sections 5, 11, 8 and 10.)

## 16. Verification order and handoff
- Run, as applicable: format, lint, static/type checks, targeted tests, integration/contract tests, broader relevant suite, build, runtime verification, security scans, drift checks. Report exact commands and outcomes; distinguish not run, unavailable, skipped, failed and passed.
- Update task state only to the proven level. Record changed files, reason, linked requirements, tests, security impact, breaking behavior, migration, rollback, known issues and next action. Never hide a regression in the change log.

## Red flags
Stop and fix when you see yourself or the diff doing any of these:
- A new abstraction (interface, base class, factory, service) with a single caller or implementation and no third-party boundary.
- Shared helper that gained a boolean/mode parameter to serve a new caller (wrong abstraction: inline and re-split).
- Business rule in a controller, Blade, React component or Flutter widget.
- Tests assert mocks/call order/private state; or DB, Actions or the unit under test are mocked.
- Tests run on SQLite/MariaDB while the project uses MySQL 8.4.
- Empty `catch`, `catch (Throwable)` without rethrow/translation, `@suppress`, `@phpstan-ignore` without reason, `any`, `!`, `as unknown as`.
- Outbound call without timeout; retry on a non-idempotent call; queue job without `$tries`/`failed()`.
- Side effect (email/job/webhook) dispatched inside an uncommitted transaction.
- Refactor mixed with behavior change; rename without a consumer grep; changed contract without expand/contract.
- Change to untested legacy code with no characterization test and no stated risk.
- Float money; `env()` outside config; secrets or PII in logs.
- New dependency not in manifest, unverified, or added for ten lines of code.
- "Cleaner" rewrite of working code outside the task; function extracted into 2-line fragments that must be read together.
- Claiming done from reading code, or reporting lint/test results that were not executed.

## How project-brain uses this
- Load when: implementing, fixing, refactoring, reviewing or writing tests (this file is the single owner of the coder protocol); when touching legacy code; when choosing a dependency; when adding logging, jobs or outbound calls.
- Gates served: Ready (test list and seams named in the packet), Code (scoped diff, tests, no speculative abstraction), Verification (tool list in section 10 executed and reported), Drift (no orphan abstractions).
- Task packet: put the behavioral tests and characterization tests under `tests`; stability choices (timeout, retry, idempotency key) under `observability`/`invariants`; refactor-only tasks stay separate from feature tasks.
- Record in `DECISIONS.md`: new dependency (why, alternatives), any deviation from section 0 or a repo convention, static-analysis baseline changes, deliberate duplication left in place (with the "third occurrence" trigger), accepted legacy risk.
- Record in `docs/` or the project map: new seams/adapters (third-party wrappers), arch-test rules added, logging event names and context keys, queue/job retry policy.
- Change log entry per `append-change`: type `refactor` only when behavior is provably unchanged (name the tests that proved it).
