# Desktop Electron (offline POS) - rules for the owner's stack

Scope: Electron desktop POS, offline-first, React+TS renderer, Laravel API, Windows target. Facts checked 2026-10-03 against official docs (URLs in Sources). Items not checked are marked UNVERIFIED. Versions come from the repo lockfile, never from this file.
Related files: `multi-surface-architecture.md` sec. 10 (offline sync contract; this file must match it), `api-design.md` sec. 9 and 14 (idempotency, If-Match, device tokens), `security-protocol.md`, `db-schema-design.md` (server ledgers), `compliance-payments.md` (invoices, 09-08, card data), `operations-monitoring.md` (crash tracking, incidents), `deploy-protocol.md` (server side only).

## 1. Defaults (decision table)

| Topic | Default | Change only if |
|---|---|---|
| Electron version | latest stable major; support policy covers the latest 3 majors, 8-week cadence | never stay on an unsupported major |
| Build/pack | electron-builder + NSIS + electron-updater | owner asks for Forge/MSIX |
| Dev tooling | electron-vite (main/preload/renderer in one config) | repo already uses another |
| Local DB | better-sqlite3-multiple-ciphers, one DB file per tenant+device | - |
| Key storage | random 32-byte key, wrapped by safeStorage, stored beside the DB | - |
| Sync | outbox queue + pull cursor + idempotency keys | - |
| Receipt print | ESC/POS raw to thermal printer; PDF/HTML print for A4 invoices | - |
| Tests | Vitest (unit, main+renderer), Playwright `_electron` (smoke E2E) | - |
| Signing | Azure Artifact Signing if the US LLC passes identity validation (section 8); else OV via cloud HSM | - |

Why electron-builder (decision, `delegated, open to reversal`): NSIS target is the supported auto-update path of electron-updater, with channels and staged rollout; the Forge Vite plugin is marked experimental (minor versions may break). Both are workable; do not mix them in one repo.

## 2. Security baseline (official checklist, 20 items; these are the ones that matter here)

Defaults in current Electron: nodeIntegration off (since v5), contextIsolation on (v12), sandbox on (v20). Never turn them off; never add a flag to "make it work".
Checklist for every BrowserWindow / webPreferences:
- [ ] `contextIsolation: true`, `sandbox: true`, `nodeIntegration: false`, `webSecurity` left on, no `allowRunningInsecureContent`, no `enableBlinkFeatures`, no `webviewTag`.
- [ ] Renderer loads only packaged local content (custom protocol such as `app://`, not `file://`) or the dev server in development. No remote pages inside the POS window. The Laravel API is called with `fetch` from the main process, not by loading a site.
- [ ] CSP set via response headers of the custom protocol (or meta tag): `default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-src 'none'; connect-src 'self'`. No `unsafe-eval`. Allow `connect-src` to the API origin only if the renderer calls it (prefer main process).
- [ ] `webContents.setWindowOpenHandler(() => ({action:'deny'}))` and a `will-navigate` handler that blocks everything except the app origin (parse with `new URL`, compare `origin`, never `startsWith`).
- [ ] `shell.openExternal` only after validating the URL: `https:` scheme + allow-list host. Never pass user text.
- [ ] `session.setPermissionRequestHandler` and `setPermissionCheckHandler`: deny all by default.
- [ ] IPC: every `ipcMain.handle` validates `event.senderFrame` origin and validates the payload (zod or equivalent) before acting. Return plain data, never throw secrets.
- [ ] Preload exposes narrow functions through `contextBridge.exposeInMainWorld`; one function per channel. Never expose `ipcRenderer`, `send`, `on`, `fs`, `shell`, or a generic `invoke(channel, ...)`.
- [ ] Production fuses flipped at package time (`@electron/fuses`, `FuseV1Options`): `RunAsNode` false, `EnableNodeOptionsEnvironmentVariable` false, `EnableNodeCliInspectArguments` false, `EnableEmbeddedAsarIntegrityValidation` true, `OnlyLoadAppFromAsar` true, `EnableCookieEncryption` true, `GrantFileProtocolExtraPrivileges` false when no `file://`. Exception: Playwright launch needs `EnableNodeCliInspectArguments` not false (Playwright docs), so use a test build with that fuse on, and the release build with it off.
- [ ] No secrets in the renderer bundle, in `app.asar`, or in `.env` shipped with the app. The renderer is public code.
- [ ] Privileged actions (refund, price override, drawer open, user admin) are authorized in main by session role, not by a renderer flag.

