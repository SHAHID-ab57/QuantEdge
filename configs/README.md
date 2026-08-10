# configs/

Repository-level, shared tooling and configuration strategy consumed across the
codebase.

## Contents

Canonical shared tooling configuration lives at the **repository root** so that CLI
tools and editor extensions auto-discover it:

| Tool                              | Canonical location          |
| --------------------------------- | --------------------------- |
| Commitlint (Conventional Commits) | `commitlint.config.mjs`     |
| Prettier (formatting)             | `.prettierrc.json`          |
| ESLint (shared linting)           | `eslint.config.mjs`         |
| Markdownlint                      | `.markdownlint.json`        |
| Secret scanning                   | `.gitleaks.toml`            |
| Staged checks                     | `lint-staged.config.mjs`    |
| Docker environment template       | `infra/docker/.env.example` |

This directory hosts repository-level configuration documentation:

- This README — the centralized configuration strategy
- `environment.example.md` — the reference catalog of environment variables

---

## Purpose

This document defines how environment variables are named, organized, loaded,
validated, and protected across the monorepo. Every future service — frontend,
backend, AI/ML, and workers — must follow these conventions so that configuration
behavior is predictable across development, testing, staging, and production.

---

## Environment Variable Naming Conventions

All environment variables are `UPPER_SNAKE_CASE` and prefixed by owning domain.

| Prefix            | Domain                          | Examples                                               |
| ----------------- | ------------------------------- | ------------------------------------------------------ |
| `APP_`            | Application-level configuration | `APP_ENV`, `APP_PORT`, `APP_LOG_LEVEL`                 |
| `DB_`             | Database connection             | `DB_URL`, `DB_POOL_SIZE`, `DB_TIMEOUT`                 |
| `REDIS_`          | Redis connection                | `REDIS_URL`, `REDIS_PASSWORD`, `REDIS_TTL`             |
| `JWT_`            | Authentication                  | `JWT_SECRET`, `JWT_EXPIRATION_MINUTES`                 |
| `DELTA_`          | Delta Exchange India            | `DELTA_API_KEY`, `DELTA_API_SECRET`, `DELTA_BASE_URL`  |
| `COINGECKO_`      | CoinGecko provider              | `COINGECKO_API_KEY`, `COINGECKO_BASE_URL`              |
| `MARKETAUX_`      | Marketaux provider              | `MARKETAUX_API_KEY`, `MARKETAUX_BASE_URL`              |
| `ETHERSCAN_`      | Etherscan provider              | `ETHERSCAN_API_KEY`, `ETHERSCAN_BASE_URL`              |
| `FRED_`           | FRED provider                   | `FRED_API_KEY`, `FRED_BASE_URL`                        |
| `DEFILLAMA_`      | DefiLlama provider              | `DEFILLAMA_BASE_URL`                                   |
| `OPENAI_`         | OpenAI provider                 | `OPENAI_API_KEY`, `OPENAI_MODEL`                       |
| `LOG_`            | Logging                         | `LOG_LEVEL`, `LOG_FORMAT`, `LOG_OUTPUT`                |
| `AI_`             | AI/ML services                  | `AI_MODEL_DIR`, `AI_BATCH_SIZE`, `AI_EXPERIMENT_DIR`   |
| `FEATURE_`        | Feature pipeline                | `FEATURE_STORE_URL`, `FEATURE_BATCH_SIZE`              |
| `SMTP_`           | Notifications                   | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` |
| `OBJECT_STORAGE_` | Object storage                  | `OBJECT_STORAGE_ENDPOINT`, `OBJECT_STORAGE_BUCKET`     |

**Rules:**

- Every variable belongs to exactly one prefix.
- Prefixes describe the owning domain, never the consuming service.
- Values are never hardcoded in source; configuration is read from the
  environment at startup.
- Boolean values use lowercase `true` / `false`.
- Ports are integers; URLs are full connection strings.
- All variables are catalogued in `configs/environment.example.md`.

---

## Configuration Hierarchy

Configuration is resolved in the following order (highest precedence first):

```text
Global defaults
      ↓
Service-level defaults
      ↓
