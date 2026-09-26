# Order-Flow Data: Accumulation Status & Retention Tradeoff

Checks the real status of order-flow/microstructure capture
(`app.services.order_flow_capture.OrderFlowCapture`, M4-E2-T1, started
2026-09-11), never revisited since — the one hypothesis in this research
thread (bid-ask imbalance, trade-flow direction) that has never actually
been tested, and the one whose retention policy (`orderflow_retention_days`,
default 60) could quietly foreclose that test before it's ever attempted,
since this data has **no backfill**: a day pruned past the retention cutoff
is gone forever, unlike every connector on this platform. Every number
below is measured against the real `trade_flow`/`orderbook_snapshots`
tables in the running dev database. Measured 2026-09-25.

## TL;DR

1. **13,891 rows short of the sample size, but real and growing.**
   2,025,791 `trade_flow` rows and 41,644 `orderbook_snapshots` rows exist
   today, spanning 2026-09-10 20:02 UTC → 2026-09-24 18:23 UTC (13.9 days),
   across both tracked symbols (BTCUSD/ETHUSD, roughly balanced).
2. **Pruning is wired correctly and proven to work — but hasn't fired yet
   in real life, because nothing is old enough.** The oldest row is 14
   days old; the retention cutoff is 60 days. `_prune()` runs on the exact
   same loop iteration as capture (they cannot silently diverge), and
   `test_prune_deletes_rows_past_the_retention_window_and_keeps_recent_ones`
   directly proves the delete-old/keep-recent behavior against synthetic
   data. First real deletion: **2026-11-09** (60 days after the earliest
   row), 46 days from today.
