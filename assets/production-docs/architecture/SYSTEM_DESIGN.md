<!-- pb:template - delete this line only when every section holds project facts or "N/A - reason"; plan_check ignores files that still carry it -->
# System Design

## 1. Architecture Drivers
رتب حسب الأولوية:
- Correctness
- Availability
- Latency
- Throughput
- Security
- Auditability
- Cost
- Maintainability
- Time-to-market

## 2. Constraints
- Team
- Budget
- Hosting
- Languages
- Regulatory
- Legacy dependencies

## 3. High-Level Architecture
وثّق:
- Clients
- API
- Workers
- Databases
- Cache
- Queue
- Storage
- External services

## 4. Critical Flows
لكل flow:
- Entry
- Sync steps
- Async steps
- Transaction boundary
- Failure points
- Recovery

## 5. Communication Model
- HTTP
- WebSocket
- Queue
- Events
- Scheduled jobs

## 6. Consistency Model
حدد strong vs eventual per domain.

## 7. Caching
- What is cached?
- Key design
- TTL
- Invalidation
- Source of truth

## 8. Concurrency
- Duplicate requests
- Race conditions
- Locks
- Optimistic concurrency
- Idempotency

## 9. Resilience
- Timeouts
- Retries
- Backoff
- Circuit breakers
- Dead-letter queues
- Fallbacks

## 10. Capacity Planning
- Peak traffic
- DB growth
- Queue volume
- Media/storage growth

## 11. Single Points of Failure
List all SPOFs and accepted risk.

## 12. Evolution Plan
ما الذي يحتاج إعادة تصميم عند 10x أو 100x load؟
