# apps/

Deployable application entry points — the runnable systems that compose services and
packages into working applications.

## Future Contents

- `web/` — Frontend application
- `api/` — Backend API service
- `workers/` — Background worker processes
- `cli/` — Operator command-line tooling

## Rules

- Contains composition and wiring only — no domain logic.
- Application-level configuration and startup concerns live here.
- See `docs/architecture/RepositoryStructure.md` for the complete organization.
