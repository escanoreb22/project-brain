<!-- pb:template - delete this line only when every section holds project facts or "N/A - reason"; plan_check ignores files that still carry it -->
# CI/CD

## Branch Strategy
- trunk-based / GitFlow / other

## Pull Request Gates
- lint
- unit tests
- integration tests
- security scan
- build
- migration check

## Build
- immutable artifact
- version/tag
- dependency lock

## Deployment
- staging
- production approval
- rolling / blue-green / canary

## Database Migrations
Rules:
- backward compatible first
- avoid long locks
- backfill separately
- remove old fields later

## Rollback
- application
- config
- feature flag
- forward-fix for irreversible DB changes

## Secrets
No secrets in repository or CI logs.
