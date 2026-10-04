<!-- pb:template - delete this line only when every section holds project facts or "N/A - reason"; plan_check ignores files that still carry it -->
# Software Architecture

## 1. Chosen Architecture Style
مثال:
- Modular Monolith
- Hexagonal
- Clean Architecture
- Event-driven
- Microservices

## 2. Why This Style
- Context
- Alternatives
- Trade-offs

## 3. Module Structure
```text
Module
├── Domain
├── Application
├── Infrastructure
└── Interface/API
```

## 4. Dependency Rules
```text
Interface → Application → Domain
Infrastructure implements ports defined inward.
```

ممنوع:
- Domain يعتمد على framework
- Domain يعتمد مباشرة على payment provider/Redis/HTTP (أي مزود دفع يمر عبر adapter خلف PaymentProvider)
- Cross-module writes بلا contract

## 5. Module Ownership
| Module | Owns | Public Interface | Forbidden Access |
|---|---|---|---|
| | | | |

## 6. Shared Kernel
حدد فقط الأشياء المسموح بمشاركتها.

## 7. Error Model
- Domain errors
- Application errors
- Infrastructure errors
- Mapping to transport errors

## 8. Configuration
- Code vs config
- Environment-specific config
- Feature flags

## 9. Architecture Fitness Rules
- No business logic in controllers
- No cross-domain DB mutation
- External calls require timeout
- Jobs must be idempotent
- Critical actions audited
