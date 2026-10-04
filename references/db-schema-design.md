# DB schema design: MySQL 8.4 (InnoDB) + Laravel migrations

> Before any of this: the 35-item Data Architecture Gate in `system-engineering-method.md` (conceptual and logical model, invariants, access patterns, volume, lifecycle). This file is the physical MySQL 8.4 layer.

Scope: relational model, constraints, keys, types, tenancy, ledgers, indexing, online migrations. Not covered here: API contracts, queues, auth (see `security-protocol.md`, `api-design.md`, `backend-architecture.md`). Paraphrased from: Kleppmann (DDIA), Karwin (SQL Antipatterns), Hernandez (DB Design for Mere Mortals), Botros & Tinley (High Performance MySQL 4e), Winand (Use The Index, Luke), Ambler & Sadalage (Refactoring Databases). Version claims checked against dev.mysql.com/doc/refman/8.4 and laravel.com/docs/12.x (dates in section 13).

## 1. Modeling process (do in this order, write results into `DATA_MODEL.md`)

1. List nouns the business tracks (entities). Drop anything that is only a screen or a report. (Hernandez, ch. on subjects/tables.)
2. For each entity: one sentence purpose, owner module, lifecycle states, who creates/updates/deletes.
3. For each pair: relationship + cardinality (1:1, 1:N, N:M) + optionality. N:M always becomes a table with its own PK and attributes (role, qty, valid_from).
4. List invariants in plain words ("a paid invoice is never edited", "stock never below 0", "one open shift per register"). Each invariant gets an enforcement layer: DB constraint first, then service transaction, then validation. Default: if MySQL can enforce it (NOT NULL, UNIQUE, FK, CHECK), it must. Deviate only when it needs cross-row logic; then use a transaction + lock + test.
5. List top 10 queries per screen/report. They drive indexes (section 9), not the reverse. (Winand.)
6. Only then write migrations. One migration = one reviewable change with `down()` that works or an explicit "irreversible" note.

## 2. Normalization and denormalization

- Default: 3NF. Every non-key column depends on the key, the whole key, nothing but the key. (Hernandez; Karwin "Multicolumn Attributes", "Metadata Tribbles".)
- Forbidden: comma-separated lists in a column (use a child table), `tag1,tag2,tag3` columns, per-year/per-tenant tables, EAV (`entity, attribute, value`) for core data, polymorphic FK pairs (`*_type + *_id`) without a real FK. (Karwin: Jaywalking, EAV, Polymorphic Associations, Metadata Tribbles.)
- Polymorphic needed (comments on many models): prefer one nullable FK per target + CHECK that exactly one is set, or a shared supertype table. Laravel `morphs()` has no FK; accept only for non-critical data.
- Denormalize deliberately, never by habit. Allowed: counters/balances (projection of a ledger), snapshots on issued documents (customer name, tax id, prices at issue time), search/read models. Each needs: source of truth named, update path (same transaction), reconcile query, owner.
- Snapshot vs reference: an issued invoice copies name/address/price/tax rate; it keeps the FK only for navigation. Never recompute an issued document from live master data.
- Trees: default adjacency list (`parent_id`) + recursive CTE (MySQL 8 supports). Closure table only when subtree queries are hot. (Karwin: Naive Trees.)

## 3. Keys

| Option | Pros | Cons | Use when |
|---|---|---|---|
| `BIGINT UNSIGNED AUTO_INCREMENT` | 8 bytes, append-only clustered inserts, smallest secondary indexes | Guessable, needs DB round trip, gaps | Default internal PK for server-created rows |
| ULID (`$table->ulid()` = CHAR(26)) / UUIDv7 | Client-generated, time-ordered, safe to expose | 26-36 bytes copied into every secondary index; more RAM | `public_id` column (default), `client_uuid` for offline rows, merging datasets; as PK only by recorded decision |
| UUIDv4 | Unguessable | Random inserts fragment the clustered index | Avoid as PK; ok as secondary `public_id` |

