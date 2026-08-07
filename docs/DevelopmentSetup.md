# Development Setup

## Purpose

This document describes the required tools, workflow, and expectations for
contributing to the platform. All engineering conventions referenced here are
defined in `docs/architecture/EngineeringStandards.md`.

## Required Tools

| Tool | Purpose | Minimum Version |
|---|---|---|
| Git | Version control | 2.40+ |
| Node.js | Node-based tooling (commitlint, prettier, eslint, markdownlint, husky) | 20+ |
| npm | Package management for tooling | 10+ |
| Python | AI/ML services and research tooling | 3.11+ |
| gitleaks | Secret scanning | Latest |

Optional: Docker (future containerized development), a code editor with the
workspace recommendations (see `.vscode/extensions.json`).

## Initial Setup

1. Clone the repository.
2. Install the Node-based development tools:

   ```bash
   npm install --save-dev husky commitlint @commitlint/cli @commitlint/config-conventional lint-staged prettier eslint @eslint/js markdownlint-cli2
   ```

3. Install gitleaks (see https://github.com/gitleaks/gitleaks) and ensure it is on
   `PATH`.
4. Enable the Git hooks:

   ```bash
   git config core.hooksPath .husky
   ```

   (Alternatively, once Husky is installed, run `npx husky init`.)
5. Install the recommended VS Code extensions when prompted, or run:
   `code --install-extension <extension-id>` for each entry in
   `.vscode/extensions.json`.

## Git Workflow

- The main branch is always releasable; work happens on short-lived feature
  branches.
- Branch naming follows the taskbook convention:

  ```
  {type}/{task-id}-{short-description}
  ```

  Example: `feature/M2-E1-T3-MT1-feature-store-api`

- One logical change per commit; each commit references its task ID in the body.
- Merges to main happen only through reviewed pull requests.

## Commit Workflow

Commits follow Conventional Commits, enforced by commitlint via the `commit-msg`
hook:

```
{type}({scope}): {description}
```

Allowed types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `build`,
`perf`, `style`.

Examples:

- `feat(market-data): add order book collection`
- `fix(prediction): correct calibration computation`
- `docs(architecture): update container diagram`

Rules:

- The subject is imperative and concise (max 100 characters).
- The scope names the affected area (service, package, or domain).
- Breaking changes use `!` and are described in the body.
- The body explains the why; task IDs are referenced as `Task: M2-E1-T3-MT1`.

## Formatting

- Prettier is the single source of formatting truth; configuration lives in
  `.prettierrc.json` (100 columns, 2-space indent, single quotes, semicolons,
  LF endings).
- Format on save is enabled in the workspace settings.
- Manual checks:
  - `npx prettier --check .`
  - `npx prettier --write .`
- EditorConfig (`.editorconfig`) applies the same basics to all editors.

## Linting

- **ESLint** (`eslint.config.mjs`) — shared, framework-agnostic rules for
  JavaScript and TypeScript. Run with `npx eslint .`.
- **Markdownlint** (`.markdownlint.json`) — documentation linting. Run with
  `npx markdownlint '**/*.md'`.
- **Python (Ruff)** — to be configured when Python services are added; the Ruff
  VS Code extension is already recommended.
- Linting runs automatically on staged files via lint-staged.

## Git Hooks

Hooks live in `.husky/` and are enabled by setting `core.hooksPath`:

| Hook | Trigger | Checks |
|---|---|---|
| `pre-commit` | Before each commit | lint-staged (eslint, prettier, markdownlint on staged files) and gitleaks secret scan |
| `commit-msg` | After commit message entry | commitlint (Conventional Commits) |
| `pre-push` | Before pushing | prettier --check, markdownlint on documentation |

If a tool is not installed, hooks fail with a message pointing to this document.
Tools are invoked through `npx --no-install` so the hook uses only locally
installed versions.

## Secret Scanning

- **gitleaks** scans staged content on every commit via the pre-commit hook.
- Configuration lives in `.gitleaks.toml`; environment example placeholders are
  allowlisted by design.
- Manual scan of the full repository:

  ```bash
  gitleaks detect --source . --config .gitleaks.toml --no-banner
  ```

- Never commit real secrets, keys, or credentials. Environment variables are
  supplied through local `.env` files (never committed) or secret management
  infrastructure.

## Development Expectations

- Read `docs/architecture/EngineeringStandards.md` before the first contribution;
  it is the contract for how the codebase is written.
- Follow the repository organization defined in
  `docs/architecture/RepositoryStructure.md`.
- Every change includes tests and documentation where appropriate; quality gates
  run in CI and locally via hooks.
- Track work in `TASKBOOK.md`; record architectural decisions in `DECISIONS.md`.
- Work in small, reviewable increments; complete reviews before marking tasks
  completed.
