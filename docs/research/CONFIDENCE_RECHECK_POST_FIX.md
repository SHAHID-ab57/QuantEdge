# Confidence Re-Check, Post Drift Fix

> ## Correction (2026-09-29, WARMUP-OFFBYONE-FIX)
>
> **`794eeaf6` is the exact job a real local/server prediction
> disagreement later traced this bug to directly** — confirmed live,
> not inferred: `app.indicators.builtin.common.period_warmup()` declared
> SMA(20)'s warmup as 20 rows when the indicator's own `calculate()`
> only nulls 19, and `_cap_rows()` silently discarded the single newest
> row from every under-sized `FeatureService.build_raw` request this
> job's own `ohlc` + `volume_log` + `sma(20)` feature set made — live
> tick or backtest step alike, both reach the database through the
> identical path. Every one of the 1,314 predictions measured below was
> computed from the candle _before_ the one it was timestamped against.
>
> **What this corrects: the _input_, not the _verdict_.** The shift ran
> one bar early, never a look-ahead (no future information ever leaked
> in). Confidence-vs-correctness is a property of the model's own output
> calibration, not of exactly which real bar its input came from; a
> systematic one-bar timing shift applied identically across all 1,314
> predictions gives no mechanism by which it would manufacture or hide a
> genuine relationship. **"The core finding holds, and is now stronger"
> below very likely still holds**, but has not been empirically
> re-measured against the fixed pipeline to confirm it exactly.
>
> This document's own tables and verdict below are left exactly as
> originally published — this is a correction note, not a retraction or
> a silent edit.

**Question:** now that RETRAIN-WITH-MINIMUM-WINDOW has replaced the drift-affected
job (`733082cc`) with a fresh, correctly-windowed one (`794eeaf6`, `ohlc` +
`volume_log` + `sma(20)`, 365-day window), does `CONFIDENCE_GATE_AUDIT.md`'s
finding — confidence does not rank correctness, AUC ≈ 0.506 — still hold? All
numbers below are freshly measured against `794eeaf6`'s own predictions;
nothing is carried over from the original audit except its methodology.
**Investigation only: no strategy code, threshold or configuration was
changed.** Measured 2026-09-24.

## Summary

1. **The core finding holds, and is now stronger.** AUC of confidence vs.
   correctness is **0.505 (block-24 95% CI: 0.476 to 0.537)** over 1,314
   genuinely held-out backtest bars — statistically indistinguishable from
   the original's 0.506 (0.491 to 0.520). This was never a drift artifact:
   the fixed model, with honestly-scaled features, still ranks correctness
   at chance.
