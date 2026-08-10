# Docker Development Infrastructure

Local development infrastructure for the platform using Docker Compose.

## Overview

This directory provides the infrastructure services required for local development:

- **PostgreSQL** — relational database (port `5432`)
- **Redis** — in-memory store / cache / broker (port `6379`)

Application services (FastAPI backend, Next.js frontend, background workers) are
intentionally **not** defined yet. Placeholder examples are included in
`docker-compose.yml` showing the pattern each future service will follow.

## Prerequisites

- Docker Engine with Compose v2 (`docker compose version`)
- No other Docker configuration is required for the infrastructure

## Quick Start

1. Prepare environment variables:

   ```bash
   cp infra/docker/.env.example infra/docker/.env
   ```

   Edit `.env` with your own strong passwords. The file is git-ignored; the
   example file contains placeholders only.

2. Start the infrastructure:

   ```bash
   docker compose -f infra/docker/docker-compose.yml up -d
   ```

3. Verify service health:

   ```bash
   docker compose -f infra/docker/docker-compose.yml ps
   ```

   Both services report a healthy status once their health checks pass.

## How to Start

```bash
docker compose -f infra/docker/docker-compose.yml up -d
```

## How to Stop

Stop the containers while keeping data volumes:

```bash
docker compose -f infra/docker/docker-compose.yml stop
```

Bring the stack down (containers removed, volumes retained):

```bash
docker compose -f infra/docker/docker-compose.yml down
```

## How to Reset

**Warning:** the following command destroys all data in the named volumes
(`postgres-data`, `redis-data`). Use only when a clean slate is intended:

```bash
docker compose -f infra/docker/docker-compose.yml down -v
```

Afterward, start the stack again with `up -d`.

## Volumes

Named volumes persist data independently of container lifecycle:

| Volume              | Backs                     | Purpose                   |
| ------------------- | ------------------------- | ------------------------- |
| `eth-postgres-data` | PostgreSQL data directory | Persistent database files |
| `eth-redis-data`    | Redis data directory      | AOF snapshot persistence  |

### Backup (PostgreSQL)

```bash
docker exec eth-postgres pg_dump -U <POSTGRES_USER> <POSTGRES_DB> > backup.sql
```

### Restore (PostgreSQL)

```bash
cat backup.sql | docker exec -i eth-postgres psql -U <POSTGRES_USER> <POSTGRES_DB>
```

### Inspect volumes

```bash
docker volume ls | grep eth-
```

## Networking

All services share the dedicated bridge network `eth-platform-net`. Future
application services attach to this network and reach infrastructure by service
name:

- `postgres` — resolves to the PostgreSQL container
- `redis` — resolves to the Redis container

Example connection strings inside the network:

- PostgreSQL: `postgresql://<user>:<password>@postgres:5432/<db>`
- Redis: `redis://:<password>@redis:6379`

From the host, connect using the published ports (`localhost:5432`,
`localhost:6379`).

## Health Checks

- **PostgreSQL:** `pg_isready` against the configured user and database.
- **Redis:** `redis-cli ping` authenticated with the configured password.

Health status is visible via `docker compose ps`. Future application services
should declare `depends_on` with `condition: service_healthy` so they wait for
infrastructure readiness.

## Future Expansion

To add an application service:

1. Create its Dockerfile (e.g., `apps/api/Dockerfile`, `apps/web/Dockerfile`).
2. Uncomment or add its service block in `docker-compose.yml`, joining
   `eth-platform-net` and depending on `postgres`/`redis` health.
3. Add host port mappings as needed (e.g., `API_PORT`, `WEB_PORT`).
4. Add the corresponding variables to `.env.example`.

Example patterns are already present as commented sections in
`docker-compose.yml`.

## Notes

- The compose file is `name: eth-ai-platform`; the project name includes stack
  isolation if multiple environments are run side by side.
- Passwords are read from the environment; the compose file never hardcodes
  credentials. Unset required variables cause Compose to fail fast.
- Production deployment is out of scope for this file; see
  `docs/deployment/DEPLOYMENT.md` for the deployment strategy.
