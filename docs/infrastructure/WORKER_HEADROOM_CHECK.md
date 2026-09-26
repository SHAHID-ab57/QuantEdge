# Worker Headroom Check (2026-09-26)

**Purpose:** before building Option A (volatility-informed position-size/leverage
scaling), measure real current load on the production single-worker API process
and give an evidence-based recommendation on whether it's safe to add Option A's
extra per-cycle work now, or whether the worker-architecture question needs
addressing first.

**Scope discipline:** this is a measurement and recommendation only. No code
changes were made for this check, and no architecture change was made
unprompted.

All numbers below are real, taken directly from the production droplet
(`159.223.142.72`) via `docker stats`, `docker logs`, `pg_stat_activity`, and
`/api/v1/system/status`, between 2026-09-26T16:44 UTC and 16:56 UTC — the
window immediately following the `db_pool_size` 5→10 deploy (see git history:
`fix(db): raise the default connection pool size from 5 to 10`).

## 1. Real current load and headroom

### CPU / memory

- `docker stats --no-stream` baseline: `eth-api` 13–15% CPU, 241–287MiB
  memory; `eth-postgres` 0–1.3% CPU, ~210–218MiB. Both well within the
  droplet's 3.8GiB memory limit (~7% used).
- 5 rapid successive samples (~5–10s apart) showed real variance:
  `eth-api` CPU ranged **14.28%–68.20%** across those samples, memory stable
  at 241–252MiB (no leak signature — memory fluctuates, doesn't climb
  monotonically).
- Host load average: `0.38, 0.90, 0.92` on a 2-core box — moderate, not
  saturated, but the 1-min/5-min/15-min spread shows load trending up over
  the hour, not flat.

### Strategy-scheduler tick duration (highly variable — see caveat)

Three real ticks observed for the same 3 strategy-enabled accounts, same
"no_action=3" outcome (no positions opened or closed, so no volatility-job
calls in any of them):

| Time (UTC) | Duration   | Note                                          |
| ---------- | ---------- | --------------------------------------------- |
| 16:45:14   | **33.08s** | First tick after container restart (16:44:33) |
| 16:50:14   | 0.48s      | Steady-state                                  |
| 16:55:15   | 0.57s      | Steady-state                                  |