- Fact (verified): InnoDB clusters rows by the PK, and every secondary index entry stores the PK columns; a long PK enlarges all indexes (MySQL 8.4 "Clustered and Secondary Indexes").
- Fact (verified): Laravel 12 `HasUuids` generates UUIDv7; `HasUlids` generates ULID; `ulid()` = CHAR(26), `uuid()` = CHAR(36) (laravel.com/docs/12.x/eloquent, /migrations).
- Fact (verified): `UUID_TO_BIN(x, 1)` time-swap helps only UUIDv1; no benefit for v4/v7. Compact storage: `BINARY(16)` via `UUID_TO_BIN(x)`; add a custom cast, not raw CHAR, when table is large (>10M rows).
- Default: bigint PK + `public_id` ULID (unique) on any table whose id appears in a URL, API or QR. `HasUlids` fills the primary key by default: override `uniqueIds()` to return `['public_id']`, and bind routes by `public_id`.
- Offline/client-generated records (Electron POS, Flutter): keep the bigint PK and add `client_uuid` (UUIDv7 generated on the device) with `UNIQUE (tenant_id, device_id, client_uuid)`; it is the sync idempotency key (`multi-surface-architecture.md` sec. 10). A ULID/UUIDv7 PK is a deviation recorded in `DECISIONS.md`; never mix styles randomly in one domain.
- Fact (verified): auto-increment values are never reused after rollback and can have gaps (innodb_autoinc_lock_mode=2 is the 8.4 default). Never use an AUTO_INCREMENT id as a legal invoice/receipt number (section 8).
- Always define an explicit PK. Never use a generic `id` for a pure join table when `(a_id, b_id)` is the natural composite PK. (Karwin: ID Required, applied with judgment.)
- Natural keys (SKU, tax id) are UNIQUE constraints, not PKs, and are scoped per tenant: `UNIQUE (tenant_id, sku)`.

## 4. Naming

Default: `snake_case`; tables plural (`invoices`); pivot tables singular_singular alphabetical (`product_tag`) or a domain name (`order_lines`); FK `<singular>_id`; booleans `is_*`/`has_*`; timestamps `*_at`; money `*_minor` + `currency`; status columns `status`; no reserved words, no abbreviations the owner does not use, no table prefixes per module unless modules share a DB with another app. Name indexes and constraints explicitly in long-lived tables (`uq_invoices_tenant_number`, `ck_invoices_total_nonneg`), because Laravel's auto names are long and break at 64 chars (MySQL identifier limit).

## 5. Data types

| Data | Default | Never |
|---|---|---|
| Money | `BIGINT` minor units + `CHAR(3)` currency (ISO 4217), exponent from config. Use `DECIMAL(19,4)` when rates/fractions of a unit are real (FX, per-gram price, tax per line before rounding) | `FLOAT`/`DOUBLE` (Karwin: Rounding Errors) |
| Quantity | `DECIMAL(18,3)` or integer base unit (grams, pieces) | float |
| Percent/rate | `DECIMAL(7,4)` or basis points `SMALLINT` | float |
| Text | `VARCHAR(n)` with real n; `TEXT` only for free text | `utf8mb3`/`utf8` alias |
| Charset | `utf8mb4` + `utf8mb4_0900_ai_ci` (verified 8.4 default). Case/accent-insensitive compare is the default: UNIQUE on emails treats `A@x.com` = `a@x.com` | Mixed collations across joined columns |
| Arabic/French search | Keep `ai_ci`; test that `é`=`e` is acceptable for the field; use `utf8mb4_0900_as_cs` or binary only for codes/tokens | Assuming ASCII lowercasing |
| Instant in time | `DATETIME(0|6)` storing UTC, `app.timezone=UTC`, convert in UI | Local time in DB |
| Audit stamps | `timestamps()` (TIMESTAMP) is fine | Future-dated values in TIMESTAMP |
| Calendar day | `DATE` (birthday, business day, fiscal date) | DATETIME at midnight |
| Flags/state | `VARCHAR(30)` + CHECK list, or lookup table when admins edit values | `ENUM` for evolving sets |
| Booleans | `BOOLEAN`/`TINYINT(1)` NOT NULL DEFAULT | nullable bool (tri-state by accident) |

- Fact (verified): TIMESTAMP range ends `2038-01-19 03:14:07` UTC and converts through the session time zone; DATETIME range is 1000-9999 with no conversion. Subscriptions, warranties, expiry, loan dates: DATETIME.
- ENUM (verified pitfalls): stored as index, sorts by definition order, numeric context returns the index, invalid value is `''` when strict mode is off, appending at the end is INSTANT while inserting in the middle rebuilds. Default: string column + CHECK, mapped to a PHP backed enum.
- JSON (verified): max size bound by `max_allowed_packet`; cannot be indexed directly, index a generated column or a multi-valued index; partial in-place update only with `JSON_SET/REPLACE/REMOVE`. Use for opaque payloads (webhook body, UI preferences, provider response). Never for data you filter, join, sum or enforce. (Karwin: EAV.)
- Nullable: NULL means "unknown/not applicable", never "zero" or "empty". Prefer NOT NULL + default. Unique index allows many NULLs (used in section 6).
- CHECK (verified): MySQL 8.0.16+ enforces CHECK; allowed: deterministic functions, same-row columns; forbidden: subqueries, other tables, non-deterministic functions (`NOW()`), AUTO_INCREMENT columns, and columns that are in an FK referential action (`ON DELETE/UPDATE`). Laravel has no CHECK builder method in the 12.x column docs: use `DB::statement`.

