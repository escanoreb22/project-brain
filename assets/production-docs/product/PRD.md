<!-- pb:template - delete this line only when every section holds project facts or "N/A - reason"; plan_check ignores files that still carry it -->
# Product Requirements Document

PRD = WHAT + WHY. It never decides HOW: no database engine, tables, Redis, REST/GraphQL, frameworks.
Those belong to architecture/ and adr/. Requirement IDs are permanent: never renumber, mark removed ones as withdrawn.

## 01. Document information
- Version / date / status (draft, in review, approved):
- Owner:
- Source documents (docs/source/*):

## 02. Product overview
- Product:
- Purpose (one paragraph a new team member understands):
- Primary users:

## 03. Problem statement
Current situation, its consequences, and how the product will change it.

## 04. Goals
## 05. Non-goals (version 1 will NOT include)
## 06. Target users
## 07. Actors and responsibilities
| Actor | Responsibility | Can | Cannot |
|---|---|---|---|

## 08. User needs
## 09. User journeys (actions, not pages)
Journey: Actor, then step, then step ... and the outcome.

## 10. Functional requirements
| ID | Actor | Requirement | Acceptance criterion | Priority |
|---|---|---|---|---|

## 11. Business rules
Summary only; the full list with enforcement points lives in BUSINESS_RULES.md (BR-xxx).

## 12. Edge cases
Double submit · connection lost · payment succeeded but response timed out · user deactivated during an active session · two users editing the same record · empty, maximum and invalid inputs.

## 13. Permissions / roles
| Role | Allowed | Forbidden |
|---|---|---|

## 14. Non-functional requirements
Summary only; measurable targets live in NON_FUNCTIONAL_REQUIREMENTS.md (NFR-xxx).

## 15. Success metrics
| Metric | Target | How measured |
|---|---|---|

## 16. Analytics requirements (events to track, no personal data unless justified)
## 17. Dependencies (external services, data, other teams)
## 18. Constraints (budget, time, legal, platform)
## 19. Risks
| Risk | Impact | Mitigation |
|---|---|---|

## 20. Acceptance criteria (Given / When / Then per key feature; full set in testing/ACCEPTANCE_TESTS.md)
## 21. Release scope (MVP)
## 22. Future scope
## 23. Open questions
| Question | Owner | Needed by |
|---|---|---|
