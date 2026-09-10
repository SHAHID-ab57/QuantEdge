# Prediction Horizon Sweep (M4-E3-T3)

Cross-linked from
[`CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`](./CONNECTOR_FEATURE_VALUE_ASSESSMENT.md).
That report established, across two model classes and every diagnostic it
could bring to bear, that no feature tested — baseline OHLCV+SMA or any of
the six Milestone-4 connectors — carries recoverable directional signal
**at a 1-hour horizon**. Every prior comparison in that thread was run at
exactly one horizon: next candle.

This sweep asks the cheap follow-up question before spending anything on
the next one: **is the open question "which features" or "which horizon"?**
Horizon is already a parameter of the `next_direction` target — no new
connector, model, or infrastructure. Sequenced the same way the connector
comparison itself was: sweep horizons with the **baseline feature set
alone** first; only redo the connector comparison at a horizon that
actually shows skill.

## TL;DR verdict

**No horizon from 1 h to 48 h shows genuine, replicable directional skill.**

- At **h = 1** the result is exactly what
  `CONNECTOR_FEATURE_VALUE_ASSESSMENT.md` § "M4-E3-T2" already reported: a
  faint held-out ROC-AUC of ~0.53 under logistic regression whose 95% CI
  barely clears 0.5, and nothing (CI includes 0.5) under Random Forest. A
  statistically-detectable, economically meaningless whisper, and only
  under one model family.
- At **h = 4, 12, 24, 48** the naive per-row bootstrap makes held-out
  ROC-AUC look like it _rises_ to 0.54–0.58 with CIs that exclude 0.5 at
  h24/h48. This is a **pseudo-replication artifact**. Consecutive
  h-step-ahead targets overlap by h−1 candles, so the ~3,400 test rows are
  not 3,400 independent outcomes — closer to n / h ≈ 71–850. A **block
  bootstrap** (block length = horizon), which preserves that dependence,
  widens **every** CI at h ≥ 4 to include 0.5.
- The generalizing models (logistic, regularized RF) at h24/h48 predict
  the majority class ("up") for essentially every test row —
  **permutation importance is exactly 0.000 for every feature**, test-F1
  matches the mechanical "always predict up" value, test accuracy equals
  the up-rate. No decision skill; the residual ROC > 0.5 is a faint
  probability-ranking effect on one contiguous, trending test block.
- The recent cross-check window (n ≈ 150) does not replicate anything —
  logistic ROC-AUC ranges from 0.39 (h12, CI _entirely below_ 0.5) to
  0.59 (h48, CI includes 0.5); Random Forest is pure overfitting (train
  ROC-AUC 0.95–0.99 on 666–699 rows). Insufficient statistical power, the
  same verdict M4-E3-T2's secondary comparison reached.

**The cheap hypotheses are now exhausted.** The A/B fork left open at the
end of the Random Forest re-test — (A) move to Epic 4.2 / Milestone 5, or
(B) build historical order-flow / microstructure persistence and test that
instead — should be made against this: no OHLCV-derived feature carries
next-1h-to-next-48h directional signal under either model class, on either
window, once overlapping-window dependence is handled honestly. Do **not**
re-run the six-connector comparison at any horizon.

---

## Method

Reuses the exact in-process dataset-build path `TrainingJobService` uses
(`MLDatasetService.build_ml_dataset` → `build_training_dataset`,
`normalize=True`) — verified byte-identical to the API path in the RF
re-test follow-up, and re-confirmed here: h = 1 full-history logistic
regression reproduces M4-E3-T2's reported baseline test ROC-AUC (0.531 vs
0.5306) to three decimals.

- **Feature set**: baseline only — `ohlcv` + `sma(period=20, source=close)`.
- **Target**: `next_direction` at `horizon` ∈ {1, 4, 12, 24, 48}.
- **Symbol / timeframe / split**: ETHUSD / 1h / 0.7 / 0.15 / 0.15
  chronological — identical to every prior comparison in the thread.
