# Confidence Gate Audit

> ## Correction (2026-09-29, WARMUP-OFFBYONE-FIX)
>
> **Every prediction this audit measured was computed from the candle
> _before_ the one it was actually timestamped against.** Whether stored
> from a real live strategy tick or a backtest step, every one reaches
> the database through the identical `PredictionService.run` →
> `FeatureService.build_raw` path. A real bug found there
> (`app.indicators.builtin.common.period_warmup()` declared SMA(20)'s
> warmup as 20 rows when the indicator's own `calculate()` only nulls 19)
> made `_cap_rows()` silently discard the single newest row from every
> under-sized request — this document's own baseline feature set (`ohlc`
>
> - `volume_log` + `sma(20)`, no `realized_volatility` to mask it)
>   included, for the full 8,126-prediction population audited below.
>
> **What this corrects: the _input_, not the _verdict_.** The bug shifted
> every measured prediction's own inputs one bar earlier than its
> `as_of` implied — a real timing error, but not a look-ahead one (no
> future information ever leaked in). This audit's own finding —
> confidence carries no measurable relationship to whether a prediction
> is later graded correct — is a property of how well the model's
> _output_ probability tracks its _own_ correctness, not of exactly
> which bar its input came from; a systematic one-bar timing shift
> applied identically across all 8,126 predictions gives no mechanism by
> which it would manufacture or hide a genuine confidence-accuracy
> relationship. **The "confidence is not meaningful, recalibration does
> not fix it" verdict below very likely still holds**, but has not been
> empirically re-audited against the fixed pipeline to confirm it
> exactly.
>
> This document's own tables and verdict below are left exactly as
> originally published — this is a correction note, not a retraction or
> a silent edit.

**Question:** does the automated strategy's 65% confidence threshold filter
anything real, and if it does not, would recalibrating the model's probability
make confidence meaningful? **Investigation only: no strategy code, threshold
or configuration was changed.** All numbers come from data already in the dev
database; the measurement scripts were run from a scratch directory and are
not part of the repository. Measured 2026-09-21.

## Summary

1. **No confidence threshold from 50% to 95% improves accuracy by a margin
   distinguishable from zero.** On the original 8,126 predictions, accuracy is
   0.460 at every gate within noise (0.455 to 0.472), and no threshold's lift over
   "no gate" has a confidence interval that excludes zero.
2. **Confidence does not rank correctness.** AUC of confidence against being
   correct is **0.506 (95% interval 0.491 to 0.520)** over 5,545 independent
   walk-forward bars. The interval rules out any AUC above about 0.52.
3. **Recalibration cannot help, and was tested.** Platt scaling and isotonic
   regression, fitted forward in time and tested on later data, produce a
   calibrated but constant-in-effect score (Brier skill vs a constant **-0.0003**
   and **-0.0077**). Both are monotone in confidence, so they cannot create
   ranking that the raw score lacks, and the raw score ranks at chance. What
   recalibration does fix is the _level_: raw confidence claims 0.89, the truth
   is 0.49.
4. **The gate is not neutral, and that is its one real effect.** It blocks 33%
   of "up" calls but only 7% of "down" calls, so it tilts the strategy further
   toward shorts. There is no evidence that tilt is good or bad.