Preload pattern:
```ts
// preload/index.ts
contextBridge.exposeInMainWorld('pos', {
  saleCreate: (input: SaleInput) => ipcRenderer.invoke('sale:create', input),
  printReceipt: (saleId: string) => ipcRenderer.invoke('print:receipt', saleId),
});
// main: handler guard
ipcMain.handle('sale:create', (e, raw) => {
  assertTrustedSender(e);            // checks e.senderFrame.url origin
  return createSale(SaleInput.parse(raw));
});
```

## 3. Architecture (main / preload / renderer)

- Layout (electron-vite): `src/main`, `src/preload`, `src/renderer`, `src/shared` (zod schemas + TS types shared by all three). Output `out/`, `package.json` main points to `./out/main/index.js`.
- Main owns: DB, sync engine, printing, updater, device binding, logging, window management. Renderer owns UI only. Renderer never touches SQLite.
- One IPC contract file in `src/shared/ipc.ts` (channel names, input/output schemas). Add a channel there first, then handler, then preload, then UI.
- Renderer state: TanStack Query over the `window.pos` API, so the UI treats the local DB as its server. The UI never knows whether it is online.
- Heavy work (sync batches, PDF, backup) in a utility process or worker thread, never blocking main on the event loop of the UI.
- i18n ar/fr/en + RTL: set `dir` and `lang` on `<html>` from the user setting; fonts bundled locally (no CDN: the app is offline). Test RTL receipts and screens.
- Single instance: `app.requestSingleInstanceLock()`; second launch focuses the first window. Two processes on one SQLite file is a bug.
- Money: integer minor units in DB and IPC. Never floats. Tax/rounding rules are shared with the server (same fixtures in both test suites).

## 4. Local database (SQLite, encrypted)

- Package: `better-sqlite3-multiple-ciphers` (fork of better-sqlite3 using SQLite3MultipleCiphers). Default cipher of the fork is its own (sqleet); for SQLCipher format set `cipher='sqlcipher'` and `legacy=4` via pragma. Pick one cipher at project start and record it in an ADR; changing later needs a rekey migration. Latest seen 13.0.3 (verify in lockfile).
- Apply the key first, before any other statement: `db.pragma("key='...'")` (use hex raw key form per cipher docs - UNVERIFIED syntax, test on the real build). Change key with `rekey`.
- Key handling:
  1. First run: generate 32 random bytes (`crypto.randomBytes`).
  2. Wrap with `safeStorage.encryptStringAsync` (the docs recommend the async API: non-blocking, `shouldReEncrypt` for key rotation, handles temporary unavailability) and store the blob in `userData/db.key`.
  3. Never log the key, never put it in the renderer, never derive it from the activation code alone.
  4. Windows uses DPAPI: protects against other Windows users, not against other processes of the same user. Say so in the threat model. `isEncryptionAvailable()` must be true after `app.whenReady()`; if false, refuse to open the DB.
  5. Backup/restore across PCs: the wrapped key does not move. Export needs a server-escrowed or user-passphrase-wrapped key (owner decision, gate: encryption).
- Pragmas on open: `journal_mode=WAL`, `synchronous=FULL` (the pragma is per connection, not per table; in WAL mode NORMAL can roll back recent commits after a power loss, and a POS must not lose sales), `foreign_keys=ON`, `busy_timeout=5000`. Keep the DB on a local disk: WAL does not work over a network filesystem (sqlite.org/wal.html).
- Migrations: numbered SQL files, applied in a transaction at startup, tracked by `PRAGMA user_version` or a `_migrations` table. Forward-only; the app refuses to start on a DB newer than itself (downgrade guard). Backup the file before migrating (copy `.db` after a WAL checkpoint).
- Native module: rebuild for Electron's ABI (electron-builder `npmRebuild` or `@electron/rebuild`); keep the `.node` file unpacked from asar (`asarUnpack`) - verify on the packaged build, not in dev.
- Schema rules: UUIDv7 primary keys generated on device (no autoincrement ids that collide), `tenant_id` and `device_id` on every synced row, `updated_at`, `deleted_at` (soft delete), `server_version` (integer from server) on synced rows.
- Tests run against a real encrypted DB file, not `:memory:` only.

