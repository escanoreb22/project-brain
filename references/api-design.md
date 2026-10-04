# API design (HTTP/JSON for SPA, Inertia, Flutter, Electron)

Load for any new endpoint, contract change, auth flow, upload, webhook or generated client. Backend layering lives in `backend-architecture.md`; DB shape in `db-schema-design.md`; threat model in `references/security-protocol.md`. This file covers the wire contract only.
Sources: Geewax, API Design Patterns (chapter numbers from memory, unverified); Google AIP (aip.dev); Zalando guidelines (opensource.zalando.com/restful-api-guidelines); Microsoft REST guidelines; RFCs below; Laravel 13.x docs.

## 0. Verified facts (checked Oct 2026)
- RFC 9110 = HTTP Semantics, Internet Standard (STD 97); it replaces RFC 7231/7232 etc. Cite 9110, not 7231.
- RFC 9457 = Problem Details for HTTP APIs, Proposed Standard, obsoletes RFC 7807. Media type `application/problem+json`.
- RFC 8288 = Web Linking (`Link` header), Proposed Standard, obsoletes RFC 5988.
- RFC 9745 = `Deprecation` response header, Proposed Standard (2025). Value is an Item Structured Field Date, written `@<unix-seconds>`, e.g. `Deprecation: @1688169599`. Not an HTTP-date.
- RFC 8594 = `Sunset` header, Informational, HTTP-date value (`Sunset: Sat, 31 Dec 2026 23:59:59 GMT`).
- RFC 6585 defines 428 Precondition Required and 429 Too Many Requests (with optional `Retry-After`).
- Idempotency-Key: IETF draft-ietf-httpapi-idempotency-key-header, rev 07, EXPIRED, never an RFC. Treat as a convention, not a standard. Semantics in the draft: value is a Structured Field string; 400 if required and missing; 409 if the first request is still in flight; 422 if the key is reused with a different payload.
- RateLimit headers: draft-ietf-httpapi-ratelimit-headers-11 (May 2026), still a draft (`RateLimit` + `RateLimit-Policy`). Do not promise them in the contract; `Retry-After` on 429 is the only guaranteed signal.
- OpenAPI: spec site lists 3.2.1, 3.1.2, 3.0.4. Default: 3.1.x (full JSON Schema 2020-12 alignment, wide tool support). Move to 3.2 only when the codegen and lint tools in use support it.
- Laravel 13.x: Sanctum tokens are stored SHA-256 hashed; `createToken($name, $abilities, $expiresAt)`; `sanctum:prune-expired`; `statefulApi()` in `bootstrap/app.php`; `cursorPaginate` exists and needs an ordered unique non-null column. Laravel 13 docs also list built-in JSON:API Resources; do not assume they exist on 12.x.
- openapi-typescript supports OpenAPI 3.0 and 3.1; companion `openapi-fetch` gives a typed fetch client.
- Standard Webhooks (standardwebhooks.com) defines headers `webhook-id`, `webhook-timestamp`, `webhook-signature`.

## 1. Contract first
- Default: one `openapi.yaml` (3.1) per API surface in `docs/api/`, written and reviewed BEFORE routes/controllers. Every endpoint, request body, response, error and security scheme is in it. Deviate only for throwaway internal Inertia page actions (see 2).
- Every operation has: `operationId` (verbs: `listOrders`, `createOrder`), `tags`, `security`, all response codes used, and `components/schemas` refs (no inline anonymous schemas for entities).
- Spec change and code change land in the same commit. The PR check lints the spec (Spectral) and runs contract tests (see 14).
- If using a code-to-spec generator (e.g. Scramble), the committed spec is still the reviewed artifact: diff it in CI and fail on unexplained changes.
- Record the spec path and surfaces in `docs/PROJECT_MAP.md` `[SYSTEM_FLOW]`; unimplemented operations go to `[ORPHANS & PENDING]`.

