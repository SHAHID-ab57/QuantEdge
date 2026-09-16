# syntax=docker/dockerfile:1
#
# Build context: services/api (this directory) — the API has no internal
# workspace dependencies (packages/ is empty, per repo root README), so it
# builds standalone rather than needing the monorepo root as context.
#
#   docker build -t eth-api -f services/api/Dockerfile services/api
#
# Pinned to the same uv/Python versions verified working in STATE.md §8
# (uv 0.11.30, Python 3.13.14 via .python-version) — not "latest", so a
# rebuild months from now doesn't silently pick up a different resolver.
# astral-sh only publishes combined uv+python+distro tags for uv's *latest*
# release, so a pinned uv version has to be copied onto a plain Python
# base instead (astral's own documented pattern for this exact reason —
# confirmed live: `ghcr.io/astral-sh/uv:0.11.30-python3.13-bookworm-slim`
# 404s, `ghcr.io/astral-sh/uv:0.11.30` with just the binary exists).

FROM python:3.13-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.30 /uv /uvx /usr/local/bin/

WORKDIR /app

# Dependencies first, separately from app code, so an app-code-only change
# doesn't invalidate the (much slower) dependency-install layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY . .
RUN uv sync --locked --no-dev

# --- Runtime stage: no uv, no build tools, just the venv + app code ---
FROM python:3.13-slim-bookworm AS runtime

RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# var/model_artifacts (app/core/config.py's model_artifact_dir) is where
# completed training jobs write real .joblib artifacts — STATE.md §9 found
# 1.9GB of these in dev, entirely gitignored. Left as a plain directory
# here (not a VOLUME) so a deployer makes a deliberate choice about where
# these persist rather than getting an anonymous volume by default.
RUN mkdir -p /app/var/model_artifacts && chown -R app:app /app/var

USER app
EXPOSE 8000

# No --reload (that's a dev-only flag that also disables uvicorn's
# multi-worker/production process model) and no MARKET_DATA_LIVE default
# baked in here — whether the live Delta WS feed runs is a runtime config
# choice (see docker-compose.yml's api service and STATE.md's flagged
# issue #6 follow-up), not something to hardcode into the image.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