- **Windows**: `full` = 2024-02-06 → 2026-09-10 (22.7k candles, the
  statistically-powered window); `recent` = 2026-07-30 → 2026-09-10 (the
  shorter cross-check window). Both from M4-E3-T2.
- **Models per (horizon, window)**:
  - `logistic` — `LogisticRegression(max_iter=200, C=1.0)`, the adapter default.
  - `rf_modest` — `RandomForestClassifier(n_estimators=200, max_depth=8,
min_samples_leaf=2)`, the RF adapter default.
  - `rf_regularized` — `RandomForestClassifier(400, max_depth=4,
min_samples_leaf=25)`, the config from the RF re-test follow-up that
    closes the overfit gap (full window only — the recent window is 666
    rows, all configs overfit there regardless, ground already covered).
- **Diagnostics, applied uniformly at every horizon**:
  - accuracy 95% noise band = `1.96 · sqrt(0.25 / n_test)`;
  - held-out ROC-AUC with a **1000-sample per-row bootstrap CI** (as in
    the connector report) **and** an **800-sample circular block
    bootstrap CI** (block length = horizon) for the full-window
    horizons, which is the correction for overlapping targets;
  - **permutation importance** on the held-out test split (accuracy drop
    per feature, 15 shuffles);
  - **threshold-artifact watch** — accuracy / F1 moving across horizons
    while ROC-AUC does not (as the horizon grows the "flat" class
    vanishes — exact close-price equality h candles ahead — shifting the
    class balance mechanically from 3-class toward binary up/down).

---

## Full-history window — the statistically-powered result

Held-out **test** metrics. `teROC` is the evaluation engine's multiclass
one-vs-rest weighted ROC-AUC; `sweep CI` is its 1000-sample per-row
bootstrap 95% CI.

| h   | model          | n_test | train acc | test acc | test F1 | test ROC-AUC | sweep CI (per-row) | overfit gap |
| --- | -------------- | ------ | --------- | -------- | ------- | ------------ | ------------------ | ----------- |
| 1   | logistic       | 3408   | 0.527     | 0.504    | 0.370   | 0.531        | [0.515, 0.549]     | +0.02       |
| 1   | rf_modest      | 3408   | 0.651     | 0.492    | 0.417   | 0.510        | [0.490, 0.529]     | +0.16       |
| 1   | rf_regularized | 3408   | 0.548     | 0.494    | 0.350   | 0.509        | [0.490, 0.529]     | +0.05       |
| 4   | logistic       | 3407   | 0.513     | 0.513    | 0.358   | 0.525        | [0.508, 0.543]     | +0.00       |
| 4   | rf_modest      | 3407   | 0.641     | 0.519    | 0.495   | 0.517        | [0.498, 0.536]     | +0.12       |
| 4   | rf_regularized | 3407   | 0.533     | 0.515    | 0.410   | 0.517        | [0.498, 0.536]     | +0.02       |
| 12  | logistic       | 3406   | 0.524     | 0.529    | 0.370   | 0.522        | [0.503, 0.540]     | −0.01       |
| 12  | rf_modest      | 3406   | 0.650     | 0.510    | 0.461   | 0.519        | [0.501, 0.538]     | +0.14       |
| 12  | rf_regularized | 3406   | 0.558     | 0.523    | 0.420   | 0.515        | [0.496, 0.533]     | +0.04       |
| 24  | logistic       | 3404   | 0.541     | 0.523    | 0.367   | 0.550        | [0.530, 0.567]     | +0.02       |
| 24  | rf_modest      | 3404   | 0.664     | 0.489    | 0.483   | 0.527        | [0.509, 0.544]     | +0.17       |
| 24  | rf_regularized | 3404   | 0.567     | 0.524    | 0.360   | 0.512        | [0.495, 0.531]     | +0.04       |
| 48  | logistic       | 3401   | 0.562     | 0.511    | 0.346   | 0.576        | [0.560, 0.595]     | +0.05       |
| 48  | rf_modest      | 3401   | 0.699     | 0.570    | 0.498   | 0.558        | [0.536, 0.576]     | +0.13       |
| 48  | rf_regularized | 3401   | 0.618     | 0.511    | 0.346   | 0.562        | [0.543, 0.579]     | +0.11       |

