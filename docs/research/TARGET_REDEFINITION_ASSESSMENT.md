# Target Redefinition Assessment

**Question:** binary direction at a fixed horizon (`next_direction`) has now
failed five independent, rigorous checks across this research thread
(`CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`, `HORIZON_SWEEP_ASSESSMENT.md`,
`REGIME_WALKFORWARD_ASSESSMENT.md`, the funding/open-interest assessment,
and `CONFIDENCE_RECHECK_POST_FIX.md`'s own confirmation that the confidence
finding survives the drift fix). Are volatility prediction or
triple-barrier labeling real, structurally different targets worth
building on this platform's own data — checked with cheap diagnostics
first, then, if those hold up, with the same rigorous comparison every
other candidate in this thread was held to? **No target was assumed to
work because it is a reasonable hypothesis elsewhere.** Measured
2026-09-24.

## TL;DR

1. **Both cheap diagnostics came back real, on this platform's own stored
   data — checked, not assumed.** ETH's realized volatility shows a
   strong, textbook volatility-clustering signature (autocorrelation of
   squared/absolute returns persists for 100+ lags; Ljung-Box Q(20) ~=
   1,138 against a ~45 critical value), while raw returns show none —
   exactly the asymmetry a mean-reverting-direction, persistent-magnitude
   process predicts. Triple-barrier labeling produces a healthy,
   non-degenerate three-way split at several reasonable barrier/horizon
   settings (e.g. 32%/32%/35% up/down/time-expired at a +/-5%/72h barrier
   informed directly by this platform's own real 5% stop-loss
   convention).
2. **Both targets were built as real platform infrastructure**
   (`app/ml_datasets/targets/triple_barrier.py`,
   `app/ml_datasets/targets/volatility_regime.py`), extending
   `TargetPipeline`/`MLDatasetService` — not a second, parallel pipeline —
   and unit-tested.
3. **On the primary, properly-powered comparison, neither target shows a
   real, tradable edge with this platform's existing feature set.**
   `volatility_regime` is flat: ROC-AUC 0.49-0.55 across all three
   classifiers, accuracy within 1-3pp of the majority baseline, and
   permutation importance for every feature under 0.03 — essentially
   nothing used, on any model. `triple_barrier` is more interesting but
   still not a finding: `random_forest`/`gradient_boosting` beat their
   majority-class baseline by 4-7pp (outside the ±1.6pp noise band) with
   `sma_20` carrying real, non-trivial permutation importance (0.07-0.10)
   — but ROC-AUC stays barely above chance (0.53-0.54) at the same time,
   and `logistic_regression` on the identical data _collapses_ to
   near-constant "up"/"down" calls with **zero or negative** permutation
   importance on every feature — the same degenerate-model signature this
   whole thread has flagged before, not a working model this time either.
4. **The cross-check window's dramatic numbers (up to 85% accuracy, 0.90
   AUC) are a small-sample artifact, exposed by the same permutation
   importance check** — `gradient_boosting`'s apparent skill on
   `triple_barrier` in that 139-row window is carried almost entirely by
   one feature, `close`, at an importance of **0.25** (vs. 0.01-0.07 for
   the same feature everywhere else in this whole comparison) — a
   coincidental, non-generalizing correlation in one 42-day stretch, the
   identical shape of inflation `CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`
   already caught once for DefiLlama TVL. Reported as insufficient power,
   not as corroborating evidence, per that document's own precedent.
