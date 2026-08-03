# Repository Structure

## Document Information

**Document:** Repository Structure — Monorepo Organization

**Scope:** Complete directory layout for the platform's source repository

**Status:** Draft

**Related documents:** DomainModel.md (Bounded Contexts), ContainerArchitecture.md
(C4 Level 2), TASKBOOK.md (Implementation Backlog)

---

## 1. Complete Repository Tree

```
platform/
├── apps/                          # Deployable application entry points
│   ├── web/                       # Frontend application
│   ├── api/                       # Backend API service
│   ├── workers/                   # Background worker processes
│   └── cli/                       # Operator command-line tooling
├── services/                      # One directory per bounded context
│   ├── identity/                  # BC1 — Identity & Access Management
│   ├── market-data/               # BC2 — Market Data
│   ├── features/                  # BC3 — Feature Engineering
│   ├── research/                  # BC4 — AI Research & Training
│   ├── prediction/                # BC5 — Prediction
│   ├── strategy/                  # BC6 — Strategy Management
│   ├── backtesting/               # BC7 — Backtesting
│   ├── execution/                 # BC8 — Trading Execution
│   ├── portfolio/                 # BC9 — Portfolio Management
│   ├── risk/                      # BC10 — Risk Management
│   ├── analytics/                 # BC11 — Analytics & Reporting
│   ├── notifications/             # BC12 — Notifications
│   └── operations/                # BC13 — Administration & Operations
├── packages/                      # Shared, reusable libraries
│   ├── contracts/                 # Versioned cross-service contracts
│   ├── config/                    # Configuration loading and validation
│   ├── logging/                   # Structured logging infrastructure
│   ├── observability/             # Metrics, traces, monitoring helpers
│   ├── testing/                   # Shared test utilities and fixtures
│   └── errors/                    # Error classification and handling
├── infra/                         # Infrastructure as code
│   ├── environments/              # Per-environment configuration
│   ├── modules/                   # Reusable infrastructure modules
│   └── base/                      # Foundation infrastructure definitions
├── configs/                       # Shared repository-level configuration
│   ├── lint/                      # Linting rules
│   ├── formatting/                # Formatting rules
│   ├── static-analysis/           # Static analysis rules
│   └── commit/                    # Commit conventions and templates
├── docs/                          # Platform documentation
│   ├── architecture/              # Architecture documents (C4, domains, data)
│   ├── api/                       # API documentation
│   ├── database/                  # Database documentation
│   ├── ai/                        # AI and research documentation
│   ├── deployment/                # Deployment documentation
│   ├── testing/                   # Testing documentation
│   ├── decisions/                 # Architecture Decision Records
│   ├── roadmap/                   # Roadmap documentation
│   └── assets/                    # Diagrams and media assets
├── tests/                         # Cross-cutting integration and E2E tests
├── scripts/                       # Automation and maintenance scripts
├── tools/                         # Developer tooling and utilities
├── .github/                       # CI/CD workflows and contribution templates
├── README.md                      # Project overview
├── PROJECT.md                     # Project charter
├── TASKBOOK.md                    # Master implementation backlog
├── REQUIREMENTS.md                # Software requirements specification
├── DECISIONS.md                   # Architecture Decision Record log
├── ARCHITECTURE.md                # Architecture overview index
├── ROADMAP.md                     # High-level roadmap
└── CHANGELOG.md                   # Version history
```

---

## 2. Directory Explanations

### `apps/`

**Purpose:** Home of deployable application entry points — the runnable systems that
compose services and packages into working applications.

**What belongs there:**
- Application entry points and bootstrapping logic.
- Composition and wiring of services and packages.
- Application-level configuration and startup concerns.
- Application-level tests.

**What should never be placed there:**
- Domain logic, business rules, or data access code.
- Code owned by a bounded context.
- Reusable libraries (these belong in `packages/`).
- Infrastructure definitions (these belong in `infra/`).

### `services/`

**Purpose:** Home of the platform's domain implementation — one directory per bounded
context. This is the primary location of platform code.

**What belongs there:**
- Complete domain implementation per context: domain model, application logic,
  data access, and infrastructure adapters.
- Service-local tests.
- Service-local configuration defaults.

**What should never be placed there:**
- Code from another bounded context.
- Application entry points (these belong in `apps/`).
- Shared libraries (these belong in `packages/`).
- Cross-service test suites (these belong in `tests/`).

### `packages/`

**Purpose:** Home of reusable libraries shared across multiple services and apps.

