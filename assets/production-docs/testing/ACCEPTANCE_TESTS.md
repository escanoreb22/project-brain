<!-- pb:template - delete this line only when every section holds project facts or "N/A - reason"; plan_check ignores files that still carry it -->
# Acceptance Tests

اربط كل اختبار بـ Requirement ID.

## Template

### TEST-001 — [Name]
**Requirement:** FR-xxx / BR-xxx

```gherkin
Given ...
And ...
When ...
Then ...
And ...
```

Every FR and BR id needs at least one TEST that names it (`plan_check` reports the untested ones).

## Categories
- Happy path
- Validation
- Authorization
- Concurrency
- Duplicate requests
- Timeout
- Recovery
- Edge cases
