# Mobile (Flutter) - rules for an AI coding agent

Scope: Flutter apps for the owner's multi-tenant SaaS (Laravel API, Sanctum). Android first (Windows dev machine, Google Play). Backend, auth and API contract rules live in `api-design.md`, `backend-architecture.md`, `security-protocol.md`; surface split in `multi-surface-architecture.md`; UI quality and the owner's UI bar in `frontend-system-design.md`; payments/privacy in `compliance-payments.md`; crash/uptime monitoring in `operations-monitoring.md`. This file covers only the Flutter-specific parts. Versions: read `pubspec.lock` and `flutter --version`; never trust this file or memory (see `research-policy.md`).

## 1. Verified facts (checked 2026-10-03)

| Fact | Value | Source |
|---|---|---|
| Flutter stable | 3.47.6 (Dart 3.13.5), released 2026-10-01; quarterly cadence | storage.googleapis.com/flutter_infra_release/releases/releases_windows.json ; https://docs.flutter.dev/install/archive |
| Play target API, new apps/updates | API 36 (Android 16) from 2026-08-31; extension to 2026-11-01 | https://developer.android.com/google/play/requirements/target-sdk |
| Play target API, existing apps | API 35 or higher, else hidden from new users on newer Android | same |
| Play Billing Library | v9 latest; v7 closes 2026-08-31 (extension 2026-11-01); v8 closes 2027-08-31 | https://developer.android.com/google/play/billing/deprecation-faq |
| 16 KB page size | apps targeting Android 15+ (API 35) must support it on 64-bit devices; first enforced 2025-11-01 (extension to 2026-05-31); the official page now says updates without it cannot be released from 2027-02-01. Tools: AGP 8.5.1+, NDK r28+ | https://developer.android.com/guide/practices/page-sizes (fetched 2026-10-03; earlier dates from secondary sources) |
| New personal accounts | personal accounts created after 2023-11-13 need a closed test with 12+ testers opted in for 14 continuous days before production; the article does not cover organization accounts (exemption UNVERIFIED) | https://support.google.com/googleplay/android-developer/answer/14151465 |
| Organization account | needs D-U-N-S number plus org documents | https://support.google.com/googleplay/android-developer/answer/10841920 |
| Riverpod | flutter_riverpod 3.x (latest 3.4.3 on pub.dev at check time) | https://pub.dev/packages/flutter_riverpod (read pubspec.lock for the project's version) |
| Account deletion | apps that allow account creation must offer in-app deletion and a web link to request deletion, declared in Data safety | https://support.google.com/googleplay/android-developer/answer/13327111 |
| `in_app_purchase_android` | 0.5.0+ uses Play Billing Library 8.0.0 | https://pub.dev/packages/in_app_purchase_android/changelog |

Rule: the target API number changes every August. Before each release read the Play target-sdk page again; set `targetSdk` to the current requirement, not the old one.

## 2. Project structure (feature-first)

```
lib/
  main_dev.dart  main_prod.dart  app.dart      # flavor entrypoints, MaterialApp.router
  core/        # api client, auth, storage, theme, l10n, router, errors, logging
  shared/      # widgets used by 2+ features, formatters
  features/<feature>/
    data/          # repository impl, DTOs (generated), local cache
    domain/        # entities, repository interface (only if logic exists)
    application/   # Riverpod notifiers/providers
    presentation/  # screens, widgets
test/  integration_test/  tool/  l10n/
```

- A feature never imports another feature's `presentation`. Cross-feature needs go through `core` or a shared provider.
- Run `code_guard.py find <Name>` before creating any widget, provider or repository (operating-protocol §3).
- Limits from operating-protocol: file <= 300 lines, function <= 40 lines. Split widgets into small classes, not into helper methods returning widgets.

## 3. State management - default: Riverpod (flutter_riverpod)

Decision: use Riverpod 3.x for every new app. Justification: compile-safe, no BuildContext dependency, built-in async/caching (`AsyncValue`), easy overrides in tests, one pattern for DI and state, large community. Re-verify the version in pubspec.lock. Record as `delegated, open to reversal` in DECISIONS.md.