**Caveat:** the 33.08s outlier is real but its cause isn't isolated — it's
either cold-start cost (model deserialization, first-use connection
warm-up) right after restart, or contention with the candle-ingestion burst
that overlapped it (`Candle ingestion started (symbol=ETHUSD timeframe=1m...)`
logged at 16:44:56.370, squarely inside the tick's ~16:44:41–16:45:14 span).
Steady-state cost for 3 directional-only predictions is closer to 0.5s. Both
figures are used in Step 2 rather than picking one, because the worst case is
the one that matters for a headroom question.

### Real sustained event rate

`/api/v1/system/status` → `delta_ws.messages_received: 10384`,
`delta_ws.uptime_seconds: 353.72` → **~29.4 trade/ticker messages/second**
sustained. Each matching event schedules one `StopLossTakeProfitMonitor`
handler invocation on the event bus (fire-and-forget, one asyncio task per
handler per event) — this is the real arrival rate of the handler that is
already timing out under load (see below).

### DB connection pool utilization

`pg_stat_activity` for `eth_platform`: **10 idle + 1 active = 11 connections**
open, i.e. the pool sits at its full new base size (`db_pool_size=10`)
essentially continuously, with occasional overflow beyond it. This confirms
the earlier hypothesis: at 29 events/sec, the base pool is kept fully
populated by `StopLossTakeProfitMonitor` alone.

### The pool-size fix reduced, but did not eliminate, the production incident

This directly bears on headroom: **fresh `TimeoutError` failures recurred
after the `db_pool_size` 5→10 deploy**, not just before it.

- 2 `StopLossTakeProfitMonitor` connection-timeout failures occurred at
  **16:50:36.129** and **16:50:36.148** — 19 milliseconds apart, i.e.
  effectively simultaneous — roughly 6 minutes after the pool-size deploy
  (16:44:33), well past any cold-start window.
- Both are the same failure signature as before: `asyncpg.connect()`'s own
  internal handshake timeout firing (`TimeoutError` raised from
  `asyncio.timeouts` inside `connect_utils._connect`), not a SQLAlchemy pool
  wait-for-slot error. This confirms it is not pool-size-limited — it's the
  connect handshake itself not completing in time.
- Both failures are tightly correlated with a real candle-ingestion burst:
  5 ingestion jobs started within a 40-second window immediately around the
  failures — `BTCUSD 1m` (16:50:20), `BTCUSD 5m` (16:50:37), `BTCUSD 15m`
  (16:50:40), `ETHUSD 1m` (16:50:41), `ETHUSD 5m` (16:50:57).
- Frequency did improve materially: 2 errors in this ~13-minute window vs.
  the dense recurrence the user's own docker-log screenshots showed before
  the fix. But "less frequent" is not "resolved," and this check should not
  be read as a stability confirmation — it isn't one.

**Root cause, now confirmed rather than inferred:** this is single-event-loop
contention, not Postgres capacity or pool size. The candle-sync scheduler,
the strategy scheduler, the live WS feed, and `StopLossTakeProfitMonitor` all
share one asyncio event loop in one uvicorn worker (documented gotcha in
`DEPLOYMENT.md` — no `--workers` flag because the live feed can't be
naively duplicated). When several schedulers' work lands in the same window,
a new `asyncpg` connection's handshake — which needs the loop to service its
callbacks promptly — can miss its window even though Postgres itself is
provably fast (isolated on-server timing tests showed 15 concurrent fresh
connections averaging ~1.05s each, far under even the original 5s timeout).
Raising the pool size helped because it means more requests find an
already-open idle connection instead of needing a fresh handshake at all —
but it doesn't help the request that still needs a new connection during a
busy window.

## 2. Option A's estimated added load

Option A adds, per strategy-scheduler cycle, per strategy-enabled account
(currently 3): one more model-inference call (volatility-job prediction) and
one more DB read (its feature-normalization stats) — the same shape of work
the directional job already does today, roughly doubling prediction-related
work per cycle (3 calls → 6).

- **Best case** (steady-state, ~0.5s/tick observed twice): doubling the
  call count would plausibly land around ~1s/tick — negligible against a
  300s cycle.
- **Worst case** (using the one 33.08s sample as the reference, since that's
  the scenario that actually matters for a headroom question — a tick that
  overlaps a candle-sync burst): doubling prediction work could plausibly
  push a similarly-unlucky tick toward 60s+, i.e. the event loop's own
  strategy-tick duty cycle roughly doubling from ~11% to ~20% of the cycle
  window during exactly the kind of overlap already shown to cause DB
  connection timeouts.
- The added DB read is small in isolation (3 extra reads per 300s is
  nothing on its own), but it is one more DB-touching operation added to the
  exact mechanism (new-connection-handshake-during-a-busy-loop) that is
  already, today, causing real failures. It adds to the problem's surface
  area, not away from it.

## 3. Recommendation

**Address the recurring connection-timeout issue (or the underlying
single-worker/event-loop contention it stems from) before adding Option A —
this is a recommendation, not a decision; final call is the user's.**

Reasoning: Option A's added load is exactly the kind of extra concurrent
DB-plus-inference work implicated in a real, still-recurring production
incident. The pool-size fix reduced the incident's frequency but did not
eliminate it, and the two fresh failures 6 minutes into this check prove the
underlying event-loop contention is still live. Adding Option A now means
adding load onto a system with a demonstrated, unresolved contention pattern,
not a comfortably idle one. This isn't a case for redesigning the worker
architecture unprompted — it's a case for finishing the fix already in
flight (or making a deliberate, informed choice to accept the residual risk)
before increasing per-cycle load further.

If the residual timeout rate (2 in ~13 minutes, i.e., roughly what's left
after the pool-size fix) is judged acceptable, proceeding with Option A is
not unreasonable — the added load is not large in absolute terms. But that
would be accepting a known, still-open reliability issue rather than
resolving it first, and should be a conscious choice, not a default.

## Addendum (2026-09-26, post-deploy): SCHEDULER-PROCESS-SPLIT deployed and re-measured

The recommendation above was acted on:
`docs/infrastructure/EVENT_LOOP_SEPARATION_DESIGN.md` designed the fix
(Option 3 — move the five DB/REST-only schedulers off `api`'s event loop
into a new standalone `scheduler` process), and it was built, verified
locally, and deployed to production the same session. This addendum
records the real, post-deploy measurement — not an assumption that
building it was enough.

**Deployed**: `docker compose build api migrate scheduler` (three distinct
image tags, confirmed) → `docker compose up -d` on the production droplet.
Both `eth-api` and `eth-scheduler` came up `healthy`; `eth-api`'s startup
log shows zero mention of any of the five relocated schedulers (candle
sync, prediction grading, external-data sync, news sync, retraining)
while `StopLossTakeProfitMonitor`, order-flow capture, and the two
paper-trading schedulers start exactly as before; `eth-scheduler`'s log
shows all five starting and ticking independently.

**Re-measured over an 11-minute real window** (19:08–19:19 UTC) at the
same real WS load as the original measurement (~27 msg/s, comparable to
the ~29.4 msg/s baseline):

- Two full candle-sync ticks ran in `scheduler`, taking **46.45s and
  33.06s** — both at or above the original 33.08s tick duration that
  coincided with the very first observed timeout. Each tick internally
  ran 4 back-to-back candle-ingestion jobs (BTCUSD/ETHUSD × 1m/5m,
  spanning ~36 seconds) — the same multi-symbol/timeframe burst shape
  that produced the 14-failure cluster documented in this file's main
  body, now happening in complete isolation from `api`.
- `api`'s own log for the full window: **zero `TimeoutError`
  occurrences** — checked directly with `grep -c`, not inferred.
- `api`'s strategy-tick durations returned to steady-state fast (11.15s
  cold-start immediately after restart, then 0.49s and 0.35s) — no
  33-second-scale outlier, consistent with candle-sync no longer sharing
  its event loop.
