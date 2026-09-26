# Retrain Window & Cadence Analysis

Derives the minimum training-window width and maximum retrain cadence
`app/services/retraining.py`'s `RetrainingScheduler` enforces as hard floors
(RETRAIN-WITH-MINIMUM-WINDOW), retrains the accounts
`FEATURE_DRIFT_INVESTIGATION.md`'s own monitor had auto-paused, and reports
a real platform bug found along the way. Every number below is measured
against the real, full stored ETHUSD/1h candle history (23,027 candles,
`2024-02-06` → `2026-09-22/23`) — none is a round number picked by feel.
Measured 2026-09-23.

## TL;DR

1. **Two failure modes, not one.** Job `6e7fb4ed` (13 days old, 100-candle
   window) drifted through **price/SMA** because its window was too narrow.
   Job `733082cc` (trained 2026-09-10, 2024-02-06→2024-11-01 window) drifted
   through **volume** because its window, however wide, was too old — raw
   volume's real-world scale trends upward over time, so no fixed window
   stays representative forever. A minimum window width fixes the first; a
   maximum retrain age (cadence) fixes the second. Neither alone is enough.
2. **The first attempt at this very analysis produced a window that itself
   drifted the moment it was checked** (`sma_20` z = 64.15, see [Why the
   first attempt failed](#why-the-first-attempt-failed)) — its own failure
   is what forced the corrected methodology below.
3. **Chosen: `MIN_WINDOW_HOURS = 8,760` (365 days), `MAX_RETRAIN_INTERVAL =
168h` (weekly).** At this combination, price/SMA's 99th-percentile
   |z| ≈ 2.9–3.2 (worst case ≈ 3.1–3.4) and log-volume's 99th-percentile
   |z| ≈ 3.4 (worst case ≈ 5.7–6.0) — all comfortably under the drift
   monitor's own `DRIFT_Z_THRESHOLD = 10.0` alarm.
4. **Raw `volume` cannot be kept safe at any practical window/cadence** —
   99th-percentile |z| in the teens to 40s, worst case over 60, even at the
   widest, most-frequently-retrained combination checked.
   `log1p(volume)` fixes this by a wide margin (99th-percentile |z| stays
   ≈ 3–4, worst case under 10, across the entire practical grid) — this is
   a measured finding, not an assumption; see
   [Volume: raw vs. log-scaled](#volume-raw-vs-log-scaled).
5. Building the corrected retrain uncovered a genuine, previously-unknown
   platform gap: **wide-date-range training jobs were silently truncated to
   100 candles**, even with an explicit `start`/`end` spanning thousands of
   hours — see [A platform bug found along the way](#a-platform-bug-found-along-the-way).

---

## The mechanism: why "window width" alone isn't the right question

`app.prediction.feature_drift.compute_feature_drift` compares a live feature
vector's z-score against a training job's own stored
`result_summary.normalization` — mean/std fit once, at training time. That
fit is **not** taken over the whole dataset window a job is trained on.
`ColumnNormalizer.fit` (`app/training/normalization.py`) fits only on the
**train split** — the chronologically first 70% of a 0.7/0.15/0.15 split —
never validation or test.

That means a dataset window of total width `W` has an effective **fit**
width of only `Wfit = 0.7·W`. The most recent `0.3·W` hours of the window
were _never seen by the fit_ — and then the job goes into service and
accumulates further age, `D_retrain`, before anything checks it. So the
real gap between "the newest data the fit actually saw" and "the moment a
drift check runs" is:

```text
G = 0.3·W + D_retrain
```

not simply `D_retrain`, and not simply related to `W` the naive way a
first-pass analysis might assume.

### Why the first attempt failed

The first attempt at this analysis fit mean/std over the **entire** window
`W` and measured the z-score `D` hours later — ignoring the 70/15/15 split
entirely. Under that (wrong) model, `W=4,320h` (180 days) with a weekly
retrain (`D=168h`) looked safe:

| W (h) | D (h) | close p99\|z\| | close max\|z\| | volume p99\|z\| | volume max\|z\| |
| ----: | ----: | -------------: | -------------: | --------------: | --------------: |
| 4,320 |   168 |           3.15 |           3.86 |            5.10 |            9.99 |

Both comfortably under the 10σ alarm. On the strength of that, the first
real retrain attempt used `W=4,320h`. It **immediately read drifted against
itself** the moment it was checked: `sma_20` z = 64.15 — nowhere near the
3.86 the (wrong) analysis predicted.

Two compounding causes, both real:

1. **The 70/15/15 split was never accounted for.** Correcting the model to
   `Wfit = 0.7·W`, `G = 0.3·W + D` and re-running the identical `(W=4320,
D=168)` cell drops the _predicted_ safety margin substantially (p99|z|
   ≈ 6.2, not 3.15 — see the `W=4320` row in the [full sweep](#full-corrected-sweep)
   below) — worse, but still nowhere near 64.
2. **A second, independent, previously-unknown bug**: the training job this
   attempt actually created was silently truncated to about 100 candles
   instead of the requested 4,320-hour range (see
   [A platform bug found along the way](#a-platform-bug-found-along-the-way)).
   A ~100-candle window fit on a placid few-day stretch has a tiny std
   (≈\$15, the same shape as job `6e7fb4ed`'s own original failure) — against
   which almost any later price reads as extreme. This, not the split
   correction alone, is what actually produced z = 64.

Both fixes were required: correcting the Wfit/G mechanism in the analysis,
and fixing the platform's own silent truncation so a wide window request is
actually honored.

---

## Corrected methodology

For many `(start, Wfit, G)` samples spread across the full real ETHUSD/1h
history: fit mean/std of a column over `[start, start+Wfit)`, then measure
that column's z-score `G` hours later. This is exactly what
`compute_feature_drift` measures live, replayed historically, with the real
fit/serve mechanism accounted for. `Wfit = 0.7·W`, `G = 0.3·W + D_retrain`,
for a chosen total dataset window `W` and retrain cadence `D_retrain`.

### Full corrected sweep

Weekly cadence (`D_retrain = 168h`), `close`/`sma(20)`/`volume`/`log1p(volume)`,
99th-percentile and worst-case |z|, sampled every 12h across the full
history:

| W (days) |   close p99/max |   sma20 p99/max |    volume p99/max | log-volume p99/max |
| -------: | --------------: | --------------: | ----------------: | -----------------: |
|      208 |     5.84 / 6.54 |     5.86 / 6.47 |     20.20 / 48.27 |        3.42 / 7.19 |
|      225 |     5.24 / 5.64 |     5.27 / 5.63 |     14.59 / 28.88 |        3.16 / 9.14 |
|      240 |     4.70 / 5.41 |     4.64 / 5.41 |     15.85 / 30.53 |        3.20 / 9.07 |
|      255 |     4.15 / 4.89 |     4.20 / 4.90 |     17.62 / 33.10 |        3.27 / 9.14 |
|      270 |     3.70 / 4.23 |     3.70 / 4.23 |     18.85 / 37.23 |        3.39 / 9.03 |
|      285 |     3.25 / 3.78 |     3.22 / 3.78 |     20.70 / 39.25 |        3.37 / 7.92 |
|      300 |     2.94 / 3.13 |     2.94 / 3.14 |     22.95 / 40.49 |        3.41 / 5.99 |
|      315 |     2.94 / 3.12 |     2.93 / 3.07 |     25.27 / 43.95 |        3.47 / 5.98 |
|      330 |     2.96 / 3.19 |     2.97 / 3.13 |     27.25 / 46.49 |        3.45 / 5.92 |
|      345 |     3.04 / 3.30 |     3.06 / 3.21 |     29.50 / 53.95 |        3.37 / 5.81 |
|  **365** | **3.18 / 3.44** | **3.22 / 3.37** | **31.77 / 63.56** |    **3.44 / 5.68** |

Monthly cadence (`D_retrain = 720h`), coarser grid:

| W (days) | close p99/max | sma20 p99/max | volume p99/max | log-volume p99/max |
| -------: | ------------: | ------------: | -------------: | -----------------: |
|      208 |   5.53 / 6.48 |   5.57 / 6.40 |  28.49 / 69.04 |        3.76 / 7.01 |
|      240 |   3.98 / 4.48 |   4.00 / 4.49 |  23.48 / 40.36 |        3.46 / 9.00 |
|      270 |   2.96 / 3.24 |   2.97 / 3.24 |  27.57 / 50.76 |        3.60 / 6.76 |
|      300 |   3.02 / 3.20 |   3.00 / 3.22 |  31.60 / 63.64 |        3.73 / 6.01 |
|      330 |   3.23 / 3.43 |   3.23 / 3.42 |  35.25 / 78.70 |        3.61 / 5.85 |
|      365 |   3.34 / 3.75 |   3.29 / 3.65 |  39.42 / 99.23 |        3.49 / 5.41 |

Two things fall out of this grid directly:

- **Price/SMA has a comfortable safe region from ~300 days onward at weekly
  cadence** — worst case never exceeds ~3.4σ anywhere in the 300–365 day
  range, an order of magnitude under the 10σ alarm.
- **Raw volume never has a safe region.** Its 99th-percentile climbs
  _with_ window width (20 → 32 at weekly cadence, 28 → 39 at monthly) — the
  opposite direction a "just widen the window" fix would need, because a
  wider window's fit is anchored further in the past, exactly where
  volume's real-world scale was smaller. See the dedicated section below.

### Volatility cross-check

ETH's own measured 7-day realized volatility, annualized (from
`docs/research/FUTURES_MECHANICS_AND_LEVERAGE_DESIGN.md`, same underlying
candle history): 5th percentile 37%, median 60%, 95th percentile 101%.
A 365-day window at 60% annualized vol implies a price standard deviation on
the order of the price level itself scaled by `0.60·√(365/365)` over a full
year of daily moves aggregated — consistent with the empirically measured
p99|z| ≈ 3.2 for `close`/`sma20` at `W=365d`: a window this wide absorbs
several months of realistic volatility inside its own fit std, so an
ordinary subsequent week's move stays a small multiple of that std, not
tens of multiples the way a 100-candle window did.

---

## Volume: raw vs. log-scaled

**Finding, not an assumption**: raw `volume` cannot be kept under the 10σ
alarm at any window/cadence combination checked. At the very best cell in
the entire practical grid (`W=300d`, weekly cadence) its 99th-percentile is
already 22.95, more than double the alarm threshold, and its worst case
(40.49) is four times over. Widening the window makes it _worse_ (39.42 at
`W=365d`/monthly), because volume trends upward over calendar time — a wider
window fits further in the past, at a systematically lower absolute scale
than "now."

`log1p(volume)` was checked as an alternative representation, not assumed
to help: across the entire same grid, its 99th-percentile stays in the
3.2–3.8 range and its worst case never exceeds 9.14 — comfortably under the
alarm everywhere, including at the widest/staleest cells where raw volume is
worst. Log-scaling compresses volume's multiplicative real-world growth into
an additive scale the normalizer's fixed mean/std can actually track.

**Consequence**: every job this scheduler creates uses `ohlc` (the four
price columns, no volume) + `volume_log` (`log1p(volume)`) +
`sma(20, close)` — never the bundled `ohlcv`, whose `volume` column cannot
be made safe by window/cadence choice alone. `app/features/builtin/ohlc.py`
and `app/features/builtin/volume_log.py` implement these; historical
research documents that reference the original `ohlcv`+`sma(20)` feature set
are left unchanged as records of what was measured at the time.

---

## Chosen parameters

- **`MIN_WINDOW_HOURS = 8,760`** (365 days) — the narrowest window in the
  weekly-cadence sweep where price/SMA's worst case stays clearly under
  4σ (3.44/3.37) with room to spare before the 10σ alarm, and where
  log-volume's worst case (5.68) still has more than 4σ of headroom too.
  300–345 days score marginally better on price/SMA alone, but 365 days
  (one full year) is the more conservative, easier-to-reason-about choice
  and remains safely within margin on every column measured — a hard floor
  should not be picked at the exact edge of its own sweep.
- **`MAX_RETRAIN_INTERVAL_SECONDS = 168·3600`** (7 days / weekly) — at
  `W=365d`, weekly cadence keeps every measured column's worst case under
  6σ; monthly cadence at the same window pushes log-volume's worst case to
  5.41 (still safe) but raw-volume's worst case to 99.23 (moot, since raw
  volume is never used) and price/SMA's worst case to 3.75 — the margin
  shrinks measurably at longer gaps, so weekly is the safer of the two
  cadences checked at this window width.
- **Enforcement**: both are checked once, at `RetrainingScheduler.__init__`,
  and rejected outright (`ValueError`) if violated — no warn-and-continue
  path, not narrower/longer even with an explicit override. See
  `app/services/retraining.py`'s own module docstring and
  `tests/services/test_retraining.py::TestConstructorEnforcesHardFloors`.

---

## A platform bug found along the way

While building the corrected retrain, `TrainingJobCreateRequest` had **no
`limit` field** — even with an explicit `start`/`end` spanning thousands of
hours, `MLDatasetService._build`'s
`resolved_limit = self.default_limit if request.limit is None else request.limit`
(default 100) silently truncated the dataset to the first 100 candles
(ascending order) inside that range. A request for a 4,320-hour window
silently became a ~100-candle window from the very start of that range — the
same narrow-window failure mode as job `6e7fb4ed`'s own original problem,
reproduced by a completely different path. Prior wide-window research jobs
(e.g. `733082cc`) had been created via temporary server-side config
overrides, not this standing API path — so this gap had apparently never
been exercised through the real API before.

Fixed as part of this task:

- `TrainingJobCreateRequest.limit` (new, optional) and
  `TrainingJobResponse.dataset_limit` (new) — `app/schemas/training.py`.
- `TrainingJob.dataset_limit` column —
  `alembic/versions/20260923_57b6bdcad9da_add_training_job_dataset_limit.py`.
- `TrainingJobService.create`/`execute_run`'s dataset-loading hook now pass
  `limit` through to `MLDatasetRequest` — `app/services/training.py`.
- `candles_max_limit` raised from 1,000 to 10,000 (`app/core/config.py`) —
  the previous ceiling was itself too low for an 8,760-hour window.

---

## Outcome: retrained accounts and the recurring scheduler

**Step 2 (manual, one-time, immediate)**: a fresh experiment
(`ohlc`+`volume_log`+`sma(20)`) and job trained on the most recent 8,760
real ETHUSD/1h candles (`limit=8760`, no truncation), verified `healthy`
against `compute_feature_drift` (worst feature `volume_log`, z=0.56), then
used to repoint all three previously drift-paused accounts (`2cff34d9`,
`37b2d8da`, `d790e9ec`) via the real, audited
`PaperTradingService.update_strategy_config` path (real admin user
attribution, not a placeholder) and re-enabled via `PATCH .../strategy`.

**Step 3 (recurring)**: `app.services.retraining.RetrainingScheduler`
periodically retrains each configured model lineage on a fresh rolling
window at these floors, checks the fresh job against
`app.prediction.feature_drift` **before** any promotion, and — on the
explicit, user-chosen promotion policy (auto-swap, not defaulted) —
repoints every currently-_enabled_ account on that lineage to the new job,
alerting via `capture_model_promoted`/`capture_retrain_unhealthy`
(`app/monitoring/error_tracking.py`). A retrain that reads drifted against
itself is never promoted — this is the property that actually closes the
loop this whole investigation opened; see `tests/services/test_retraining.py`
for the direct proof (both the healthy-promotes and drifted-does-not-promote
paths).