## 2. Which transport per client (decision table)
| Client | Transport | Auth | Notes |
|---|---|---|---|
| Inertia React (same app) | Inertia page props + form posts to web routes | session cookie | No public JSON API needed. Do not invent REST for page data. Shared validation errors arrive as props. |
| React SPA, same parent domain | `/api/v1` JSON | Sanctum SPA cookie + CSRF | `GET /sanctum/csrf-cookie`, send `X-XSRF-TOKEN`, `Accept: application/json`, `Origin`/`Referer`. |
| Flutter mobile | `/api/v1` JSON | Sanctum bearer token per device | Token in Keystore/Keychain via secure storage. |
| Electron POS | `/api/v1` JSON + offline queue | bearer token per device/terminal | Idempotency-Key mandatory on writes (offline replay). |
| Third party / webhooks out | `/api/v1` + webhooks | scoped token / HMAC | Abilities (`orders:read`) per token. |
Default: ONE `/api/v1` surface shared by SPA, Flutter and Electron; web-only needs go through Inertia. Do not fork per-client endpoints; use sparse fields and `include` instead (Zalando; Geewax ch. 9). Exception: operations with no shared equivalent (POS bootstrap bundle, batch sync) live under `/api/v1/pos/*` and call the same Actions (`multi-surface-architecture.md` sec. 1, 10).

## 3. Resources and naming
- Plural lowercase kebab-case nouns, max 2 nesting levels: `/orders/{order}/lines`. Deeper -> top-level resource with filter (`/lines?order_id=`) (Geewax ch. 5; Zalando).
- JSON fields `snake_case` (matches Eloquent/Dart json_serializable config) - pick once, record in DECISIONS.md. IDs are opaque strings in JSON: the `public_id` ULID (`db-schema-design.md` sec. 3); never expose auto-increment ids.
- Standard methods first (Geewax ch. 8; AIP-131..135): list GET, get GET, create POST, update PATCH (partial), replace PUT (rare), delete DELETE. Actions that are not CRUD: `POST /orders/{id}/cancel` as a sub-resource verb (Geewax ch. 10 custom methods) - never `PUT /orders/{id}?status=cancelled`.
- Booleans positive (`is_active`), enums as lowercase strings documented in the spec; never numeric codes. Unknown enum value on the client must not crash (Dart: `@JsonKey(unknownEnumValue:)`; TS: `| (string & {})` only if spec says open enum).
- Singleton settings: `/tenant/settings` (GET/PATCH), not a list.

## 4. Versioning and deprecation
- Default: URL major version `/api/v1`. New major only for breaking change; additive changes stay in v1 (see 13). Never version per endpoint.
- Mobile/desktop clients cannot be force-updated instantly: keep N and N-1 live. Minimum sunset window: 6 months for mobile/desktop, 3 months web-only. Record the dates in DECISIONS.md.
- Deprecating: add `Deprecation: @<unix>` (RFC 9745) and `Sunset: <HTTP-date>` (RFC 8594) plus `Link: <https://docs.example/migrate>; rel="deprecation"` (RFC 8288) on every response of the old operation; mark `deprecated: true` in the spec; log per-client usage; remove only after traffic is zero or the date passes.
- Clients send `X-Client: <surface>/<semver>`; `GET /api/v1/meta` returns `min_client_version` per surface; below it the API answers `400` problem+json `code: client_outdated` + `update_url`, so Flutter/Electron show a forced-update screen instead of crashing (`multi-surface-architecture.md` sec. 11).

## 5. Methods and status codes
| Case | Code |
|---|---|
| read ok / update ok with body | 200 |
| created (set `Location`) | 201 |
| accepted for async work | 202 + status resource (see 9) |
| delete / update with no body | 204 |
| bad syntax, missing required header | 400 |
| not authenticated / token expired | 401 (SPA session expiry may be 419 CSRF: treat as re-login) |
| authenticated but forbidden | 403 |
| not found OR not in caller's tenant | 404 (never 403 for other-tenant ids; leaks existence) |
| method not allowed | 405 + `Allow` |
| state conflict, duplicate unique | 409 |
| ETag mismatch | 412 |
| payload too large | 413 |
| semantic/validation error | 422 |
| missing `If-Match` where required | 428 |
| rate limited | 429 + `Retry-After` |
| server error | 500 (never leak trace; `APP_DEBUG=false`) |
- GET/HEAD safe and cacheable; PUT/DELETE idempotent; POST/PATCH not (RFC 9110 sec. 9). Never mutate on GET (prefetch, crawlers).
- Always send `Accept: application/json`; Laravel returns HTML redirects otherwise. Force JSON on `api/*` in `bootstrap/app.php` (`shouldRenderJsonWhen`).

