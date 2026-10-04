<!-- pb:template - delete this line only when every section holds project facts or "N/A - reason"; plan_check ignores files that still carry it -->
# Deployment Architecture

> Owner default: CloudPanel VPS behind Cloudflare (WAF/TLS/CDN), PHP-FPM app, queue workers via supervisor, scheduler cron, Inertia SSR process, MySQL 8.4, Redis. Replace only with an ADR.

## 1. Environments
- Local
- Test
- Staging
- Production
- Preview (optional)

## 2. Runtime Components
- CDN/WAF
- Load balancer
- App instances
- Workers
- Scheduler
- MySQL 8.4 (owner default; PostgreSQL only with an ADR)
- Redis
- Queue broker
- Object storage
- Search
- Observability

## 3. Deployment Diagram
Add C4 Deployment / infrastructure diagram.

## 4. Statelessness
حدد ما إذا كانت app instances stateless.

## 5. Scaling
| Component | Horizontal | Vertical | Trigger |
|---|---|---|---|
| | | | |

## 6. Networking
- Public endpoints
- Private services
- Firewall/security groups
- TLS termination

## 7. Zero-Downtime
- Rolling / blue-green / canary
- Backward-compatible DB migrations

## 8. Rollback
- Application rollback
- Migration rollback/forward-fix
- Feature flag disable