Read naively, this table looks like "longer horizons show more skill": the
logistic ROC-AUC climbs 0.53 → 0.53 → 0.52 → 0.55 → 0.58, and at h24/h48
its per-row CI excludes 0.5. **Three things say that is not skill:**

### 1. Overlapping targets — the per-row CI is not valid at h > 1

A 1-hour candle series produces `next_direction_h` targets that overlap:
row _t_'s 24-hour-ahead outcome and row _t+1_'s share 23 of their 24
candles. The ~3,400 "test rows" at h24 are ~142 independent 24-hour
outcomes; at h48, ~71. A bootstrap that resamples rows as if independent
therefore reports a CI several times too narrow — exactly where the
ROC-AUC crept up.

The **circular block bootstrap** (resample contiguous blocks of length =
horizon, preserving the dependence) is the correction. Full-history
window, binary "up vs not-up" ROC-AUC (the honest question once "flat" is
~empty):

| h   | model          | ROC-AUC | per-row CI     | **block CI (overlap-corrected)** | n effective |
| --- | -------------- | ------- | -------------- | -------------------------------- | ----------- |
| 1   | logistic       | 0.532   | [0.513, 0.551] | **[0.514, 0.552]**               | ~3400       |
| 1   | rf_regularized | 0.507   | [0.489, 0.529] | **[0.488, 0.527]**               | ~3400       |
| 4   | logistic       | 0.516   | [0.497, 0.535] | **[0.491, 0.540]**               | ~850        |
| 4   | rf_regularized | 0.515   | [0.496, 0.534] | **[0.488, 0.542]**               | ~850        |
| 12  | logistic       | 0.512   | [0.491, 0.530] | **[0.468, 0.550]**               | ~284        |
| 12  | rf_regularized | 0.513   | [0.494, 0.531] | **[0.469, 0.555]**               | ~284        |
| 24  | logistic       | 0.540   | [0.520, 0.560] | **[0.483, 0.596]**               | ~142        |
| 24  | rf_regularized | 0.512   | [0.494, 0.531] | **[0.451, 0.573]**               | ~142        |
| 48  | logistic       | 0.562   | [0.546, 0.581] | **[0.484, 0.642]**               | ~71         |
| 48  | rf_regularized | 0.561   | [0.541, 0.578] | **[0.482, 0.640]**               | ~71         |

At **h = 1** the target windows don't overlap, so the two CIs agree — a
built-in sanity check — and logistic's [0.514, 0.552] barely clears 0.5
(the same whisper M4-E3-T2 reported), RF's includes it. At **every horizon
h ≥ 4 the block-bootstrap CI includes 0.5.** The apparent long-horizon
skill was an artifact of counting overlapping windows as independent
observations.

### 2. The generalizing models predict a constant — permutation importance is exactly zero

At h24 / h48, `logistic` and `rf_regularized` have:

- **test accuracy ≈ 0.51** = the "up" fraction of the test set (h48 test
  class distribution: 1738 up / 1661 down / 2 flat);
- **test F1 ≈ 0.35** = exactly `up_rate · F1(up)` for a model that
  predicts "up" every time (`0.511 · 0.676 ≈ 0.345`);
- **permutation importance = +0.000 for every one of the six features**
  (open, high, low, close, volume, sma_20) — shuffling any input column
  changes held-out accuracy by nothing, because the prediction was never
  a function of the inputs.