## 5. Offline-first sync with the Laravel API

Contract source: `multi-surface-architecture.md` sec. 10 (endpoints, per-item results, conflict rules) and `api-design.md` sec. 9 (idempotency). This section adds the device side only; if they disagree, the server contract wins and this file is corrected.
Tables: `outbox(id, client_uuid uuid unique, entity, entity_id, op, payload json, created_at_device, attempts, next_attempt_at, status)`, `sync_state(cursor, last_pull_at, clock_offset_ms)`.

Write path (push):
1. Business action and outbox row are written in ONE local transaction. The UI never calls the server directly.
2. Sync loop sends the outbox in order per entity to `POST /api/v1/pos/sync`, batches of N (start 50). Each item carries its `client_uuid` (fixed at creation, reused on every retry) plus `device_id` and schema version; the batch request also sends an `Idempotency-Key` per `api-design.md` sec. 9.
3. Server dedupes permanently on the unique index `(tenant_id, device_id, client_uuid)`, so a replay after weeks offline returns the original result (no time-limited key store needed). It returns a per-item result: `{client_uuid, status: applied|duplicate|rejected|conflict, server_version, error_code}`. HTTP 200 on a batch does not mean every item succeeded.
4. Device marks an item done only on `applied` or `duplicate`. `rejected` or `conflict` goes to the visible "needs attention" list (never silently dropped); `conflict` re-pulls the entity first. Transient (network, 5xx, 429) retries with exponential backoff + jitter, cap 15 min.

Read path (pull): cursor-based `GET /api/v1/pos/bootstrap?since=<cursor>` returning changes with `server_version`, tombstones for deletes, `next_cursor`, `has_more`. Apply in one local transaction per page. Initial sync = snapshot + cursor.

Conflict rules (decide per entity, write in the spec):
| Entity kind | Rule |
|---|---|
| Sales, payments, stock movements, cash events | append-only ledger rows, no conflict; server never edits, corrects by reversal rows |
| Stock quantity | derived from movements, never synced as a number |
| Catalog (products, prices) | server wins; device edits are rejected unless the role allows, then sent with the base `server_version` (If-Match); mismatch -> `conflict` |
| Customers, settings | server wins (`multi-surface-architecture.md` sec. 10): device edits carry the base `server_version`; mismatch -> `conflict`, device re-pulls and tells the user; never decided by device clock |
| Deletes | tombstone wins over update unless the update has higher `server_version` |

Clock skew: never trust the device clock for ordering. Order by `server_version` and local sequence. Record `clock_offset_ms = server Date header - local time` on each sync; show a warning when |offset| > 5 min; stamp each sale with both `device_time` and `device_seq`. Server stores `received_at`. Block activation/sync when offset > 24 h (default threshold, recorded in DECISIONS.md as `delegated, open to reversal`).
Receipt numbering offline: legal invoice numbers come from server-allocated ranges per device or a provisional local number replaced on sync (`multi-surface-architecture.md` sec. 10); a per-device series (`deviceCode-yyyymm-seq`) is only for non-fiscal tickets. Moroccan invoices need a unique sequential number without gaps (`compliance-payments.md` sec. 8, UNVERIFIED there); whether per-device ranges satisfy it is an owner/accountant gate.
Offline limits (policy, owner decision): max offline days before the app locks sales (default 7 days), shown as a countdown; refunds above a threshold need online approval.
Tests: kill the app mid-sync, drop network per item, send the same batch twice, send out-of-order, skewed clock; assert no duplicate sale on the server and no lost sale on the device.

## 6. Device binding and activation

- Activation code: server-generated, single use, short expiry (24-72 h), bound to tenant + plan + max devices, stored hashed on server, rate-limited. Entered once on first run.
- Flow: app sends `{code, device_fingerprint, app_version}` over HTTPS -> server returns `{device_id, device_token, tenant, license{plan, expires_at, grace_days}}`. Token stored via safeStorage, never in plain files.
- Fingerprint: a random install id generated at first run (stored in the wrapped store) plus coarse hardware hints (machine GUID). It is a binding aid, not a secret; do not claim anti-piracy. Do not collect more than needed; list device data in the data map and CNDP declaration (`compliance-payments.md` sec. 2-4).
- Server controls: list devices per tenant, revoke a device, reset slot. On next sync a revoked device gets 401 `device_revoked` -> app locks, keeps data readable for export per policy (owner decision).
- Offline license: signed license blob (Ed25519, public key in app) with `expires_at` and `grace_days`; verify locally; app reminds before expiry. Never read the system date alone: compare with last-seen server time too.
- Gate (auth/billing): any change to license enforcement, device limits, or token format needs owner approval.