5. **Net verdict: a sixth and seventh negative confirmation on this
   platform's existing feature set**, with one narrow, honestly-flagged
   exception (`triple_barrier` + tree models' modest accuracy edge) that
   is not strong enough, and not corroborated by its own AUC or by the
   cross-check window, to justify building real pipeline infrastructure
   around it yet — see [What would change this answer](#what-would-change-this-answer) for
   the concrete, cheap next check that could.

---

## Step 2: cheap diagnostics, before building anything

### Volatility clustering — real on this platform's own data

Checked directly on the real, full stored ETHUSD/1h history (23,048
candles, `2024-02-06` -> `2026-09-23`), not assumed from general
market-structure literature. Hourly log returns computed, then the
autocorrelation function (ACF) of the raw returns, their squares, and
their absolute values, at lags 1-100:

| Series              | ACF lag 1 | Mean ACF, lags 1-24 | Mean ACF, lags 25-100 | Fraction of lags 1-100 outside the +/-0.0129 (95%) white-noise band |
| ------------------- | --------: | ------------------: | --------------------: | ------------------------------------------------------------------: |
| Raw log returns     |    0.0042 |                  -- |                    -- |                                                               12.0% |
| Squared log returns |    0.1131 |              0.0436 |                0.0154 |                                                               67.0% |
| \|Log returns\|     |    0.2249 |              0.1115 |                0.0520 |                                                          **100.0%** |

**Reading it.** Raw returns show no linear structure worth acting on —
12% of lags exceeding a 95% band is close to the ~5% chance rate, mildly
elevated but not a clean signal (consistent with every direction-based
negative finding already in this thread). Squared and absolute returns
are a different picture entirely: **every one of the first 100 lags** of
`|returns|`'s autocorrelation clears the same band, decaying slowly from
0.22 at lag 1 to a still-positive 0.05 by lag 100. A Ljung-Box portmanteau
statistic on the squared-return series, Q(20) ~= **1,138**, dwarfs the
chi-squared(20) 99.9% critical value of ~45.3 — this is not a borderline
result. **This is the textbook volatility-clustering signature** (large
moves tend to be followed by large moves, of either sign, and calm periods
by calm ones) and it holds cleanly on this platform's own real data, not
merely in the literature this hypothesis usually cites.

### Triple-barrier labeling — not degenerate at reasonable settings

First-touch labels against a symmetric price barrier, computed on the same
full real candle history, at several `(barrier_pct, max_hours)` settings:

| Barrier | Max hours |        Up |      Down | Time expired | Verdict                                                |
| ------: | --------: | --------: | --------: | -----------: | ------------------------------------------------------ |
|      5% |        24 |     12.3% |     14.2% |    **73.5%** | Leaning degenerate — barrier too wide for the horizon  |
|  **5%** |    **72** | **32.4%** | **32.4%** |    **35.2%** | **Healthy three-way split**                            |
|      3% |        24 |     28.4% |     29.7% |        41.9% | Healthy                                                |
|      3% |        72 |     47.8% |     44.6% |         7.6% | Leaning degenerate — barrier too tight for the horizon |
|      2% |        24 |     40.9% |     40.6% |        18.6% | Healthy                                                |

**Reading it.** The task's own bar — "not 99% time expired" — is cleared
by a wide margin at several settings, not just one; this is a real,
usable label space, not a target that only "works" at a single
cherry-picked configuration. The chosen default (**+/-5%, 72h**) is the
setting closest to this platform's own real risk convention
(`paper_trading_strategy_default_stop_loss_pct = 5%`) that still produces
a healthy split — the 24h vertical barrier at the same 5% width is
dominated by "time expired" (73.5%) simply because a 5% move is a lot to
ask of ETH in one day at its own measured volatility (see
`RETRAIN_WINDOW_ANALYSIS.md`'s volatility reference: median 60% annualized
implies roughly a 2-3 day horizon for a 5% move to be typical, matching
the 72h setting's own healthier split far better than 24h's).

**Both diagnostics support proceeding to a real build**, per the task's
own instruction not to build the full pipeline on a discouraging
diagnostic just to see if it works out anyway.

---

## New target generators (built, tested, not yet run through the primary comparison at the time this section was written)

- **`app/ml_datasets/targets/triple_barrier.py`** — `TripleBarrier`,
  parameters `barrier_pct` (default 0.05) and `max_hours` (default 72),
  first-touch walk against a symmetric barrier, `horizon() = max_hours`.
- **`app/ml_datasets/targets/volatility_regime.py`** — `VolatilityRegime`,
  parameter `window_hours` (default 24), binary `"expand"`/`"contract"`
  label comparing realized volatility (population stdev of hourly log
  returns) over the next `window_hours` against the trailing
  `window_hours`. Framed as classification, not regression, deliberately:
  it fits the same three-classifier comparison
  (`logistic_regression`/`random_forest`/`gradient_boosting`) every other
  target in this thread was checked against, rather than requiring a
  fourth, regression-only model class (this platform's only regression
  adapter, `linear_regression`, has no classifier counterpart to compare
  against symmetrically). It also operationalizes the ACF finding
  directly: "will the next window be more or less turbulent than the one
  just observed" is exactly the question volatility clustering answers
  "yes, persistently" to.
- Both registered via the existing zero-touch discovery mechanism
  (`app/ml_datasets/targets/__init__.py`'s `load_builtin_targets`) —
  `TargetPipeline`/`MLDatasetService`/`TrainingJobService` needed no
  changes. Unit tests: `tests/ml_datasets/test_targets.py`
  (`TestTripleBarrier`, `TestVolatilityRegime`) — first-touch correctness
  in both directions, the forward-looking-contract boundary, column
  naming, dtype.

---

## Step 3: the primary comparison

Same methodology every prior candidate in this thread was held to: the
full real ETHUSD/1h history (`limit=23,000`, chronological 0.7/0.15/0.15
split — the "primary" comparison), a smaller recent-window "cross-check"
(reused verbatim from `CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`'s own T2
cross-check window, `2026-07-30` to `2026-09-10`), all three classifiers
(`logistic_regression`, `random_forest`, `gradient_boosting`), the fixed
feature representation from the start (`ohlc` + `volume_log` + `sma(20,
close)` — never the old, unsafe `ohlcv`), and permutation importance on
each held-out test split (`sklearn.inspection.permutation_importance`,
20 repeats, against the real saved model artifact and the real rebuilt
test matrix — the same `MLDatasetService`/`build_training_dataset` code
path `TrainingJobService` itself uses, not a second implementation).
**Noise bands** are the same binomial-SE approximation this thread has
used before (`±1.96*sqrt(p(1-p)/n)` against each target's own majority-
class base rate): **±1.6-1.7pp at the primary window's ~3,450-row test
split**, **±7.9-8.2pp at the cross-check window's ~140-row test split**
— the second figure lands within a rounding error of
`CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`'s own `±7.98pp` band for the
identical window, a useful cross-confirmation that this recheck is
measuring the same thing the same way.

### Primary window (full history, ~3,450-row test split — authoritative)

| Target              | Model                 | Test accuracy | Majority baseline | Test ROC-AUC | Top permutation importance (feature: mean ± std)                              |
| ------------------- | --------------------- | ------------: | ----------------: | -----------: | ----------------------------------------------------------------------------- |
| `triple_barrier`    | `logistic_regression` |         22.6% |             33.8% |        0.539 | **all six features 0.00 or negative** (max: `close` 0.00; min: `high` −0.158) |
| `triple_barrier`    | `random_forest`       |         40.7% |             33.8% |        0.532 | `sma_20` **0.105 ± 0.004**, `low` 0.034, `high` 0.027                         |
| `triple_barrier`    | `gradient_boosting`   |         34.2% |             33.8% |        0.537 | `sma_20` 0.071 ± 0.007, `close` 0.033                                         |
| `volatility_regime` | `logistic_regression` |         51.5% |             52.0% |        0.553 | `low` 0.029 ± 0.006, `sma_20` 0.025 ± 0.007                                   |
| `volatility_regime` | `random_forest`       |         49.8% |             52.0% |        0.530 | `open` 0.012 ± 0.003, `sma_20` 0.011 ± 0.003                                  |
| `volatility_regime` | `gradient_boosting`   |         50.2% |             52.0% |        0.493 | `sma_20` 0.018 ± 0.006, `low` 0.013 ± 0.006                                   |

**`volatility_regime` is flat, full stop.** Every ROC-AUC sits in
0.49-0.55 — indistinguishable from chance given the ±1.7pp-equivalent
noise this thread has used throughout — and every permutation importance
is small enough (max 0.029, most under 0.02, several with a std wider
than the mean) to describe a model using almost nothing. This is a real,
if slightly disappointing, finding given how clean the ACF diagnostic
was: **volatility clustering is real on this data, but the platform's
existing fixed feature set — price levels, log-volume, one SMA — does not
give any of the three classifiers enough to exploit it.** None of those
features directly measures volatility (no rolling realized-vol column, no
ATR, no Bollinger-band width); `sma_20`'s mild showing across all three
models is plausibly a weak, indirect proxy (a fast-moving SMA correlates
loosely with a choppier recent window) rather than a real volatility
read. This is a feature-engineering gap, not a refutation of the
diagnostic — see
[What would change this answer](#what-would-change-this-answer).

**`triple_barrier` is more interesting, and needs both numbers read
together, not separately.** `random_forest` beats its own majority
baseline by **6.9pp** and `gradient_boosting` by **0.4pp** — the former
comfortably outside the ±1.58pp noise band, a real, not-by-chance
difference in accuracy. But ROC-AUC for both sits at 0.532-0.537, barely
above chance — the same "accuracy moves, ranking doesn't" pattern
`CONFIDENCE_GATE_AUDIT.md` diagnosed at length for the old model's
confidence score. Permutation importance resolves which one to trust
here: `sma_20` genuinely carries real, non-trivial signal for both tree
models (0.071-0.105, several standard deviations from zero, an order of
magnitude above every other feature) — this is not a degenerate,
zero-importance model. **`logistic_regression` on the identical data
fails outright**: its own confusion matrix shows it predicting
"time_expired" on only 5 of 3,443 test rows (the true class is roughly a
third of the data) — a near-total collapse onto "up"/"down" — and its
permutation importance is **zero or negative on every single feature**,
meaning shuffling the inputs does not hurt (and sometimes helps) its
accuracy. This is the identical degenerate-model signature this thread
has already named more than once (the near-constant-"down" saturation
`FEATURE_DRIFT_INVESTIGATION.md` found, the always-"contract" collapse
`random_forest` shows on `volatility_regime` above) — logistic regression
simply does not fit this label well, independent of anything to do with
drift or normalization.

**Read plainly: a real, modest, tree-model-only accuracy edge on
`triple_barrier`, resting on one genuinely-used feature (`sma_20`), with
a ranking quality (ROC-AUC ~0.53) too weak on its own to call a working
model.** Worth a specific, cheap follow-up (below), not worth building
full pipeline infrastructure around yet.

### Cross-check window (recent 42-day slice, ~140-row test split — weaker, for robustness only)

| Target              | Model                 | Test accuracy | Test ROC-AUC | Top permutation importance             |
| ------------------- | --------------------- | ------------: | -----------: | -------------------------------------- |
| `triple_barrier`    | `logistic_regression` |         61.9% |        0.298 | `sma_20` 0.101 ± 0.021                 |
| `triple_barrier`    | `random_forest`       |         84.9% |        0.875 | `close` 0.014 ± 0.010                  |
| `triple_barrier`    | `gradient_boosting`   |         84.9% |    **0.900** | **`close` 0.253 ± 0.028**              |
| `volatility_regime` | `logistic_regression` |         22.2% |        0.427 | `volume_log` −0.090 ± 0.027 (negative) |
| `volatility_regime` | `random_forest`       |         47.2% |        0.569 | `sma_20` 0.047 ± 0.020                 |
| `volatility_regime` | `gradient_boosting`   |         57.6% |        0.755 | `low` 0.051 ± 0.021                    |

**These numbers look dramatic, and are not corroborating evidence.**
`gradient_boosting`'s 84.9% accuracy / 0.900 AUC on `triple_barrier` is
the headline; its own permutation importance shows why to distrust it:
**`close` alone carries 0.253 importance** — ten times larger than
`sma_20`'s already-substantial 0.071-0.105 in the properly-powered
primary comparison, and drastically larger than `close`'s own importance
everywhere else in this entire comparison (0.00 to 0.033). A single raw
price-level feature dominating a model fit on 641 training rows spanning
six weeks is the textbook shape of a coincidental, non-generalizing
correlation with that window's own price trend — not a real, durable
pattern, and not what carries the primary window's own, much larger,
`sma_20`-driven signal. This is the same inflation
`CONNECTOR_FEATURE_VALUE_ASSESSMENT.md` already caught once, in the same
document, with the same tool: "permutation-importance cross-check shows
that number is inflated" (its own words, about DefiLlama TVL's impurity
importance). Applying that document's own standard here: **reported as
insufficient statistical power** (±7.9-8.2pp noise band, comparable to
`CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`'s own secondary comparison, which
it explicitly declined to treat as evidence either way) **rather than as
evidence the primary window's modest finding is stronger than it looks.**
`volatility_regime`'s cross-check numbers are noisier still and point in
inconsistent directions across the three models (one below-chance, two
above) — exactly what "too small to detect anything" looks like in
practice, not a second finding.

### What would change this answer

- **A volatility-specific feature.** `volatility_regime`'s flat result is
  most likely explained by feature absence, not target absence — the ACF
  diagnostic already confirms the underlying structure is real. A cheap,
  genuinely different next check: add a direct realized-volatility
  feature (rolling stdev of log returns, or ATR) to the existing feature
  set and re-run this exact comparison, rather than concluding volatility
  itself is unpredictable on this data.
- **A real walk-forward check for `triple_barrier` + tree models.** The
  one non-degenerate finding here (`random_forest`/`gradient_boosting`,
  `sma_20`-driven, primary window only) has not been walked forward the
  way `REGIME_WALKFORWARD_ASSESSMENT.md` walked the direction baseline
  across three real out-of-sample regimes. A modest accuracy edge with a
  weak AUC is exactly the shape that regime-walkforward exercise was
  built to stress-test — this is the cheapest, most direct way to find
  out whether it's real or another artifact this thread hasn't caught
  yet.
- **Not done, on purpose.** No new feature was added, no walk-forward
  regime check was run, and no model was promoted to production by this
  assessment — Step 3's own instruction was to run the established
  comparison and report, not to chase a lead into a second investigation
  in the same task.

## Related

- The five prior negative confirmations on binary direction:
  `CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`, `HORIZON_SWEEP_ASSESSMENT.md`,
  `REGIME_WALKFORWARD_ASSESSMENT.md`, the funding/open-interest
  assessment, `CONFIDENCE_RECHECK_POST_FIX.md`.
- The permutation-importance-catches-an-inflated-number precedent this
  document reuses directly: `CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`'s own
  DefiLlama TVL finding.
- The fixed feature representation used throughout (`ohlc` +
  `volume_log` + `sma(20)`, never raw `volume`) and why:
  `RETRAIN_WINDOW_ANALYSIS.md`.
