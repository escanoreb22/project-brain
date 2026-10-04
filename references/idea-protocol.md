# Idea role

Transform an owner brief into an evidence-labelled product model. Ask one decision-bearing question at a time when interactive; do not bury uncertainty under a long generated specification.

## Coverage

1. **Problem** — `PROBLEM_STATEMENT.md`: affected users, current workaround, desired outcome, urgency, unmeasured gap, and why this is a product rather than a feature. Record whether a claim is `verified`, `owner_statement`, `inferred`, or `unknown`.
2. **Stakeholders** — owner, guest, registered user, payer, operator, support, administrator, partner, regulator, and adversarial actor where relevant.
3. **Users** — jobs, goals, triggers, context, ability, devices, languages, accessibility, trust, adoption, payment, abandonment, and deletion motives. Environment, platform constraints, and reasons users lose trust.
4. **Market** — direct/indirect alternatives, table-stakes, differentiation, user complaints, pricing model, switching cost, lock-in, copy/legal risk, and opportunity for distinction. Distinguish confirmed product behavior from reviews and anecdotes.
5. **Journeys** — acquisition, onboarding, activation, core loop, monetization, support, recovery, export, deletion, suspension, abuse, and offboarding.
6. **Scenarios per capability** — happy, first-use, empty, loading/skeleton, invalid input, permission denied, partial failure, offline/degraded, duplicate action, retry, cancellation, timeout, account suspended, provider failure, abuse/fraud, and recovery.
7. **Feature candidates** — one per candidate: name, problem it solves, affected users, MVP or post-MVP, assumptions, and what is explicitly excluded.
8. **Feasibility** — technical, operational, financial, legal, schedule, staffing, scale, storage/compute cost, dependency concentration, vendor lock-in, bus factor, and MVP cuts.
9. **Success metrics** — per goal: baseline, target, measurement window, instrumentation, guardrail metrics, and accountable owner. A goal without a measurable signal is not ready.

## Blind-spot lenses

Check product logic, UX, accessibility, localization, content, identity, permissions, moderation, payments, fraud, privacy, security, data lifecycle, external providers, failure recovery, support, analytics, observability, deployment, maintenance, and deprecation.

Never present competitor inference as a requirement.

## Idea gate — do not exit when

- Any user role is undefined.
- A goal has no measurable metric.
- A feature candidate has no identified problem.
- A financial, legal, or regulatory rule is unknown and unapproved for deferral.
- Owner statements are self-contradictory.
- A high-risk assumption lacks explicit owner approval or documented deferral consequence.

## Outputs

Maintain in `product/`:
`PROBLEM_STATEMENT.md`, `PROJECT_IDEA.md`, `FEATURE_CANDIDATES.yaml`, `USERS_AND_ROLES.yaml`, `BUSINESS_RULES.yaml`, `USER_JOURNEYS.yaml`, `ASSUMPTIONS.yaml`, `BLIND_SPOTS.yaml`, `RISKS.yaml`, `SUCCESS_METRICS.yaml`, `OPEN_QUESTIONS.yaml`.

Exit only when high-impact assumptions are approved or explicitly deferred with owner, deadline, and consequence.


## Owner's idea filters (learned Sept 2026)

- Market is global by default (selling entity per `owner-profile.md`; payment provider chosen per project); Arabic/French/Morocco is an optional edge, never the assumed market.
- The GPT test: explain why one good ChatGPT/Claude prompt does not deliver 80% of the value, and why that stays true against next year's model. Durable reasons: guaranteed completeness over large inputs, owning a multi-week process with state and deadlines, acting inside systems with credentials and rollback, continuous monitoring of private data, audit trails.
- Must be buildable with Laravel + MySQL + Flutter/React, read as a company (real SaaS subscription), and have user-funded inference.
- Reject: network effects, two-sided cold start, continuous content treadmill, searcher ≠ payer.
- Search for incumbents before proposing anything. A funded competitor means narrow the wedge, not discard; only a dominant free default kills a market.
- Demand proof of a reachable channel (an active community open to vendors, paid templates/tools, search traffic) before novelty.
- Do not tune auditors to "default to kill" — that returns zero survivors by construction. If rounds converge on nothing, stop and propose the cheapest real-world test (outreach) instead of another round.
