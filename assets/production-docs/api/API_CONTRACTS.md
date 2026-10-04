<!-- pb:template - delete this line only when every section holds project facts or "N/A - reason"; plan_check ignores files that still carry it -->
# API Contracts

Contract before UI. If the repo uses OpenAPI, `docs/openapi/*.yaml` is the source and this file only lists conventions.

## Conventions
- Auth (AuthN) and policy (AuthZ) per endpoint:
- Pagination (cursor / page, max page size):
- Rate limits (per user / per IP / per tenant):
- Idempotency (`Idempotency-Key` on which POSTs, retention window):
- Versioning (URL / header, compatibility window):

## Error taxonomy (stable codes)
| HTTP | Code | When |
|---|---|---|
| 400 | | malformed request |
| 401 | | not authenticated |
| 403 | | not allowed |
| 404 | | not found or not visible to this tenant |
| 409 | | state conflict / duplicate |
| 422 | | business rule violated (carries the BR id) |
| 429 | | rate limited |

## Endpoints
| Method | Path | FR/BR | Input | Output | Errors | Policy |
|---|---|---|---|---|---|---|
