# infra/

Infrastructure-as-code definitions describing the platform's deployment environment.

## Future Contents

- `environments/` — Per-environment configuration (`dev`, `staging`, `prod`)
- `modules/` — Reusable infrastructure modules
- `base/` — Foundation infrastructure definitions

## Rules

- No application code or domain logic.
- Deployment and provisioning configuration only.
- See `docs/architecture/RepositoryStructure.md` for the complete organization.