```php
DB::statement('ALTER TABLE invoices ADD CONSTRAINT ck_invoices_total_nonneg CHECK (total_minor >= 0)');
DB::statement("ALTER TABLE invoices ADD CONSTRAINT ck_invoices_status CHECK (status IN ('draft','issued','void'))");
```

## 6. Foreign keys, deletion, soft deletes

- Default: real FK on every relationship (InnoDB creates the referencing index if missing; still name your own). Keyless entry is a defect. (Karwin: Keyless Entry.)
- ON DELETE choice (verified actions: RESTRICT, NO ACTION, CASCADE, SET NULL; SET DEFAULT is rejected by InnoDB):

| Relationship | Choice |
|---|---|
| Money, stock, documents, audit, ledgers | `restrictOnDelete()` always |
| Pure children owned by one parent (invoice lines, cart items, draft attachments) | `cascadeOnDelete()` only if the parent can be hard-deleted at all |
| Optional reference (assigned_to, category) | `nullOnDelete()` and nullable column |
| Tenant root (`tenants`) | `restrictOnDelete()`; tenant purge is a job (below) |

- Fact (verified): cascaded FK actions do not fire triggers. Do not rely on triggers (audit, ledger guards) to see cascaded deletes.
- Fact (verified): `foreign_key_checks=0` does not re-validate rows afterward. Use `Schema::withoutForeignKeyConstraints()` only in seeders/tests, never to "make a migration pass".
- Soft deletes: Default: use only when a human-visible restore/trash is a requirement. Otherwise: status column (`archived_at`) for business-archived rows, hard delete for mistakes in drafts, purge job for retention/GDPR.
- Soft delete + UNIQUE trap: `UNIQUE (tenant_id, code)` blocks re-creating a deleted code; `UNIQUE (code, deleted_at)` does not work because NULLs are distinct. Fix with a virtual column:

```php
$table->string('code', 40);
$table->softDeletes();
$table->string('live_code', 40)->nullable()->virtualAs('IF(deleted_at IS NULL, code, NULL)');
$table->unique(['tenant_id', 'live_code'], 'uq_products_tenant_live_code');
```

- Every query on a soft-deleted table must carry the scope; reports and exports are where it leaks. Add a test that deleted rows do not appear in lists, counts, exports.
- Retention: archive table (same columns + `archived_at`) when old rows slow hot queries and must stay queryable; purge job when law/policy says delete. Purge deletes in chunks (1k rows, by PK range) inside short transactions, logs counts, never one giant `DELETE`. Retention periods are an owner gate (`SKILL.md` section 5).

## 7. Multi-tenancy (shared DB, `tenant_id` column: the owner's default)

- Naming: all references use `tenant_id` -> `tenants`. If the repo already uses another name (`company_id`, `merchant_id`, `workspace_id`), keep it everywhere in that project; one name per project, recorded in the glossary.

- Every tenant-owned table has `tenant_id BIGINT UNSIGNED NOT NULL` + FK to `tenants`. Tables without it must be in an explicit allowlist (global lookups: currencies, countries, plans).
- Indexes lead with `tenant_id` for every tenant-scoped list/lookup: `(tenant_id, status, created_at)`, `UNIQUE (tenant_id, number)`. A tenant-scoped query that cannot use a `tenant_id` prefix is a bug.
- Cross-tenant link prevention at DB level: parent has `UNIQUE (tenant_id, id)`; child FK is composite `(tenant_id, parent_id) -> parents (tenant_id, id)`. Default for money/stock/documents; for low-risk tables rely on scope + tests.
- App layer: global scope or a base trait that sets `tenant_id` on create and filters on read; queue jobs carry `tenant_id` explicitly and re-bind tenant context; raw `DB::table()` calls must filter by hand (grep for them in review).
- Route-model binding must resolve through the tenant scope (a foreign id returns 404, not 403 and never data).
- Mandatory tests per tenant table: (1) user of tenant A cannot read, update, delete tenant B row by id; (2) lists contain only A rows; (3) A cannot attach B's row as a child/reference; (4) jobs/exports are scoped. Put them in a shared feature test helper.
- Tenant purge/export: by `tenant_id` per table in dependency order, driven by a table registry so a new table cannot be forgotten (test: every table with `tenant_id` is in the registry).
- Separate-DB-per-tenant: only on explicit owner decision (isolation contract, huge tenants). Record as ADR.

