<!-- pb:template - delete this line only when every section holds project facts or "N/A - reason"; plan_check ignores files that still carry it -->
# Webhook Design

## Inbound Webhooks
لكل provider:
- Endpoint
- Signature algorithm
- Timestamp tolerance
- Replay protection
- Event IDs
- Idempotency
- Payload retention

## Processing Pattern
```text
Receive
→ Verify signature
→ Persist event
→ Respond quickly
→ Queue
→ Process
→ Record result
```

## Retries
يجب تحمل duplicate and out-of-order events.

## Outbound Webhooks
- Signing
- Delivery IDs
- Retry schedule
- Max attempts
- Dead-letter state
- Customer observability
