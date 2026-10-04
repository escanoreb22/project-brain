# Compliance and payments - legal/privacy rules and payment flows for the owner's SaaS
Scope: Morocco law 09-08 / CNDP, GDPR basics, policies and cookies, retention and audit design, Moroccan invoices, Stripe, Google Play Billing, Apple IAP, manual bank transfer, refunds, PCI.
Not legal advice. Everything legal here is a build default; the owner (with a lawyer) decides. Related files: `security-protocol.md`, `db-schema-design.md`, `backend-architecture.md`, `api-design.md`, `mobile-flutter.md` (Play Billing client side), `desktop-electron.md` (POS receipts, device data), `operations-monitoring.md` (incident runbook), `multi-surface-architecture.md`.
Verified on official or primary sources on 2026-10-03 unless marked UNVERIFIED.

## 0. Owner decisions that frame this file (2026-10-03)

- **The payment provider is chosen per project by its PRD.** Never assume Stripe. Possible providers include Stripe, Google Play Billing, Apple IAP, Moroccan gateways (e.g. CMI), PayPal, manual bank transfer with proof, cash on delivery. Read the PRD; if it is silent, ask once (owner gate) with a recommended default.
- Implement every provider behind one **PaymentProvider adapter** in the domain: `createCheckout/charge`, `verify(eventOrReceipt)`, `handleWebhook(signedPayload)`, `refund`, `status`. Common rules for all providers: server-side verification, signed webhooks or receipts, idempotency keys, append-only payment ledger, no card data on our servers.
- Sections 9-13 below are provider-specific: load only the one the project uses.
- **Privacy law applies per project data scope:** law 09-08/CNDP when the project processes personal data of people in Morocco; GDPR when it targets people in the EU. A project that processes neither does not need those steps; record the scope in DECISIONS.md.

## 1. Gate rule (SKILL.md section 5)
Billing, pricing, payouts, legal/privacy text and cross-border transfer are owner gates when the approved docs/DECISIONS.md do not already settle them (SKILL.md section 5). The agent builds what the PRD specifies; it never invents the policy. Ask once, batched, with a default (section 15).

## 2. Morocco: law 09-08 and CNDP (only when the project processes personal data of people in Morocco)
Facts (sources: cms.law flash info on law 09-08; upsilon-consulting.com CNDP guides; cndp.ma):
- Law 09-08 (2009) is the data protection law; the authority is the CNDP.
- Automated processing of personal data must be declared to the CNDP BEFORE it starts. Sensitive data (health, origin, politics, religion, union, genetic) needs prior authorization instead of a simple declaration.
- Transfer abroad: prior CNDP authorization is needed unless the destination gives adequate protection (articles 43 and 44). Secondary sources state exceptions, for example transfer necessary to perform a contract with the person. CNDP keeps the list of adequate countries; the EU is generally treated as adequate in practice.
- CNDP offers accelerated procedures and forms for transfers (it did so for a major cloud vendor in 2022).
- Cookies: CNDP deliberation D-939-2025 (28 Nov 2025, PDF read 2026-10-03) sets the simplified declaration for cookies, filed on CNDP-FORMS before cookies are used. Allowed purposes: ads by browser or location without profiling, content personalization, social sharing, audience statistics without profiling. Profiling needs prior CNDP authorization. Prior consent is required for personalized-ad and social-sharing cookies; cookie data and the user's choice are kept 6 months maximum; transfers abroad need prior CNDP authorization. Details in section 5.
- No enacted replacement of 09-08 as of 2026; a GDPR-aligned reform is only discussed. Re-check before each release that handles personal data at scale.
Defaults for the agent:
- Treat every project with Moroccan users or a Moroccan controller as "must declare". Add a `docs/compliance/cndp.md` with: controller identity, data categories, purposes, recipients, retention, transfers (country + safeguard), security measures. These are the fields a CNDP request needs.
- Hosting on a VPS outside Morocco, Cloudflare, Stripe, Firebase, email and analytics providers are all transfers. List each in the processor register (section 4).
- Never process sensitive data (health, biometrics) without an explicit owner gate and an authorization plan.
- Collect only needed fields; state purpose and retention on each form.
UNVERIFIED: whether the US is on the CNDP adequate list; current declaration fees and form numbers; breach notification (secondary sources say 09-08 has no explicit GDPR-style deadline, the CNDP encourages prompt notice); exact CNDP position for a US LLC serving Moroccan data subjects. Owner gate: ask the owner to confirm with CNDP or a Moroccan lawyer.