**What belongs there:**
- Versioned cross-service contracts (events, commands, queries, types).
- Generic infrastructure: configuration, logging, observability, testing, errors.
- Any library with at least two consumers and no domain semantics.

**What should never be placed there:**
- Domain models or business rules.
- Context-specific logic.
- Application entry points.
- Code with a single consumer (it belongs with that consumer).

### `infra/`

**Purpose:** Home of infrastructure-as-code definitions describing the deployment
environment.

**What belongs there:**
- Environment definitions (`dev`, `staging`, `prod`).
- Reusable infrastructure modules.
- Foundation infrastructure (networking, base services).
- Deployment and provisioning configuration.

**What should never be placed there:**
- Application code or domain logic.
- Shared libraries.
- Repository-level tooling configuration (this belongs in `configs/`).

### `configs/`

**Purpose:** Home of repository-level, shared configuration consumed across the
codebase.

**What belongs there:**
- Linting rules and tool configuration.
- Formatting rules.
- Static analysis rules.
- Commit conventions and templates.

**What should never be placed there:**
- Runtime application configuration (this belongs in `apps/` or `services/`).
- Secret or environment-specific values (these belong in `infra/`).
- Infrastructure definitions.
- Source code.

### `docs/`

**Purpose:** Home of all platform documentation, organized by discipline.

**What belongs there:**
- Architecture documents.
- API, database, AI, deployment, and testing documentation.
- Architecture Decision Records.
- Roadmap and planning documentation.
- Diagrams and media assets.

**What should never be placed there:**
- Source code.
- Generated build artifacts.
- Personal notes or ephemeral documents.
- Documentation generated automatically by tooling at build time.

### `tests/`

**Purpose:** Home of tests that span multiple services — integration tests,
end-to-end tests, and cross-cutting validation suites.

**What belongs there:**
- Cross-service integration tests.
- End-to-end workflows.
- Performance and load test suites.
- Shared test infrastructure spanning multiple services.

**What should never be placed there:**
- Service-local unit tests (these live inside the service).
- Test utilities intended for reuse (these belong in `packages/testing/`).

### `scripts/`

**Purpose:** Home of automation scripts for repository maintenance, local development,
and operational tasks.

**What belongs there:**
- Development setup scripts.
- Repository maintenance utilities.
- Operational automation invoked by developers and CI.

**What should never be placed there:**
- Application code.
- Production-grade tooling with a UI (these belong in `apps/` or `tools/`).
- One-off personal scripts.

### `tools/`

**Purpose:** Home of developer tooling and utilities that support development
without being part of the runtime platform.

**What belongs there:**
- Scaffolding and generator tooling.
- Custom developer utilities.
- Code generation helpers.

**What should never be placed there:**
- Runtime platform components.
- Infrastructure definitions.
- Repository configuration (this belongs in `configs/`).

### `.github/`

**Purpose:** Home of CI/CD workflow definitions and contribution templates.

**What belongs there:**
- CI/CD pipeline definitions.
- Contribution and issue templates.
- Repository automation configuration.

**What should never be placed there:**
- Application code.
- Domain logic.
- Documentation content (this belongs in `docs/`).

### Root-level files

**Purpose:** Project-level governance and documentation.

**What belongs there:**
- `README.md` — project overview.
- `PROJECT.md` — project charter.
- `TASKBOOK.md` — master implementation backlog.
- `REQUIREMENTS.md` — software requirements specification.
- `DECISIONS.md` — architecture decision record log.
- `ARCHITECTURE.md` — architecture overview index.
- `ROADMAP.md` — high-level roadmap.
- `CHANGELOG.md` — version history.

**What should never be placed there:**
- Source code.
- Additional documentation that fits an existing directory.
- Generated artifacts.

---

## 3. Repository Organization Rules

### Shared Code Policy

- **Share contracts, not implementations.** Cross-service communication happens only
  through versioned contract artifacts in `packages/contracts/`.
- **Never share domain models.** If two contexts need the same domain concept, each
  context owns its model; only contracts cross boundaries.
- **Two-consumer rule.** A new package is created only when at least two consumers
  exist or the package is platform-wide infrastructure.
- **No domain semantics in packages.** Packages contain generic infrastructure only.

### Import Direction

Dependencies flow downward and never upward:

```
apps/  →  services/  →  packages/  →  external dependencies
```

- Apps may depend on services and packages.
- Services may depend on packages and on other services only through contracts.
- Packages may never depend on services or apps.
- No circular dependencies are permitted between packages.
- No service may import another service's internal implementation.

