<!-- pb:template - delete this line only when every section holds project facts or "N/A - reason"; plan_check ignores files that still carry it -->
# Test Strategy

## 1. Test Pyramid
- Unit
- Integration
- Contract
- API
- E2E

## 2. Unit Tests
Focus on domain rules and pure logic.

## 3. Integration Tests
- DB
- Queue
- Cache
- Storage
- External adapters via test doubles/sandbox

## 4. API Tests
Validate:
- schemas
- auth
- authorization
- errors
- idempotency
- pagination

## 5. Contract Tests
Consumer ↔ Provider compatibility.

## 6. E2E
Use only for critical journeys.

## 7. Migration Tests
Test migrations against production-like data volume.

## 8. Load Tests
- baseline
- peak
- spike
- soak
- stress

## 9. Security Tests
- auth bypass
- tenant isolation
- privilege escalation
- rate limiting
- injection
- unsafe uploads

## 10. Test Data
- deterministic
- no production secrets
- privacy-safe