## 3. GDPR basics (only when the project targets people in the EU)
Applies when you offer services to people in the EU, even from Morocco or a US LLC.
- Lawful basis (one per purpose): contract, legal obligation, legitimate interest, consent. Consent only where needed (marketing, non-essential cookies). Record the basis in the data map.
- Processors: a written DPA with each processor (hosting, email, Stripe, support tools). Contract must bind the processor to documented instructions, confidentiality, security, deletion or return at the end, and sub-processor rules (GDPR art. 28, gdpr-info.eu/art-28-gdpr).
- Data subject rights: access, rectification, erasure, restriction, portability, objection. Reply within one month, extendable by two months for complex cases, free of charge in principle (art. 12).
- Breach: controller notifies the supervisory authority without undue delay and, where feasible, within 72 hours of becoming aware, unless no risk to people; processors tell the controller without undue delay (art. 33).
- Non-EU controller serving EU people may need an EU representative (art. 27). UNVERIFIED for this owner; owner gate.
- Transfers from the EU to a US LLC or to Morocco need a valid mechanism (adequacy decision, SCCs, or other). UNVERIFIED which mechanism applies today to the owner's entity; owner gate.
Build rules:
- Export endpoint: one job that assembles a user's data as JSON/CSV; admin-triggered and self-service; logged.
- Erasure: see section 6 (anonymize, keep what law requires).
- Breach runbook file: `docs/compliance/breach-runbook.md` with detect, contain, assess, notify (72h clock starts at awareness), log. It extends the incident runbook in `operations-monitoring.md` sec. 10; do not keep two procedures.
- Data map file: `docs/compliance/data-map.md` (table, columns, purpose, basis, retention, processor, transfer).

## 4. Processor register (one file, kept current)
| Processor | Data | Country | DPA/terms | Transfer safeguard | Used for |
|---|---|---|---|---|---|
| Stripe | payer name, email, billing address, card tokens | US/EU | Stripe DPA | UNVERIFIED per project | payments |
| Cloudflare | IP, request metadata | global | Cloudflare DPA | UNVERIFIED | CDN/WAF |
| VPS host | everything stored | per host | host DPA | per host | hosting |
| Email provider | email, name | per vendor | vendor DPA | per vendor | transactional mail |
| Google (Play, Firebase) | device and purchase tokens | global | Google terms | UNVERIFIED | mobile billing/push |
Agent rule: adding any new third-party SDK or API that receives personal data = add a row first, and tell the owner (privacy gate).