The model has **no decision skill**. The only reason ROC-AUC (which reads
`predict_proba`, not the argmax) sits slightly above 0.5 is that the
model's near-constant probability output has a faint rank-correlation with
outcomes _within one contiguous test block that trended upward_. Over a
2.5-year sample where ETH ran from ~\$2,400 to ~\$2,500 in sustained
moves, and with a chronological split whose train and test periods both
trend, a model that leans "up" ranks up-days slightly above down-days
without predicting anything.

(`rf_modest` does move on permutation importance at h24/h48 — but its
train/test accuracy gap is 0.13–0.17. That is overfitting leaking into the
held-out score, the exact effect the RF re-test follow-up documented; the
regularized RF, gap 0.04–0.11, shows the zero.)

### 3. Threshold / class-balance artifact

Across horizons the class balance shifts mechanically: "flat" (exact
h-candle-ahead close equality) is 12 / 3408 rows at h1 and 1–2 / 3400 by
h24. Test accuracy and F1 wobble with that shift (0.50 → 0.51 → 0.53 →
0.52 → 0.51 accuracy; F1 0.37 → 0.36 → 0.37 → 0.37 → 0.35) while carrying
no information. This is the "F1 moves, ROC doesn't" watch from the
connector report, in its purest form — here the _accuracy_ moves and the
_discrimination_ (block-corrected ROC-AUC) does not clear 0.5.

---

## Recent cross-check window (n ≈ 150) — no replication, insufficient power

| h   | model     | n_test | train acc | test acc | test F1 | train ROC | test ROC-AUC | CI / note                                            |
| --- | --------- | ------ | --------- | -------- | ------- | --------- | ------------ | ---------------------------------------------------- |
| 1   | logistic  | 151    | 0.53      | 0.56     | 0.51    | 0.54      | —            | ROC undefined (test set has 2 of 3 classes)          |
| 1   | rf_modest | 151    | 0.88      | 0.54     | 0.53    | **0.96**  | —            | ROC undefined; train ROC 0.96 = memorization         |
| 4   | logistic  | 150    | 0.54      | 0.54     | 0.38    | 0.59      | —            | ROC undefined                                        |
| 4   | rf_modest | 150    | 0.88      | 0.55     | 0.54    | **0.95**  | —            | ROC undefined                                        |
| 12  | logistic  | 149    | 0.58      | 0.55     | 0.39    | 0.51      | **0.389**    | CI [0.301, 0.479] — _entirely below 0.5_             |
| 12  | rf_modest | 149    | 0.90      | 0.61     | 0.58    | **0.97**  | 0.712        | CI [0.631, 0.790] — overfit, disagrees with logistic |
| 24  | logistic  | 147    | 0.62      | 0.46     | 0.29    | 0.49      | —            | ROC undefined                                        |
| 24  | rf_modest | 147    | 0.93      | 0.77     | 0.75    | **0.98**  | —            | ROC undefined; acc 0.77 = majority-class rate        |
| 48  | logistic  | 144    | 0.68      | 0.57     | 0.41    | 0.58      | 0.586        | CI [0.498, 0.682] — lower bound touches 0.5          |
| 48  | rf_modest | 144    | 0.94      | 0.82     | 0.82    | **0.99**  | 0.907        | CI [0.854, 0.954] — train ROC 0.99, pure overfit     |

Nothing here is interpretable as skill. Where ROC-AUC is defined at all,
logistic ranges from 0.39 (below chance, h12) to 0.59 (h48, CI touches
0.5) with no coherent pattern; the two model families disagree wildly on
the same 149 rows (h12: logistic 0.39, RF 0.71), which is what
small-sample noise plus overfitting looks like, not a signal both would
see. Every RF run has a train ROC-AUC of 0.95–0.99 on 666–699 training
rows — memorization. This is the same "insufficient statistical power"
finding as M4-E3-T2's secondary comparison, and for the same reason: ~150
held-out rows cannot support a directional-skill judgement.

