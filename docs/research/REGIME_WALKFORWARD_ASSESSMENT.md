# Regime Walk-Forward Assessment (M4-E3-T4)

Cross-linked from
[`HORIZON_SWEEP_ASSESSMENT.md`](./HORIZON_SWEEP_ASSESSMENT.md) and, through
it, [`CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`](./CONNECTOR_FEATURE_VALUE_ASSESSMENT.md).

Every experiment in this thread — M4-E3-T1 through the horizon sweep —
rested on a single chronological train/val/test split, evaluated against
exactly one test-period market regime. The horizon sweep's own diagnosis
of the h24/h48 illusion ("a near-constant probability output
rank-correlating with one contiguous, trending test block") is the reason
that matters: a single test window can make a model look skillful or
unskillful for reasons unrelated to real, general predictive ability. The
"no recoverable skill anywhere" conclusion the A/B fork depends on could
itself be a property of the one regime every evaluation happened to test
against.

This is the last cheap check. The Backtesting engine (already built,
already verified for no-look-ahead) walks a fixed model over any historical
range, one live prediction plus an immediate grade per step. Applying it
across genuinely different regimes — an uptrend, a downtrend, a
choppy/range-bound period — **is** a walk-forward validation, using
infrastructure that already exists.

## TL;DR verdict

**The "no recoverable skill" finding holds identically across all three
regimes.** One baseline model (OHLCV + SMA(20), `next_direction` h=1,
logistic regression) trained on an early 2024 window and walked
forward — every regime strictly out-of-sample — over:

| Regime    | Window (UTC)            | Net price Δ                  | Steps | Graded | **ROC-AUC (up-vs-not)** | **95% CI**         | Accuracy | Base rate (up) |
| --------- | ----------------------- | ---------------------------- | ----- | ------ | ----------------------- | ------------------ | -------- | -------------- |
| Uptrend   | 2025-05-01 → 2025-07-20 | **+100 %**                   | 1 920 | 1 920  | 0.512                   | **[0.485, 0.537]** | 0.481    | 0.519          |
| Downtrend | 2025-10-15 → 2025-12-25 | **−28 %**                    | 1 704 | 1 704  | 0.507                   | **[0.480, 0.534]** | 0.498    | 0.500          |
| Choppy    | 2026-03-01 → 2026-05-20 | **+8 %** (range 1 900–2 470) | 1 920 | 1 920  | 0.495                   | **[0.469, 0.521]** | 0.498    | 0.498          |

**Every regime's ROC-AUC 95% CI includes 0.5.** No regime shows
discrimination distinguishable from chance. The finding is not an artifact
of the single test regime prior evaluations drew from — it reproduces
across a doubling uptrend, a sharp decline, and a flat range.

The one metric that _does_ vary by regime — the backtest engine's reported
precision (0.62 uptrend / 0.25 downtrend / 0.46 choppy) — is an artifact,
not skill: the model is a **near-constant "down" predictor** (99.8 %+ of
its calls are "down" in every regime), so its precision is just how often
"down" happened to be right in that regime's actual outcome distribution.
A threshold-independent metric (ROC-AUC) removes that and shows ~0.5
everywhere. This is exactly the kind of regime-sensitive _surface_ metric
that could be mistaken for regime-dependent skill; it isn't.

**The cheap checks are exhausted.** The A/B fork — (A) Epic 4.2 /
Milestone 5, or (B) build historical order-flow / microstructure
persistence — can now be decided knowing the negative result holds across
horizons _and_ regimes, on a genuine walk-forward.

---

## Step 1 — Regime identification

Criteria, applied to the actual stored ETHUSD/1h history (monthly net
return, intra-window range, and trend consistency inspected directly —
[full monthly table below](#appendix--monthly-regime-scan)):

- **Uptrend** — a window where price rises substantially and consistently.
  ETH's clearest sustained advance is **2025-05 → 2025-07**: \$1 797 →
  \$3 592 close-to-close (+100 %), with each of the three months net
  positive or flat (+40.6 % / −1.6 % / +48.4 %). Window: `2025-05-01 →
2025-07-20`, ~1 920 hourly candles.
- **Downtrend** — a window where price falls substantially and
  consistently. **2025-10 → 2025-12**: \$4 119 → \$2 947 (−28 %), months
  −7.2 % / −22.2 % / (partial) — a steady decline off the 2025-08 peak.
  Window: `2025-10-15 → 2025-12-25`, ~1 704 candles.
- **Choppy / range-bound** — a window with little net movement but
  repeated reversals. **2026-03 → 2026-05**: \$1 962 → \$2 111 (+8 % net),
  oscillating in a \$1 900–\$2 470 band (+7.3 % / +6.7 % / −11.2 %).
  Window: `2026-03-01 → 2026-05-20`, ~1 920 candles.

The three windows are non-overlapping, each ~1 700–1 920 hourly steps
(under the engine's `MAX_BACKTEST_STEPS` = 2 000), and — importantly — all
three fall **strictly after** the model's training window, so every one is
a true out-of-sample walk-forward, not a re-test of training data.

Hourly up-fraction is ~50 % in every window (uptrend 51.9 %, downtrend
50.0 %, choppy 49.8 %) — the uptrend's +100 % comes from _asymmetric move
sizes_, not from more up-hours, so per-regime accuracy is close to
apples-to-apples and ROC-AUC is the honest skill metric.

## Step 2 — Walk-forward evaluation via the existing backtest engine

**Model.** A logistic-regression training job (`733082cc-…`, experiment
`f2c26957-…`), the exact baseline this thread has used — `feature_set` =
OHLCV + SMA(20), `target_config` = `next_direction` h=1, `split_config` =
0.7/0.15/0.15, `max_iter` 200, `C` 1.0, `normalize_features` true — trained
on **`2024-02-06 → 2024-11-01`** (4 499 train / 964 val / 965 test rows).
Its own held-out test metrics: accuracy 0.504, ROC-AUC 0.559, F1 0.435
(train ROC-AUC 0.599 — a mild overfit, consistent with everything prior).
This is a _different fit_ from the horizon sweep's h=1 baseline (which
trained on the full history); training on an early window is what makes the
three regimes genuinely out-of-sample.

**Evaluation.** `POST /api/v1/backtests/run` for each regime window,
`step` = 1h, unmodified. The engine walks `as_of` across `[start, end)`,
calls `PredictionService.run` then `PredictionService.grade_now` per step
(both the exact code paths a live caller and the periodic grader use), and
reports `aggregate_metrics` from `app.evaluation.engine.default_engine` —
the shared `EvaluationEngine`, no parallel scorer. Every step in all three
runs graded successfully (5 544 / 5 544 total).

### Per-regime detail

| Regime    | Model's predictions         | Actual outcomes            | Mean P("up")     | Accuracy | ROC-AUC | CI             |
| --------- | --------------------------- | -------------------------- | ---------------- | -------- | ------- | -------------- |
| Uptrend   | 1 916 down · 4 up           | 921 down · 996 up · 3 flat | 0.118 (sd 0.121) | 0.481    | 0.512   | [0.485, 0.537] |
| Downtrend | 1 703 down · 1 up           | 850 down · 852 up · 2 flat | 0.089 (sd 0.111) | 0.498    | 0.507   | [0.480, 0.534] |
| Choppy    | 1 906 down · 12 up · 2 flat | 958 down · 957 up · 5 flat | 0.111 (sd 0.131) | 0.498    | 0.495   | [0.469, 0.521] |

(ROC-AUC here is binary up-vs-not-up — "flat" is 2–5 rows per regime — with
a 5 000-sample per-row bootstrap 95% CI. A row bootstrap is valid at h=1
because consecutive predictions grade against adjacent, non-overlapping 1h
windows, unlike the horizon sweep's h > 1 where a block bootstrap was
needed.)

**What the model actually does:** it predicts "down" almost every single
step, in every regime — mean P("up") ≈ 0.09–0.12, i.e. it assigns ~10 %
probability to "up" essentially always. Trained on the 2024 window (net
down from the February peak: \$3 527 high → \$2 520 by November), it learned
a "down" prior and carries it, unchanged, into an uptrend, a downtrend, and
a flat range alike. Its accuracy is just the "down" fraction of whatever
regime's outcomes it lands in; its ROC-AUC — whether the ~10 % it does
assign to "up" ranks true up-hours above true down-hours — is
indistinguishable from a coin flip in all three.

---

## Verdict

| Regime              | ROC-AUC | 95% CI clears 0.5?  | Verdict  |
| ------------------- | ------- | ------------------- | -------- |
| Uptrend (+100 %)    | 0.512   | No ([0.485, 0.537]) | No skill |
| Downtrend (−28 %)   | 0.507   | No ([0.480, 0.534]) | No skill |
| Choppy (+8 % range) | 0.495   | No ([0.469, 0.521]) | No skill |

The negative finding is **regime-invariant**. It is not the property of one
test window; it holds across three genuinely distinct market regimes on a
true out-of-sample walk-forward, using the platform's own verified
backtesting and grading code. Combined with the horizon sweep (negative
across 1 h – 48 h) and the Random Forest re-test (negative under a
non-linear model), there is no remaining cheap hypothesis under which an
OHLCV-derived feature set carries recoverable next-candle directional
signal.

## After this

Decide the A/B fork:

- **Option A** — Epic 4.2 (Delta REST/WS completion, liquidation heatmap)
  / Milestone 5 (production hardening). Now backed by negative results
  across model classes, horizons, _and_ regimes.
- **Option B** — build historical order-flow / microstructure persistence
  and test _that_ feature family. The one hypothesis with real theoretical
  grounding that this thread's infrastructure cannot cheaply reach; the
  regime check was the last prerequisite for deciding whether to pay that
  cost.
- A regime-aware-modelling redirect is **not** indicated: performance did
  not vary meaningfully by regime, so there is no regime signal for a
  regime-aware model to exploit.

---

## Evidence trail

- No application code changed. The Backtesting engine, prediction service,
  and grading logic were used exactly as they ship.
- 1 training job (`733082cc-…`) + 3 backtest runs (`7ae94008-…` uptrend,
  `2570044b-…` downtrend, `07265f34-…` choppy) — all real persisted rows,
  fully graded (5 544 predictions), kept as the record.
- Per-regime ROC-AUC CIs and confusion counts recomputed directly from the
  persisted `predictions` rows (tagged with each run's `backtest_run_id`).
- `uv run pytest tests/backtest tests/prediction` and the full backend
  suite pass unchanged.

## Appendix — monthly regime scan

ETHUSD/1h, close-to-close monthly, used to pick the three regime windows:

| Month   | Net return | Low – High    | Month   | Net return  | Low – High    |
| ------- | ---------- | ------------- | ------- | ----------- | ------------- |
| 2024-02 | +43.2 %    | 2 329 – 3 527 | 2025-05 | **+40.6 %** | 1 751 – 2 790 |
| 2024-03 | +7.9 %     | 3 057 – 4 096 | 2025-06 | −1.6 %      | 2 112 – 2 879 |
| 2024-04 | −16.8 %    | 2 811 – 3 731 | 2025-07 | **+48.4 %** | 2 372 – 3 942 |
| 2024-05 | +25.4 %    | 2 815 – 3 978 | 2025-08 | +19.3 %     | 3 354 – 4 957 |
| 2024-06 | −8.7 %     | 3 218 – 3 889 | 2025-09 | −5.7 %      | 3 823 – 4 769 |
| 2024-07 | −6.1 %     | 2 807 – 3 563 | 2025-10 | **−7.2 %**  | 3 406 – 4 755 |
| 2024-08 | −22.3 %    | 2 130 – 3 243 | 2025-11 | **−22.2 %** | 2 622 – 3 918 |
| 2024-09 | +3.8 %     | 2 151 – 2 728 | 2025-12 | +4.8 %      | 2 719 – 3 447 |
| 2024-10 | −3.8 %     | 2 310 – 2 771 | 2026-01 | −17.7 %     | 2 228 – 3 404 |
| 2024-11 | +46.7 %    | 2 357 – 3 742 | 2026-02 | −19.9 %     | 1 741 – 2 475 |
| 2024-12 | −9.6 %     | 3 100 – 4 109 | 2026-03 | **+7.3 %**  | 1 906 – 2 386 |
| 2025-01 | −1.9 %     | 2 912 – 3 744 | 2026-04 | **+6.7 %**  | 2 016 – 2 464 |
| 2025-02 | −32.6 %    | 2 072 – 3 331 | 2026-05 | **−11.2 %** | 1 965 – 2 423 |
| 2025-03 | −17.8 %    | 1 753 – 2 550 | 2026-06 | −22.0 %     | 1 504 – 2 021 |
| 2025-04 | −2.1 %     | 1 384 – 1 957 | 2026-07 | +18.2 %     | 1 552 – 1 981 |
|         |            |               | 2026-08 | +32.3 %     | 1 821 – 2 566 |

Bold rows are the months inside the three chosen regime windows.
