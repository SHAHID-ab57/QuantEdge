# Event-Loop Separation Design (2026-09-26)

**Purpose:** design real separation between background scheduled work and
the API's request-serving event loop — the confirmed root cause behind the
still-recurring `StopLossTakeProfitMonitor` DB connection timeouts
(`docs/infrastructure/WORKER_HEADROOM_CHECK.md`). Design only — nothing in
this document has been implemented. A recommendation is given, but the
choice is the user's.

## Grounding: what actually runs where today

Everything lives in one `Runtime` composition root
(`services/api/app/runtime.py`), built once per process and driven entirely
by the single uvicorn worker's one event loop (`services/api/Dockerfile`'s
`CMD` has no `--workers` flag; `app/application.py`'s `lifespan` calls
`start_runtime()`/`shutdown_runtime()` directly). Reading `Runtime.__init__`
and `Runtime.start()` closely, the eight background/live components split
into two groups by a real dependency, not a naming convention:

**Group 1 — coupled to the live in-process state (bus/`MarketStateManager`),
fed by the single Delta WebSocket connection:**

| Component                                                          | Coupling                                                                                    |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| `StopLossTakeProfitMonitor`                                        | constructed with `state_manager=`, `.attach(self.bus)` — reacts to every trade/ticker event |
| `OrderFlowCapture`                                                 | constructed with `aggregator=self.order_book` (built off the same bus), `.attach(self.bus)` |
| `PaperTradingStrategyScheduler`                                    | constructed with `state_manager=` — reads the live price to decide entries/exits            |
| `PaperFundingScheduler`                                            | constructed with `state_manager=` — same                                                    |
| The Delta WS client + `MarketDataPipeline` + `MarketStreamGateway` | the live feed itself and its one browser-facing push channel                                |

**Group 2 — independent interval-based pollers, DB/REST-only, no
dependency on `bus` or `state_manager` at all (confirmed directly from
their constructor calls in `Runtime.start()`):**

| Component                    | Constructor args                                                                   |
| ---------------------------- | ---------------------------------------------------------------------------------- |
| `CandleSyncScheduler`        | `interval_seconds`, `backfill_days`                                                |
| `PredictionGradingScheduler` | `interval_seconds`                                                                 |
| `ExternalDataSyncScheduler`  | `sources`, `interval_seconds`, `backfill_days`                                     |
| `NewsSyncScheduler`          | `interval_seconds`, `backfill_days`                                                |
| `RetrainingScheduler`        | `targets`, `window_hours`, `min_retrain_interval_seconds`, `tick_interval_seconds` |

This split matters because it directly explains the real evidence already
gathered: the two measured `TimeoutError` failures were tightly correlated
with a **candle-ingestion burst** (`CandleSyncScheduler`, Group 2) — a
component that has no architectural reason to share a process with the live
feed and the monitor at all. The task's own framing (treat all named
schedulers as one bucket) doesn't hold up under the actual code — Group 1
and Group 2 have fundamentally different separability, and that changes
which options are actually low-risk.

## Option 1 — One new process, move everything named in the task

New `docker-compose` service (mirroring the existing `migrate` service's
pattern: same build context/Dockerfile as `api`, different `command`) runs
_all_ of candle-sync, order-flow capture, the strategy scheduler, the
funding scheduler, retraining, and the monitor.

**Real blocker found during investigation:** Group 1 components don't just
run on a schedule — they read live in-memory state (`MarketStateManager`,
the order book aggregator) that only exists inside the process holding the
actual Delta WebSocket connection. Moving them to a second process means
one of:

- A second, independent Delta WS connection in the new process — this is
  exactly the anti-pattern already documented in `DEPLOYMENT.md`'s known
  gotcha (the live feed can't be naively duplicated: double-subscribing to
  the same channels, double the exchange-side connection count, and now
  two independently-drifting copies of "the latest price").
- Building a cross-process live-state bridge (e.g., Redis pub/sub — Redis
  is already deployed infrastructure, already wired into `api`'s
  `REDIS_URL`, but not consumed by any app code yet per this project's own
  state docs — this would be its first real use) so the new process
  mirrors `MarketStateManager` from events published by the process that
  owns the real connection.

Either path is a substantial, separate design problem in its own right —
not something to fold into this task silently. Also note: `OrderFlowCapture`
specifically depends on `OrderBookAggregator`, itself built from the same
bus — same blocker applies to it, not just the monitor and the two
strategy schedulers.

**Change size:** large. `Runtime` would need to become two different
composition roots (or one with a process-role switch), plus a new bridge
mechanism for Group 1. Higher effort than it looks at first glance.

**Failure mode:** if solved correctly, a crash in the new process leaves
`api` fully able to serve requests and (for whichever Group 1 pieces stayed
behind) keep trading safety checks running; whatever moved into the new
process (open positions' stop-loss/take-profit checks, if the monitor
moved) would go dark until the process/bridge recovers — a real, higher-
stakes outage than a batch job pausing, since it's a trading safety check,
not a data-freshness one.

## Option 2 — Multiple uvicorn workers + Redis leader-election

Run `api` with `--workers N`; guard scheduler startup (all of it, Group 1
and Group 2) behind a Redis-backed lock so exactly one worker actually
builds/starts them, spreading HTTP handling across the other workers.

