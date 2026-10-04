# Glossary — plain-language terms (for explaining to beginners)

Use one line from here when a term first appears in a reply to an owner whose profile says beginner. Do not paste the whole list.

| Term | Plain meaning |
|---|---|
| Vibe coding | Building software by describing what you want to an AI agent. Works best when the agent is given rules, a plan and checks — this skill is those. |
| Product brief | One page: the idea, who has the problem, why now. |
| PRD | Product Requirements Document: what the product must do, for whom, and why. Never how. |
| FR (functional requirement) | One thing the product must do, with an ID: `FR-001 Owner can create a branch`. |
| BR (business rule) | A rule that must never break: `BR-003 completed financial records are never deleted`. |
| NFR (non-functional requirement) | A measurable quality: speed, uptime, security, data retention. `API answers in under 300 ms`. |
| Acceptance criterion / Gherkin | How we know a requirement is done: Given (situation), When (action), Then (result). |
| Domain model | The real things in the business (customer, order, invoice) before any table exists. |
| Bounded context | A part of the system that owns its own data (Billing owns invoices; Orders cannot edit them directly). |
| Project map | The index of the project: what exists, where, why, how it connects, and its status. |
| Architecture | How the code and components are organized (the "how"). |
| ADR | Architecture Decision Record: a short note explaining why an important technical choice was made. |
| Schema / migration | The database structure / a versioned script that changes it. |
| Index | A database shortcut that makes a frequent query fast. Added because of a real query, not "just in case". |
| Transaction | Several database changes that succeed or fail together. |
| Idempotency | Doing the same request twice has the effect of doing it once (no double payment on a retry). |
| Multi-tenancy / tenant | Many customers share one system; each customer's data must stay invisible to the others. |
| IDOR | A security hole where changing an ID in a URL shows someone else's data. |
| CWE | A numbered catalogue of software weakness types (CWE-89 = SQL injection). |
| Webhook | A message another service sends to your system when something happens (payment succeeded). Must be verified. |
| Queue / job | Work done in the background after the user's request returns (emails, reports). |
| Outbox | A table that stores "messages to send" in the same transaction as the data change, so none are lost. |
| Staging | A copy of production for testing before release. |
| CI/CD | Automatic checks and deployment on every change. |
| Rollback | Going back to the previous working version after a bad release. |
| RPO / RTO | How much data you may lose / how long you may be down after a disaster. |
| SLO | A target for reliability you measure, e.g. 99.9% of requests succeed. |
| Traceability | Every requirement can be followed to its API, code, table, test and work item — nothing is lost. |
| WBS / backlog | The work cut into pieces / the ordered list of those pieces (epic, feature, story, task). |
| Gate | A checkpoint that must pass before the next phase (e.g. no database work before the data plan is complete). |

## Red flags

- Explaining every term in every reply to an experienced owner (follow the owner profile).
- Using a term from this list in a doc without an ID or a definition when the owner is a beginner.

## How project-brain uses this

Commitment 1 in `SKILL.md` adapts replies to the owner's level from `references/owner-profile.md`; for a beginner, the first use of a term gets its plain meaning from this table.
