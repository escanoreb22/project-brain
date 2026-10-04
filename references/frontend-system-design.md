# Frontend system design (anti-slop, owner bar)

Single owner of design rules (the former `frontend-system-design.md` is merged here); also read `owner-profile.md`. Stack: React + TS + Inertia SSR or SPA, Tailwind, shadcn/ui-style primitives, ar/fr/en with RTL. Sources: (Wathan & Schoger, Refactoring UI), (Pickering & Bell, Every Layout), (Pickering, Inclusive Components), (Yablonski, Laws of UX), (Krug, Don't Make Me Think), (Norman, Design of Everyday Things), Apple HIG https://developer.apple.com/design/human-interface-guidelines/, WCAG 2.2 https://www.w3.org/TR/WCAG22/, web.dev Core Web Vitals, Material 3 motion https://m3.material.io/styles/motion.

## Designer role and inputs
- Design task completion, comprehension, recovery, trust, and accessibility, not decoration.
- Inputs to read first: audience, devices, platform conventions, content types, roles/permissions, languages and direction, brand assets, owner screenshots, accessibility target, business goals, technical constraints, explicit likes/dislikes. Competitor work is evidence, not a template to copy.
- Coverage: information architecture, navigation, search/filter, hierarchy, deep links, back behavior and role visibility; every screen and state (sec. 5, plus first-run, invalid, partial, destructive confirmation, small screen, keyboard, RTL, text scaling); task flows with interruption, save/resume, undo, error prevention, recovery, support and deletion; semantic tokens for color, type, spacing, radius, elevation, motion, breakpoints and iconography (sec. 1); components with anatomy, variants, states, content limits, validation, keyboard, focus and semantics; responsive, localization expansion, reduced motion, contrast, touch targets and assistive technology.
- Accessibility target: WCAG 2.2 AA for web unless the owner approves another level; for native apps adapt the applicable principles and platform guidance.

## Owner's UI bar (from repeated corrections)

- Reference system: Apple HIG. One professional icon family, with semantic status colors (red, orange, yellow, green, blue) — not only green/blue/gray/white.
- Avoid a flat white page with one dark brand green for sidebars/footers/sliders; check contrast and the overall palette before shipping.
- Language menus show a flag next to each language. Use the Arabic font the owner supplies; check every hero/menu in RTL.
- Data: smooth curves/area charts by default, bento KPI cards (big number + sparkline + small tiles), never bare tables of numbers where a trend matters.
- Motion: only when asked or when it serves the flow; smooth frame rate; compact size; starts when the section enters the viewport, stops when it leaves; respect reduced motion.
- No duplicated titles, no two buttons where one action suffices, no disabled placeholders, no fake data the product does not have.
- When the owner sends a mockup or design handoff, it becomes the reference: apply its tokens exactly and record it in DECISIONS.md.
- Change only what was asked. A request for animation is not a request for new sections.
- Done means checked in a real browser at desktop and phone widths, in every supported language, with every form submitted using valid data.

## 1. Tokens: three layers
- Default: primitive -> semantic -> component. Primitives hold raw values (`--blue-600`). Semantic holds meaning (`--color-action`, `--color-danger-bg`, `--surface-1`). Components consume semantic only (`--btn-bg: var(--color-action)`).
- Rule: no hex, px or ms literals in components. Grep `#[0-9a-f]{3,8}` in component folders (`resources/js/components`, or `resources/js/*/components` and `shared/ui`) must return nothing outside the token files.
- Light/dark: swap the semantic layer only, via `[data-theme=dark]` or `.dark`. Ship dark only if the PRD asks; do not half-build it.
- Tailwind v4: declare in `@theme { --color-action: ...; }`; v3: map in `tailwind.config` to CSS variables. Record which in DESIGN_SYSTEM.md.
- RTL: logical utilities only (`ms-/me-/ps-/pe-/start-/end-/text-start`), never `ml-/pr-/left-/text-left`. Mirror directional icons (chevrons, arrows, back) with `rtl:-scale-x-100`. Never mirror logos, clocks, media controls, numerals. Charts: keep the time axis left-to-right by default, decide per chart and record it.
- Set `<html lang dir>` from the locale server-side (SSR) so first paint is correct.

## 2. Type, Arabic, spacing
- Scale: 12/14/16/18/20/24/30/36/48 (ratio about 1.2-1.25) (Refactoring UI, typography chapter). Body 16 on web, 14 only in dense tables. Max 2 families, 3-4 weights.
- Pairing default: one UI sans (Latin) + one Arabic family with matching x-height. Candidates: IBM Plex Sans Arabic, Noto Sans Arabic, Cairo, Tajawal. An owner-supplied font wins; record it in DECISIONS.md. Self-host woff2, `font-display: swap`, preload only the weight used above the fold, split by `unicode-range` (ar/latin).
- Arabic needs more vertical room: body line-height 1.7-1.8 (Latin 1.5), headings 1.3-1.4. This is a rule of thumb: check visually (clipped diacritics or descenders = too tight). Arabic often reads smaller: add 1-2px or compare x-heights.
- Never letter-space or uppercase Arabic; no italics for Arabic. Numerals: choose Western (0-9) or Arabic-Indic per locale, record in DECISIONS.md, apply uniformly via `Intl.NumberFormat(locale, ...)`. Money, IDs, phones stay consistent on a screen.
- Spacing: 4px base; scale 4/8/12/16/24/32/48/64. Related items closer than unrelated (proximity, Laws of UX). Layout primitives (Every Layout): Stack, Cluster, Sidebar, Switcher, Grid, Center. Build these 5-6 small components instead of ad-hoc flex hacks.
- Grid: 12 columns desktop, public content max-width 1200-1280, admin content fluid with 24px gutter, 16px side gutter at 390.

## 3. Color and contrast
- Build a neutral ramp (9-11 steps, slightly tinted toward brand), 1 brand ramp, 5 status ramps: danger red, warning orange, caution yellow, success green, info blue (owner bar). Each status ships `fg`, `bg-subtle`, `border`, `solid` tokens.
- WCAG 2.2 AA (verified at w3.org): text 4.5:1 (large text 3:1) (SC 1.4.3); UI components and graphical objects 3:1 (SC 1.4.11); pointer targets at least 24x24 CSS px or spaced (SC 2.5.8); focused element not entirely hidden by sticky content (SC 2.4.11). Owner touch target: 44x44 (Apple HIG) on mobile and POS.
- Check pairs mechanically (script or axe) in every shipped theme. Placeholder, disabled-but-informative and table secondary text are the usual 3:1 failures.
- Status is never color alone: icon + label. Charts: color + marker/label, max 5-6 series.
- Default: neutral surfaces + one brand accent for primary actions and active nav. Do not flood sidebars/footers with brand color.

## 4. Icons and component library
- One family only (Lucide is the shadcn default; Phosphor or Tabler acceptable). Fixed stroke width, sizes 16/20/24. Exceptions: brand/payment logos and flags. Flags beside language names as SVG, not emoji (emoji flags fail on Windows).
- Structure (single-surface app; with several surfaces the same split lives in `shared/ui` and `<surface>/components`, see `multi-surface-architecture.md` sec. 7; an existing repo layout wins): `components/ui/*` = primitives (Button, Input, Select, Dialog, Sheet, Popover, Tabs, Toast, Table, Badge, Skeleton; copied from shadcn/Radix and owned). `components/app/*` = domain blocks (DataTable, PageHeader, StatCard, EmptyState, ConfirmDialog, FormField, StatusBadge). `pages/*` only compose. Pages never restyle primitives with one-off classes: add a variant (cva).
- Do not hand-roll dialogs, menus, comboboxes, tabs: use Radix/Headless (Pickering, Inclusive Components).
- Each component documents variants, sizes, states, content limits (truncation rule), keyboard map in COMPONENT_CATALOG.yaml.

## 5. States inventory (per component and per screen)
- Mandatory: default, hover, focus-visible, active, disabled (reason shown when non-obvious), loading (skeleton shaped like final layout, not spinner-only), empty (what + why + one CTA), error (what happened + fix + retry), denied (403: which permission, who grants), partial (one widget fails, others render), offline (banner, queued writes if PWA), success, long content, 0/1/10k rows, long fr/ar strings (fr is often 20-30% longer than en).
- A screen with fewer than 6 states covered is not done. Inertia: use `<Deferred>`/deferred props for skeletons; handle 403/419/429/500 pages explicitly.

## 6. Data-dense admin patterns
- Tables: sticky header, text start-aligned, numbers end-aligned with `tabular-nums`, row height 40-48 with compact toggle, column visibility, server-side sort/pagination (cursor for large sets). Never client-sort 10k rows.
- Filters: search + 2-4 visible filters + "More filters"; applied filters as removable chips; state lives in the URL query (shareable, back button works); "Reset" visible when active.
- Bulk actions: checkbox column; selection bar replaces toolbar and shows count; destructive bulk confirms with the count; "select all N matching" is distinct from "select page".
- Row: one primary click target opens a detail drawer (Sheet 480-640px, keeps list context, deep-linkable `?id=`, Esc closes, focus returns to the row); kebab for secondary actions.
- Exports/imports: queued job, progress, result summary, notify when done.
- Money: end-aligned, fixed decimals, currency code, `Intl.NumberFormat`; never hand-format floats.

## 7. Dashboards
- Layout: bento grid: 1 hero KPI card (big number, delta, sparkline), 3-4 small KPI tiles, 1-2 primary charts, 1 recent-activity table. Max 6-8 widgets above the fold.
- Charts: smooth area/line (monotone curve) by default; bars only for categorical comparison; donuts max 4 slices. Default library Recharts (or visx), one theme from tokens. Tooltips on hover and focus; short axis labels; zero baseline for bars.
- Every number carries period, comparison basis and unit. Real data or a labeled empty state; no fabricated demo data in production views.
- Date range control is global to the dashboard and stored in the URL.

## 8. Forms
- Label above input, always visible; placeholder is never the label. One column except short related pairs. Mark required once; or mark "optional" when few fields are optional.
- Validate on blur and submit; map Laravel 422 to Inertia `errors` per field; error text under the field; long forms add a summary of links; focus the first invalid field.
- Helper text only where the user would otherwise err (format, unit, consequence): one short line, muted yet 4.5:1. If most fields have helper text, delete most of it.
- Never lose input on validation failure. Autosave (debounced, "Saved" indicator) only where the PRD or owner asks for it. Do not re-ask data already given in the flow (SC 3.3.7).
- Submit: one primary button with pending state (disable, prevent double submit, idempotency key for money). Success = redirect to the created record or list, toast naming the record. Destructive: confirm dialog naming the object; the button is the verb ("Delete invoice 1042"), not "OK".
- Auth forms allow paste and password managers (SC 3.3.8). Mobile: correct `type`, `inputmode`, `autocomplete`.

## 9. Navigation per surface
- Decide surfaces first (see `multi-surface-architecture.md`; only surfaces in the PRD or owner request): public site, tenant admin, platform admin, customer portal, POS/desktop, mobile app. Each has its own shell and nav; share primitives and tokens, not layouts.
- Admin web: start-side sidebar (collapsible, 6-9 grouped items, active state, permission-filtered); top bar with search/command palette, tenant switcher, notifications, user menu, language (flags), theme toggle only if dark mode ships. Breadcrumbs from depth 3.
- Mobile web: bottom tab bar max 5 or a drawer; sticky primary action; no hover-only affordances.
- POS/Electron: targets 44px+, visible shortcuts, no hover menus, always-visible connection/sync state.
- Hide links by permission server-side, not CSS. Every cross-surface flow (merchant ticket -> platform support) must have a route and screen on both ends before `verified`.
- Krug: each page answers where am I, what can I do, where can I go. Norman: visible affordance, immediate feedback, recoverable errors.

## 10. Motion
- Allowed purposes: feedback, orientation, attention, continuity. Anything else is removed.
- Durations: micro 100-150ms, standard 200-250ms, large panels 300ms max; exit faster than enter. Material 3 duration tokens run short1 50ms ... medium2 300ms ... extra-long4 1000ms; UI work stays in the short/medium range. Easing: default and enter `cubic-bezier(0.2,0,0,1)` (M3 standard), exit `cubic-bezier(0.3,0,1,1)` (M3 standard-accelerate); linear only for progress/spinners.
- Animate `transform` and `opacity` only; never width/height/top/left.
- `@media (prefers-reduced-motion: reduce)`: drop translate/scale/parallax, keep opacity or instant. Moving content that lasts over 5s needs a pause mechanism (SC 2.2.2): the owner prefers no button, so decorative motion must finish within 5s or stop after one cycle, pause when off-screen, and stop under reduced motion; anything longer that cannot stop gets a small pause control.
- Play-in-viewport: `IntersectionObserver` threshold about 0.3; start on enter, pause on leave, `once` for reveals; no play/pause button for decorative loops (owner bar). Video: muted, `playsinline`, poster, `preload="metadata"`.
- Test frame rate with CPU throttling in DevTools; choppy = simplify or remove.

## 11. Performance budgets
- Core Web Vitals "good" at p75, mobile and desktop separately: LCP <= 2.5s, INP <= 200ms, CLS <= 0.1 (https://web.dev/articles/vitals; same budgets in `operations-monitoring.md` sec. 8).
- Budgets: public-page initial JS <= 170 KB gz (team default, not a standard); route-level splitting (Inertia page resolve with `import.meta.glob`); lazy-load chart/editor libs. LCP image: `fetchpriority=high`, not lazy, explicit width/height. Preload fonts; size-adjusted fallback.
- INP: no task over 50ms on interaction; debounce search 250-300ms; virtualize lists over 200 rows; `useTransition` for heavy filtering.
- CLS: reserve space for images, banners, skeletons; skeleton size equals final size.
- Measure (Lighthouse + throttling) before claiming. Public sites: Lighthouse mobile performance >= 90 (owner SEO bar).

## 12. i18n and RTL testing
- Every string via keys (Laravel lang JSON shared as Inertia prop, or react-i18next), including aria-labels, toasts, validation, empty states. Plurals via ICU/`Intl.PluralRules` (Arabic has 6 forms).
- Dates, numbers, currency via `Intl.*` with the locale; record calendar and numbering decisions. Public sites: `/`, `/fr`, `/ar` with `hreflang` and canonical.
- Per-locale pass: layout mirrored, icons flipped correctly, truncation, mixed-direction strings (`<bdi>` or `dir=auto`), phone/email/URL inputs `dir=ltr`, drawers open from the start edge, charts legible.
- Stress test with the longest fr string and a long Arabic string in every button, badge, tab and table header.

## 13. SSR hydration pitfalls (React #418 family)
- Cause: server HTML differs from the first client render (react.dev hydrateRoot reference). Typical: `new Date()`/`Date.now()`, `toLocaleString()` without fixed locale and timeZone, `Math.random()`, `typeof window` branches in render, `matchMedia`, invalid nesting (`<div>` in `<p>`), extra whitespace, extensions mutating the DOM.
- Default: `Intl.DateTimeFormat(locale, {timeZone: tenantTz})` with identical locale and zone on server and client; Laravel sends ISO UTC. Relative time ("5 min ago") resolves after mount in `useEffect`.
- Client-only values: stable placeholder first, set in `useEffect` (two-pass). `suppressHydrationWarning` only on one text node with an unavoidable difference.
- Restart the SSR process after each build. Check the dev console for hydration warnings in each locale.
- Not verified: react.dev/errors/418 returned 404; message text and numbering rely on the hydration reference.

## 14. Images, uploads, PWA
- Upload UX: instant local preview via `URL.createObjectURL` (revoke after), progress, retry, then swap to the stored URL without reload. Validate type/size client and server (`security-protocol.md`).
- Delivery: `srcset`/`sizes` or `<picture>`: AVIF > WebP > JPEG/PNG, derivatives generated at upload by a queue job, explicit `width/height`, `loading=lazy` below the fold, `decoding=async`, meaningful `alt` or `alt=""` if decorative. Cloudflare image features only if enabled for the zone.
- PWA only if the PRD requires install/offline: manifest (name, icons 192/512 + maskable, `display`, `start_url`, `theme_color`), versioned service-worker cache with update prompt, offline fallback page. Never cache authenticated API responses across users or tenants.

## 15. ANTI-SLOP CHECKLIST (tell -> fix)
These are conditional design failures, not universal bans: every visual choice needs a product function and a system token. Also avoid gratuitous glass/hero blocks and copying competitors.
1. Generic hero + 3 feature cards + CTA -> real product screenshot, specific claims, only sections the PRD needs.
2. Purple/indigo-pink gradients, blobs, glow -> neutral surface + token accent; gradient only from a brand asset.
3. Emoji as icons -> one icon family.
4. Mixed icon sets or stroke widths -> one family, fixed sizes.
5. Everything `rounded-2xl` + `shadow-lg` -> radius per component class (input 8, card 12, pill full); shadow only for overlays; borders in dense UI.
6. Cards nested in cards -> one container level; dividers and spacing.
7. Everything centered -> start-align text; center only hero, empty state, auth.
8. Lorem-like/buzzword copy ("unlock the power") -> concrete verbs, numbers, product nouns from CONTENT_GUIDELINES.
9. Redundant titles (page, card, tab all say "Orders") -> one title per level.
10. Two buttons for one action ("Create" + "Add new") -> one primary per view.
11. Decorative stats ("99.9%", "10k+") -> measured sourced numbers or remove.
12. Low-contrast gray text -> 4.5:1; secondary text is darker, not lighter.
13. Giant empty sections, 120px+ padding -> spacing scale; section padding 64-96 desktop, 40 mobile.
14. Fake testimonials, logos, avatars, reviews -> remove; never ship fabricated social proof.
15. Placeholder as label -> persistent label.
16. Disabled placeholder buttons/menus for unbuilt features -> do not render; log in `[ORPHANS & PENDING]`.
17. Spinner-only loading -> skeleton shaped like content.
18. "Something went wrong" -> cause, next step, retry, reference id.
19. Hover-only actions -> also on focus and touch.
20. White page + one dark brand block -> neutral ramp with 2-3 surface levels + status colors.
21. Bar charts for trends, pie overload -> smooth area/line, sparkline in KPI.
22. Identical card grid for unlike content -> bento sized by importance.
23. Icon in a colored circle above every heading -> only where it aids scanning.
24. Fade-up/bounce on every element -> motion purposes (section 10).
25. Helper text/tooltip on every field -> keep only error-preventing text.
26. Default shadcn/Tailwind look with no token changes -> set brand, radius, font, neutral tint first.
27. Stock illustrations / abstract 3D shapes -> real product shots, or brand assets generated via Codex CLI (pipeline in `agentic-workflow.md` sec. 10: file in the project's assets folder, provenance in `docs/ASSETS.md`).
28. Inconsistent button heights -> size tokens 32/36/40/44.
29. Dark mode as inverted colors -> designed semantic dark tokens, contrast checked.
30. Overflow/truncation in fr/ar -> longest-string test, allow wrap.
31. "John Doe", round fake numbers in views -> realistic seed in dev, true empty states in prod.
32. Language switcher as codes (EN/FR/AR) -> flag + native name.
33. Toast for everything -> toast for non-blocking confirmation, inline for errors, dialog for decisions.
34. Sticky header + sticky bar + chat bubble stacking on mobile -> max one top and one bottom sticky.

## 16. Design-review procedure (real browser)
1. Build; restart SSR if used. Log in with seeded test users per role. List the URLs under review.
2. For each locale in {ar (rtl), fr, en} and width in {1440, 768, 390}: load each changed screen, screenshot, check mirrored layout, icons, no horizontal scroll, clipped text, target sizes, sticky overlaps.
3. Per screen run states: loading (throttle), empty, error (force 500/422), denied, long content.
4. Submit every form with valid data (redirect, toast, record visible without refresh), then with invalid data.
5. Keyboard pass: tab order, visible focus, Esc closes overlays, focus returns. Dark theme pass if shipped.
6. Console: zero errors and hydration warnings; network: no failed requests; Lighthouse on public pages.
7. Apply section 15 to the screenshots; list hits and fixes. Log results in `DESIGN_QA.yaml`: URL, locale, width, passed/failed/not run.
8. If the owner supplied a mockup, diff against it; any mismatch is a failure.

## 17. Design outputs and QA
- Maintain `DESIGN_SYSTEM.md`, `INFORMATION_ARCHITECTURE.yaml`, `SCREEN_INVENTORY.yaml`, `USER_FLOWS.md`, `WIREFRAMES.md`, `COMPONENT_CATALOG.yaml`, `INTERACTION_RULES.md`, `CONTENT_GUIDELINES.md`, `ACCESSIBILITY.md`, `DESIGN_QA.yaml`.
- Verify: primary tasks, errors, keyboard/focus, screen-reader semantics, contrast, text scaling, RTL/LTR, responsive layouts, localization, content extremes, visual regression (procedure in sec. 16).

## Red flags
- Hex/px literals in components; `ml-`/`left-` in RTL products; gray-400 body text.
- A screen with only the happy state; spinner-only loads; no 403 page.
- Hydration warnings; `suppressHydrationWarning` used broadly; `new Date()` in render.
- More than one icon family, emoji icons, fabricated stats or testimonials.
- Two primary buttons, duplicated titles, helper text on every field.
- Animating width/height; autoplay loops with no viewport control; no reduced-motion branch.
- LCP image lazy-loaded; unsized images; fonts without `font-display`.
- "Done" without screenshots at 3 widths x 3 locales.
- New sections added when only style or motion was requested.

## How project-brain uses this
- Load when: design-system setup, new screen or component, dashboard/table/form work, motion requests, perf or i18n issues, UI review before `verified`. For Flutter screens also load `mobile-flutter.md` (sec. 7-8 and the sec. 18 emulator audit); for the Electron POS, `desktop-electron.md`.
- Gates: design phase exit (tokens, components, state inventory defined); `implemented -> verified` for UI tasks (section 16 evidence); release_ready (CWV, a11y, locale pass).
- Record in `.project-brain/DECISIONS.md`: font, icon family, numerals/calendar, dark-mode scope, chart library, mockup adoption. Point `canonical_docs` in STATE.yaml at DESIGN_SYSTEM.md.
- Record in `docs/`: DESIGN_SYSTEM.md (token tables), COMPONENT_CATALOG.yaml, SCREEN_INVENTORY.yaml (states per screen), DESIGN_QA.yaml (locale x width results); unwired UI goes to `[ORPHANS & PENDING]`.
- Delegation: generate imagery/assets with Codex CLI per `agentic-workflow.md` sec. 10 (output copied into the project's assets folder; prompt summary, date and licence note in `docs/ASSETS.md`).