---

## Per-horizon verdict

| Horizon  | Full window (block-corrected)                                                  | Recent window                            | Verdict                                                                                       |
| -------- | ------------------------------------------------------------------------------ | ---------------------------------------- | --------------------------------------------------------------------------------------------- |
| **1 h**  | logistic ROC 0.53, CI [0.514, 0.552] — barely clears 0.5; RF CI includes 0.5   | ROC undefined (2/3 classes)              | **No skill** — the M4-E3-T2 whisper, one model family only, economically meaningless          |
| **4 h**  | both models CI includes 0.5                                                    | ROC undefined                            | **No skill**                                                                                  |
| **12 h** | both models CI includes 0.5                                                    | logistic 0.39 (CI below 0.5); RF overfit | **No skill**                                                                                  |
| **24 h** | both models CI includes 0.5 (per-row CI misleadingly excluded it for logistic) | ROC undefined / logistic acc 0.46        | **No skill** — per-row CI was a pseudo-replication artifact                                   |
| **48 h** | both models CI includes 0.5 (per-row CI misleadingly excluded it for both)     | logistic CI touches 0.5; RF pure overfit | **No skill** — apparent 0.56–0.58 ROC is a constant-prediction model ranking a trending block |

No horizon shows skill that holds across **both** model classes **and**
**both** windows once overlapping-target dependence is handled. Step 2's
conditional — "re-run the six-connector comparison at that horizon" — is
**not triggered**. There is no horizon worth redoing it at.

---

## Evidence trail

- No new application code. Analysis run in-process against
  `MLDatasetService.build_ml_dataset` → `build_training_dataset`
  (`normalize=True`); h = 1 full-history logistic reproduces M4-E3-T2's
  reported baseline test ROC-AUC (0.531 vs 0.5306).
- 25 model fits (5 horizons × {full: 3 configs, recent: 2 configs}), each
  with train/validation/test accuracy + F1 + ROC-AUC, per-row bootstrap
  CI, permutation importance, class distributions.
- 10 additional fits for the circular block bootstrap (5 horizons ×
  {logistic, regularized RF}, full window), block length = horizon,
  n_effective ≈ n / horizon.
- All numbers above are read directly from the run outputs, not
  paraphrased.
- `tests/training tests/ml_datasets tests/evaluation` and the full backend
  suite pass unchanged (no application code touched).

## After this

**Follow-on (M4-E3-T4):** one more cheap check before the fork —
[`REGIME_WALKFORWARD_ASSESSMENT.md`](./REGIME_WALKFORWARD_ASSESSMENT.md).
Every result here still rests on one chronological split against one
test-period regime. A baseline model trained on an early 2024 window was
walked forward, via the existing Backtesting engine, over three genuinely
distinct out-of-sample regimes — a +100 % uptrend, a −28 % downtrend, a
flat choppy range. ROC-AUC was 0.50–0.51 in all three (every 95% CI
includes 0.5); the model predicts a near-constant "down" regardless of
regime. The negative finding is regime-invariant, not a single-window
artifact.

The A/B fork from the Random Forest re-test can now be made against a
fully exhausted set of cheap hypotheses rather than a single result:

- **No OHLCV-derived feature carries recoverable next-1h-to-48h
  directional signal**, under logistic regression or Random Forest, on the
  full history or a recent window, across an uptrend / downtrend / choppy
  regime, once overlapping-window dependence is handled. Two model classes,
  five horizons, two windows, three regimes, bootstrap CIs — the finding
  this thread has circled, in its strongest form.
- **Option A** (Epic 4.2 / Milestone 5) is now backed by an actually
  exhausted set of cheap tests.
- **Option B** (build historical order-flow / microstructure persistence
  and test _that_) remains the only untested hypothesis with real
  theoretical grounding — but it carries the infrastructure cost these
  research tasks were the prerequisite for deciding to pay.