Environment (dev / test / staging / prod)
      ↓
Runtime override
```

| Layer                  | Description                                      | Where it lives                                      |
| ---------------------- | ------------------------------------------------ | --------------------------------------------------- |
| Global defaults        | Values shared by all services                    | `configs/` and shared packages                      |
| Service-level defaults | Values specific to a service, applied by default | The service's own configuration module              |
| Environment            | Environment-specific overrides                   | `.env` files (local) or platform-managed (deployed) |
| Runtime override       | Values provided at launch or deploy time         | CLI flags, deployment manifests, runtime injection  |

**Rules:**

- Global defaults never contain secrets.
- Service defaults never override environment values.
- Environment values always win over defaults.
- Runtime overrides win over environment values.
- Every layer is explicit; no silent configuration.

---

## Configuration Loading Strategy

Services load configuration in a consistent sequence:

1. **Declare defaults.** Each service declares its global and service-level
   default values in its configuration module.
2. **Resolve environment.** The active environment is read from `APP_ENV`
   (`development`, `test`, `staging`, `production`).
3. **Inject variables.** Values are injected from the environment: `.env`
   files in local development, platform secrets and environment in deployed
   environments.
4. **Centralize parsing.** The shared configuration package performs parsing,
   type coercion, and defaulting — services never parse raw variables
   themselves.
5. **Validate before use.** Configuration is validated at startup; invalid
   configuration fails fast (see Validation Strategy).

**Loading rules:**

- Every service reads configuration once at startup; no mid-runtime reload
  except where explicitly designed.
- Missing optional variables fall back to documented defaults only when a
  default is declared.
- Missing required variables fail startup with a descriptive error.

---

## Secrets Policy

**What must never be committed:**

- API keys, tokens, passwords, private keys, or seed phrases.
- `.env` files (git-ignored; only `.env.example` variants are committed).
- Connection strings containing embedded credentials.
- Certificate or key artifacts (`.pem`, `.key`, `.p12`, `.pfx`).

**Secret rotation principles:**

- Rotate secrets on a defined schedule and immediately on suspected exposure.
- Use versioned secret management in production.
- No secret is shared across environments.
- Rotation is transparent to services — secrets come from the environment or
  secret manager, never from code.

**Local development strategy:**

- Developers maintain an untracked `.env` beside the relevant
  `.env.example` templates (root and `infra/docker/`).
- Infrastructure passwords follow the same policy as application secrets.
- gitleaks scans commit; see `docs/DevelopmentSetup.md` for secret scanning.

---

## Validation Strategy

At startup, every service config validation runs the following checks:

1. **Completeness** — every required variable is present; missing values are
   reported with the exact variable name.
2. **Type correctness** — values are parsed and coerced (integers, booleans,
   durations, URLs); coercion failures fail startup.
3. **Range checks** — numeric settings (ports, sizes, timeouts) fall within
   documented bounds.
4. **Format validation** — URLs, keys, and other formatted values match their
   expected patterns.
5. **Secret presence** — secrets required for the active environment must be
   present; no silent defaults.

Validation fails fast: a service must never start partially configured.

---

## Documentation

### How Developers Create Local Environments

1. Copy the template: `cp .env.example .env`.
2. Fill in values; generate strong passwords with `openssl rand -base64 32`.
3. Start infrastructure: `docker compose -f infra/docker/docker-compose.yml up -d`.
4. Run services; they read `.env` automatically — never commit it.

### How Production Differs

- No `.env` files; variables are injected by the platform secret manager.
- Secrets are audited, rotated, and scoped per environment.
- Services fail fast if required configuration is absent.
- Configuration changes follow a change-management process.

### Best Practices

- One variable per line; names aligned; documented; locality explicit.
- Prefer full connection URLs over assembling them in code.
- Route all loading through `packages/config`.
- Keep `.env.example` templates in sync with code and this catalog.
- Validate before use; fail fast with actionable messages.

### Common Mistakes

- Committing `.env` without removing it from staging.
- Building URLs from fragments at call time instead of full config values.
- Silently defaulting when a required secret is missing.
- Duplicating variable names across packages.
- Adding variables without updating the catalog templates.