## 5. Privacy policy, terms, cookie consent: minimums
Privacy policy must state (each in ar/fr/en):
- Controller identity and contact (the owner's legal entity from `owner-profile.md`, or the project entity) and a privacy contact email.
- Data categories, purposes, lawful basis, recipients/processors, transfers and safeguards, retention periods, rights and how to exercise them, complaint route (CNDP; EU authority for EU users), cookie summary, CNDP declaration receipt (recepisse) numbers, last-updated date.
Terms of service minimums:
- Parties, service description, accounts and tenant roles, acceptable use, plans/prices/taxes, billing cycle, renewal and cancellation, refund policy, data ownership and export on exit, suspension rules, liability limits, governing law and venue (owner gate), change notice.
Cookie consent:
- Essential cookies (session, CSRF, locale) need no consent but must be listed.
- Analytics, ads, third-party embeds: block until opt-in; "reject" as easy as "accept"; store the choice with timestamp and policy version; allow withdrawal from a footer link.
- Same screen for Moroccan and EU users by default. CNDP D-939-2025 only requires opt-in for personalized-ad and social-sharing cookies, but GDPR needs it for analytics too, so the single banner blocks all non-essential cookies until opt-in.
- Before the first cookie, show (CNDP D-939-2025): controller identity, purposes, data categories, recipients and transfers abroad, contact for access/rectification/opposition, CNDP receipt references. Keep cookie data and the stored choice 6 months maximum, then re-ask.
- No pre-ticked boxes. No tracking scripts loaded before consent (check network tab).
Acceptance of terms: store `terms_version`, `accepted_at`, `ip_hash` per user at signup and on each major version.
Never copy a competitor's legal text; write from the data map. Final wording is an owner/lawyer gate.

## 6. Retention and deletion design
Decision table:
| Data | Default | Mechanism |
|---|---|---|
| Account/tenant (cancelled) | 30 days archived, then purge | soft delete `deleted_at` + restore + scheduled purge job |
| Invoices, accounting records | keep 10 years (Morocco, CGI art. 211; see section 8) | never purge; anonymize personal fields only if law allows; other countries UNVERIFIED |
| Audit logs | 1 year hot, then archive 2-5 years (owner gate) | append-only table, partition by month |
| Payment tokens/customer ids | until subscription ends + dispute window | delete at purge |
| Marketing consent records | keep while consent is valid + proof period | immutable consent log |
| Backups | rotate 30 days | purge propagates by expiry; document it in privacy policy |
| Uploads (proofs, IDs) | delete when purpose ends | job + storage delete |
Rules:
- Soft delete for user-facing "delete"; hard purge only by a queued job with a dry-run log and owner approval of the policy.
- Erasure request: anonymize PII columns (name, email, phone, address) in rows that must stay (invoices, ledger), delete the rest; write an erasure log entry (who, when, request id, no PII).
- Related statuses stay consistent: archiving a tenant suspends its users, subscriptions, API keys and jobs; restoring reverses them (see playbook 3.3 in SKILL.md).
- Retention is a config table or enum, not magic numbers in jobs. Test purge on MySQL with FK constraints.
- Destructive purge job on production = owner gate.

## 7. Audit logs
- Log: actor id, tenant id, action, subject type/id, old/new values for sensitive fields only (never raw card data, passwords, tokens), IP, user agent, request id, UTC time.
- Must log: login/logout/fail, role/permission changes, plan and price changes, payments, refunds, manual activations, exports, deletions/purges, impersonation, settings and webhook secret rotations.
- Append-only: no UPDATE/DELETE grants to the app role on the audit table; admin UI is read-only.
- Writes happen in the same transaction as the business change (or via an outbox), so a rolled-back change leaves no log.
- Retention per section 6; access to logs is itself logged.

## 8. Invoices in Morocco
Sources (secondary, based on CGI article 145 and DGI practice): clicpaie.ma invoice guide, upsilon-consulting.com article 146 guide, cms.law finance law summaries. Official DGI text not fetched: mark UNVERIFIED until the owner's accountant confirms.
Mandatory mentions (default checklist):
- Seller: legal name and legal form, capital, full address, ICE (15 digits), IF, RC (with court/city), TP (taxe professionnelle).
- Buyer: name, address, ICE (required for business buyers; missing ICE can cost the buyer VAT/expense deduction).
- Invoice: unique sequential number without gaps, issue date, description, quantity, unit price excluding tax, total HT, VAT rate and amount, total TTC, payment method/terms.
- Retention: 10 years for invoices and accounting documents (CGI art. 211; CMS law-firm summary of finance law 73-16, official DGI text not read). Penalty: about 100 MAD per ICE omission or error per secondary sources (UNVERIFIED).
- Cash limit and e-invoicing rules: UNVERIFIED; 2026 sources say e-invoicing format and dates are still pending.
Design rules:
- Table `invoices` immutable once issued; corrections by a credit note with its own number; numbering sequence per issuer and fiscal year via a locked counter (not auto-increment shared with drafts).
- Money in integer minor units + currency; store VAT rate used per line.
- Snapshot seller and buyer identity on the invoice row (profile edits must not rewrite old invoices).
- PDF is generated from the stored snapshot; keep the file or reproducible template version.
- Entity matters: a foreign entity (e.g. a US LLC) issuing to local businesses vs a local entity issuing: tax treatment differs. Owner gate; do not guess VAT.
- Stripe-hosted invoices do not carry Moroccan mentions by default; if Moroccan-compliant invoices are required, generate them in the app and use Stripe only to collect payment. UNVERIFIED how far Stripe invoice customization can cover ICE/IF/RC.

## 9. Stripe (only when the project's PRD uses Stripe)
Defaults (docs.stripe.com):
- Use Checkout (hosted or embedded) and Billing; Customer Portal for card update and cancel. This keeps card data off your servers (section 12).
- Subscriptions: provision on `invoice.paid` AND subscription status `active`; revoke on `canceled` or `unpaid`; notify on `invoice.payment_failed` and `past_due`; handle `invoice.payment_action_required` (3DS).
- One-time Checkout: fulfill from the webhook (`checkout.session.completed`, plus async success events for delayed methods); the success page only shows status. Fulfillment must be idempotent because both paths may fire.
- Also subscribe to `charge.refunded`, `charge.dispute.created`, `radar.early_fraud_warning.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `customer.subscription.trial_will_end`.
Webhook endpoint rules:
- Route accepts POST, outside CSRF and auth middleware, throttled by IP, HTTPS only.
- Verify `Stripe-Signature` with the endpoint secret `whsec_...` on the RAW body; never re-encode JSON first. Library default tolerance is 5 minutes; never set 0.
- Return 2xx fast; do real work in a queued job. Stripe retries up to 3 days in live mode (sandbox: 3 times over hours).
- Events can arrive out of order and twice: store `event.id` in `stripe_events` (unique) and skip seen ones; re-fetch the object from the API when order matters; do not rely on `created`.
- Separate secrets for test and live; per-endpoint secrets; roll periodically (old secret can stay up to 24 hours).
Idempotency:
- Send `Idempotency-Key` (random v4 UUID, max 255 chars, no PII) on every POST that creates or changes money objects; key stored by the order/attempt row so retries reuse it.
- Same key with different params returns an error; keys are pruned after at least 24 hours.
- Do not send keys on GET/DELETE.
Laravel snippet (raw body, queue):
```php
$event = \Stripe\Webhook::constructEvent(
    $request->getContent(), $request->header('Stripe-Signature'), config('services.stripe.webhook_secret'));
if (StripeEvent::query()->where('event_id', $event->id)->exists()) { return response('', 200); }
StripeEvent::create(['event_id' => $event->id, 'type' => $event->type]);
ProcessStripeEvent::dispatch($event->id);
return response('', 200);
```
(Check package versions in `composer.lock`; use the official `stripe/stripe-php`.)
SCA/3DS:
- Required for EEA cards; use Checkout/Billing/PaymentIntents, which handle it. Never use the legacy Charges API.
- Off-session renewals: save the card via Checkout/SetupIntent with consent text (permission, frequency, amount rule) and flag payments `off_session`; handle `requires_action` by emailing the customer.
Tax:
- Stripe Tax is optional; it calculates and reports but filing/registration is separate. UNVERIFIED for Morocco and for the owner's registration status. Default: no Stripe Tax until the owner decides; store tax lines explicitly.
Test mode:
- Develop and run tests with test keys and test cards only; `stripe listen --forward-to` for local webhooks; `stripe trigger` for events; test 3DS cards, declines, disputes. Live keys never appear in the repo, chat or logs (owner-profile: remind rotation).
Account notes: Morocco is not on Stripe's supported-country list (stripe.com/global, checked 2026-10-03), so the Stripe account belongs to the US LLC. Payouts, pricing, currencies = owner gate.

## 10. Google Play Billing (only for Play-distributed digital goods)
Source: developer.android.com Play Billing integrate/security/RTDN docs.
Flow (all entitlement decisions on the server):
1. App buys via Play Billing, sends `purchaseToken` + product id to your backend.
2. Backend calls the Google Play Developer API (`purchases.products` or `purchases.subscriptionsv2`) to verify. Grant only when state is purchased, not pending. Check obfuscated account/profile ids match the user.
3. Use `purchaseToken` as the unique key (globally unique). Do not use `orderId` as key (not always present).
4. Acknowledge (or consume) from the backend after granting. Deadline: 3 days from purchase, else Google refunds automatically and revokes. Pending purchases start the 3-day window only after they become purchased.
5. Subscribe to RTDN (Cloud Pub/Sub push to your endpoint with an authenticated token). A notification only says "something changed": always call the API for full state. Dedupe by Pub/Sub `messageId`.
6. Handle: subscription renewed, canceled, on hold, grace period, recovered, expired, revoked; one-time purchased or canceled; voided purchase (revoke access, adjust ledger); pending refund review (chargeback: reply within 24 hours via the review API).
7. Also poll the Voided Purchases API on a schedule as a safety net, and reconcile daily.
Rules:
- Same user on web (Stripe) and mobile (Play): one `subscriptions` table with `provider` (stripe|play|apple|bank), `provider_ref`, `status`, `current_period_end`; entitlement computed from it, never from the client.
- Link tokens to one user; reject a token already bound to another user.
- Test with license testers and Play test tracks; never trust a debug client.
- Play fees, payment-policy applicability (digital goods inside the app must use Play Billing; B2B web subscriptions bought outside the app generally do not) = UNVERIFIED for this owner; owner gate before choosing what mobile sells.

## 11. Apple IAP (note)
- If an iOS app sells digital features inside the app, Apple IAP rules likely apply. Official docs not verified in this run; UNVERIFIED.
- Technical shape if the owner chooses it: StoreKit 2 on device, App Store Server API and Server Notifications V2 on backend, signed (JWS) transactions verified server-side. Map into the same `subscriptions` table with `provider=apple`.
- Default: do not build iOS billing until the owner states the iOS plan (not in the stated stack).

## 12. Card data and PCI scope
- Never receive, log, store or transmit PAN, CVC or full track data on your servers, DB, logs, queues or support tickets. Use the chosen provider's hosted page or iframe fields (e.g. Stripe Checkout/Elements, a CMI hosted page) so card data goes straight to Stripe.
- Safe to store: Stripe ids, brand, last4, expiry month/year, fingerprint. Stripe states these are not PCI-sensitive.
- Target scope: SAQ A (all card entry is in a Stripe-hosted page/iframe). Custom forms that handle card fields yourself, or pages with script that can alter the payment page, push you toward bigger SAQs. SAQ eligibility details: confirm on the Stripe Dashboard compliance page and PCI SSC; the exact SAQ mapping per integration is UNVERIFIED here.
- Payment pages: TLS 1.2+, no mixed content, minimal third-party JS, CSP allowing Stripe origins (checkout.stripe.com, js.stripe.com, hooks.stripe.com for 3DS).
- Electron POS and Flutter: card present or in-app card entry is a separate topic; default is the chosen provider's hosted/redirect flow or official SDK. Owner gate before any custom card entry.
- Add a log scrubber test: fail CI if a 13-19 digit Luhn-valid number appears in logs or fixtures.

## 13. Manual bank transfer activation (Morocco-friendly flow)
State machine for `payment_orders` (method=bank_transfer):
`pending_proof -> proof_uploaded -> under_review -> approved | rejected -> (approved) activated`; `expired` after N days (default 7) without proof.
Steps:
1. Tenant picks plan, system creates an order with unique reference code (e.g. `HS-2026-000123`), amount, currency, bank details from settings, invoice/proforma PDF.
2. Tenant uploads proof (image/PDF): type allow-list by content sniffing, max 5 MB, random filename, private disk, virus scan if available, signed URL for review only, EXIF stripped.
3. Admin reviews: sees reference, amount, payer name, proof; approves or rejects with reason.
4. Approve: one DB transaction sets order approved, creates payment row, creates or extends subscription, writes ledger and audit rows, issues invoice (section 8), sends email. Idempotent per order id (double click safe).
5. Reject: reason in tenant locale, allows re-upload.
Rules:
- Two-person rule above an owner-set amount (default: off, owner gate).
- Admin cannot approve their own tenant's order.
- Amount mismatch: approve only the matched amount or mark partial; never silently activate.
- Proof files are personal/financial data: retention per section 6 (default delete 12 months after the order is accounted; owner gate), access logged.
- Notify finance role; daily list of orders pending over 48 hours.
- Fraud signals: same proof hash reused across orders, reference not matching.

## 14. Refunds and disputes
- Refund policy text lives in the terms (owner gate). Default: no automatic refund; owner/admin decides per case.
- Stripe refund: via API with an idempotency key, from an admin action that writes audit + credit note + subscription adjustment; wait for `charge.refunded` to finalize local state.
- Disputes: on `charge.dispute.created` flag the tenant, pause risky actions, collect evidence (invoice, access logs, terms acceptance record, usage proof), submit via Dashboard/API before the deadline shown on the dispute (deadline length UNVERIFIED here; read it on the dispute object). Keep `terms_version` acceptance and usage logs to support evidence.
- Play: respond to chargeback reviews within 24 hours; revoke on voided purchases.
- Bank transfer refunds: manual, recorded as a credit note and a ledger entry with proof of payout.
- Never delete payment rows after a refund; add reversing entries.

## 15. Owner gate list (ask once, batched, with defaults)

No default payment provider exists: if the PRD does not name one, the provider is a gate question. Privacy items apply only within the project's data scope (section 0).
| # | Question | Recommended default |
|---|---|---|
| 1 | Which entity sells and invoices (US LLC or Moroccan entity), and VAT treatment | The owner's selling entity from `owner-profile.md` invoices via the PRD's payment provider; local legal mentions only if a local entity issues |
| 2 | CNDP declaration filed? who files, with which transfer safeguards | declare before launch; list the PRD's payment provider, host, Cloudflare as transfers |
| 3 | Serve EU users now? EU representative and transfer mechanism | yes only after DPA + SCC check |
| 4 | Privacy policy, terms, refund policy final text and governing law | draft from data map, lawyer review |
| 5 | Retention periods (audit, proofs, backups, cancelled tenants) | section 6 table |
| 6 | Plans, prices, currencies, trial, grace period, dunning | no hard-coded prices; config table |
| 7 | Provider-side tax calculation (if the PRD's provider offers it) on or off | off until registered |
| 8 | Sell in mobile apps (Play/Apple)? what exactly | web billing only until decided |
| 9 | Bank transfer: bank details, review roles, amount threshold for two-person rule | single reviewer, no threshold |
| 10 | Any sensitive data (health, biometrics, IDs)? | no |
| 11 | Purge jobs on production | dry-run first, owner approves |
| 12 | Analytics/ads trackers | none until consent banner is live |

## Red flags
- Any code or log containing a card number, CVC, or full Stripe secret key.
- Webhook handler without signature verification, with parsed-then-reencoded body, or doing slow work before returning 2xx.
- Fulfillment on the success page only, or a webhook handler that is not idempotent (no stored event id).
- Entitlement granted by the client or before server-side verification (Play/Apple/Stripe).
- Play purchase not acknowledged within 3 days, or pending purchase treated as paid.
- Invoice edited after issue, numbering gaps, or missing ICE/IF/RC on a Moroccan invoice.
- Hard-delete of tenants, invoices or audit logs; purge without dry-run.
- Third-party SDK or analytics added with no processor-register row or consent gate.
- Trackers firing before consent; "accept" easier than "reject".
- Prices, tax rates, refund rules or legal text invented by the agent instead of owner-decided config.
- Live Stripe keys used in tests or pasted into docs.
- A legal claim in code or docs stated as fact while still UNVERIFIED.

## How project-brain uses this
- Load when a task touches billing, subscriptions, invoices, signup/consent, cookies, data export/deletion, uploads of proofs, third-party SDKs, or hosting region. Roles: `backend`, `api`, `security`, `db`, `docs`.
- Section 15 feeds the owner-gate batch (SKILL.md section 5); answers go to `DECISIONS.md` as owner decisions, defaults as `delegated, open to reversal`.
- PRD/map traceability: every payment or privacy requirement gets an ID and a test (webhook signature, idempotent replay, out-of-order events, bank proof approve twice, erasure keeps invoices, purge dry-run).
- `pb-security-reviewer` checks sections 9, 10, 12, 13 and the red flags; `pb-verifier` replays the chosen provider's test events (e.g. Stripe CLI for Stripe, Play test tracks for Play Billing) and replays each webhook twice.
- Before a release: refresh UNVERIFIED items with `research-policy.md` (official sources, versions from lockfiles), update `docs/compliance/*`, and record the change in the change log.
- Never write pasted keys (Stripe, Google service accounts) into docs or memory; remind the owner once to rotate.
Sources:
- https://cms.law/fr/mar/legal-updates/flash-info-maroc-etat-des-lieux-de-la-protection-des-donnees-a-caractere-personnel-au-maroc-loi-n-09-08
- https://upsilon-consulting.com/transfert-international-donnees-personnelles-maroc/
- https://www.cndp.ma/wp-content/uploads/2025/12/ (Deliberation N° D-939-2025 du 28/11/2025, cookies, PDF read)
- https://cms.law/en/fra/legal-updates/Maroc-Loi-de-finances-2018-Procedures-fiscales (CGI art. 211, 10-year retention)
- https://stripe.com/global
- https://gdpr-info.eu/art-12-gdpr/ , /art-28-gdpr/ , /art-33-gdpr/
- https://clicpaie.ma/blogs/modele-facture-maroc/ , https://upsilon-consulting.com/pieces-justificatives-des-achats-article-146-du-cgi/
- https://docs.stripe.com/webhooks , /api/idempotent_requests , /billing/subscriptions/webhooks , /strong-customer-authentication , /security/guide , /disputes , /tax
- https://developer.android.com/google/play/billing/integrate , /security , /rtdn-reference