## 6. Errors: RFC 9457 problem+json
Default shape for every non-2xx on `/api/*`, `Content-Type: application/problem+json`:
```json
{ "type": "https://api.example.com/problems/insufficient-stock",
  "title": "Insufficient stock", "status": 409,
  "detail": "Line 2 requests 5, only 3 available.",
  "code": "stock.insufficient", "request_id": "01J...",
  "errors": [ { "pointer": "/lines/1/qty", "code": "qty.exceeds_stock", "message": "..." } ] }
```
- `code` is a stable machine string (`domain.reason`), documented in the spec, never renamed after release. Clients branch on `code`, never on `title`/`detail`/message text.
- `title` is constant per type; `detail` is human text, localized (see 12); `type` is a stable URI (need not resolve; resolving to a doc page is better).
- Validation (422): `errors[]` with JSON Pointer `pointer` (RFC 6901) into the request body, per-field `code` + localized `message`. Laravel's default `{message, errors:{field:[..]}}` is NOT RFC 9457: map it in the exception handler (`bootstrap/app.php` `withExceptions`) once, in one place; keep field keys so Inertia forms still work.
- 401/403/404/429/500 use the same envelope. Include `request_id` (also in `X-Request-Id` and logs).
- Never put SQL, stack traces, file paths, or whether an email exists in `detail`.
- Spec: define `components/responses/Problem` once and reference it.

## 7. Success shape, resources, Laravel conventions
- Single: `{ "data": {...} }`; list: `{ "data": [...], "meta": {...}, "links": {...} }`. Pick wrapped (Laravel default) and keep it; do not call `JsonResource::withoutWrapping()` on one surface only.
- One `JsonResource` per entity, in the module's `Http/Resources` (or `app/Http/Resources` when the app has no `modules/`; `backend-architecture.md` sec. 2); controllers return `->toResource()` / resource classes, never models or `toArray()` on models (leaks columns, breaks the contract).
- Relations only via `whenLoaded()`; counts via `whenCounted()`; conditional fields via `when()`. Controller eager-loads from an allowlisted `include`; N+1 in a resource = bug (test with `Model::preventLazyLoading()` in non-prod).
- Resources output public ids, ISO strings, money object (see 11), never raw internal columns (`tenant_id`, hashes).
- Meta via `additional()` or `paginationInformation()`; keep the pagination envelope identical across all lists.
- Request side: one `FormRequest` per write operation; `authorize()` uses a Policy; rules mirror the spec (`required`, max lengths, `Rule::enum`). Spec and rules diverging = contract-test failure.

## 8. Pagination, sorting, filtering, sparse fields
- Default: cursor/keyset pagination for every list that can exceed ~100 rows or is written to often: `?limit=50&cursor=<opaque>`; response `meta.next_cursor` (null at end), `links.next`. Tokens opaque, URL-safe, not client-parseable (AIP-158; Geewax ch. 22). Default limit 25-50, hard max 100, clamp rather than error (AIP-158).
- Laravel: `->orderBy('created_at')->orderBy('id')->cursorPaginate($limit)`. Requires a unique, non-null order key (add `id` tiebreaker); no page numbers, no jump-to-page. Index the order columns (composite with `tenant_id` first).
- Offset `?page=` only for small admin tables where the UI needs page numbers and rows < ~10k. `total` is optional and may be an estimate; do not run `COUNT(*)` on big tables per request.
- Adding pagination to a shipped list later is a breaking change (AIP-158): paginate from day one.
- Sort: `?sort=-created_at,name`; allowlist per endpoint in the spec (enum); unknown -> 422. Never pass client strings to `orderBy` unchecked.
- Filter: `?filter[status]=paid&filter[created_from]=2026-01-01`; allowlist per endpoint; typed and validated; operators as suffix (`_from`, `_to`, `_in`). Free-text `?q=` separate. No client-supplied SQL/expressions (Geewax ch. 23 warns on expression languages: avoid).
- Sparse fields/include: `?fields=id,name,total` and `?include=customer,lines` only where a client measurably needs it (mobile payload). Allowlist; default responses stay small.
- Bulk reads by ids: `GET /orders?filter[id_in]=a,b` capped at 100 ids.