## 8. Ledgers, documents, sequences

**Append-only ledger** (stock, credits/wallet, money): (Kleppmann ch. 11 event sourcing idea, scaled down.)
- Table `*_movements`: `id, tenant_id, subject_id, delta` (signed), `reason`, `ref_type/ref_id` (source document), `idempotency_key`, `created_by`, `created_at`. No `updated_at`, no soft delete. Corrections are new reversing rows.
- Projection `*_balances (tenant_id, subject_id, balance, version)` updated in the same transaction as the insert (`UPDATE ... SET balance = balance + ?`), with CHECK `balance >= 0` when negatives are forbidden. Lock order: always the same (balance row by PK ascending) to avoid deadlocks; retry on deadlock (error 1213) up to 3 times.
- Reconcile command: `SUM(delta)` per subject = balance; run in CI on seeded data and nightly in prod; mismatch = alert, not auto-fix.
- Enforce immutability: app has no update/delete path; DB user for web app lacks UPDATE/DELETE on the ledger if the host allows; otherwise `BEFORE UPDATE/DELETE` trigger with `SIGNAL SQLSTATE '45000'` (remember cascades skip triggers).

**Immutable issued documents** (invoice, receipt, quote accepted):
- States `draft -> issued -> void`. `draft` is editable; `issued` rows are never updated (guard in model + trigger/CHECK where cheap). Change = new revision row (`document_id`, `revision`, `UNIQUE (document_id, revision)`) or a credit note referencing the original. Void keeps the row and number.
- Issued rows store snapshots (party name/address/tax id, line descriptions, unit price, tax rate, totals, currency, locale). Totals are stored, and a test asserts `sum(lines) == total` using integer math.

**Atomic number sequences** (invoice 2026-000123, gapless per tenant/series/year):
- Table `number_sequences (tenant_id, series, period, next_value, PRIMARY KEY (tenant_id, series, period))`.
- In the same transaction that issues the document: `SELECT next_value ... FOR UPDATE`, use it, `UPDATE next_value = next_value + 1`. Rollback rolls the counter back, so no gaps. Add `UNIQUE (tenant_id, series, number)` on the document as the second guard.
- Draft documents get no legal number; the number is assigned at issue. Never derive numbers from `MAX(number)+1` or AUTO_INCREMENT.

## 9. Audit, outbox, idempotency, optimistic locking

- Audit log `audit_logs (id, tenant_id, actor_type, actor_id, action, subject_type, subject_id, changes JSON, ip, request_id, created_at)`; append-only; written in the same transaction as the change for money/permissions/settings; index `(tenant_id, subject_type, subject_id, created_at)`. Store changed fields only, redact secrets, never PII beyond need. Business events (who issued, who voided) are explicit rows, not only model observers.
- Outbox `outbox (id, tenant_id, topic, payload JSON, available_at, processed_at NULL, attempts, last_error)`; insert in the same transaction as the state change, a worker drains with `SELECT ... FOR UPDATE SKIP LOCKED` (MySQL 8.0+), marks processed, retries with backoff; consumers must be idempotent. Use for webhooks, emails, third-party calls after commit. (Kleppmann ch. 11, ch. 12 "dual writes".)
- Idempotency keys `idempotency_keys (tenant_id, user_id, key, endpoint, request_hash, response_status, response_body JSON, locked_at, expires_at, UNIQUE (tenant_id, user_id, key))`. Flow: insert key (unique violation = replay or in-flight), run, store response in the same transaction as the effect; same key + different hash or endpoint = 422, still in flight = 409 (HTTP contract in `api-design.md` sec. 9). Mandatory for payments, credits, orders from POS/mobile retries, inbound webhooks (dedupe by provider event id).
- Optimistic locking: `version INT UNSIGNED NOT NULL DEFAULT 1` on rows edited concurrently by humans. `UPDATE t SET ..., version = version + 1 WHERE id = ? AND version = ?`; 0 rows = conflict. HTTP: return ETag from version, require `If-Match`, answer 412 on mismatch and 428 when missing (RFC 9110 sec. 13.1.1; RFC 6585). Use pessimistic `FOR UPDATE` only for short money/stock sections. (Kleppmann ch. 7 lost updates / write skew.)
- Check-then-insert races (`exists()` then `create()`) are bugs: back them with a UNIQUE constraint and catch the duplicate-key error (1062).
- Transactions: wrap multi-row money/stock changes in `DB::transaction($fn, 3)`; keep them short; no HTTP calls inside; default isolation REPEATABLE READ is what InnoDB gives, so rely on locks, not on re-reads, for invariants across rows.

