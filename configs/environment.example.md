# Environment Variable Reference

**Superseded for anything actually implemented — see below before trusting a
row in this file.** This document previously tried to be the canonical
catalog for both real, currently-read variables and future/aspirational
ones in one mixed list, using a naming scheme that had drifted from the
real code (`JWT_SECRET` vs. the real `JWT_SECRET_KEY`, `DELTA_WEBSOCKET_URL`
vs. the real `DELTA_WS_URL`/`DELTA_WS_PRIVATE_URL`, `DB_TIMEOUT` which no
field reads at all, and no mention whatsoever of candles/pagination/
rate-limiting/lockout/paper-trading/order-flow, all real and implemented).
Fixed as part of the audit in `STATE.md` §4 — see that file for the full
account of what was wrong and why.

## For anything real and currently implemented, use the source of truth directly

- **`services/api/.env.example`** — every one of the 106 real, typed
  settings `services/api/app/core/config.py` actually reads, generated
  directly from that file, grouped by section, with real code-level
  defaults shown as comments and secrets left blank with instructions.
  This is now the only place that list should be maintained — duplicating
  it here would just create a second copy to keep in sync, which is
  exactly how this file went stale the first time.
- **`apps/dashboard/.env.example`** — the 3 real frontend variables
  (`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`, `NEXT_PUBLIC_APP_NAME`).
  Already accurate; unchanged by this pass.
- **`infra/docker/.env.example`** — the 6 real Docker Compose variables
  (`POSTGRES_*`, `REDIS_*`). Already accurate; unchanged by this pass.

## Not yet implemented — genuinely future, not currently read by anything

Kept here (not in `services/api/.env.example`, which documents only what
exists today) because these name real target-state work described in
`docs/architecture/ContainerArchitecture.md`/`DataArchitecture.md`, not
invented placeholders. Confirmed absent from the codebase as of this pass
(no `OPENAI_API_KEY`, `AI_MODEL_DIR`, or `FEATURE_STORE_URL` read
anywhere in `services/api/app`) — do not treat any of these as configurable
yet.

| Variable             | Would gate                                                                                                                                                                                                |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `OPENAI_API_KEY`     | An LLM-backed service — none exists yet.                                                                                                                                                                  |
| `OPENAI_MODEL`       | Same.                                                                                                                                                                                                     |
| `AI_MODEL_DIR`       | A model-artifact store distinct from the real, already-implemented `MODEL_ARTIFACT_DIR` (`services/api/.env.example`) — would only matter if/when a _separate_ AI service is split out of `services/api`. |
| `AI_BATCH_SIZE`      | Same future-service scope.                                                                                                                                                                                |
| `AI_EXPERIMENT_DIR`  | Same future-service scope — distinct from the real, already-implemented Experiment Management System, which stores experiments in Postgres, not a directory.                                              |
| `FEATURE_STORE_URL`  | The Feature Store bounded context (`ContainerArchitecture.md`) — target-state, confirmed not built (`STATE.md`/`docs/PROJECT_STATE.md`).                                                                  |
| `FEATURE_BATCH_SIZE` | Same.                                                                                                                                                                                                     |
| `LOG_FORMAT`         | Structured (JSON) logging — real logging today is `logging.basicConfig` only, no format switch exists.                                                                                                    |
| `LOG_OUTPUT`         | Same — no log-destination config exists today.                                                                                                                                                            |

## Removed from this file — real names were simply wrong

Previously listed under invented or mismatched names; the _real_ variable
now lives correctly in `services/api/.env.example`, so it isn't repeated
here: `JWT_SECRET`→real `JWT_SECRET_KEY`, `DELTA_WEBSOCKET_URL`→real
`DELTA_WS_URL`/`DELTA_WS_PRIVATE_URL`, `DB_TIMEOUT` (no such field —
`DB_POOL_SIZE`/`DB_MAX_OVERFLOW` are the real pool-shaped settings),
`REDIS_TTL` (no such field — Redis-backed TTLs are computed per-mechanism
in code, not one global setting).

See `configs/README.md` for the monorepo's naming/hierarchy/loading
conventions — its prefix table is illustrative of the pattern (`JWT_`,
`DB_`, etc.), not a field-by-field catalog, but note its own `JWT_`/`DB_`/
`REDIS_` example values (`JWT_SECRET`, `DB_TIMEOUT`, `REDIS_TTL`) share
this same now-fixed naming drift and weren't in this task's scope to
correct — worth a follow-up pass.
