<!-- pb:template - delete this line only when every section holds project facts or "N/A - reason"; plan_check ignores files that still carry it -->
# Production Readiness Checklist

> Tick an item only with evidence on the same line: `- [x] Rate limits - evidence: tests/Feature/RateLimitTest.php, routes/api.php:12`. `plan_check --gate production` counts a tick without `evidence:` as unticked.

## Product
- [ ] PRD approved
- [ ] Business rules documented
- [ ] Acceptance criteria complete
- [ ] Out-of-scope clear

## Domain
- [ ] Entities defined
- [ ] Ownership defined
- [ ] State machines documented
- [ ] Invariants enforced

## Architecture
- [ ] Architecture drivers known
- [ ] Boundaries clear
- [ ] Dependency rules clear
- [ ] Failure modes reviewed
- [ ] SPOFs known

## Database
- [ ] Constraints
- [ ] Indexes based on access patterns
- [ ] Transactions
- [ ] Concurrency strategy
- [ ] Backup/restore tested

## API
- [ ] OpenAPI/contracts
- [ ] Stable errors
- [ ] AuthN/AuthZ
- [ ] Pagination
- [ ] Rate limits
- [ ] Idempotency
- [ ] Versioning

## Security
- [ ] Threat model
- [ ] Secrets management
- [ ] Tenant isolation
- [ ] PII handling
- [ ] Audit logs

## Reliability
- [ ] Timeouts
- [ ] Retries/backoff
- [ ] DLQ
- [ ] Outbox where required
- [ ] External provider failures handled

## Operations
- [ ] Logs
- [ ] Metrics
- [ ] Traces
- [ ] Alerts
- [ ] SLOs
- [ ] Incident process

## Deployment
- [ ] CI/CD
- [ ] Staging
- [ ] Zero-downtime migration approach
- [ ] Rollback
- [ ] Feature flags where useful

## Testing
- [ ] Unit
- [ ] Integration
- [ ] API
- [ ] Contract
- [ ] Critical E2E
- [ ] Load
- [ ] Security
- [ ] Migration

## Release
- [ ] Runbook
- [ ] Ownership
- [ ] Monitoring dashboard
- [ ] Support process
- [ ] Post-release validation