## 10. Indexing (Winand; Botros & Tinley)

- Composite order: equality columns first (tenant first), then the range or ORDER BY column last. An index `(tenant_id, status, created_at)` serves `WHERE tenant_id=? AND status=? ORDER BY created_at`; it does not serve a query on `status` alone.
- One index per real query pattern; remove an index shotgun (Karwin: Index Shotgun) after checking usage (`sys.schema_unused_indexes`; test removal with `ALTER ... ALTER INDEX x INVISIBLE`).
- Functions on indexed columns (`DATE(created_at) = ?`, `LOWER(email)`) defeat the index; rewrite as range or add a generated column + index. Leading-wildcard `LIKE '%x'` cannot use a B-tree; use FULLTEXT (`$table->fullText()` exists for MySQL) or a search engine.
- Covering index when a hot list reads few columns; do not add every column.
- FK columns need an index with the FK column first (InnoDB creates one if absent).
- Pagination (same rule as `api-design.md` sec. 8): API and growing lists use keyset; `WHERE (created_at, id) < (?, ?) ORDER BY created_at DESC, id DESC LIMIT 50` backed by `(tenant_id, created_at, id)`. Laravel `cursorPaginate()` (verified) requires ordering on unique/combined-unique non-null columns and gives no page numbers; offset `paginate()` only for admin tables that need page numbers and stay under ~10k rows. Do not run `COUNT(*)` on big tables per request.
- Every new hot query gets an `EXPLAIN` (or `EXPLAIN ANALYZE`) in the task evidence: expected key, rows, no filesort on big tables, no full scan. Test with realistic volume (100k+ rows seeded), not 20 rows. Row estimates on tiny data prove nothing.
- Avoid N+1: eager load; assert query counts in tests for list endpoints.
- Aggregates for dashboards: precomputed daily rows (`daily_stats`) updated by a job, not live `SUM` over millions of rows. Denormalization rules from section 2 apply.

## 11. Online migrations on MySQL 8.4 (Ambler: refactor in small, reversible steps with a transition period)

Verified facts (dev.mysql.com 8.4 Online DDL; laravel.com/docs/12.x/migrations):
- INSTANT: add column (any position), drop column, rename column (same type), set/drop default, rename table, add/drop virtual generated column, append ENUM members. Max 64 row versions of instant add/drop per table; after that it fails until the table is rebuilt (`OPTIMIZE TABLE`/rebuild resets the counter).
- INPLACE with concurrent DML: add/drop/rename secondary index (`LOCK=NONE`), extend VARCHAR within the same length-byte class (0-255 or 256+), change NULL/NOT NULL (INPLACE, rebuilds the table).
- COPY (blocks writes): change column type, decrease VARCHAR size, add stored generated column, change charset, drop PK alone.
- Laravel 12 exposes `->instant()` and `->lock('none'|'shared'|'exclusive'|'default')` on column/index/FK definitions; `instant()` cannot combine with `after()`/`first()` per the Laravel docs. Use them so MySQL errors instead of silently taking a long lock.
- `->change()` redefines the whole column: any modifier not repeated (nullable, default, comment, unsigned) is dropped. Always restate all modifiers.

Rules:
- Default for any table over ~100k rows or any production table: add nullable column or column with default, `->instant()`; then backfill in chunked jobs; then tighten (NOT NULL, CHECK, FK) in a later migration after verifying with a count query.
- Expand/contract for destructive changes: (1) expand: add new column/table; (2) dual-write in code; (3) backfill in chunks (by PK range, sleep between, resumable); (4) switch reads; (5) stop writing old; (6) contract: drop old in a later release. Never rename + deploy code in one step unless the table is empty or the app is offline. Dropping a column/table = owner gate (destructive) plus verified backup.
- Backfills never live inside the DDL migration; use a command/job with progress and idempotence.
- Add FK or unique to a table with data: first query for violators (`GROUP BY ... HAVING COUNT(*)>1`, `LEFT JOIN ... IS NULL`), clean, then add.
- Shared hosting without terminal: ship migrations in the ZIP, run via a protected one-time route/cron, keep each migration fast; no long backfills there.
- Test migrations on MySQL 8.4 only (never SQLite/MariaDB; owner rule): fresh `migrate:fresh --seed`, then migrate from the last released schema dump with data (`schema:dump` squashes old ones), then `migrate:rollback` once for reversible ones.
- Production: backup first, restore-check (below), run during low traffic, watch metadata locks (a long open transaction blocks DDL and queues all queries behind it).

