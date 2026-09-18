# Deployment

## Purpose

This document describes how this platform is actually deployed today, not
how a mature deployment process would eventually look. It exists so the
next deploy (by this same person, or anyone else who picks this up) doesn't
have to rediscover, by hand, the same bugs and gotchas the first real
deployment surfaced. Audience today: a solo operator deploying by hand over
SSH — there is no team, no on-call rotation, and no automation standing
between a `git push` and production.

## Status

One production deployment has been completed and verified as of
2026-09-18. The `api` and `web` containers on the production droplet are
running commit `d009d1b` on `dev`. The process is entirely manual — there
is no CI/CD, so "deployed" means someone ran the commands in
[Deployment procedure](#deployment-procedure) by hand and confirmed the
result. This is not "Complete" in any permanent sense: the next deploy
still requires a human to SSH in and run the same steps correctly.

## Overview

The stack is four containers on one machine, orchestrated by
`infra/docker/docker-compose.yml`:

- `web` — the Next.js 15 dashboard (`apps/dashboard`), served standalone on
  port 3000.
- `api` — the FastAPI backend (`services/api`), served by a single
  `uvicorn` process on port 8000.
- `postgres` — PostgreSQL 17 (`postgres:17-alpine`).
- `redis` — Redis 7 (`redis:7-alpine`), used for rate limiting, login
  lockout, and token revocation.

Plus one one-shot `migrate` service (see
[Deployment procedure](#deployment-procedure)). All four/five services run
on a single DigitalOcean droplet, on one Docker bridge network. There is no
load balancer, no reverse proxy, and no multi-instance setup — `web` and
`api` are each a single container.

**Real architectural constraint discovered during today's deploy**: the
`api` container's `uvicorn` process is started with no `--workers` flag
(`services/api/Dockerfile`'s `CMD`) — a single ASGI worker. That same
process also owns the live Delta Exchange WebSocket feed and every
background scheduler (candle sync, external-data sync, news sync,
prediction grading, paper-trading strategy, order-flow capture) via
`app/runtime.py`'s `Runtime` composition root. Naively adding
`--workers N` would duplicate the live WS connection and every scheduler
N-fold across worker processes — a real redesign, not a config flag. This
constraint is **not yet documented in `ARCHITECTURE.md`** — that file's own
"Deployment View" section still says "No production deployment topology is
defined anywhere in this repository yet," and its "Scalability Strategy"
section is an unwritten placeholder (`> To be completed in future tasks.`).
Today it exists only in this session's commit messages (notably
`d009d1b`, `c32d777`) and here.

## Environments

**Production** — one DigitalOcean droplet ("the production droplet"). Its
IP address is deliberately not written into this file, or anywhere else in
this repository; it is kept in the operator's own private notes. Current
verified spec: 2 vCPUs, 3.8 GiB RAM, 77 GiB disk, DigitalOcean region
`nyc1` (confirmed live via SSH — `nproc`, `free -h`, `df -h`, and the
droplet metadata service).

**Staging** — does not exist. There is no environment between a developer's
machine and production.

## Deployment procedure

The stack is deployed with `docker compose -f infra/docker/docker-compose.yml`,
run from the repository root on the production droplet (`~/app`, checked
out on `dev`). Three real gotchas below were each hit for the first time
during today's deploy — they are not hypothetical.

**Backend (`services/api`) change:**

```bash
git pull
docker compose -f infra/docker/docker-compose.yml build --no-cache api
docker compose -f infra/docker/docker-compose.yml up -d api
```

`up -d` — not `restart` — matters here for a concrete reason hit today:
`docker compose restart api` restarts the existing container with its
existing environment baked in; it does **not** re-read `services/api/.env`
(the `env_file` the `api` service loads). A CORS fix that only changed
`.env` (`CORS_ORIGINS`) had no effect until the container was recreated
with `up -d`, which does pick up `env_file` changes. If only `.env` changed
and the image itself didn't, `up -d api` alone (no rebuild) is enough —
recreating the container is what re-reads the env file; rebuilding the
image is only needed when the image's own contents (code, dependencies)
changed.

**Frontend (`apps/dashboard`) change:**

```bash
git pull
docker compose -f infra/docker/docker-compose.yml build --no-cache web
docker compose -f infra/docker/docker-compose.yml up -d web
```

Same `build` vs `up -d` split, plus two gotchas specific to the frontend
that today's session hit and fixed (commits `f3d63f3`, `af8a7c9`):

- Next.js's `NEXT_PUBLIC_*` variables are inlined into the client bundle
  **at build time only** — setting them as container runtime environment
  variables after the fact does nothing. `docker-compose.yml`'s `web`
  service passes them as Docker build `args`
  (`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_APP_NAME`, `NEXT_PUBLIC_WS_URL`),
  and `apps/dashboard/Dockerfile` must explicitly convert each `ARG` to an
  `ENV` before the `RUN pnpm --filter @eth-ai/dashboard build` step, or
  the build step's own `process.env` never sees them and the build falls
  back to `env.ts`'s hardcoded defaults, silently.
- Separately, `apps/dashboard/src/config/env.ts` must reference each
  `NEXT_PUBLIC_*` variable **by its literal name**
  (`process.env.NEXT_PUBLIC_API_URL`, not a spread or dynamic lookup over
  the whole `process.env` object) — Next's inlining pass is a static
  find-and-replace over source text, so anything that reads the value
  indirectly defeats it even if the build-arg/env plumbing above is
  correct. Confirmed live during today's session: a build with a
  distinctive test value produced a bundle with zero occurrences of it
  until this was fixed.

A related edit was found live on the server during this pass, only in its
working tree and not in git history (`git status --porcelain` on the
server showed `M turbo.json`, uncommitted): `turbo.json`'s `build` task
carried a task-level `env` array declaring the three `NEXT_PUBLIC_*`
variables. Investigated directly rather than assumed: the production
Docker build does **not** actually go through Turborepo at
all — `apps/dashboard/Dockerfile` runs
`pnpm --filter @eth-ai/dashboard build`, which executes the dashboard
package's own `build` script (`apps/dashboard/package.json`: plain
`"next build"`, confirmed) directly via pnpm's own workspace filtering,
never invoking `turbo run build`. So this `turbo.json` edit is **not**
what fixes `NEXT_PUBLIC_*` inlining in the Docker deploy path described
above — that's fully explained by the two Dockerfile/`env.ts` fixes above
alone. The `turbo.json` edit is still a real, harmless correctness
improvement for Turborepo's own build cache (it tells Turbo these
variables affect the `build` task's output, relevant if anyone ever runs
`pnpm build`/`turbo run build` directly, e.g. locally without Docker) —
committed into this repo as part of writing this document, so it isn't
silently lost on the next `git pull` from the server.

**Database migrations:** the `migrate` service in `docker-compose.yml`
runs `alembic upgrade head` once and exits; `api` declares
`depends_on: migrate: condition: service_completed_successfully`, so it
runs automatically on every `docker compose up -d api` — there is no
separate manual migration step. It is idempotent: running it again with
nothing new to migrate is a no-op exit 0, confirmed by design (Alembic's
own version-tracking table) and by repeated real runs during today's
session.

**Why a full rebuild vs. just `up -d`:** `build` is needed whenever the
image's own contents change — application code, dependencies
(`uv.lock`/`pnpm-lock.yaml`), or the Dockerfile itself. `up -d` alone
(no rebuild) is sufficient when only compose-level runtime configuration
changed — `environment:` values in `docker-compose.yml`, or the contents
of a mounted/`env_file`-referenced file like `services/api/.env` — because
recreating the container re-reads those without needing a new image.

## CI/CD Pipeline

None exists. There is no `.github/` directory and no CI configuration of
any kind in this repository. Every deploy today is a person running the
commands in [Deployment procedure](#deployment-procedure) by hand over
SSH. Local git hooks (Husky — lint-staged, commitlint, gitleaks,
`prettier --check`/`markdownlint` on push) are the only automated quality
gate that exists anywhere in this project, and they run on the
developer's own machine, not in any shared pipeline.

## Infrastructure

The production droplet is a single DigitalOcean VM: 2 vCPUs, 3.8 GiB RAM,
77 GiB disk (confirmed live via SSH). It runs all four containers
(`postgres`, `redis`, `api`, `web`) plus the one-shot `migrate` job.

Sizing rationale, evidenced directly by today's own investigation rather
than assumed: candle-heavy Postgres queries on a 1.36M-row table
(`ETHUSD`/`1m`) were measured costing ~1.5s of database time per
`/candles` request before today's fixes, and a chart page's own concurrent
fetch pattern (up to 10 simultaneous page requests) was enough to push
individual request latency to 25–30s on this box before the frontend
concurrency limit and stats/quality caching fixes (commits `833ed4b`,
`c32d777`, `d009d1b`) landed. At the time of writing, live load on the
droplet is `1.73, 1.35, 1.68` (1/5/15-minute load average on 2 cores,
via `uptime`).

**Open note, not yet resolved**: earlier in this same session, the droplet
was observed under meaningfully higher load than the level measured above
— `docker stats` showed the `api` container at ~36% CPU even at rest, and
host `uptime` showed a load average of `4.69, 4.02, 2.54` on these same 2
cores, versus `1.73, 1.35, 1.68` now. Whether the droplet's size was
changed at any point, and whether its current size reflects a deliberate
steady-state decision or simply whatever it was left at, is **not
something this pass could independently verify** — there is no
DigitalOcean API/`doctl` access from this environment, only SSH into the
running machine, and no resize history is visible from inside it. Flagging
this rather than asserting a specific resize history: it's worth
deliberately re-evaluating the droplet's size once the query-cost and
concurrency fixes above have been running for a while at real usage
levels.

There is no documented performance write-up elsewhere in this repo
(`TASKBOOK.md`, `STATE.md`, and `ARCHITECTURE.md` were all checked and
contain no reference to this investigation) — the commit messages above
are the only record of it.

## Known gotchas

Concrete issues hit during today's deploy that aren't permanently fixed at
the root — read this before the next deploy so none of these are
rediscovered the hard way:

- **`docker compose restart` does not pick up `env_file` changes.**
  `up -d` recreates the container (which re-reads `env_file`); `restart`
  does not. This bit a CORS fix today. See
  [Deployment procedure](#deployment-procedure).
- **Model artifact volume.** `services/api/.dockerignore` excludes `var/`
  from the Docker build context on purpose (it held ~1.9 GB of dev-machine
  debris before this session's cleanup), which means the `api` container's
  `/app/var/model_artifacts` is an empty directory unless explicitly bind
  -mounted. `docker-compose.yml`'s `api` service now has
  `../../services/api/var/model_artifacts:/app/var/model_artifacts` as a
  bind mount (commit `ace3ddd`) — confirm this line is still present
  before the next deploy; if it's ever removed, paper trading's automated
  strategy will fail with a real `FileNotFoundError` on every prediction,
  exactly as it did in production before this fix. The real artifact set
  (~47 MB / 210 files) still has to be present on the host path
  separately — the bind mount doesn't create or sync the data itself.
- **Stats/quality caching is a 30-second, in-process cache, not a
  permanent fix.** `get_candle_stats`, `count_invalid_ohlc`, and
  `count_out_of_order` (`app/repositories/candles.py`) still run full
  scans over the requested range on a cache miss — the 30s TTL cache
  (`_ANALYTICS_CACHE`) only collapses concurrent identical requests (e.g.
  one chart page's own 10 parallel page fetches) into one real
  computation. This is fine at today's low, single-operator traffic;
  revisit before multi-user load, since the underlying query cost hasn't
  been reduced, only its repetition.
- **Single-worker/live-feed constraint.** See
  [Overview](#overview) — this API cannot safely run multiple `uvicorn`
  workers without first redesigning which process owns the live Delta
  WebSocket feed and the background schedulers. Don't add `--workers N`
  to the Dockerfile's `CMD` as a quick scaling fix; it will duplicate the
  live feed and every scheduler once per worker.

## Monitoring & Alerting

Nothing beyond manual checks exists. There is no metrics collection, no
log aggregation, no uptime monitoring, and no alerting configured anywhere
for the production droplet. The only ways to check on the system today
are:

- `docker compose -f infra/docker/docker-compose.yml logs -f <service>`,
  run manually over SSH.
- `docker compose -f infra/docker/docker-compose.yml ps` / `docker stats`
  for container health and resource usage.
- `GET /api/v1/health` (liveness + DB connectivity) and
  `GET /api/v1/system/health` / `/system/status` (per-component status:
  API, database, Delta REST/WS, event bus, state manager) — polled
  manually, not by any external monitor.

## Rollback Strategy

What's actually possible today:

- **Code rollback**: `git checkout <previous-commit>` on the production
  droplet's `~/app`, followed by the same `build`/`up -d` steps in
  [Deployment procedure](#deployment-procedure) for whichever service(s)
  changed. This is a manual, multi-minute operation (a full `--no-cache`
  image rebuild), not an instant switch.
- **Database rollback**: `alembic downgrade -1` (or a specific revision)
  can be run manually against the same database the `migrate` service
  targets, using the same image (`make db-downgrade REV=-1` locally, or
  the equivalent `docker compose run --rm migrate alembic downgrade -1`
  on the server). No automated migration rollback runs as part of any
  deploy — a bad migration has to be downgraded by hand.
- **Database restore from backup**: there is no automated backup process
  and no `sync_local_to_server.sh` or equivalent script anywhere in this
  repository (checked directly — `scripts/` contains only a placeholder
  `README.md`, and `services/api/scripts/` has no backup/restore script).
  The only documented restore procedure is the manual one in `STATE.md`
  §5: `pg_dump`/`pg_restore` run **inside** the `eth-postgres` container
  (the host's own `pg_dump` client is a mismatched major version and
  fails against this project's Postgres 17), producing a timestamped
  dump file that has to be moved and restored by hand. No scheduled or
  automatic database backup currently runs on the production droplet.

What isn't possible: no blue/green or canary deployment, no automated
rollback trigger, no traffic shifting — there is exactly one droplet and
one running copy of each service, so any rollback is a manual, in-place
replacement with brief downtime while the container rebuilds/recreates.
