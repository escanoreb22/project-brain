<!-- pb:template - delete this line only when every section holds project facts or "N/A - reason"; plan_check ignores files that still carry it -->
# Bounded Contexts

## 1. Context Map
| Context | Responsibility | Owns | Publishes | Consumes |
|---|---|---|---|---|
| | | | | |

## 2. Boundary Rules
- Context لا يعدل بيانات Context آخر مباشرة.
- Cross-context behavior يمر عبر explicit contract.
- لا يوجد shared mutable model بلا ملكية واضحة.

## 3. Integration Styles
- Direct application call
- Internal API
- Domain event
- Integration event
- Queue/message

## 4. Dependency Direction
وثّق:
```text
Context A → Context B
```
ولماذا.

## 5. Anti-Corruption Layers
استخدم Adapter عندما يكون External/Legacy model مختلفًا عن Domain model.
