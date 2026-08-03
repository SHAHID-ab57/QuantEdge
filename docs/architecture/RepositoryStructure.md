# Repository Structure

## Document Information

**Document:** Repository Structure — Monorepo Organization

**Scope:** Logical organization of the platform's source repository

**Status:** Draft

**Related documents:** DomainModel.md (Bounded Contexts), ContainerArchitecture.md
(C4 Level 2)

---

## 1. High-Level Repository Tree

```
platform/
├── apps/                          # Deployable applications (entry points)
│   ├── web/                       # Frontend application
│   ├── api/                       # Backend API service
│   ├── workers/                   # Background worker processes
│   └── cli/                       # Command-line tooling for operators
├── services/                      # One directory per bounded context service
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
│   ├── contracts/                 # Cross-service contracts (events, commands, types)
│   ├── config/                    # Configuration loading and validation
│   ├── logging/                   # Logging infrastructure
│   ├── observability/             # Metrics, traces, and monitoring helpers
│   ├── testing/                   # Shared test utilities and fixtures
│   └── errors/                    # Common error handling primitives
├── infra/                         # Infrastructure configuration
│   ├── environments/              # Per-environment configuration
│   ├── modules/                   # Reusable infrastructure modules
│   └── base/                      # Foundation infrastructure definitions
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
├── tests/                         # Cross-cutting, integration, and E2E tests
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

## 2. Purpose of Top-Level Directories

| Directory | Purpose |
|---|---|
| `apps/` | Deployable application entry points that compose services and packages into runnable systems. Contains no domain logic — only composition, wiring, and deployment concerns. |
| `services/` | One directory per bounded context. Each service owns its complete domain implementation — model, application logic, and infrastructure adapters. This is the primary location of platform code. |
| `packages/` | Reusable libraries shared across multiple services and apps. Contains only generic infrastructure with no domain semantics. |
| `infra/` | Infrastructure-as-code definitions describing the platform's deployment environment, environments, and reusable infrastructure modules. |
| `docs/` | All platform documentation, organized by discipline. |
| `tests/` | Tests that span multiple services — integration tests, end-to-end tests, and cross-cutting validation suites. Service-local tests live inside each service. |
| `scripts/` | Automation scripts for repository maintenance, local development setup, and operational tasks. |
| `tools/` | Developer tooling — generators, linters, formatting configuration, and utility applications that assist development without being part of the runtime platform. |
| `.github/` | CI/CD workflow definitions and contribution templates. |

---

## 3. Ownership and Responsibilities

**Ownership follows the bounded contexts.** Each directory in `services/` has a
single owner context. No two contexts share a service directory, and no service
directory contains code owned by another context.

| Level | Owner | Responsibilities |
|---|---|---|
| `services/<context>/` | Owning bounded context | All domain logic, application services, data access, and adapters for that context. |
| `packages/<library>/` | Platform engineering (shared ownership) | Generic infrastructure libraries; no context owns them exclusively. |
| `apps/<app>/` | Platform engineering | Composition and deployment wiring only. |
| `infra/` | Platform engineering | Environment definitions and infrastructure modules. |
| `docs/` | All contributors | Each team maintains the documentation for its area. |
| `tests/` | Platform engineering | Cross-cutting test suites; service-local tests owned by the service. |
| `scripts/`, `tools/` | Platform engineering | Shared development and automation utilities. |

**Ownership rules:**

- Domain code is never shared across services. If two services need the same domain
  concept, the concept is either duplicated deliberately within each context (DDD
  per-context models) or promoted to a contract artifact — never a shared domain
  library.
- Packages are approved for sharing only when they contain no domain semantics.
- A service's internals are private to that service; other services interact with it
  only through its published contracts.
- Changes to `packages/` require review by affected services because packages have
  multiple consumers.

---

## 4. Organizing Shared Code

**Principle: share contracts, not implementations.**

Shared code is organized into two tiers:

**Tier 1 — Contracts (`packages/contracts/`):**

- Cross-service communication artifacts: event schemas, command definitions, query
  types, and payload structures.
- Contracts are versioned. Breaking changes require a new contract version and
  coordinated migration.
- Contracts are the only shared code with cross-service semantics; they define the
  interfaces, not the behavior.

**Tier 2 — Infrastructure packages:**

- `config/` — configuration loading and validation shared by all runnable units.
- `logging/` — consistent structured logging across services.
- `observability/` — metrics and tracing emission helpers.
- `testing/` — test utilities, fixtures, and assertion helpers.
- `errors/` — error classification and handling primitives.

**Rules for shared code:**

- New packages are created only when at least two consumers exist or the package
  is infrastructure that all services require.
- Packages must not depend on services; dependencies flow downward —
  apps → services → packages.
- Packages must not depend on each other except through defined, acyclic
  relationships.
- Domain models, business rules, and context-specific utilities never belong in
  packages.
- Each package declares its responsibilities explicitly in its documentation.

---

## 5. Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Directories | kebab-case, lowercase | `market-data`, `feature-store` |
| Services | Named after their bounded context | `services/prediction/` |
| Packages | Single descriptive word or kebab-case | `contracts`, `observability` |
| Contract artifacts | `{domain}-{event|command|query}-{name}` | `prediction-forecast-produced` |
| Event names | Past-tense domain events | `forecast-produced`, `order-filled` |
| Command names | Imperative domain commands | `submit-order`, `retrain-model` |
| Query names | Descriptive noun phrases | `get-portfolio-state` |
| Task references | TASKBOOK convention | `M0-E1-T1-MT2` |
| Environment names | Lowercase, single word | `dev`, `staging`, `prod` |
| Infrastructure modules | Descriptive kebab-case | `data-store`, `message-backbone` |

**Naming principles:**

- Names describe responsibilities, not technologies.
- Names remain stable across the project lifecycle; renaming is reserved for cases
  of genuine misnaming.
- Public artifacts (contracts, APIs) follow stricter naming review than private
  implementation details.

---

## 6. Adding Future Applications and Services

**New application (entry point):**

1. Add a new directory under `apps/` named for its purpose (e.g., `apps/worker-paper-trading/`).
2. Compose existing services and packages; do not implement domain logic in the app.
3. If the app needs new cross-service communication, extend contracts first.

**New service (bounded context):**

1. Add a new directory under `services/` named after the context.
2. Define the context's contracts in `packages/contracts/` before implementation.
3. Implement the context's domain model and application logic within the directory.
4. Register the service in the appropriate infrastructure and CI configuration.
5. Add corresponding documentation under `docs/` and tasks to `TASKBOOK.md`.

**New shared library:**

1. Add a new directory under `packages/` following the naming conventions.
2. Confirm at least two consumers or platform-wide infrastructure need.
3. Document the package's responsibilities and its relationship to other packages.

**General addition rules:**

- No new top-level directory category is required for growth; the four code
  categories (`apps/`, `services/`, `packages/`, `infra/`) are stable.
- New components integrate through existing contracts; structural reorganization
  is not required.
- Each addition updates the repository documentation accordingly.

---

## 7. Repository Organization Principles

1. **Bounded context alignment.** The repository mirrors the domain model — every
   context has a clear home, and ownership is unambiguous.

2. **Dependency direction.** Dependencies flow downward: `apps/` → `services/` →
   `packages/`. Services never depend on apps; packages never depend on services.
   Cross-service dependencies occur only through contracts.

3. **No shared domain ownership.** Domain logic is never shared between services;
   each context owns its domain exclusively.

4. **Contracts as boundaries.** All cross-service communication is defined by
   versioned contract artifacts, keeping services loosely coupled.

5. **Cohesion within directories.** Code is grouped by responsibility and domain,
   not by technical layer. A service directory contains its own model, logic, and
   adapters together.

6. **Test proximity.** Service-local tests live with the service; only
   cross-cutting tests live at the repository root.

7. **Infrastructure and code separation.** Deployment configuration (`infra/`)
   is separate from application code so that neither obscures the other.

8. **Documentation colocation.** Documentation lives with the subject it describes;
   general project documents live at the root.

---

## 8. Recommendations for Maintainability

1. **Enforce ownership boundaries in CI.** Automated checks verify that services
   do not import each other's internals and that dependency direction rules are
   respected.

2. **Contract versioning discipline.** Changes to shared contracts require version
   bumps and coordinated consumer migration; breaking changes are scheduled, never
   silent.

3. **Small, reviewable changes.** Each change targets a single service, package, or
   app; cross-cutting changes are decomposed into sequential, reviewable commits.

4. **Quality gates.** Linting, formatting, static analysis, and tests run on every
   change before merge; coverage requirements are defined per service.

5. **Ownership documentation.** Each service and package maintains a concise
   README stating its responsibility, boundaries, and maintainer.

6. **Dependency hygiene.** Shared dependencies are managed centrally; dependency
   upgrades are reviewed for impact across all consumers.

7. **Regular structure reviews.** The repository layout is reviewed periodically
   against the architecture documents to detect drift between documentation and
   organization.

8. **Automated scaffolding.** New services, packages, and apps are created through
   scaffolding tooling that enforces the conventions defined here.

9. **Taskbook synchronization.** Every structural change updates `TASKBOOK.md` so
   the backlog reflects the repository's actual organization.

10. **Avoid premature extraction.** Co-deployment of services in early milestones is
    acceptable, but directory boundaries are never blurred for deployment
    convenience — boundaries exist in the repository from day one.