| Situation | Use |
|---|---|
| Server data | `AsyncNotifier` / `FutureProvider` wrapping a repository |
| Form / UI state | `Notifier` or local `StatefulWidget` (do not globalize ephemeral state) |
| DI (Dio, storage, repos) | plain `Provider`, overridden in tests |
| Existing app already on Bloc/Provider | keep it; do not migrate unasked (scope rule) |

Rules: no business logic in widgets; providers expose immutable state; never call `ref.read` in `build` for reactive data; dispose resources via `ref.onDispose`. Do not mix a second state library.

## 4. API client generated from OpenAPI

- Single source of truth: the Laravel OpenAPI file (`api-design.md`). Mobile never hand-writes DTOs for endpoints that exist in the spec.
- Generator: `openapi-generator` with the `dart-dio` generator (default choice) or an equivalent that emits typed models + Dio client. Pin the generator version in `tool/` and commit generated code under `lib/core/api/generated/` (or generate in CI; pick one, document it). UNVERIFIED: generator option names, check the generator docs at generation time.
- Wrap the generated client in repositories. UI never touches the generated client directly.
- Dio interceptors: auth header, `Accept-Language` (current locale), `X-Request-Id`, retry only idempotent GET, 401 -> clear session and route to login, 422 -> map field errors to form fields.
- Send `Idempotency-Key` on sensitive POSTs (payments, order creation) per `api-design.md`.

## 5. Auth: Sanctum tokens + secure storage

- Login endpoint returns a personal access token (mobile token flow, not the cookie SPA flow): `POST /v1/auth/token` with `device_name` + `device_id`, sliding refresh and revoke-on-logout exactly as `api-design.md` sec. 14 defines. Name tokens per device; abilities per scope.
- Store the token only in `flutter_secure_storage` (Android Keystore backed). Never in `SharedPreferences`, logs, crash reports or analytics.
- Logout: call revoke endpoint, delete storage, clear caches, clear Dio state, unregister the push token.
- Tenant context: send the active tenant explicitly (header or path) as the API defines; never infer it client-side from a cached object.
- Android: set `android:allowBackup="false"` or exclude the secure storage files from backup (otherwise restored tokens break).
- Release builds: enable code shrinking/obfuscation (`--obfuscate --split-debug-info`), keep symbols for crash reports. Obfuscation is not secrecy: no secrets in the app bundle.

## 6. Offline cache

Default is online-first with a read cache. Full offline-write sync is a gate-level design (conflicts, ids, queue); do not add it unless the PRD says so.

| Need | Choice |
|---|---|
| Small prefs (locale, theme) | `shared_preferences` |
| Cached lists/entities | `drift` (SQLite) with a table per aggregate; or Isar-like only if already used |
| Secrets | secure storage only |
| Images | `cached_network_image` |

Rules: cache keyed by tenant id + user id; wipe on logout and tenant switch; every cached row has `fetched_at`; show stale data with a visible "offline" state; never cache money balances as authoritative. Writes while offline: disable the action with a clear message unless the PRD defines a queue. Use `connectivity_plus` for hints only; the real test is the request result.

## 7. i18n: ar / fr / en + RTL