2. **A new, more urgent finding: the 65%/70% confidence gate now blocks
   every single prediction.** The fixed model's confidence tops out at
   **0.591** across 1,314 backtest bars and **0.509** across every live
   prediction seen so far — nowhere near the 65% (two accounts) or 70%
   (one account) threshold each retrained account is configured with.
   **All three re-enabled accounts have placed zero trades since
   retraining** — 150 live predictions, 150 `no_action` decisions, 0
   orders. This is not a hypothetical: it is the account's actual
   recorded behavior. See [The gate now blocks everything](#the-gate-now-blocks-everything-not-just-most).
3. **Recalibration still cannot help — but for a different, better
   reason.** Platt scaling on the fixed model has skill ≈ 0.0000 (same
   verdict as before: monotone recalibration cannot create ranking a
   score at chance doesn't have). What changed is _why_ it's a non-issue
   now: the old model's raw confidence was badly miscalibrated (ECE 0.40,
   claiming 0.89 against a true 0.49); the fixed model's raw confidence is
   already nearly calibrated on its own (**ECE 0.013**, mean confidence
   ≈0.506 against true accuracy ≈0.516) — because it is honestly reporting
   "close to 50/50," which happens to be close to the truth. Isotonic
   regression is worse than before (skill −0.14) purely as a small-sample
   overfitting artifact — expected, and explained below, not a new
   negative finding about the model.
4. **The gate's old directional tilt is gone, because there is nothing
   left for it to tilt.** The original found the gate blocked 33% of "up"
   calls against 7% of "down" calls. On the fixed model, at 65%, it blocks
   **100% of both** — the tilt disappeared because there is no longer
   any daylight between the two call types' confidence, not because the
   underlying asymmetry was fixed.
5. **One directional-AUC check lands just outside 0.5 — flagged, not
   claimed.** P(up) vs. realized "up" gives AUC 0.528 (95% CI 0.502 to
   0.556), barely excluding chance. Given this recheck ran several
   distinct AUC checks and this is the one that lands at the edge, the
   same multiple-comparisons caution the original audit named applies
   directly — see [A boundary-adjacent AUC](#a-boundary-adjacent-auc-not-treated-as-a-finding).

**This is new information relevant to D1/D2, reported per the task's own
instruction, not acted on here:** the strategy is not merely "gated by a
threshold that doesn't improve accuracy" (the original finding) — on the
fixed model, that same gate is a **complete stop**, and has been since the
moment the drift fix went live. Whether to lower the threshold, remove the
gate (as the original audit already recommended, on different grounds), or
leave the accounts intentionally idle is a decision for you, not
implemented here.

## Data and method

- **Set.** All graded predictions from training job `794eeaf6` (the live
  ETHUSD/1h job every re-enabled account now points at). Two sources,
  kept separate exactly as the original audit separated backtest from
  live:
  - **Backtest (primary, N=1,314).** `794eeaf6`'s own held-out **test
    split** — the last 15% of its 8,760-hour training window
    (`2026-07-30 02:00` to `2026-09-22 19:00`), which `ColumnNormalizer`
    and the model's own fit never saw (see `RETRAIN_WINDOW_ANALYSIS.md`
    for why the split is 70/15/15 and why that boundary is real). Walked
    with a real `POST /backtests/run`-equivalent call (`BacktestService`,
    run `7abc6dc2`), one prediction + one grade per hour, via the exact
    same unmodified `PredictionService.run`/`grade_now` every live
    prediction uses — 1,314 steps, 1,314 graded, no truncation.
  - **Live (secondary, N=150 rows, 5 distinct bars).** Every real
    scheduler-generated prediction since the retrained accounts were
    re-enabled (`2026-09-22 19:23` onward). Confirmed by direct
    inspection: 150 rows collapse to **5 distinct `as_of` hours** — the
    same per-tick pseudo-replication the original audit found in its own
    134-bar live set, more extreme here only because so little wall-clock
    time has passed. Every duplicate row within a bar shares an identical
    confidence and outcome (the input candle hasn't moved), so this is
    genuinely 5 independent observations, not 150.
- **Why the backtest window is narrower than the original's 5,546 bars,
  and why that's structural, not a shortcut.** The original job
  (`733082cc`) finished training in November 2024, leaving ~22 months of
  real, never-touched-by-training data to walk forward over by the time
  of that audit. `794eeaf6` was deliberately trained on the _most recent_
  365 days, finishing training less than a day before this recheck — by
  construction, there is no calendar time left over that is both real and
  untouched by its fit, except its own internal test split (1,314 hours)
  and whatever live data accumulates going forward. This is the direct
  trade-off named in `RETRAIN_WINDOW_ANALYSIS.md`'s own recurring-retrain
  design: freshness (never letting normalization go stale) costs
  backtest-window depth (less accumulated calendar time to check it
  against). It is real and worth naming plainly, not something to route
  around.
- **Bar independence.** The backtest series is already 1,314 predictions
  for 1,314 distinct hours — one prediction per bar by construction (a
  real walk-forward backtest, not a repeated live tick), so it needs no
  deduplication, exactly like the original's own 5,546-bar backtest
  portion. Bootstrap resampling still uses circular blocks (length 1 and
  24, mirroring the original) to check whether any serial dependence in
  _correctness_ changes the picture; it does not, materially.
- **Effective sample sizes.** Backtest: 1,314 rows, 1,314 bars. Live: 150
  rows, 5 bars.

## Step 1: accuracy at every threshold

Backtest series (the 1,314-bar held-out test split). Lift is accuracy at
the threshold minus no-gate accuracy (0.516); interval is the block-24
bootstrap.

| Threshold | Kept  | Kept %   | Accuracy | 95% CI, block 1 | 95% CI, block 24 | Lift vs no gate [block-24 CI] |
| --------- | ----- | -------- | -------- | --------------- | ---------------- | ----------------------------- |
| 50%       | 1,128 | 85.8%    | 0.518    | 0.489 to 0.546  | 0.493 to 0.545   | +0.002 [-0.009, +0.013]       |
| 55%       | 9     | 0.7%     | 0.444    | 0.125 to 0.800  | 0.167 to 1.000   | -0.072 [-0.340, +0.492]       |
| 60%       | 0     | 0.0%     | —        | —               | —                | —                             |
| **65%**   | **0** | **0.0%** | —        | —               | —                | —                             |
| 70%       | 0     | 0.0%     | —        | —               | —                | —                             |
| 75%-95%   | 0     | 0.0%     | —        | —               | —                | —                             |

**Reading it.** Confidence tops out at 0.591 across the entire 1,314-bar
series (percentiles: p50 0.503, p75 0.508, p95 0.523, p99 0.545, max
0.591). Nothing in this series, or in the live set (max 0.509), reaches
60%, let alone 65% or 70%. The 55% row (9 bars) is already too small to
say anything (its own 95% CI spans nearly the entire [0,1] range) — a
preview of how thin the tail is even before reaching the account's actual
thresholds. Every threshold at or above 60% keeps exactly zero
predictions.

### The gate now blocks everything, not just most

This is the practically load-bearing finding. Checked directly against the
real account state, not inferred:

| Account    | `strategy_confidence_threshold_pct` | Live predictions since retrain  | `no_action` decisions | Orders placed |
| ---------- | ----------------------------------- | ------------------------------- | --------------------- | ------------- |
| `2cff34d9` | 65%                                 | (shared 150 across all 3 accts) | 150                   | **0**         |
| `d790e9ec` | 65%                                 |                                 |                       | **0**         |
| `37b2d8da` | 70%                                 |                                 |                       | **0**         |

Every one of the 150 real live predictions logged since these accounts
were re-enabled resulted in a `no_action` decision, average confidence
0.506. Zero orders have been placed. This is a direct, mechanical
consequence of the drift fix, not a coincidence: the old model's
confidence was saturated (mean 0.889, driven by feature z-scores tens of
standard deviations out of range) precisely _because_ it was drifted —
fixing the drift removed the mechanism that was pushing confidence toward
0 or 1. What's left is the model's _honest_ uncertainty about a ~50/50
target, and no logistic regression that isn't badly miscalibrated reports
90%+ confidence on a coin flip. **The 65%/70% gates were never calibrated
against what an honestly-scaled model on this data actually produces** —
they were set, and have gone unquestioned, while the only model ever
running in production was one whose confidence happened to already be
saturated for an unrelated reason (drift). Now that the drift is gone, the
threshold's implicit assumption ("a real signal will occasionally clear
65%") is exposed as never having been checked against this model's actual
achievable range.

## Step 1b: AUC of confidence vs. correctness

| Set                                               | AUC   | 95% CI (block 1) | 95% CI (block 24) |
| ------------------------------------------------- | ----- | ---------------- | ----------------- |
| Fixed model, backtest (N=1,314)                   | 0.505 | 0.475 to 0.536   | 0.476 to 0.537    |
| Original audit, backtest (N=5,546, for reference) | 0.507 | —                | 0.491 to 0.523    |

Statistically indistinguishable from the original. The wider interval here
is expected and mechanical — a quarter of the original's sample size
produces a wider bootstrap interval, not a different point estimate.
**The finding is confirmed to not be a drift artifact**: it survives on a
model whose features are, by the same `compute_feature_drift` check this
whole thread built, reading `healthy` (worst feature `volume_log`,
z=0.56).

## Step 1c: directional AUC and a boundary-adjacent result

The strategy acts on direction, so `P(up)` was checked against realized
up-vs-not, the same second angle the original audit used:

| Check                                 | AUC   | 95% CI (block 24) |
| ------------------------------------- | ----- | ----------------- |
| P(up) vs. realized up, fixed model    | 0.528 | 0.502 to 0.556    |
| P(up) vs. realized up, original audit | 0.505 | 0.490 to 0.519    |

### A boundary-adjacent AUC, not treated as a finding

The lower bound (0.502) sits barely above 0.5 — the one result among
several run here (correctness AUC at two block lengths, directional AUC,
per-fold recalibration AUCs, a threshold sweep) that lands at an edge
rather than squarely inside the null range. The original audit's own
"what this does not cover" section named this exact risk explicitly:
looking at several thresholds and bins and treating whichever one looks
best as a finding. `REGIME_WALKFORWARD_ASSESSMENT.md`'s own downtrend
result cleared 0.5 by 0.001 at a boundary and was read as "not a
meaningfully different picture" for the same reason. Applying the same
standard here: **one boundary-adjacent interval, out of several checks, on
a sample a quarter the size of the original's, is not evidence of real
directional skill** — it would need independent replication (e.g. on the
next several thousand hours of live/backtest data as they accumulate) to
be taken as anything more than a candidate worth re-checking, not a
finding to act on.

## Step 2: recalibration, re-run

Forward-chained: fit on the earliest of six chronological folds (219
bars), test on the remaining five (1,095 bars, test base rate 0.516) —
proportionally the same split shape as the original, scaled to this
sample's size.

| Score                       | Brier  | Skill vs constant | Log-loss | ECE    | AUC    |
| --------------------------- | ------ | ----------------- | -------- | ------ | ------ |
| Raw confidence, fixed model | 0.2501 | **-0.0012**       | 0.6933   | 0.0126 | 0.5050 |
| Platt scaling               | 0.2497 | -0.0000           | 0.6926   | 0.0002 | 0.5050 |
| Isotonic regression         | 0.2836 | -0.1356           | 1.3186   | 0.1144 | 0.5034 |
| Constant (train base rate)  | 0.2497 | 0.0000            | 0.6926   | 0.0000 | n/a    |

- **The ranking verdict is unchanged**: Platt skill is 0.0000 (to four
  decimal places, exactly flat), confirming the same "monotone
  recalibration cannot create ranking a chance-level score lacks" logic
  as before.
- **What's genuinely different: raw confidence is already almost
  calibrated.** ECE fell from the original's 0.40 to **0.0126** — not
  because anything was recalibrated, but because a model that isn't
  saturated naturally reports numbers close to its own true accuracy on a
  near-50/50 target. This is a real, structural improvement in honesty
  (the number printed is no longer a lie), even though it carries no more
  ranking information than before.
- **Isotonic regression got worse, and that's a small-sample artifact,
  not a new finding.** With confidence compressed into a ~0.498-to-0.591
  range and only 219 training bars, isotonic regression's step function
  has very few points per step and pins its extremes at exactly 0 and 1
  the moment a single training bar in a low-confidence bin happens to be
  wrong — visible directly in the fitted output (39 distinct levels,
  range **[0.0000, 1.0000]**, i.e., it is emitting _0% and 100%_
  confidence from a model whose own raw range never exceeds 60%). This is
  isotonic regression overfitting a narrow, low-N calibration set, the
  same overfitting risk the original audit already flagged ("isotonic...
  overfits") — worse in degree here only because the raw score has far
  less spread to work with and the per-fold sample is a quarter the size.
  Not evidence the fixed model is harder to calibrate; if anything, Platt
  scaling's ECE of 0.0002 shows the opposite.

## The gate's tilt, before and after

| Set                | Call | N     | Mean confidence | Share passing 65% | Accuracy |
| ------------------ | ---- | ----- | --------------- | ----------------- | -------- |
| Fixed, backtest    | up   | 512   | 0.503           | **0%**            | 0.531    |
| Fixed, backtest    | down | 802   | 0.508           | **0%**            | 0.506    |
| Original, backtest | up   | 17    | 0.521           | 0%                | 0.471    |
| Original, backtest | down | 5,527 | 0.895           | 93.8%             | 0.492    |

The original's headline tilt effect (blocking 33% of "up" calls against
7% of "down" calls) doesn't reproduce — not because the underlying
asymmetry between the two call types went away (mean confidence is still
slightly higher for "down," 0.508 vs 0.503, the same direction as before),
but because **there is no longer a regime where the gate is selective**:
at 65% it blocks both calls completely, so there is nothing left for a
tilt to act on. The original's own caveat — "there is no evidence that
tilt is good or bad" — is now moot in a different way: the tilt can't
happen at all while the gate is a hard stop.

## What would change this answer, and what this does not cover

- **More live data.** The 5-bar live set is far too small to say anything
  (even the original's 134 bars were called "too small to say anything");
  this will grow every day the accounts stay enabled, and is worth
  re-checking once it reaches a size comparable to the original's live
  set.
- **A different model class.** This is still one logistic regression.
  `HORIZON_SWEEP_ASSESSMENT.md`/`CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`
  already checked other model kinds on the same no-skill target and found
  the same answer; nothing here revisits that.
- **The threshold itself.** This recheck did not test what accuracy looks
  like at thresholds between 50% and 55% at finer granularity, since the
  practical question — "does the gate as configured (65%/70%) ever pass
  anything" — already has a clean, load-bearing answer (no).
- **Not done, on purpose.** No threshold, no strategy code, and no
  account configuration was changed by this recheck.

## Related

- The finding this recheck follows up: `CONFIDENCE_GATE_AUDIT.md` (AUC
  0.506, measured on the drift-affected job `733082cc`).
- The fix that made this recheck necessary, and the mechanism (saturated
  confidence as a symptom of feature drift) that explains why the gate's
  behavior changed so completely: `RETRAIN_WINDOW_ANALYSIS.md`,
  `FEATURE_DRIFT_INVESTIGATION.md`.
- The pseudo-replication method this recheck reuses for the live set:
  `CONFIDENCE_GATE_AUDIT.md`'s own bar-block adaptation of
  `HORIZON_SWEEP_ASSESSMENT.md`'s circular block bootstrap.
- No-skill findings by model class, horizon and regime, all still
  standing: `CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`,
  `HORIZON_SWEEP_ASSESSMENT.md`, `REGIME_WALKFORWARD_ASSESSMENT.md`.