3. **Real storage growth (31.5 MB/day combined) matches the original ~31
   MB/day projection almost exactly — but for reasons the projection
   didn't anticipate, and the match is partly coincidental.** Real
   per-row size validates the original estimate closely (`trade_flow`
   188.9 vs. 185 bytes/row projected; `orderbook_snapshots` 1,360.7 vs.
   ~1,400 bytes/row projected). But the _split_ between the two tables is
   very different from what was projected — see
   [Why the total matches but the split doesn't](#why-the-total-matches-but-the-split-doesnt).
4. **This is a dev environment, not an always-on deployment, and that
   dominates the real accumulation rate.** Gap analysis on
   `orderbook_snapshots` (fixed 15s cadence, so gaps are directly
   observable) finds ~10 days 5.5 hours of downtime across the 13.9-day
   span — real capture uptime ≈ 27%, not the continuous operation the
   original projection implicitly assumed.
5. **The current 60-day cap permanently blocks anything past a thin
   cross-check-scale window; it was never going to support the
   multi-month/year depth every other analysis in this thread has
   actually needed.** A 42-day (this thread's own "cross-check window"
   scale) depth arrives 2026-10-22, comfortably inside the current cap.
   A 365-day ("primary window" scale, matching
   `RETRAIN_WINDOW_ANALYSIS.md`'s own `MIN_WINDOW_HOURS`) depth is
   **never reachable at any calendar distance under the current policy**
   — it requires extending retention itself, not just waiting.
6. **Recommendation: extend `orderflow_retention_days` to 365 now, not
   later.** Real measured cost is modest (≈11.2 GB steady-state at 365
   days, ≈9.4 GB more than the current 60-day cap) and nothing is at risk
   of deletion for another 46 days regardless — there is no cost to
   deciding today, and a real, irreversible cost (permanently lost
   history) to deciding after 2026-11-09. See
   [Recommendation](#recommendation) for the full reasoning and the case
   against.

---

## Real accumulation status

Queried directly against the running dev Postgres database
(`eth_platform`), not estimated:

| Table                 |      Rows | Size (on-disk) | Date range (`captured_at`)                      |
| --------------------- | --------: | -------------: | ----------------------------------------------- |
| `trade_flow`          | 2,025,791 |         365 MB | 2026-09-10 20:02:28 → 2026-09-24 18:23:09 (UTC) |
| `orderbook_snapshots` |    41,644 |          54 MB | 2026-09-10 20:02:38 → 2026-09-24 18:23:35 (UTC) |

Both symbols are represented and roughly balanced (`trade_flow`: BTCUSD
1,061,626 / ETHUSD 964,165; `orderbook_snapshots`: BTCUSD 20,828 / ETHUSD
20,816) — capture is not silently favoring or dropping one symbol.

Per-day row counts are **highly variable**, not a steady daily rate —
`trade_flow` ranges from 21,893 rows (2026-09-10, a partial day) to
337,594 rows (2026-09-18) across full calendar days, over a 15× spread.
This variability, plus the pattern in the next section, is real market
and real-environment noise, not a data-quality problem.

## Pruning: wired, tested, not yet exercised on real data

`OrderFlowCapture._loop()` runs capture (trade flush + snapshot) and the
retention sweep (`_prune()`, gated on `orderflow_prune_interval_seconds`,
default 3600s) as **one loop, one task** — there is no separate scheduler
for pruning that could silently stop while capture keeps running, the
exact failure mode connector health monitoring exists to catch elsewhere.
Since the service is only ever constructed when `orderflow_capture_enabled`
and `market_data_live` are both true (`app/runtime.py`), pruning is
running in this environment precisely when, and only when, capture is.

**Not directly observable in the real database yet** — the oldest row is
14 days old, and the retention cutoff is 60 days, so nothing has aged
past it. That is expected and correct, not a gap to close: the sweep
computing `now - 60 days` and deleting nothing because nothing qualifies
is exactly what "not silently stalled" looks like at this stage.

**Proven instead against synthetic data with real wall-clock times**
(`tests/services/test_order_flow_capture.py`,
`test_prune_deletes_rows_past_the_retention_window_and_keeps_recent_ones`):
seeds one `trade_flow` and one `orderbook_snapshots` row older than the
retention window and one newer, calls `_prune()` directly, and asserts
exactly the old rows are gone and the new ones survive
(`capture.trades_pruned == 1`, `capture.snapshots_pruned == 1`). A second
test (`test_a_prune_failure_is_swallowed_and_does_not_lose_the_loop`)
proves a failed prune attempt doesn't kill the loop. Both pass today (`uv
run pytest tests/services/test_order_flow_capture.py`, 8/8 passed — note:
the task's own suggested path, `tests/orderflow`, does not exist in this
repo; the real, correct path is `tests/services/test_order_flow_capture.py`,
run here instead per this platform's own "confirm the prerequisite
actually exists" rule).

**First real deletion will happen 2026-11-09** (60 days after the
earliest row, 2026-09-10). From that date on, under the current policy,
the tables become a genuine rolling 60-day window — never growing past
that depth again.

## Why the total matches but the split doesn't

The original projection (`ARCHITECTURE.md` § "Funding Rate, Open
Interest & Order-Flow Capture") extrapolated from a 10-minute live sample
(582 trades, 100 snapshots) to ~15 MB/day for `trade_flow` and ~16 MB/day
for `orderbook_snapshots`, ~31 MB/day combined. The real, 13.9-day
measurement:

| Table                 | Real rate (MB/day) | Original projection | Difference |
| --------------------- | -----------------: | ------------------: | ---------- |
| `trade_flow`          |               27.5 |                 ~15 | +83%       |
| `orderbook_snapshots` |                4.1 |                 ~16 | -75%       |
| **Combined**          |           **31.5** |             **~31** | **+1.7%**  |

The combined total landing almost exactly on the original estimate is
**two errors of opposite sign canceling out, not confirmation the
original method was right**:

- **`orderbook_snapshots` is timer-driven** (one snapshot every 15s per
  symbol, regardless of market activity) — a deterministic 11,520
  rows/day if the process ran continuously. Real average: 2,933 rows/day,
  about **25% of that** deterministic ceiling.
- **Gap analysis on `orderbook_snapshots`** (ETHUSD; gaps are directly
  measurable because the cadence is fixed) finds 23 gaps longer than one
  hour, totaling 10 days 5.5 hours of downtime across the 13.9-day span —
  the longest single gap is 21.6 hours. Real capture uptime ≈ **27%** of
  calendar time. This is a **dev-environment usage pattern** (the
  pipeline runs only while a developer has `MARKET_DATA_LIVE=true` up),
  not evidence of a bug — `orderbook_snapshots`' own count (2,933/day)
  divides almost exactly into its deterministic ceiling (11,520/day) at
  this same ~27% uptime figure, which is a strong internal cross-check
  that the accumulation _mechanism_ is behaving exactly as designed for
  however much wall-clock time it's actually running.
- **`trade_flow` is event-driven**, so its count depends on real trade
  arrival rate during whatever hours capture happens to be up. The
  original 10-minute sample (58.2 trades/min combined) turns out to have
  badly under-sampled real activity: at ~27% uptime, the real 146,238
  trades/day (full calendar days) implies roughly **380 trades/min**
  while actually connected — about **6.5× higher** than the original
  sample suggested. A 10-minute window is a poor basis for extrapolating
  a bursty, market-activity-driven rate; the deterministic snapshot
  cadence is a far more reliable one for validating the capture
  _mechanism_ itself, which it does.

**Practical consequence**: the real ~31.5 MB/day blended rate is a valid
basis for projecting storage cost at this same operating pattern (dev,
intermittent), but if this platform ever runs continuously (e.g. toward
Milestone 6), the real rate would very likely be dominated much more
heavily by `trade_flow`'s true per-active-hour volume and could land
meaningfully higher than 31.5 MB/day — worth re-checking once actual
production-like usage exists, not assumed to hold forever from a
14-day, dev-only sample.

## Retention tradeoff: what different windows actually buy

**Depth vs. time**, using this thread's own established scales
(`TARGET_REDEFINITION_ASSESSMENT.md`'s 42-day "cross-check window";
`RETRAIN_WINDOW_ANALYSIS.md`'s 365-day/8,760-hour "primary window"),
measured from when capture actually started (2026-09-10):

| Target depth                    | Reached (calendar date)   | Achievable under current 60-day cap?                     |
| ------------------------------- | ------------------------- | -------------------------------------------------------- |
| 42 days (cross-check scale)     | 2026-10-22 (28 days away) | **Yes** — comfortably inside 60 days                     |
| 60 days (the cap itself)        | 2026-11-09 (46 days away) | Yes, by definition — then rolls forever                  |
| 90 days                         | 2026-12-09                | **No** — pruned at day 60 under current policy           |
| 180 days                        | 2027-03-09                | **No**                                                   |
| 365 days (primary-window scale) | 2027-09-10 (one year)     | **No — never, at any distance**, without a policy change |

The current 60-day cap is not "too short today and fine later" — it is a
**hard, permanent ceiling** on how much history this platform will ever
have retained for order-flow, regardless of how long capture keeps
running. A cross-check-scale analysis is fine under it. A primary-scale
one, the kind that actually gave every other hypothesis in this thread
real statistical power, is structurally impossible under it, forever,
unless the policy itself changes.

**Real storage cost**, projected from the measured 31.5 MB/day blended
rate (steady-state size once the pipeline has run at least that many
days; today's actual size is smaller since capture only started 14 days
ago):

| `orderflow_retention_days` | Projected steady-state size | Incremental cost vs. today's 60-day policy |
| -------------------------: | --------------------------: | ------------------------------------------ |
|               60 (current) |                     1.85 GB | —                                          |
|                         90 |                     2.77 GB | +0.92 GB                                   |
|                        180 |                     5.54 GB | +3.69 GB                                   |
|                        365 |                    11.24 GB | +9.39 GB                                   |

For a platform already storing 2+ million real trade rows and 24,000+
hourly candles per symbol, ~11 GB steady-state is not a meaningful
infrastructure cost by itself — the real question is whether the
optionality is worth deciding to keep before it's gone, not whether the
disk space is affordable.

## Recommendation

**Extend `orderflow_retention_days` to 365, and do it before 2026-11-09**
(when the current 60-day cap starts permanently deleting real history for
the first time). The case for deciding now rather than later:

- **The cost of waiting to decide is real and irreversible; the cost of
  deciding now is zero.** Nothing is pruned for another 46 days regardless
  of what the policy says today — extending now costs nothing this month
  and forecloses nothing. Waiting past 2026-11-09 to decide means some
  real, non-backfillable history is already gone by the time the decision
  is made.
- **The storage cost is modest and well-quantified** (≈9.4 GB more than
  today's policy, from a real measured rate, not a guess).
- **365 days matches this thread's own established "primary window"
  scale**, not an arbitrary round number — the same depth
  `RETRAIN_WINDOW_ANALYSIS.md` needed for genuine statistical power in
  every other analysis here.
- **The counter-case is real and worth stating plainly**: nothing
  downstream reads these tables yet, and may never — this is committing
  real (if modest) storage to a hypothesis that hasn't been tested at
  all, not a fix for a proven-valuable pipeline. If the platform decides
  order-flow analysis isn't worth pursuing before 365 days' worth of
  motivation to actually use this data materializes, the extended
  retention would have been unnecessary cost, not a large one, but not
  zero either.

This was presented as a recommendation, not a decision, in this task —
`orderflow_retention_days` was not changed here, per the explicit
instruction not to change the policy unilaterally. **Update
(HOUSEKEEPING-1): accepted.** `orderflow_retention_days` was raised from
60 to 365 in `app/core/config.py` (and the local `.env`/`.env.example`).
**Not yet live in this environment**: the currently-running dev server
was deliberately left running rather than restarted as part of this
change — it holds the real, still-accumulating order-flow capture loop
this whole document is about, and restarting it was judged a separate,
riskier action than editing the versioned config default. The new value
takes effect on this environment's next restart, whenever that happens
for unrelated reasons.

## What this does not resolve

- No feature generator, connector-abstraction integration, or analysis of
  `trade_flow`/`orderbook_snapshots` exists yet — that remains a fully
  separate, future task, unaffected by this one.
- The real accumulation rate is measured from a 13.9-day, dev-only,
  ~27%-uptime sample. If usage patterns change (continuous operation, a
  different symbol set), the rate — and therefore the storage projection
  — should be re-measured, not assumed to hold.
- This check did not, and should not, prune or otherwise mutate real
  captured data to more directly test the retention sweep against real
  rows — that would destroy real, non-backfillable history for a test
  that synthetic data (`tests/services/test_order_flow_capture.py`)
  already answers correctly.
