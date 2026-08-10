# Engineering Standards

## Document Information

**Document:** Engineering Standards

**Scope:** Conventions every contributor must follow

**Status:** Draft

**Related documents:** RepositoryStructure.md, DomainModel.md, TASKBOOK.md

---

## Purpose

This document defines the engineering conventions that every contributor must
follow when working in this repository. It exists to ensure consistency across
the codebase, reduce review friction, preserve maintainability over the project's
lifetime, and make the platform's code comprehensible to contributors regardless
of their background.

These standards are framework-agnostic and focus on principles rather than specific
technologies. Where tooling is referenced, it is described in terms of its purpose,
not its implementation.

Standards may evolve; changes to this document are reviewed with the same rigor as
code changes.

---

## Repository Organization Rules

1. The repository follows the structure defined in `docs/architecture/RepositoryStructure.md`.
   Every artifact lives in the directory its type requires; no exceptions.

2. Domain code belongs exclusively to its bounded context under `services/`. No
   other service, app, or package may import another service's internal
   implementation.

3. Shared code lives in `packages/` and follows the two-consumer rule: a package is
   created only when at least two consumers exist or when it is platform-wide
   infrastructure.

4. Contracts are the only permitted cross-service communication mechanism. Services
   never access each other's data directly.

5. Application entry points live in `apps/` and contain composition only — no
   domain logic.

6. Infrastructure definitions live in `infra/`; repository-level tooling
   configuration lives in `configs/`.

7. Documentation is colocated: service and package documentation lives with the
   artifact; general documentation lives in `docs/`.

8. Structural changes update the repository documentation in the same change.

---

## Naming Conventions

### Directories

- kebab-case, lowercase: `market-data`, `feature-store`.
- Named for responsibility, never for technology.
- Stable across the project lifecycle.

### Files

- kebab-case, lowercase for multi-word names: `feature-engine.ts`.
- Test files are colocated and suffixed with `.test`.
- Configuration files use the repository's standard configuration naming.

### Components

- Named for their role within their context.
- Components are nouns describing responsibility: `OrderValidator`,
  `ForecastPublisher`.
- Component names are unique within their package.

### Classes

- PascalCase: `MarketDataService`, `RiskEngine`.
- Class names describe the role, not the implementation.

### Functions

- camelCase: `computeVolatility`, `validateOrder`.
- Functions are named after what they do; booleans read as questions
  (`isValid`, `hasEnoughLiquidity`).
- One responsibility per function.

### Interfaces

- PascalCase, named after the capability they describe: `ForecastProvider`,
  `DataSink`.
- Interface names describe contracts, not implementations.

### Types

- PascalCase for named types: `OrderType`, `PredictionDistribution`.
- camelCase for values and variables.
- Type names describe the domain concept they represent.

### Environment Variables

- UPPER_SNAKE_CASE: `MARKET_DATA_API_URL`, `MAX_RETRIES`.
- Prefixed to identify their owning domain where applicable.
- Never committed; always documented in the owning service's configuration
  documentation.
- Defaults are defined in code; environment overrides only where necessary.

### Configuration Files

- Named descriptively and consistently across the repository.
- Configuration is validated at load time; invalid configuration fails fast.
- Secrets never appear in configuration files committed to the repository.

---

## Dependency Rules

### Allowed Dependency Directions

Dependencies flow downward:

```text
apps/  →  services/  →  packages/  →  external dependencies
```

- Apps may depend on services and packages.
- Services may depend on packages.
- Packages never depend on services or apps.
- Services interact with other services only through `packages/contracts/`.

### Shared Package Usage

- Shared packages are used through their public interfaces only.
- A package's internal modules are private to that package.
- New shared packages follow the two-consumer rule.
- Contract packages are versioned; consumers pin supported versions.

### Circular Dependency Policy

- Circular dependencies are prohibited at every level: between packages, between
  services, and within packages.
- Cycles are detected by automated analysis in CI.
- When a cycle is detected, the dependency is resolved by extracting the shared
  concept into a lower-level package or into contracts — never by weakening
  boundaries.

---

## Code Organization Principles

1. **Single Responsibility Principle.** Every class, function, and module has one
   clearly stated responsibility. If a component's description requires "and", it
   should be split.