- Postgres now shows connections from two independent pools (16 total
  observed: `api`'s + `scheduler`'s), comfortably under `max_connections`
  (100) — the two-pool tradeoff named in the design doc, confirmed
  harmless in practice.

**Honest limits of this evidence**: 11 minutes and 2 candle-sync cycles is
a real but modest sample — the original incident's own failure rate was
itself uneven (2 failures in one 13-minute window, 14 in under 25 seconds
in another), so a single clean window is meaningful, comparable evidence
of resolution, not a permanent guarantee. This is not being declared
"fixed forever" on the strength of one observation window — matching this
document's own standing rule about not generalizing from a thin sample.
Continued passive monitoring of `eth-api`'s logs during real candle-sync
bursts is the recommended way to build confidence over the coming days,
the same way the original pattern was itself only found by repeated real
checks rather than one look.

**Verdict for Option A**: the specific, measured blocker this document
raised is resolved as far as this evidence shows. Group 1's remaining
event-loop coupling (`StopLossTakeProfitMonitor`, order-flow capture, the
two paper-trading schedulers) is unchanged and still shares `api`'s loop
with the live feed — if a _different_ contention source ever surfaces
there, that's the Option 1/2 live-state-bridge problem, not something this
change touches. Proceeding with Option A is reasonable now, with the same
expectation as everything else in this thread: verify with real
measurement after it ships, don't assume.