## 12. Seeding, backup, restore

- Three seed sets: `reference` (permissions, plans, currencies, countries; idempotent `upsert`, runs in prod), `demo` (realistic volume, never in prod), `test` (factories). Reference seeders must be re-runnable. Seed users use generated test passwords stored in the project's seed/example file, never real ones.
- Seed realistic distributions (many tenants, one huge tenant, Arabic/French names, long strings, zero/negative edge amounts) so indexes and RTL layouts are tested honestly.
- Backups: nightly `mysqldump --single-transaction --routines --triggers` or physical backup + binlog if point-in-time is needed; stored off the VPS (not only CloudPanel local); encrypted if it contains PII.
- A backup that was never restored does not count. Monthly (and before any destructive migration): restore into a scratch DB, run row counts for key tables + the ledger reconcile + one smoke login. Record date and result in `HANDOFF.md`.

## 13. Schema doc template (one block per table in `docs/DATA_MODEL.md`)

```text
### table_name   (owner module: X)   [tenant: tenant_id | global]
Purpose: one sentence.
Lifecycle: created by / mutable until / deleted by (soft|archive|purge|never).
Columns: name type null default - meaning (only non-obvious ones)
Invariants: I1 ... (enforced by: UNIQUE uq_x | CHECK ck_x | FK | service+lock | test T-nn)
Indexes: name (cols) - serves query Q1/Q2
Relations: FK -> table (ON DELETE x)
Money/PII: columns holding money or personal data; retention
Open questions / decisions: B-xx / D-xx
```

Verification dates: MySQL 8.4 and Laravel 12.x docs fetched 2026-10-03.

## Red flags (stop and fix)

- `FLOAT`/`DOUBLE` on money, quantity or rate; money stored as formatted string.
- Tenant table without `tenant_id`, or a tenant list query without it in the index prefix; raw query without tenant filter.
- No FK on a relationship, or `cascadeOnDelete()` on ledger/document/audit children.
- AUTO_INCREMENT or `MAX()+1` used as a legal document number.
- UPDATE/DELETE path on a ledger or issued document; balance updated outside the movement transaction.
- `exists()` then insert without a UNIQUE constraint behind it.
- JSON column that is filtered, joined or summed; ENUM for a set that changes; TIMESTAMP for a future date.
- `->change()` without restating modifiers; renaming/dropping a column in the same release as the code change; backfill inside a DDL migration.
- Migration or tests run on SQLite/MariaDB; index claims without `EXPLAIN` on realistic volume.
- Offset pagination or per-request `COUNT(*)` on a table that will exceed ~10k rows.
- Soft delete with a plain UNIQUE index on the business key.
- Backups never restored; destructive migration without a verified backup and owner approval.

## How project-brain uses this

- Load when: designing or changing tables, writing a migration, adding a status/money/stock/number field, building a report query, planning tenancy, or reviewing slow queries. Load before writing `DATA_MODEL.md` in the architecture phase.
- Gates served: architecture gate (data model complete: invariants, indexes, tenancy, lifecycle), pre-code tracker gate (migration reviewed against section 11), security gate (tenancy tests, destructive migrations, retention), verification gate (migrations on MySQL 8.4, `EXPLAIN` evidence, reconcile and cross-tenant tests executed).
- Record in the repo: `docs/DATA_MODEL.md` (section 13 template per table), key-type and money-representation choices and any CHECK/trigger guard in `DECISIONS.md` (ADR with alternatives), retention periods and tenant purge registry in `docs/` (owner gate), each migration with `append-change --type migration --rollback "<how>"`, restore-check date in `HANDOFF.md`.
- Record in `.project-brain/`: invariants list with the test id that proves each, open backfills (task state `blocked` until the contract migration ships), and any table pending in `[ORPHANS & PENDING]` (e.g. ledger table created but projection not wired).
- Related files: `security-protocol.md` (tenancy, authz), `engineering-principles.md` sec. 16 (verification order), `quality-gates.md`, `deploy-protocol.md` (backup before migrate).