## 9. Idempotency, concurrency, long-running work
- Idempotency (Default: required on money, order, stock and any POST that an offline client may replay; optional elsewhere). Header `Idempotency-Key: <uuid>`. Draft is expired, so this is OUR documented contract:
  - store `(tenant_id, user_id, key)` unique + endpoint + request hash (table: `db-schema-design.md` sec. 9) + response status/body + `expires_at` (24-72 h); compose the lookup key with tenant+user, never trust the raw key alone;
  - same key + same hash -> replay stored response with `Idempotent-Replayed: true`; same key + different hash -> 422; first still running -> 409 (+`Retry-After`); missing on a required route -> 400;
  - create the row inside the same DB transaction as the effect. Natural unique keys (client-generated UUID `client_uuid` on the entity) are stronger for offline POS; prefer them for Electron sync.
  - deduplication detail: Geewax ch. 27; queue-side idempotency in `backend-architecture.md` sec. 6.
- Optimistic concurrency (Default: on every mutable entity edited by humans): return strong `ETag` (hash of `updated_at`+id or a `version` int) on GET; PATCH/PUT/DELETE require `If-Match`; mismatch -> 412; absent -> 428 (RFC 9110 conditional requests; RFC 6585). Also store `version` column; update with `where version = ?` and check affected rows. Never last-write-wins on invoices, prices, stock.
- Long-running (> ~2 s, imports, exports, PDF batches): `202 Accepted` + `Location: /v1/operations/{id}`; `GET` returns `{id, status: queued|running|succeeded|failed|cancelled, progress, result_url|error(problem)}`; `DELETE`/`POST cancel` to cancel; client polls with backoff, honors `Retry-After`; results expire (Geewax ch. 11-12). Push (Reverb/FCM) is an optimization, polling is the contract.
- Retries: clients retry only GET/PUT/DELETE and POST with Idempotency-Key; exponential backoff + jitter on 429/502/503/504 (Geewax ch. 30).

## 10. File upload
- Default: presigned direct-to-storage (S3-compatible/R2) for files > 5 MB or mobile: `POST /v1/uploads {filename, size, mime, sha256}` -> `{upload_id, url, headers, expires_at}`; client PUTs; `POST /v1/uploads/{id}/complete`; server then validates and attaches. Small images/docs (< 5 MB, e.g. avatars): multipart `POST` to Laravel directly. Large resumable (video/backups): chunked/tus-style; deviate only when needed.
- Validate server-side regardless of client claims: size cap, extension allowlist, MIME sniffed from content (`finfo`), image re-encode to strip EXIF/polyglots, random storage name (never user filename), per-tenant path prefix, private bucket + signed GET URLs (short TTL). Virus scan (ClamAV via queue) for user-to-user or public-facing files; file stays `status=pending` until scanned.
- Never serve user uploads from the app origin with the sniffed type (XSS); `Content-Disposition: attachment` for non-images; serve through signed storage URLs (R2/S3 host) or a controller. Never add a new subdomain or host for files without an owner request (`owner-profile.md`). Quota per tenant. `413` for oversize, `415` for disallowed type, `422` for invalid content. Nginx `client_max_body_size` and PHP `upload_max_filesize`/`post_max_size` must match the spec limit.

## 11. Data formats
- Time: ISO 8601 / RFC 3339 UTC with `Z` for instants (`2026-10-03T14:05:00Z`); store UTC; dates without time `YYYY-MM-DD`; tenant timezone sent as IANA name (`Africa/Casablanca`) and applied only in the UI. Laravel: `$casts` datetime + `toIso8601ZuluString()` in resources.
- Money: integer minor units + ISO 4217 currency, as an object: `"total": {"amount": 12050, "currency": "MAD"}`. Never floats. Currency minor-unit exponent comes from a table (MAD 2, JPY 0, KWD 3), not hard-coded 100. Decimal quantities (kg, litres) as strings (`"1.250"`) to avoid float loss in JS/Dart; DB `DECIMAL`.
- Large ints: ids as strings; JS loses precision above 2^53.
- Locale: BCP 47 tags (`ar`, `fr`, `en`, `ar-MA`). Phone E.164. Country ISO 3166-1 alpha-2. Language/currency are separate fields.
- `null` vs absent: absent = not requested or not changed (PATCH); `null` = explicit empty. State it in the spec per field. PATCH is JSON Merge Patch semantics (RFC 7396) unless the spec says otherwise.