**Real blocker found during investigation:** `Runtime` is a per-process
singleton (`app/runtime.py`'s module-level `_runtime`). Uvicorn workers are
separate OS processes with no shared memory — each would build its own
`Runtime`. If only the elected leader's `Runtime.start()` actually connects
the live feed and runs the Group 1 components, then the other N-1 workers
serving HTTP requests would have an **empty, permanently-stale**
`MarketStateManager`/`EventBus`. That's not a hypothetical — this app's own
request handlers read that in-memory state directly: `/api/v1/ws/market`
(the browser-facing live gateway) and `/api/v1/system/status`'s live
connection/freshness fields would return empty or stale data whenever a
request happens to land on a non-leader worker. Fixing this requires the
_same_ live-state broadcast bridge Option 1 needs, plus a Redis lock/lease
with proper TTL and re-election handling (a naive one-time claim risks a
window with zero or two leaders during a crash/restart).

**Change size:** largest of the three. It retrofits leader-awareness and a
live-state bridge into every HTTP-serving worker, on top of adding the lock
itself (the first real use of the existing `redis` dependency) — more
surface than cleanly separating by process role.

**Failure mode:** if the leader worker crashes, some other worker must win
a re-election and reconnect the live feed; until it does, every worker
(leader included, mid-transition) risks serving stale live-state reads —
a wider blast radius than Option 1, because the staleness is visible on
_any_ request, not just requests specifically routed to a separated
process.

## Option 3 — Split by the dependency that actually exists (recommended)

Move only **Group 2** (candle-sync, prediction-grading, external-data-sync,
news-sync, retraining) into a new `scheduler` docker-compose service —
same build context and Dockerfile as `api`, a different `command`, exactly
mirroring the `migrate` service's already-proven pattern in this exact
compose file. Group 1 (the monitor, order-flow capture, the two live-state-
coupled schedulers, and the WS client itself) stays in `api`, unchanged.

This is not the naive reading of the task's own component list, but it's
the one actually grounded in what's separable today without inventing a
new cross-process state-sharing mechanism. It also directly targets the
one failure mode with real measured evidence: the candle-ingestion burst
that coincided with both observed `TimeoutError`s.

**Change size:** smallest by a wide margin. `Runtime.start()`/`shutdown()`
lose the five `if settings.X_enabled:` blocks that build Group 2 — nothing
else in `Runtime` changes, because Group 1 already doesn't touch Group 2's
code paths. A new small entrypoint (e.g. `app/scheduler_main.py`) builds
just those five schedulers directly from settings and awaits a shutdown
signal, reusing every scheduler class completely unmodified — they already
depend only on `get_engine()`/settings, never on `Runtime`, `bus`, or
`state_manager`.

**Failure mode:** if the new `scheduler` process crashes, candle-sync,
grading, external-data-sync, news-sync, and retraining simply stop ticking.
`api` keeps serving requests and keeps running the monitor/strategy/funding
checks completely unaffected — those never depended on this process.
Whatever the DB last had stays fully readable (e.g., `/markets/{symbol}/
candles` reads from the DB, not live state); the visible effect of an
outage is growing staleness in candle/news/external data, not a trading
safety gap. Concretely new: this process has no HTTP port, so it can't
reuse `api`'s existing `urllib.request` healthcheck — it needs its own
liveness signal (e.g. a heartbeat-file touch per tick) before this ships,
which is an implementation detail for the follow-up build task, not solved
here.

**Operational notes for whoever builds this:**

- `docker compose build api migrate` already has to run together today
  because they share a build context but get separate image tags (a bug
  that has bitten this project's own deploys twice — see git history). A
  third service (`scheduler`) sharing that same context makes this a
  three-way rule: `docker compose build api migrate scheduler`.
- Each process gets its own `get_engine()` singleton and its own
  connection pool. Two processes means two pools against the same
  Postgres instance instead of one — worth confirming Postgres's
  `max_connections` comfortably covers both before shipping (current
  usage sits at ~11 connections against a default limit an order of
  magnitude higher, so this is a check, not an expected problem).

**What this does not solve:** the strategy scheduler, funding scheduler,
order-flow capture, and the monitor still share `api`'s one event loop with
the live feed. If contention from those (rather than from candle-sync)
turns out to still cause timeouts after this change ships, that's the
Option 1/2 problem — deferred, not solved, and worth a real measurement
pass (mirroring `WORKER_HEADROOM_CHECK.md`'s method) after Option 3 is live
before assuming it's fully resolved.

## Recommendation

**Option 3.** It's the smallest real change, it doesn't require inventing a
new cross-process live-state bridge, it reuses a pattern already proven in
this exact compose file (`migrate`), and it directly removes the one
component with actual measured correlation to the production incident.
Options 1 and 2 both look simpler than they are until the live-state
coupling is accounted for — each would end up building the same missing
piece (a Redis-based live-state bridge) as a prerequisite, which is a
bigger and separate decision than "move some background loops."

If Option 3 doesn't fully eliminate the timeout pattern once measured
post-deploy, the live-state bridge becomes a deliberate, scoped follow-up
task — not something to build speculatively now.
