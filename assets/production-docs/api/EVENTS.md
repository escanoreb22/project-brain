<!-- pb:template - delete this line only when every section holds project facts or "N/A - reason"; plan_check ignores files that still carry it -->
# Events and Queues

| Event | Producer | Consumers | Payload | Idempotency key | Outbox? | Retry / DLQ |
|---|---|---|---|---|---|---|

Rules: every consumer tolerates duplicates and out-of-order delivery; side effects decided inside a DB transaction go through the outbox.