## 7. Printing

- Thermal receipts: ESC/POS. Library candidate: node-thermal-printer (Epson, Star, Custom and others; tcp, system printer, or port; has an Arabic codepage option). Verify with the owner's actual printer model; ESC/POS dialects differ.
- Arabic/RTL on thermal printers is the risky part: printer codepages are limited and shaping is poor. Default: render the receipt to a bitmap (HTML -> canvas -> raster ESC/POS image) for ar; use text mode for fr/en. Decide per printer model after a physical test (UNVERIFIED which printer).
- Windows transports: LAN `tcp://ip:9100` (most reliable), USB via the Windows print spooler with raw mode, or serial. Do not depend on native printer modules that need rebuilds unless proven on the packaged build.
- A4/PDF: `webContents.printToPDF` (returns a Buffer; header/footer templates supported) and `webContents.print({silent, deviceName, pageSize, printBackground})`. Get printers with `getPrintersAsync()`; `deviceName` is the system name, not the display name. Print from a hidden window loading a local template, with CSP applied.
- Print jobs are queued in the local DB (`print_jobs`) so a printer-off event does not lose the receipt; "reprint" is audited (who, when, copy number marked on the paper).
- Cash drawer: ESC/POS pulse command through the printer; log each open with user + reason.
- Tests: golden-file test of the generated ESC/POS byte stream per receipt type and per locale.

## 8. Packaging, signing, update

