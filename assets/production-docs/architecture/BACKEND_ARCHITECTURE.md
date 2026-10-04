<!-- pb:template - delete this line only when every section holds project facts or "N/A - reason"; plan_check ignores files that still carry it -->
# Backend Architecture

How operations and business rules execute.

## Request path
Route, then validation (form request), then authorization (policy), then use case / action, then domain rules, then persistence, then response resource.

## Use cases
| Use case | FR/BR | Transaction boundary | Side effects after commit | Idempotent? |
|---|---|---|---|---|

## Domain services and where each BR is enforced
## Background jobs and scheduled tasks
| Job | Trigger | Idempotency key | Timeout | Retries / backoff | On final failure |
|---|---|---|---|---|---|

## Error mapping (domain, application, infrastructure, transport)
## Integration adapters (one port per external provider)