## 12. i18n of API messages
- Server picks locale from `Accept-Language` (fall back to user/tenant default); returns `Content-Language`. Only `title`/`detail`/validation `message` are localized; `code`, enums and keys never are.
- Clients MAY ignore server text and map `code` to their own localized strings (Flutter ARB / i18next). Required for offline-first Electron/Flutter. Keep lang files `ar`, `fr`, `en` complete (`lang/{ar,fr,en}/validation.php`); missing key = CI failure.
- Business data translations (product names) are data fields, `name: {ar, fr, en}` object or `?lang=` projection, per `db-schema-design.md`; do not mix with UI messages.

## 13. Backward-compatible evolution (inside a major)
Allowed: add optional request field; add response field; add endpoint; add enum value ONLY if clients were told enums are open; relax validation; add optional query param; new error `code` on an existing status.
Breaking (needs new major or a flag): remove/rename field or endpoint; change type, format, unit or meaning (incl. money scale, timezone); make optional -> required; tighten validation; change default sort/limit; remove enum value; change auth scheme; change status code semantics; add pagination to an unpaginated list (Geewax ch. 25; AIP-180).
- Clients must ignore unknown response fields (Dart `json_serializable` default; TS no strict parsing). Servers must reject unknown request fields only if the spec says so; default: ignore + log.
- Gate: spec diff tool (`oasdiff breaking`) in CI against the last released spec.

## 14. Auth, device binding, rate limits
- Web SPA: Sanctum cookie; `statefulApi()`, `stateful` domains, `supports_credentials=true`, `withCredentials`+`withXSRFToken`, session `domain=.example.com`, same top-level domain required. 401/419 -> go to login. Do not use tokens for the first-party SPA (Sanctum docs).
- Mobile/desktop: bearer token via `POST /v1/auth/token {email, password, device_name, device_id}`; one token row per device (name = what the user recognizes); abilities per client type; short `expiration` per token, not "never"; store `device_id`, `last_used_at`, `ip`, `user_agent` (extend `PersonalAccessToken` model). User can list and revoke devices in settings; password change/role change revokes all tokens.
- Sanctum has no refresh-token flow. Default: long-lived per-device token (30-90 days sliding via re-issue on `POST /v1/auth/refresh` with the still-valid token, old one deleted) + revoke on logout/stolen. If tokens must be short (< 1 day) or third-party OAuth is needed, deviate to Passport/OAuth2 PKCE and record it in DECISIONS.md (owner gate: auth change).
- Tokens only in `Authorization: Bearer`; never in URL/query/logs (mask in log middleware). Electron: OS keychain (safeStorage), not localStorage. Flutter: flutter_secure_storage.
- Login throttling: `RateLimiter::for('login', by email+ip, 5/min)`; API default `throttle:api` per user/token (60-120/min), stricter on auth, OTP, export, upload-init; 429 + `Retry-After`. Never rate-limit by IP alone behind Cloudflare: configure trusted proxies so `request()->ip()` is the real client (CF-Connecting-IP).
- Tenancy: tenant comes from the authenticated principal (token/session), NEVER from a client-supplied header/body/path alone. If a subdomain or `X-Tenant` header is used, verify membership server-side. Global scope on every tenant model; cross-tenant id -> 404. Contract test: user of tenant A requests tenant B id on every operation.
- Server-to-server and webhooks use HMAC, not user tokens. Every operation lists `security` in the spec (`cookieAuth`, `bearerAuth`); public ones explicitly `security: []`.

