# configs/

Repository-level, shared tooling configuration consumed across the codebase.

## Contents

Canonical shared tooling configuration lives at the **repository root** so that CLI
tools and editor extensions auto-discover it:

| Tool | Canonical location |
|---|---|
| Commitlint (Conventional Commits) | `commitlint.config.mjs` |
| Prettier (formatting) | `.prettierrc.json` |
| ESLint (shared linting) | `eslint.config.mjs` |
| Markdownlint | `.markdownlint.json` |
| Secret scanning | `.gitleaks.toml` |
| Staged checks | `lint-staged.config.mjs` |

This directory hosts additional repository-level tooling that is not auto-discovered
by tools, including commit templates and non-standard tooling configuration.

## Rules

- No runtime application configuration.
- No secrets or environment-specific values.
- See `docs/architecture/RepositoryStructure.md` and `docs/DevelopmentSetup.md`.