### Dependency Boundaries

- A service's internals are private to that service.
- All cross-service interaction occurs through `packages/contracts/`.
- `infra/`, `configs/`, and `scripts/` contain no code that services import at
  runtime.
- Contract changes require version bumps and coordinated consumer migration.
- Dependency boundaries are enforced by automated checks in CI.

### Package Ownership

- `services/<context>/` — owned exclusively by that bounded context.
- `packages/<library>/` — shared ownership by platform engineering; changes require
  review by all affected consumers.
- `apps/<app>/` — owned by platform engineering; composition only.
- `infra/` — owned by platform engineering.
- `docs/` — owned by each contributor for their area.
- No directory has multiple owners; every directory has a single accountable owner.

### Folder Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Directories | kebab-case, lowercase | `market-data`, `feature-store` |
| Services | Named after their bounded context | `services/prediction/` |
| Packages | Single descriptive word or kebab-case | `contracts`, `observability` |
| Contract artifacts | `{domain}-{event\|command\|query}-{name}` | `prediction-forecast-produced` |
| Event names | Past-tense domain events | `forecast-produced`, `order-filled` |
| Command names | Imperative domain commands | `submit-order`, `retrain-model` |
| Query names | Descriptive noun phrases | `get-portfolio-state` |
| Environments | Lowercase, single word | `dev`, `staging`, `prod` |
| Infrastructure modules | Descriptive kebab-case | `data-store`, `message-backbone` |

**Naming principles:**

- Names describe responsibilities, not technologies.
- Names remain stable across the project lifecycle.
- Public artifacts (contracts, APIs) follow stricter naming review than private
  implementation details.

---

## 4. Future Expansion Strategy

The repository is designed so that growth never requires restructuring the
four code categories: `apps/`, `services/`, `packages/`, and `infra/`.

**Adding a new application:**

1. Add a directory under `apps/` named for its purpose.
2. Compose existing services and packages; implement no domain logic in the app.
3. Extend contracts first if new cross-service communication is required.
4. Register the app in `infra/` and `.github/` configuration.

**Adding a new service (bounded context):**

1. Add a directory under `services/` named after the context.
2. Define the context's contracts in `packages/contracts/` before implementation.
3. Implement the domain model and application logic within the directory.
4. Register the service in `infra/` and CI configuration.
5. Add documentation under `docs/` and tasks to `TASKBOOK.md`.

**Adding a new shared library:**

1. Add a directory under `packages/` following naming conventions.
2. Confirm the two-consumer rule or platform-wide infrastructure need.
3. Document the package's responsibilities and relationships.

**Adding new configuration or infrastructure:**

1. Repository-level configuration joins `configs/`.
2. Environment configuration joins `infra/environments/`.
3. Reusable infrastructure joins `infra/modules/`.

**General expansion rules:**

- New components integrate through existing contracts; no structural reorganization
  is required.
- Directory categories are stable; no new top-level category is anticipated.
- Every addition updates the repository documentation and taskbook.

---

## 5. Repository Maintenance Guidelines

1. **Enforce boundaries in CI.** Automated checks verify import direction,
   dependency boundaries, and the absence of cross-service internal imports.

2. **Contract versioning discipline.** Breaking contract changes are scheduled,
   versioned, and migrated with all consumers — never silent.

3. **Small, reviewable changes.** Each change targets a single directory; broad
   changes are decomposed into sequential, reviewable commits.

4. **Quality gates.** Linting, formatting, static analysis, and tests run on every
   change; coverage requirements are defined per service.

5. **Ownership documentation.** Every service, package, and app maintains a concise
   README stating its responsibility, boundaries, and owner.

6. **Central dependency management.** Shared dependencies are managed centrally;
   upgrades are reviewed for impact across all consumers.

7. **Periodic structure reviews.** The repository layout is reviewed against the
   architecture documents to detect and correct drift.

8. **Automated scaffolding.** New services, packages, and apps are created through
   tooling that enforces the conventions defined in this document.

9. **Taskbook synchronization.** Every structural change updates `TASKBOOK.md` so
   the backlog reflects the repository's actual organization.

10. **Cleanup discipline.** Dead code, unused packages, and orphaned configuration
    are removed in the changes that make them obsolete — never left for later.

11. **Avoid premature extraction.** Co-deployment of services in early milestones
    is acceptable, but directory boundaries are never blurred for deployment
    convenience — boundaries exist from day one.

12. **Documentation freshness.** Changes to the repository structure update this
    document in the same change; the tree and the repository never diverge.
