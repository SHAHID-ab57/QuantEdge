# packages/

Shared, reusable libraries consumed across multiple services and apps.

## Future Contents

- `contracts/` — Versioned cross-service contracts (events, commands, queries, types)
- `config/` — Configuration loading and validation
- `logging/` — Structured logging infrastructure
- `observability/` — Metrics, traces, monitoring helpers
- `testing/` — Shared test utilities and fixtures
- `errors/` — Error classification and handling primitives

## Rules

- No domain semantics — generic infrastructure only.
- Two-consumer rule: created only when at least two consumers exist.
- See `docs/architecture/RepositoryStructure.md` for shared code policy.