## 15. Webhooks (outgoing from our app)
Only when the PRD requires outgoing webhooks; otherwise skip this section except the incoming-webhook bullet.
- Payload: `{id, type: "order.paid", created_at, api_version, data}`; stable event ids; at-least-once delivery, so consumers dedupe on `id`.
- Sign: HMAC-SHA256 over `id.timestamp.body` with per-endpoint secret; headers `webhook-id`, `webhook-timestamp`, `webhook-signature: v1,<base64>` (Standard Webhooks). Receivers reject timestamps older than 5 min and compare with `hash_equals`. Support secret rotation (two active secrets).
- Retry with exponential backoff + jitter for ~24-72 h on non-2xx/timeout (5 s timeout); disable endpoint after sustained failure and notify the tenant admin; keep a delivery log with replay button.
- Outgoing URLs: https only, block private/loopback/link-local IPs and redirects (SSRF), resolve DNS at send time.
- Incoming webhooks (Stripe, payment gateways): verify signature on RAW body before parsing, check timestamp, store event id unique, return 2xx fast and process on a queue.

## 16. Contract tests and generated clients
- Pest feature test per operation: assert status, JSON structure against the spec (e.g. `league/openapi-psr7-validator` or Spectator in Laravel) for success AND error responses; one tenant-isolation test per operation; one test each for 401, 403, 404, 422 shape, 412/428 where used.
- Spec lint: Spectral ruleset (operationId, tags, problem responses, no inline entity schemas). Breaking-change check: oasdiff.
- TypeScript: `openapi-typescript openapi.yaml -o resources/js/api/schema.d.ts` + `openapi-fetch` (typed client; set base URL, credentials, XSRF). Regenerate in CI and fail on dirty diff. Do not hand-write response types.
- Dart/Flutter: generate from the same spec (openapi-generator `dart-dio` or Chopper/retrofit codegen) into `packages/api_client`; pin the generator version; wrap in a repository so UI never touches generated classes. Generator choice not verified here; verify output on a real endpoint before adopting.
- A mock server from the spec (Prism) lets Flutter/Electron work before the backend exists; remove when the real endpoint passes contract tests.

## Red flags
- Route exists with no entry in `openapi.yaml`; spec edited after the code.
- Controller returns an Eloquent model or `$model->toArray()`; response contains `tenant_id`, `password`, internal ids.
- Error handled by parsing `message` text; custom error shapes per controller; stack trace or SQL in a response.
- Offset pagination on a growing table; list without `limit` cap; `orderBy($request->sort)` unchecked.
- Floats for money or quantity; local-time strings without offset; numeric ids in JS above 2^53.
- POST that creates money/stock effects with no idempotency; PUT/PATCH with no `If-Match`.
- Tenant id read from request body; 403 returned for another tenant's id; missing cross-tenant test.
- Sanctum token with no expiry and no device row; token in URL/log; SPA using bearer tokens.
- Breaking change shipped inside `/v1`; deprecation with no `Deprecation`/`Sunset` headers and no usage log.
- Upload trusts client MIME/filename; public bucket; no size limit in nginx+PHP+spec.
- Webhook without signature, timestamp check or dedupe; SSRF-able target URLs.
- Generated client files hand-edited; spec and TS/Dart types out of sync.
- Per-client forked endpoints (`/mobile/orders`, `/pos/orders`) duplicating logic.

## How project-brain uses this
- Load when: planner writes the API/interface spec (`IF-xx`); coder adds or changes an endpoint, auth, upload or webhook; designer needs the data contract for a screen; reviewer checks drift between spec and code.
- Gates served: planning (contract before tasks), tracker (every route maps to an operation; orphan = pending), security (sections 6, 9, 10, 14, 15), verifying (contract tests green, client types regenerated, real-device check for Flutter/Electron).
- Owner gates triggered: auth/token model, tenancy resolution, money format, new major version or sunset dates, public/third-party API exposure.
- Record: `docs/api/openapi.yaml` (canonical), `docs/api/CONVENTIONS.md` only for project-specific deviations from this file (one line each, with reason); DECISIONS.md entries for casing, wrapped vs unwrapped envelope, sunset windows, token lifetime, idempotency retention, upload size limits, `delegated, open to reversal` where the owner did not choose; `[SYSTEM_FLOW]` lists each client -> endpoints; `HANDOFF.md` notes spec version and which clients are regenerated.