5. **A correction to an earlier finding.** The 3,043 live predictions are only
   **134 distinct hourly bars** (22.7 predictions per bar). The live-only
   correlation reported in the leverage research (-0.052, "significantly
   negative") was inflated by that duplication; properly counted it is -0.032
   with AUC 0.482 (interval 0.391 to 0.565): no signal in either direction.

**Recommendation: remove the gate as decorative** (keep the "confidence is
present" check). Details, the choice this leaves you, and what would change the
answer are in [Recommendation](#recommendation).

## Data and method

- **Set.** All graded `classification` predictions, all `logistic_regression`,
  ETHUSD, 1-hour horizon. To match the earlier analysis exactly, the primary set
  is the **frozen 8,126**: the 5,546 walk-forward backtest predictions plus the
  first 2,580 live ones by creation time (it reproduces the earlier headline:
  accuracy 0.460, 91.7% retained at 65%). The current 8,589 is reported too.
- **Every prediction that claims "up" or "down"** is a call of a direction;
  `is_correct` compares it to the realized next-hour outcome.
- **Pseudo-replication, and why the horizon-sweep correction needed adapting.**
  The horizon sweep used a circular block bootstrap with block length equal to
  the horizon. Here the horizon is 1 hour, which would mean blocks of one _row_,
  and that does not fix the actual problem: rows are not the independent unit,
  **bars are**. The 3,043 live rows are 134 bars, so resampling rows treats each
  bar's outcome as about 23 independent observations. This audit therefore
  resamples **bars** (unique `as_of`) in circular blocks, at block length 1 (the
  sweep's rule applied to bars) and **24 hours** (a conservative allowance for
  regime persistence). Both are shown; they barely differ on the backtest, which
  says correctness has little serial dependence there. 3,000 resamples for the
  threshold sweep, 1,500 for the AUCs.
- **How much it matters.** At the 65% gate on the frozen set, a naive per-row
  bootstrap gives accuracy [0.449, 0.472] (width 0.023) and a lift of [-0.003,
  +0.003]. The bar-block interval is [0.434, 0.492] (width 0.058) and the lift is
  [-0.010, +0.013]. The naive interval is about 2.5 times too narrow for the level
  and 4 times for the lift, which is the quantity the gate is claimed to improve.
- **Effective sample sizes.** Frozen set: 8,126 rows, 5,664 distinct bars.
  Backtest: 5,546 rows, 5,545 bars (one prediction per bar). Live: 3,043 rows,
  **134** bars.

## Step 1: accuracy at every threshold

Frozen set (the original 8,126). Lift is accuracy at the threshold minus
accuracy with no gate; its interval is the paired 24-hour block bootstrap.

| Threshold | Rows kept | Kept   | Bars kept | Accuracy | 95% CI, block 1 | 95% CI, block 24 | Lift vs no gate [block-24 CI] |
| --------- | --------- | ------ | --------- | -------- | --------------- | ---------------- | ----------------------------- |
| 50%       | 8,125     | 100.0% | 5,663     | 0.460    | 0.426 to 0.495  | 0.436 to 0.489   | 0.000 [0.000, 0.000]          |
| 55%       | 7,966     | 98.0%  | 5,591     | 0.459    | 0.424 to 0.494  | 0.434 to 0.489   | -0.001 [-0.004, +0.002]       |
| 60%       | 7,778     | 95.7%  | 5,465     | 0.457    | 0.422 to 0.493  | 0.431 to 0.489   | -0.003 [-0.010, +0.002]       |
| **65%**   | 7,455     | 91.7%  | 5,293     | 0.460    | 0.425 to 0.495  | 0.434 to 0.492   | **+0.000 [-0.010, +0.013]**   |
| 70%       | 7,214     | 88.8%  | 5,072     | 0.457    | 0.420 to 0.493  | 0.429 to 0.490   | -0.003 [-0.014, +0.010]       |
| 75%       | 6,649     | 81.8%  | 4,818     | 0.472    | 0.438 to 0.507  | 0.444 to 0.502   | +0.012 [-0.006, +0.035]       |
| 80%       | 6,215     | 76.5%  | 4,496     | 0.470    | 0.434 to 0.506  | 0.441 to 0.502   | +0.009 [-0.009, +0.034]       |
| 85%       | 5,644     | 69.5%  | 4,062     | 0.462    | 0.422 to 0.502  | 0.431 to 0.500   | +0.002 [-0.015, +0.025]       |
| 90%       | 5,000     | 61.5%  | 3,522     | 0.462    | 0.420 to 0.505  | 0.431 to 0.502   | +0.002 [-0.015, +0.025]       |
| 95%       | 4,027     | 49.6%  | 2,725     | 0.455    | 0.407 to 0.505  | 0.419 to 0.501   | -0.006 [-0.027, +0.024]       |

**Reading it.** Accuracy is flat across the whole range. The best-looking gate
(75%, +1.2 percentage points) has an interval of [-0.6, +3.5], and it is the best
of ten thresholds, so some apparent lift is expected from selection alone. Tightening
the gate to 95% throws away half the predictions and retains accuracy of 0.455.
The gate does not become more selective in a useful way as it tightens: it just
discards volume.

The walk-forward backtest alone (5,545 independent bars, the cleanest series):
accuracy 0.491 to 0.498 at every threshold, every lift interval includes zero, the
widest lift being +0.006 at 90% ([-0.005, +0.016]). The live period alone (134 bars,
accuracy 0.375) is too small to say anything, and its point estimates are
lower, not higher, at high confidence (0.349 at 90% and 95%; both intervals
include the no-gate 0.375).

**Binned view** (backtest bars; row-bootstrap intervals, so slightly optimistic):

| Confidence  | Bars  | Accuracy | 95% CI         |
| ----------- | ----- | -------- | -------------- |
| below 0.60  | 193   | 0.451    | 0.378 to 0.523 |
| 0.60 - 0.70 | 389   | 0.524    | 0.481 to 0.571 |
| 0.70 - 0.80 | 562   | 0.473    | 0.432 to 0.516 |
| 0.80 - 0.90 | 964   | 0.477    | 0.445 to 0.508 |
| 0.90 - 0.95 | 794   | 0.511    | 0.477 to 0.547 |
| 0.95 - 0.99 | 1,147 | 0.485    | 0.457 to 0.513 |
| 0.99 - 1.00 | 1,496 | 0.501    | 0.474 to 0.528 |

There is no monotone trend. The 0.60 to 0.70 bin looks best (0.524) and is the
one a gate would sit inside, but it is one of seven bins, its interval covers
0.49, and the bins on either side are below it. Note the shape: 27% of
predictions have confidence above 0.99. The model's probabilities are close to
saturated, which is why the mean is 0.89 while accuracy is 0.49.

**Why accuracy is what it is.** The model predicts "down" for 5,526 of 5,545
backtest bars (99.7%), so its accuracy equals the share of bars that were
"down": **0.492, identical to a constant-"down" baseline**. A gate on confidence
can only change accuracy by choosing which _market states_ to keep, and
confidence carries no information about them that shows up in correctness.

## Step 2: would recalibration help?

Two standard techniques, both fitted **forward in time** so nothing is tested on
data it was fitted on: Platt scaling (logistic regression on logit(confidence))
and isotonic regression, trained on the earlier folds and tested on the next, on
the 5,545-bar walk-forward series (6 contiguous folds; test = folds 2 to 6,
4,621 bars, base rate 0.495).

| Score                       | Brier  | Skill vs constant | Log-loss | ECE   | AUC for correctness [block-24 CI] |
| --------------------------- | ------ | ----------------- | -------- | ----- | --------------------------------- |
| Raw confidence, as reported | 0.4231 | **-0.692**        | 2.018    | 0.400 | 0.507 [0.491, 0.523]              |
| Platt scaling               | 0.2502 | -0.0003           | 0.6935   | 0.014 | 0.498 [0.482, 0.514]              |
| Isotonic regression         | 0.2520 | -0.0077           | 0.7197   | 0.020 | 0.500 [0.484, 0.517]              |
| Constant (train base rate)  | 0.2501 | 0.0000            | 0.6933   | 0.009 | 0.500                             |

- **Raw confidence is badly miscalibrated:** it is worse than predicting the base
  rate by 69% on Brier score, with an expected calibration error of 0.40.
- **Recalibration fixes the calibration and only that.** ECE falls from 0.40 to 0.014
  and the score becomes an honest probability, but it is honest because it
  collapses toward the base rate: the fitted Platt slope is **0.0067** (essentially
  flat), the isotonic fit has nine distinct levels spanning only 0.435 to 0.579, and
  the calibrated score on test data ranges from 0.463 to 0.519. Skill over a constant
  is zero (-0.0003) or slightly negative (isotonic, -0.0077: it overfits).
- **This is not a tuning problem.** Platt and isotonic (increasing) are monotone in
  confidence, so they preserve its ranking exactly, and the ranking's AUC is 0.506.
  A monotone transform of a score that ranks at chance ranks at chance. Recalibration
  could only have helped if confidence carried information that was merely
  mis-scaled; it does not.
- **Out of time, on the live bars.** Fitted on all of the backtest and tested on
  the 134 live bars (a later period, generated differently): Platt Brier 0.2498 vs
  constant 0.2495 (skill -0.001), isotonic -0.019, raw confidence -0.879 (mean
  predicted 0.910 against a live base rate of 0.463); AUC 0.485 / 0.475 / 0.482. Small
  sample, same answer.
- **Directional version.** The strategy acts on direction, so the probability of "up"
  was also checked against realized up-vs-not-up: AUC **0.505 [0.490, 0.519]**;
  forward-chained Platt on P(up) has skill -0.0005 and AUC 0.497 [0.482, 0.512]. The
  probability is not informative about direction either, which is the same finding as
  the earlier horizon and regime studies, from a different angle.

Answering the question as posed: this is a case where the model neither has
discriminative skill nor "knows when it is more likely to be right". Both were
tested separately, and both are absent.

## The gate's one real effect: it tilts toward shorts

Confidence is not distributed the same for both calls:

| Set      | Call | Rows  | Bars  | Mean confidence | Share passing 65% | Accuracy |
| -------- | ---- | ----- | ----- | --------------- | ----------------- | -------- |
| Backtest | down | 5,527 | 5,526 | 0.895           | 93.8%             | 0.492    |
| Backtest | up   | 17    | 17    | 0.521           | 0.0%              | 0.471    |
| Live     | down | 2,535 | 118   | 0.904           | 91.5%             | 0.363    |
| Live     | up   | 508   | 36    | 0.754           | 69.1%             | 0.439    |

Across all 8,589 predictions the 65% gate blocks **174 of 525 "up" calls (33%)**
against **559 of 8,062 "down" calls (7%)**. So although it filters nothing for
accuracy, it does change behaviour: it removes proportionally far more longs than
shorts, on a strategy that was already almost always short. The live "up" calls
were somewhat more accurate than the "down" calls (0.439 vs 0.363), but that is 36
and 118 bars, with no interval that supports a conclusion, and over a period in
which the market rose in 69 of 134 bars.

## Recommendation

**Remove the gate as decorative complexity. Neither tightening nor recalibrating
is supported by this data.**

- **Tighten:** no. No threshold's lift is distinguishable from zero on any of four
  views of the data (frozen, current, backtest, live), and tightening to 95% halves
  the number of predictions for no accuracy gain.
- **Recalibrate as a follow-up task:** no. It was tested. It repairs a
  meaningless-but-large miscalibration (ECE 0.40 to 0.014) into a score that is
  honest and useless, because the ranking underneath it is at chance. A recalibration
  task would produce a well-scaled number that still means nothing.
- **Remove:** yes, with two qualifications that are your call:
  1. **Keep the "confidence is present" check.** It is not a quality filter, it is
     what restricts the strategy to model kinds that produce a probability (a
     regressor has none and always logs `no_action`).
  2. **Removing the threshold changes behaviour**, because of the tilt above: with
     the gate off, the strategy acts on the roughly one in three "up" calls it
     currently blocks, so it will be somewhat _less_ short. This is a change in
     trading behaviour, not a neutral cleanup, and this data cannot say which
     behaviour is better. It is still the more honest state: the strategy would
     follow the model's raw call rather than a filter that selects by a number
     that has no relationship to correctness.
  - A no-code equivalent exists today: the per-account
    `confidence_threshold_pct` accepts any value above 0, so setting it to 1 disables
    the filter for that account without changing any code or the default. That would
    let you watch the difference before committing to removing it.

## What would change this answer, and what this does not cover

- **A different model.** Every one of these predictions is from one logistic
  regression, whose probabilities are nearly saturated (27% above 0.99). A model
  class with better-behaved probabilities, or with real skill, could have an
  informative confidence. This finding is about _this_ model's confidence, not
  confidence in general. If the model ever gains real discriminative skill, this
  should be re-run, not assumed.
- **Power.** On 5,545 backtest bars the AUC interval is about +/-0.014, so this
  rules out any confidence effect above roughly AUC 0.52; it cannot rule out a
  tiny one. The live evidence (134 bars, interval about +/-0.09) is weak in
  isolation and is not what the conclusion rests on.
- **Multiple comparisons.** Ten thresholds and seven bins were looked at; nothing
  clears its own interval, and no selection is offered as a finding.
- **Live-bar disagreement.** In 20 of 134 live bars, repeated predictions
  disagreed on correctness (their inputs moved between ticks); the live series was
  reduced to the first prediction per bar for the AUC and calibration work. The
  threshold sweep counts all rows but resamples by bar, so it is not affected.
- **Growing data.** The live set grows every scheduler tick (8,126 at the earlier
  analysis, 8,589 now), so the current-set figures will keep moving; the frozen set
  is the reproducible one, and the current set agrees with it (accuracy 0.451 at
  no gate and 0.450 at 65%).
- **Not done, on purpose.** No threshold, no strategy code and no configuration was
  changed by this audit.

## Related

- The original finding this audit follows up: mean confidence 0.889 against
  accuracy 0.460 over 8,126 graded predictions, in
  `FUTURES_MECHANICS_AND_LEVERAGE_DESIGN.md` (Part 5, D1). Its live-only
  correlation should be read through the correction above.
- The pseudo-replication method it adapts: `HORIZON_SWEEP_ASSESSMENT.md`.
- No-skill findings by model class, horizon and regime:
  `CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`, `HORIZON_SWEEP_ASSESSMENT.md`,
  `REGIME_WALKFORWARD_ASSESSMENT.md`.