2. **High cohesion.** Related behavior lives together. A module's elements belong
   together because they serve the same purpose.

3. **Loose coupling.** Components interact through well-defined interfaces and
   contracts; they know as little as possible about each other's internals.

4. **Separation of concerns.** Domain logic, application logic, and infrastructure
   adapters are separated. Cross-cutting concerns — logging, configuration,
   observability — are applied through interfaces, not interleaved.

5. **Composition over inheritance.** Behavior is assembled from composable parts
   rather than inherited through class hierarchies.

6. **Dependency inversion.** High-level policy does not depend on low-level details;
   both depend on abstractions.

7. **Fail fast.** Invalid inputs, states, and configurations are rejected at the
   boundary as early as possible.

8. **Prefer explicit over implicit.** Implicit behavior, magic values, and hidden
   state are avoided.

---

## Documentation Standards

1. Documentation is a first-class deliverable with the same review requirements
   as code.

2. Every service, package, and app maintains a README stating its responsibility,
   boundaries, and owner.

3. Public interfaces (contracts, APIs) are documented at the point of definition.

4. Complex logic is documented with the rationale, not a restatement of the code.

5. Configuration variables are documented with their purpose and defaults.

6. Architecture documentation is updated in the same change as the code it
   describes.

7. Documentation uses professional language and consistent formatting.

8. No TODOs are committed; incomplete work is tracked in `TASKBOOK.md`.

---

## Git Standards

1. The trunk-based branching model is followed; the main branch is always
   releasable.

2. One logical change per commit. Work that spans multiple commits is grouped
   into reviewable pull requests.

3. Work-in-progress code is never committed to the main branch.

4. Commits are small, self-contained, and independently revertible.

5. Each commit references the task ID from `TASKBOOK.md` where applicable.

6. Merge to main happens only through reviewed pull requests.

7. Large refactors are decomposed into sequential, reviewable changes.

---

## Branch Naming

Branches follow the pattern:

```text
{type}/{task-id}-{short-description}
```

| Element     | Convention                                            | Example             |
| ----------- | ----------------------------------------------------- | ------------------- |
| Type        | `feature`, `fix`, `refactor`, `docs`, `chore`, `test` | `feature`           |
| Task ID     | TASKBOOK identifier                                   | `M2-E1-T3-MT1`      |
| Description | Short kebab-case summary                              | `feature-store-api` |

Full example: `feature/M2-E1-T3-MT1-feature-store-api`

Branches are short-lived; long-lived branches are merged or abandoned.

---

## Commit Message Convention

Commits follow the Conventional Commits specification:

```text
{type}({scope}): {description}
```

**Types:**

| Type       | Usage                              |
| ---------- | ---------------------------------- |
| `feat`     | New capability                     |
| `fix`      | Bug correction                     |
| `refactor` | Behavior-preserving restructuring  |
| `docs`     | Documentation only                 |
| `test`     | Test additions or corrections      |
| `chore`    | Maintenance, tooling, dependencies |
| `build`    | Build or dependency configuration  |
| `ci`       | CI configuration                   |
| `perf`     | Performance improvement            |
| `style`    | Formatting, no behavior change     |

**Examples:**

- `feat(market-data): add order book collection`
- `fix(prediction): correct calibration computation`
- `refactor(risk): extract limit validation`
- `docs(architecture): update container diagram`
- `chore: upgrade shared dependencies`

**Rules:**

- The description is imperative and concise: "add", "fix", "remove".
- The scope names the affected area (service, package, or domain).
- Breaking changes are indicated with a `!` and described in the body.
- The body explains the why, not the what.
- Task IDs are referenced in the body: `Task: M2-E1-T3-MT1`.

---

## Pull Request Guidelines

1. A pull request addresses one logical change and references its task ID.

2. The pull request description explains the change, its rationale, and its
   verification.

3. Tests and documentation are included in the same pull request as the code.

4. The change must pass all CI quality gates before review.

5. Reviewers are chosen from owners of the affected areas.

6. Pull requests are kept small; large changes are split into sequential
   requests.

7. The author addresses every review comment; disagreements are resolved by
   discussion, not by dismissing comments.

8. Only reviewed and approved pull requests merge to main.

---

## Review Checklist

Reviewers verify that every change:

- [ ] Satisfies the stated task in `TASKBOOK.md`.
- [ ] Follows repository organization and naming conventions.
- [ ] Respects dependency directions and boundaries.
- [ ] Is free of circular dependencies and cross-boundary imports.
- [ ] Includes tests appropriate to the change.
- [ ] Includes or updates documentation.
- [ ] Handles errors explicitly and fails fast where appropriate.
- [ ] Contains no secrets, hardcoded credentials, or debug leftovers.
- [ ] Has a conventional commit message with task reference.
- [ ] Avoids unrelated changes.
- [ ] Is readable — names are meaningful and logic is comprehensible.
- [ ] Does not introduce regressions in covered paths.

---

## Testing Expectations

1. Behavioral changes are accompanied by tests written alongside implementation,
   never retrofitted.

2. Test types are used appropriately: unit tests for isolated logic, integration
   tests for cross-component behavior, end-to-end tests for critical workflows.

3. Tests are deterministic: no reliance on wall-clock timing, network availability,
   or shared mutable state.

4. Time-series code is tested against synthetic and curated fixtures with known
   outcomes.

5. Service-local tests live with the service; cross-cutting tests live in
   `tests/`.

6. Coverage requirements are defined per service and enforced in CI.

7. Failing tests block merge; flaky tests are fixed or removed promptly.

8. Test code follows the same standards as production code.

---

## Logging Guidelines

1. Logs are structured and machine-parseable, not free-form text.

2. Log levels are used consistently:

   | Level   | Usage                                 |
   | ------- | ------------------------------------- |
   | `debug` | Diagnostic detail for development     |
   | `info`  | Normal lifecycle events               |
   | `warn`  | Unexpected but recoverable conditions |
   | `error` | Failures requiring attention          |

3. Every log entry identifies the service, component, and operation.

4. Sensitive data — credentials, keys, personal information — is never logged.

5. Error logs include the error context: operation, inputs identifiers, and
   correlation identifiers, without dumping payloads.

6. Logging is not used for control flow; it records what happened.

7. High-frequency events log at `debug`, never `info` or above.

---

## Error Handling Principles

1. Errors are classified and handled according to type: expected domain conditions,
   infrastructure failures, and unexpected defects.

2. Fail fast at boundaries: invalid inputs are rejected at the entry point.

3. Expected conditions (e.g., unavailable data, rejected order) are represented as
   explicit results, not exceptions used for control flow.

4. Unexpected failures propagate to a boundary that handles them centrally —
   never swallowed silently.

5. Retryable failures follow defined retry policies with backoff and bounded
   attempts; non-retryable failures fail immediately.

6. Partial failures are reported explicitly; operations either succeed
   completely, fail completely, or document their partial state.

7. Error messages are actionable: they state what failed and what can be done.

8. No error handling is duplicated across layers; each layer handles what it is
   responsible for and delegates the rest.

---

## Security Principles

1. Security by design: access control, validation, and data protection are
   integrated at every layer, not added after the fact.

2. All user input is validated and treated as untrusted until proven otherwise.

3. Secrets never appear in code, configuration, or logs; secrets are managed
   through dedicated secret management infrastructure.

4. Authentication and authorization are enforced centrally through the Identity &
   Access boundary; no component implements its own access control.

5. Sensitive data is protected in transit and at rest according to its
   classification.

6. Dependencies are scanned for known vulnerabilities; updates are applied
   through the change process.

7. Least privilege: every component and user receives only the access its role
   requires.

8. Audit records capture security-relevant events: access changes, authentication
   events, and authorization denials.

9. Security findings are tracked in `TASKBOOK.md` and addressed with the priority
   their severity demands.

---

## Future Maintenance Guidelines

1. Standards evolve through the same review process as code; this document is
   version-controlled.

2. Contributors are expected to raise gaps in these standards rather than work
   around them.

3. Enforcement is automated where practical — linting, formatting, static
   analysis, and boundary checks run in CI.

4. Technical debt is tracked in `TASKBOOK.md` and `DECISIONS.md`, never left
   undocumented.

5. These standards are reviewed periodically against the architecture documents
   to ensure they remain aligned with the platform's direction.

6. New contributors are expected to read this document before their first
   contribution; it is the contract for how the codebase is written.