electron-builder baseline (names to verify in the installed version's schema):
- `appId` stable forever (changing it breaks updates). `productName`, `win.target: nsis`, `nsis.oneClick: false` or true per owner (default true, per-user install, no admin needed -> smooth silent updates), `asar: true`, `asarUnpack` for the native module, `npmRebuild`.
- Fuses flipped in an `afterPack` hook with `@electron/fuses`.
- Signing: set `win.azureSignOptions` (endpoint, codeSigningAccountName, certificateProfileName, publisherName must equal the certificate CN) with Entra service-principal env vars in CI; do not combine with signtoolOptions. Never store creds in the repo.
  - Azure Artifact Signing (formerly Trusted Signing): Basic 9.99 USD/month (5,000 signatures); needs a paid Azure subscription (no free/trial). Public Trust for organizations in the USA, Canada, EU, UK, Australia, New Zealand, Japan, South Korea, Singapore, Switzerland, Norway and Israel; individuals only USA/Canada. The owner's US LLC is the applicant (US address, LLC website and domain email), not the Morocco address. Identity validation takes 1-20 business days; documents must be issued within the last 12 months. Third parties reported (2025) a minimum 3-year business history for organizations; the current official pages do not state it (UNVERIFIED). If validation fails, fall back to OV on a cloud HSM.
  - OV/EV from a CA: private key must be on HSM/token since June 2023; use a cloud-HSM service for CI. EV no longer gives instant SmartScreen trust (since 2024); do not pay the EV premium for that reason alone.
  - SmartScreen: Microsoft's Artifact Signing FAQ says prompts stop once the file hash has enough download history. Keep the same signing identity, expect warnings on each new release at first, and warn pilot customers.
  - Conflict: the Electron docs page still describes EV as mandatory (2023 wording) while the Microsoft page says EV no longer bypasses SmartScreen. Follow Microsoft's page; both agree on HSM storage.
- Always sign installer AND the app exe/dll inside; timestamp every signature (RFC3161) so signatures outlive the cert.
- Update (electron-updater, NSIS):
  - Provider: generic HTTPS on the owner's CloudPanel VPS behind Cloudflare, or GitHub Releases (private repo needs a token - do not ship a token in the app; use generic).
  - Upload order: installer first, `latest.yml` last, so clients never see a manifest pointing at a missing file.
  - Channels: `latest` (stable) and `beta` for pilot tenants; setting per device from the server, not by user. Staged rollout: set `stagingPercentage` (0-100) in the channel yml and raise it over days. Bad release: ship a higher version number (clients do not downgrade by default).
  - Install timing: default installs on quit; for a POS never interrupt a sale. Update only when no open transaction and the till is closed; show "update ready, restart at end of day".
  - DB migrations run on the next start after update; backup first (section 4). Server must stay compatible with the previous 2 desktop versions: send `X-App-Version`, return 426 `upgrade_required` only with a published minimum version and a grace window.
  - Never auto-update during activation of a new shift. Log every update event.
- Per-release artifacts: installer, `latest.yml`, blockmap, SHA-256 list, release notes in ar/fr/en.

## 9. Logs and crashes

- Logging: `electron-log` or pino to `userData/logs`, rotating (e.g. 10 MB x 5), JSON lines, levels, correlation ids for sync batches. Redact tokens, keys, card data, customer PII. Never log payloads of sales in full at info level.
- Crashes: `crashReporter.start({uploadToServer:false})` keeps dumps locally in `app.getPath('crashDumps')`; upload only to an owner-approved endpoint. Hosted option: `@sentry/electron` (setup and scrubbing in `operations-monitoring.md` sec. 3; adding it needs a processor-register row and the privacy gate in `compliance-payments.md` sec. 4). Handle `uncaughtException` and `unhandledRejection` in main: log, show a recovery dialog, never swallow.
- "Export diagnostics" menu item: zips logs + app version + sync state (no DB, no keys) for support.
- Renderer crash (`render-process-gone`): reload the window and restore draft cart from the local DB.
- Watchdog: if the DB is locked/corrupt on start, offer restore from the last automatic backup (daily and before migration, keep 7).

## 10. Testing

- Unit (Vitest): domain logic, money math, outbox state machine, conflict rules, ESC/POS builders, migrations (apply all on empty DB; apply last migration on previous schema fixture).
- Integration: sync engine against a real Laravel test server on MySQL 8.4 (project's real engine) with the idempotency and per-item ACK contract; run the same fixtures on both sides.
- E2E: Playwright with `_electron.launch({ args: ['out/main/index.js'] })`. Playwright's Electron support is experimental, needs the `nodeCliInspect` fuse not false, cannot see native dialogs (stub dialog calls in main behind a test flag). Run against the built app (`electron-vite build`), then once against the installed NSIS build in CI.
- Matrix for release: ar RTL, fr, en; 1366x768 and 1920x1080; offline start; offline -> online reconnect; low disk; clock skew; printer off.
- Security tests: attempt navigation to external URL, `window.open`, IPC call with bad payload, IPC call from a wrong frame origin, `require` in devtools of production build (must fail).

## 11. Windows specifics

- Dev machine is Windows: use `python`, `npm`, PowerShell paths; long path support on; keep the repo path short (native builds).
- Native build needs Visual Studio Build Tools (C++ workload) and Python; prefer prebuilt binaries; check on a clean VM.
- Data location: `app.getPath('userData')` (per-user `%APPDATA%`). Never write into Program Files. Back up by file copy only after WAL checkpoint.
- Antivirus: unsigned or new binaries get quarantined; whitelist guidance for customers; sign everything.
- Auto-start option (`app.setLoginItemSettings`), kiosk/fullscreen option for POS, disable DevTools in production, disable zoom shortcuts if they break layouts.
- Minimum OS: Electron 23+ runs only on Windows 10 and later (Electron blog, Windows 7-8.1 deprecation notice). Win 7/8.1 tills cannot run a supported Electron major; say so before a customer is promised support.
- Scanner (HID keyboard wedge) input: listen at window level, ignore when a text input has focus unless it is the scan field; test with ar keyboard layout active.
- Time zone and DST: store UTC, display Africa/Casablanca (or tenant zone). Casablanca has a special Ramadan offset - never hardcode offsets.

## 12. Release checklist

- [ ] Version bumped, release notes ar/fr/en, `appId` unchanged.
- [ ] Electron on a supported major; `npm audit` reviewed; lockfile committed.
- [ ] Unit + integration + Playwright smoke green on the packaged build.
- [ ] Security checklist (section 2) re-run; fuses verified on the built exe (`@electron/fuses` read mode).
- [ ] DB migration tested from the oldest supported version fixture; backup-before-migrate works; downgrade guard works.
- [ ] Sync contract tested against the server version that will be live; server deployed first (backward compatible), desktop second.
- [ ] Installer and inner exe signed and timestamped; signature verified (`signtool verify /pa`).
- [ ] Clean-VM install, first-run activation, offline sale, reconnect sync, print receipt (ar + fr), update from previous version.
- [ ] Upload installer, blockmap, then `latest.yml`; start with `stagingPercentage` 10 or beta channel.
- [ ] Monitor crash/sync error rate 24-48 h before raising the percentage.
- [ ] Rollback plan: higher fixed version ready; server minimum-version flag untouched.
- [ ] Handoff entry: version, channel, percentage, known issues.

## Red flags

- `nodeIntegration: true`, `contextIsolation: false`, `sandbox: false`, `webSecurity: false`, or `--no-sandbox` anywhere.
- `ipcRenderer` or a generic `invoke(channel)` exposed to the renderer; IPC handlers without sender and payload validation.
- Loading a remote URL in the POS window; `file://` in production; `shell.openExternal` with unchecked input.
- DB key, activation secret, or API token in the repo, bundle, logs, or plain file.
- Device clock used to order or resolve conflicts; outbox row removed on HTTP 200 without per-item ACK; retries without a stable `client_uuid`; sync endpoints or statuses that differ from `multi-surface-architecture.md` sec. 10.
- Sale and outbox written in two separate transactions; stock quantity synced as a number.
- Auto-update that restarts the app during a sale; `latest.yml` uploaded before the installer; changed `appId`.
- Unsigned installer, or signing keys in CI logs; EV purchased only to skip SmartScreen.
- Tested only in dev mode (`npm run dev`), not on the packaged signed build; Playwright run against a build with fuses that block it, or release shipped with that test build.
- Native module not unpacked from asar; works on dev PC, crashes on clean install.
- Arabic receipt printed with a wrong codepage and never tested on the real printer.

## How project-brain uses this

- Planning (`planning-playbook.md`, `multi-surface-architecture.md`): the POS is a separate surface; add sections 5, 6, 8 as spec headings (sync contract, device binding, release) and put legal numbering, offline limit and key-escrow decisions in `[ORPHANS & PENDING]` as owner gates.
- Building: pb-implementer loads sections 2-4 for any main/preload/DB task and section 5 for any sync task; run `code_guard.py find` before adding an IPC channel or table; update `src/shared/ipc.ts` first.
- Review: pb-security-reviewer runs section 2 checklist and the section 10 security tests; pb-verifier requires evidence on the packaged build, real MySQL for sync, and an ar/fr RTL check before "done".
- Gates (SKILL.md section 5): encryption key custody, license/device enforcement, auto-update policy, signing identity, and tax receipt numbering are owner gates.
- Release: use section 12 as the completion checklist; log shipped version, channel and rollout percentage in HANDOFF.

## Sources

- https://www.electronjs.org/docs/latest/tutorial/security
- https://www.electronjs.org/docs/latest/tutorial/context-isolation
- https://www.electronjs.org/docs/latest/tutorial/fuses
- https://www.electronjs.org/docs/latest/api/safe-storage
- https://www.electronjs.org/docs/latest/api/web-contents
- https://www.electronjs.org/docs/latest/api/crash-reporter
- https://www.electronjs.org/docs/latest/tutorial/updates
- https://www.electronjs.org/docs/latest/tutorial/code-signing
- https://www.electronjs.org/docs/latest/tutorial/automated-testing
- https://www.electronjs.org/docs/latest/tutorial/electron-timelines
- https://playwright.dev/docs/api/class-electron
- https://www.electron.build/docs/features/auto-update
- https://www.electron.build/docs/features/code-signing/code-signing-win
- https://www.electronforge.io/config/plugins/vite
- https://electron-vite.org/guide/
- https://www.sqlite.org/wal.html
- https://github.com/m4heshd/better-sqlite3-multiple-ciphers
- https://github.com/Klemen1337/node-thermal-printer
- https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options
- https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart
- https://learn.microsoft.com/en-us/azure/artifact-signing/faq
- https://www.electronjs.org/blog/windows-7-to-8-1-deprecation-notice
