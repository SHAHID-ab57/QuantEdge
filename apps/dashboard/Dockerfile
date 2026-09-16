# syntax=docker/dockerfile:1
#
# Build context is the MONOREPO ROOT, not this directory — pnpm workspaces
# need the root pnpm-lock.yaml/pnpm-workspace.yaml to resolve, even though
# the dashboard itself has zero `workspace:` dependencies today (checked:
# apps/dashboard/package.json has none — packages/ is still empty).
#
#   docker build -t eth-dashboard -f apps/dashboard/Dockerfile .
#
# Pinned to `packageManager: pnpm@11.15.1` (root package.json). Node 24,
# NOT the root package.json's stated `engines.node: >=20` floor — pnpm
# 11.15.1 itself refuses to run under Node <22.13 (confirmed live: it
# throws ERR_UNKNOWN_BUILTIN_MODULE on node:sqlite under Node 20, since
# that module doesn't exist before Node 22). The repo's own dev machine
# runs Node v24.12.0 (STATE.md §8) — this pins to that, not the stale
# `>=20` floor, which is a real discrepancy worth fixing in package.json
# separately (see STATE.md's Docker follow-up).

FROM node:24-bookworm-slim AS base
RUN corepack enable && corepack prepare pnpm@11.15.1 --activate

# --- deps: install once, cached separately from source changes ---
FROM base AS deps
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/dashboard/package.json apps/dashboard/package.json
RUN pnpm install --frozen-lockfile

# --- builder: full source, real `next build` ---
FROM base AS builder
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY --from=deps /repo/apps/dashboard/node_modules ./apps/dashboard/node_modules
COPY . .
# Consumed only at build time (baked into the static/client bundle by
# Next.js) — see apps/dashboard/.env.example; not a secret.
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_APP_NAME
ARG NEXT_PUBLIC_WS_URL
RUN pnpm --filter @eth-ai/dashboard build
# This app genuinely has no apps/dashboard/public/ directory (confirmed:
# no static-asset folder exists in the source) — Next's standalone output
# still expects one to exist to copy, so make an empty one rather than
# have the runtime stage's COPY fail on a directory nothing ever created.
RUN mkdir -p apps/dashboard/public

# --- runtime: standalone server output only (see next.config.ts) ---
FROM node:24-bookworm-slim AS runtime
RUN groupadd --system app && useradd --system --gid app --no-create-home app
WORKDIR /app

COPY --from=builder /repo/apps/dashboard/public ./public
COPY --from=builder /repo/apps/dashboard/.next/standalone ./
COPY --from=builder /repo/apps/dashboard/.next/static ./apps/dashboard/.next/static

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

USER app
EXPOSE 3000

# standalone output nests the entrypoint at the original workspace path.
CMD ["node", "apps/dashboard/server.js"]
