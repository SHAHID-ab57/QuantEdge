# Eth AI Platform

A professional AI-powered Ethereum Market Analysis and Probabilistic Prediction
Platform for research, education, and decision support.

## Overview

The platform collects, processes, and analyzes Ethereum market data to produce
probabilistic forecasts and quantitative research outputs. It combines quantitative
finance, machine learning, data engineering, and production software engineering
into a single, modular system.

The platform does not provide financial advice and does not guarantee profitable
trading. All outputs are analytical inputs intended to support informed,
evidence-based decision-making.

## Repository Philosophy

- **Architecture-first.** Design is documented before implementation begins.
- **Bounded context ownership.** Domain code lives exclusively within its owning
  service; cross-service communication happens only through versioned contracts.
- **Reproducible research.** Every experiment, dataset, and model is versioned,
  documented, and traceable.
- **Probabilistic thinking.** Uncertainty is measured and communicated honestly;
  nothing is presented as a guaranteed prediction.
- **Professional engineering.** Quality gates, documentation, and standards apply
  to every change.

## Directory Overview

| Directory   | Purpose                                                                  |
| ----------- | ------------------------------------------------------------------------ |
| `apps/`     | Deployable application entry points (web, api, workers, cli)             |
| `services/` | One directory per bounded context — the platform's domain implementation |
| `packages/` | Shared, reusable libraries (contracts, config, logging, observability)   |
| `infra/`    | Infrastructure-as-code definitions                                       |
| `configs/`  | Repository-level tooling configuration                                   |
| `docs/`     | All platform documentation                                               |
| `scripts/`  | Automation and maintenance scripts                                       |
| `tests/`    | Cross-cutting integration and end-to-end tests                           |
| `tools/`    | Developer tooling and scaffolding utilities                              |

## Getting Started

### Prerequisites

| Tool    | Minimum Version               |
| ------- | ----------------------------- |
| Node.js | 20+                           |
| pnpm    | 9+                            |
| Python  | 3.11+ (future AI/ML services) |

### Install Dependencies

```bash
pnpm install
```

Installation triggers the `prepare` script, which wires the Git hooks via Husky.
If hooks are not active, enable them explicitly:

```bash
git config core.hooksPath .husky
```

### Workspace Commands

Scripts are orchestrated with Turbo; tasks run across all workspace packages
(`apps/*`, `services/*`, `packages/*`, `tools/*`).

| Command             | Purpose                                    |
| ------------------- | ------------------------------------------ |
| `pnpm dev`          | Run all packages in development mode       |
| `pnpm build`        | Build all packages in dependency order     |
| `pnpm lint`         | Lint all packages                          |
| `pnpm lint:fix`     | Lint and autofix all packages              |
| `pnpm format`       | Format the entire repository with Prettier |
| `pnpm format:check` | Verify formatting                          |
| `pnpm test`         | Run tests across all packages              |
| `pnpm typecheck`    | Type-check all packages                    |
| `pnpm check`        | Run lint and typecheck together            |
| `pnpm clean`        | Remove build artifacts across all packages |
| `pnpm docs:lint`    | Lint documentation with markdownlint       |

### Workspace Structure

- `pnpm-workspace.yaml` defines the workspace packages.
- `turbo.json` defines the task graph (build order, caching, outputs).
- `tsconfig.base.json` provides the shared TypeScript base configuration;
  packages extend it and may override compiler options as needed.
- Dependencies between workspace packages are declared in each package's
  manifest using the `workspace:` protocol.

## Development Status

**Planning Phase** — The repository is in the early planning and documentation
stage. Architecture, requirements, and engineering standards are being established.
The workspace foundation is in place; no application code has been created yet.

Progress is tracked in `TASKBOOK.md`; decisions are recorded in `DECISIONS.md`.

## License

License to be determined.
