<!-- pb:template - delete this line only when every section holds project facts or "N/A - reason"; plan_check ignores files that still carry it -->
# Project Map

The navigation map of the project. It does not repeat the other docs: it says what exists, where it is,
why it exists, how the parts connect, and the current status. Any developer or AI agent starts here.

Status: draft | Stack: (see architecture/ARCHITECTURE.md) | Source precedence: docs/source/* > PRD > this map

## [SYSTEM_FLOW]
One paragraph: who uses the system, the core loop, and what must never break.

## Project tree
- Product areas: (e.g. Authentication, Onboarding, Workspace, Billing, Settings)
- Applications / surfaces: (e.g. Web app, Mobile app, Admin panel, Public API)
- Backend domains: (e.g. Identity, Organizations, Orders, Billing, Notifications, Reporting)
- Infrastructure: (database, cache, queue, object storage, monitoring)
- Integrations: (payment provider, email, SMS, OAuth)
- Operations: (CI/CD, backups, monitoring, incident handling)

## Documents index
| Area | Document | Answers | Status |
|---|---|---|---|
| Product | product/PRODUCT_BRIEF.md | what is the idea | |
| Product | product/PRD.md | what the product must do and why | |
| Product | product/BUSINESS_RULES.md | rules that must never break | |
| Product | product/NON_FUNCTIONAL_REQUIREMENTS.md | measurable quality targets | |
| Domain | domain/DOMAIN_MODEL.md, BOUNDED_CONTEXTS.md, STATE_MACHINES.md | the real concepts, owners, lifecycles | |
| Architecture | architecture/SYSTEM_CONTEXT.md, SYSTEM_DESIGN.md | how the whole system works | |
| Architecture | architecture/ARCHITECTURE.md, BACKEND_ARCHITECTURE.md | how code is organized and rules execute | |
| Data | data/DATA_ARCHITECTURE.md, RETENTION_POLICY.md | how the truth is stored and kept | |
| API | api/API_CONTRACTS.md (or openapi/), EVENTS.md, WEBHOOKS.md | how clients and systems talk | |
| Interfaces | interfaces/*.md | how each application behaves | |
| Security | security/SECURITY.md | how system and data are protected | |
| Operations | operations/*.md, delivery/CI_CD.md | how it runs in production | |
| Testing | testing/TEST_STRATEGY.md, ACCEPTANCE_TESTS.md | how we prove it is correct | |
| Delivery | delivery/BACKLOG.md, product/ROADMAP.md | what work, in which order | |
| Decisions | adr/ | why important technical decisions were made | |

## Traceability (one row per FR)
| FR | BR | API | Use case / action | Tables | Events | Tests | Work item |
|---|---|---|---|---|---|---|---|

## Phases (dependency order)
Task row: `ID | objective | FR/BR/NFR IDs | acceptance criterion | files/areas | tests | status`

## Decisions needed from the owner
| Decision | Options | Recommended default |
|---|---|---|

## [ORPHANS & PENDING]