- Packages: `flutter_localizations` (SDK), `intl`. Config `l10n.yaml` with `arb-dir: lib/l10n`, `template-arb-file: app_en.arb`, no `synthetic-package` key (the option was removed and current Flutter warns about it; generated files land in the source tree and are committed; import `lib/l10n/app_localizations.dart`, never `package:flutter_gen`). Files: `app_en.arb`, `app_fr.arb`, `app_ar.arb`. Generation via `flutter gen-l10n` (https://docs.flutter.dev/ui/internationalization).
- Zero hard-coded user strings. Every key exists in all three ARB files (CI check: key sets equal).
- Plurals and placeholders use ICU syntax in ARB; Arabic has 6 plural forms (zero, one, two, few, many, other): supply all of them.
- Layout: use `EdgeInsetsDirectional`, `AlignmentDirectional`, `start/end`, never `left/right`. Icons that imply direction (back, chevron, send) must mirror; use `matchTextDirection` or `Directionality`-aware icons.
- Numbers/dates: `intl` formatters with the active locale; one digit policy across all surfaces (`frontend-system-design.md` sec. 2). Default: Latin digits (0-9) in every locale, recorded in DECISIONS.md as `delegated, open to reversal`; do not stop to ask.
- Locale source order: user setting -> device locale if supported -> `fr`. Persist the choice; send it as `Accept-Language`.
- Language picker: flag + native language name for each locale (owner bar; `frontend-system-design.md` sec. 15 item 32). Use the Arabic font the owner supplies, bundled as an asset.
- Test: golden tests per locale (en, fr, ar) for each core screen; run text-scale 1.0 and 1.5.

## 8. Theming from design tokens

- Tokens (color, type scale, spacing, radius, elevation) come from the project design system doc. One `AppTokens` class (a `ThemeExtension`) holds them; `ThemeData` is built from it for light and dark.
- Use Material 3 (`useMaterial3: true`) with a custom `ColorScheme`; no raw `Color(0x...)` or magic numbers in widgets (grep check).
- Owner UI bar applies on mobile (`frontend-system-design.md`, `owner-profile.md`): Apple HIG feel, one icon family, status color tokens (red/orange/yellow/green/blue), smooth area/line charts and bento KPI cards, no default-Material look, no disabled placeholders for unbuilt features.

## 9. Testing

| Layer | Tool | Rule |
|---|---|---|
| Unit | `flutter_test`, `mocktail` | repositories, notifiers, formatters, mappers; failure paths included |
| Widget | `flutter_test` + `ProviderScope(overrides)` | each screen: loading, data, empty, error states |
| Golden | `matchesGoldenFile` (or `golden_toolkit`-style helper) | per core screen x locale (ar RTL, fr, en) x text scale; generate on one OS only (CI Linux) to avoid font drift |
| Integration | `integration_test` on emulator | login, one critical flow per feature, locale switch; real staging API with seeded tenant |

- Commands: `flutter analyze` (zero issues), `dart format --set-exit-if-changed .`, `flutter test`, `flutter test integration_test -d <device>`.
- Backend for integration tests: a staging Laravel on MySQL 8.4 with seed data, never mocks of the real contract in integration runs.
- Report passed / failed / not run (SKILL.md commitment 7). Reading code is not evidence.

## 10. Flavors dev / prod

- Android `productFlavors` `dev` and `prod` in `android/app/build.gradle(.kts)`: distinct `applicationId` (`.dev` suffix), app name, icon badge. Dart entrypoints `main_dev.dart`, `main_prod.dart` (or `--dart-define-from-file`).
- Config per flavor: API base URL, Sentry/Firebase project, Play Billing product ids (test vs real). Non-secret only; secrets never in `--dart-define` of release builds.
- Run: `flutter run --flavor dev -t lib/main_dev.dart`; build: `flutter build appbundle --flavor prod -t lib/main_prod.dart --release`.

## 11. Release to Google Play

Checklist for the first release:
1. Account: Organization account owned by the owner's company (see `owner-profile.md`), D-U-N-S number, org documents, payments profile. Do not use a personal account (it triggers the 12-testers/14-days rule and mixes identity). Account creation and payment are owner actions (prohibited for the agent).
2. App: unique `applicationId` (never changes after publish), app name, icon, feature graphic, screenshots per locale (ar/fr/en), privacy policy URL, Data safety form, content rating, target audience, ads declaration.
3. Signing: use Play App Signing. Create an upload keystore once (`keytool`), store it and passwords in the owner's password manager and offline backup; never commit it; `key.properties` is git-ignored. Losing the upload key is recoverable via Play support but slow.
4. Build: `flutter build appbundle` (AAB, not APK). Increment `version: x.y.z+build` in pubspec (build number strictly increasing).
5. `targetSdk` = current Play requirement (section 1); 16 KB page-size alignment verified (build with current AGP/NDK; AAB: `bundletool dump config --bundle=<app>.aab | grep alignment` must show `PAGE_ALIGNMENT_16K`; APK: `zipalign -c -P 16 -v 4 <app>.apk`).
6. Track order: Internal testing (up to 100 testers, fast) -> Closed -> Production staged rollout (start 5-10 percent, watch crash-free rate, then raise).
7. Upload the obfuscation mapping/debug symbols to the crash reporter and Play Console.
8. Permissions: request only what a feature uses, at the moment of use, with a rationale string in 3 languages. Remove unused permissions from the merged manifest (check `build/.../AndroidManifest.xml`).
9. Policy: account deletion path in-app and a web link to request deletion if accounts can be created (Play policy, section 1); declare it in Data safety. Do not collect data not declared in Data safety.

Release is an owner gate (SKILL.md section 5): prepare everything, ask before pressing "promote to production".

## 12. In-app purchases (Google Play Billing) with server verification

When it applies: Play policy requires Google Play Billing for digital goods and subscriptions consumed in the app. Physical goods and services (for example POS hardware, B2B services paid outside) are different; decide per product and record it. Billing, pricing and legal terms are an owner gate. Policy text: verify at https://support.google.com/googleplay/android-developer/answer/9858738 at design time (UNVERIFIED here).

Rules:
- Package: `in_app_purchase` (official plugin, wraps Play Billing). Confirm in pubspec.lock that `in_app_purchase_android` is 0.5.0+ (Billing Library 8; v7 is rejected for new apps and updates after 2026-08-31, extension 2026-11-01; v9 is latest). A plugin that lags: pin a newer one or override the Android dependency.
- Flow: app shows product (from Play query) -> user buys -> app sends `purchaseToken` + `productId` to the Laravel API -> server verifies with the Google Play Developer API (`purchases.subscriptionsv2.get` for subscriptions, `purchases.products.get` for one-time) using a service account -> server grants the entitlement -> server calls acknowledge (or consume) -> app refreshes entitlement from the API. The client never grants entitlement alone.
- Unacknowledged purchases are refunded by Google after about 3 days: acknowledge only after the server has stored the entitlement.
- Idempotent grant keyed by the purchase token / order id; store `purchaseToken`, `orderId`, state, expiry, tenant id.
- Real-time developer notifications (RTDN via Pub/Sub) are the source for renewals, cancellations, refunds, grace period. Add a webhook endpoint; verify the message and re-fetch state from the API; never trust the notification body alone.
- Prefer `subscriptionsv2` (older `subscriptions` methods are deprecated): https://developer.android.com/google/play/billing/play-developer-apis-deprecations
- Tenancy: tie the purchase to the tenant/account at purchase time with an obfuscated account id sent in the billing flow; reject a token already linked to another tenant.
- Test with license testers and the internal track; Stripe is not used for Play-distributed digital goods inside the app (Stripe stays for web checkout, subject to policy review, UNVERIFIED).
- Server keys (service account JSON) live in backend secrets only, never in the app.

## 13. Push notifications

- Default: `firebase_messaging` (FCM). Backend sends with the FCM HTTP v1 API (OAuth 2.0 service account); the legacy HTTP/XMPP APIs were shut down in July 2024.
- Android 13+ (API 33) needs the runtime `POST_NOTIFICATIONS` permission: ask in context, not at launch; handle denial.
- Store the FCM token on the server per device + user + tenant; refresh on `onTokenRefresh`; delete on logout.
- Payload: data + notification, localized by the server using the user's locale; deep link via `go_router`. Create notification channels (one per category) so users can mute categories.
- Background handler must be a top-level function; test the three states (foreground, background, terminated).

## 14. Crash reporting and logging

- Default: Sentry (`sentry_flutter` + `sentry_dart_plugin`), the same tracker as web and desktop (`operations-monitoring.md` sec. 3). Keep Crashlytics only if the project already uses it; never run both. Wire `FlutterError.onError` and `PlatformDispatcher.instance.onError` (`SentryFlutter.init` does this); `runZonedGuarded` is no longer the primary path.
- Enabled in prod flavor only. Attach: app version, flavor, locale, tenant id (opaque id, not name). Scrub tokens, emails, phone numbers, card data.
- Upload symbols/mapping for obfuscated builds on every release.

## 15. Accessibility

Checklist per screen (verify on emulator with TalkBack and font scale 1.5-2.0):
- Every interactive element has a `Semantics` label (icon buttons need `tooltip` or `semanticLabel`) in all 3 languages.
- Touch target >= 48x48 dp (Material; also satisfies the 44 pt HIG bar in `frontend-system-design.md` sec. 3); contrast >= 4.5:1 text, 3:1 large text/icons.
- Test with `tester.ensureSemantics()` and `meetsGuideline(androidTapTargetGuideline)` / `labeledTapTargetGuideline` in widget tests.

## 16. Performance

- Measure in profile mode on a real low-end device (never debug, never emulator only). Tools: Flutter DevTools, `flutter run --profile`.
- Targets (defaults): cold start < 2 s on a mid device, 60 fps scroll without jank, no frame over 16 ms in lists.
- Lists: `ListView.builder`, `const` constructors, stable keys, paginate (cursor) from the API, never load all rows.
- Images: sized to display, cached, webp/avif from the backend; decode with `cacheWidth`.
- Rebuilds: use `select` on providers, split widgets, avoid `setState` high in the tree. No heavy work on the UI isolate: use `compute`/isolates for large JSON.

## 17. Pre-release checklist (all must be true)

- [ ] `pubspec.lock` checked: Flutter/Dart versions, Billing Library >= v8, no abandoned plugins
- [ ] `flutter analyze` 0 issues; `dart format` clean; `code_guard.py scan --changed` exit 0
- [ ] Unit, widget, golden (ar/fr/en) and integration tests pass; results reported
- [ ] OpenAPI client regenerated, no diff; API base URL is production in prod flavor
- [ ] ARB key sets equal in ar/fr/en; RTL screenshots reviewed for every core screen
- [ ] `targetSdk` matches current Play rule; 16 KB alignment checked; permissions minimal
- [ ] Release signed via Play App Signing upload key; version code incremented
- [ ] Obfuscation symbols uploaded; crash reporting verified with a test crash on the internal track
- [ ] Billing flow tested with license tester: buy, verify on server, acknowledge, refund, restore
- [ ] Push tested in 3 app states; token cleared on logout
- [ ] Data safety form and privacy policy match real data use
- [ ] Internal track install on a real low-end device; staged rollout plan written
- [ ] DECISIONS.md, HANDOFF.md, change log updated; owner approved production promotion

## 18. Replacing pb-ui-auditor on mobile

`pb-ui-auditor` drives a real browser; it cannot see an Android app. On mobile use this loop instead (run by `pb-verifier` or the main agent):
1. Emulators: one small phone (360x640 dp), one standard (411x891), one tablet if supported; Android API 36 image plus one older (API 29-31).
2. Screenshot script: an `integration_test` that walks every route in each locale (ar, fr, en) and dark/light, calling `binding.takePictures` / `IntegrationTestWidgetsFlutterBinding.takeScreenshot` into `build/audit/<locale>/<screen>.png`. Seed data from the staging fixture, including empty and error states.
3. Golden diffs for stable components; the agent reads the PNGs (Read tool shows images) and applies the anti-slop checklist and owner UI bar from `frontend-system-design.md`: contrast, spacing, one icon family, status colors, no duplicate titles, RTL mirroring, text overflow at scale 1.5.
4. Semantics check via the guideline matchers (section 15) and a manual TalkBack pass noted as "not run" if not performed.
5. Report per screen: pass/fail, evidence file path, and what was not checked (real device, iOS).

## Red flags

- Token, secret or service-account key stored in `SharedPreferences`, assets, `--dart-define` or logs.
- Entitlement granted on the client without server verification, or purchase acknowledged before the server stored it.
- Billing Library below v8 or `targetSdk` below the current Play requirement at upload time.
- Hand-written DTOs for an endpoint that exists in the OpenAPI spec.
- Hard-coded strings, `left/right` paddings, or missing keys in one ARB file.
- Cached data not scoped by tenant/user or surviving logout.
- A `double` used for money; a second state-management library added unasked.
- Debug-mode performance claims; "done" without emulator or test evidence.
- Personal Play account used instead of the LLC Organization account; keystore committed to git.
- Version numbers in this file used instead of `pubspec.lock` / official pages.

## How project-brain uses this

- Loaded for role `frontend`/`surfaces`/`implement` when the surface is mobile (Flutter), together with `api-design.md` (contract), `security-protocol.md` (auth/money) and `multi-surface-architecture.md` (cross-surface checks).
- Planning: map items for mobile cite sections of this file as criteria (e.g. "ARB equal in 3 locales", "Billing verified server-side").
- Verification: `pb-verifier` runs section 9 commands and the section 18 emulator loop in place of `pb-ui-auditor`; the report states passed / failed / not run.
- Gates: Play release, billing/pricing, auth changes and signing keys are owner gates (SKILL.md section 5); everything else is decided and logged as `delegated, open to reversal`.
- Re-verify section 1 facts before each release (research-policy.md); update this file when sources change.
