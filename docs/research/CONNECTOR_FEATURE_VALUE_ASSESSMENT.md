# Connector Feature Value Assessment

**Follow-ons:**
[`HORIZON_SWEEP_ASSESSMENT.md`](./HORIZON_SWEEP_ASSESSMENT.md) (M4-E3-T3)
takes the baseline feature set alone across prediction horizons 1 h – 48 h;
[`REGIME_WALKFORWARD_ASSESSMENT.md`](./REGIME_WALKFORWARD_ASSESSMENT.md)
(M4-E3-T4) walks the baseline model forward, via the existing Backtesting
engine, over three distinct out-of-sample market regimes (a +100 %
uptrend, a −28 % downtrend, a flat choppy range). Neither finds
recoverable directional skill — no horizon, no regime, ROC-AUC ~0.5
throughout. The cheap hypotheses are exhausted.

Two passes exist:

- **M4-E3-T2 (2026-09-10)** — the current, authoritative assessment. Redone
  on the corrected training pipeline (`start`/`end` now respected end to
  end), with the results split into a statistically-powered **primary**
  comparison and an explicitly under-powered **secondary** one. **Read this
  first.**
- **M4-E3-T1** — the original attempt, kept below as the historical record.
  Its verdict for all six features was **UNDETERMINED, blocked by a
  platform limitation**; that blocker (`FIX-TRAINING-DATE-RANGE`, commits
  `8634694` + `39d4389`) has since been fixed, which is what made T2
  possible.

---

## M4-E3-T2 — Redone on the corrected training pipeline

### TL;DR verdict (T2)

**With real statistical power, no connector feature produces a robust,
material improvement over the OHLCV + SMA(20) baseline.** On the primary
comparison (full ETHUSD/1h history, 22,711 samples, 3,408 held-out test
rows) every single-feature variant moves held-out accuracy and ROC-AUC by
**less than one percentage point** versus baseline — inside the ~±1.7 pp
95% noise band for a test set that size — except DefiLlama TVL, which
_slightly hurts_ held-out performance (−2.1 pp accuracy, −1.8 pp ROC-AUC).
The one eye-catching number, Fear & Greed's +4.9 pp validation F1, is a
class-balance shift in the decision threshold, not better discrimination:
its ROC-AUC barely moves.

The secondary comparison (Etherscan / CoinGecko / Marketaux, bounded to
those connectors' real 4-day backfill depth, 69 samples, 11 test rows) is
**too small to detect anything** — all five variants produce byte-identical
held-out predictions and all are overfitting-flagged. It is reported as
_insufficient statistical power_, not as evidence that those three features
have no value.

So the honest verdict is a clean split: **primary features (Fear & Greed,
FRED, DefiLlama) — measured, and no meaningful help; secondary features
(Etherscan, CoinGecko, Marketaux/News) — still not measurable, this time
purely for lack of data depth, not a pipeline bug.**

### Step 1 — Baseline and connector depth, confirmed against the live system

**Live baseline.** The experiment driving the one live automated
paper-trading strategy (account `2cff34d9-…-f8ba2c180164`) is still
`565ca966-1437-4f28-b7d9-1d58002e38af`; its current training job is
`6e7fb4ed-7142-4c8b-953e-b95788a4014b`
(`dataset_version="retrain-2026-09-09-real-recent-data"`, from
`PREP-RETRAIN-AND-BACKFILL`). Its `dataset_start`/`dataset_end` are both
**NULL** — it uses the corrected "most recent N candles" default, so it
currently trains on roughly the last 100 ETHUSD/1h candles
(`close` mean `2488.60`, range `2452.65`–`2513.45` — recent levels).
`feature_set` = OHLCV + SMA(20), `target_config` = `next_direction` h=1,
`split_config` = 0.7 / 0.15 / 0.15, `model_type` = `logistic_regression`,
hyperparameters `{epochs 10, learning_rate 0.001, batch_size 32,
random_seed 42, validation_frequency 1, max_iter 200}`. Every T2 variant
matches all of these exactly, varying only the feature set.

**Connector backfill depth**, re-checked directly against
`external_data_points` / `news_articles`:

| Source                        | Real coverage (first → last)        | Depth        | Group         |
| ----------------------------- | ----------------------------------- | ------------ | ------------- |
| `eth_tvl` (DefiLlama)         | 2017-09-27 → 2026-09-10 (daily)     | ~9 years     | Primary       |
| `fear_greed` (Alternative.me) | 2018-02-01 → 2026-09-10 (daily)     | ~8.6 years   | Primary       |
| `fed_funds_rate` (FRED)       | 1996-12-03 → 2026-09-01 (monthly)   | ~30 years    | Primary       |
| `news_sentiment` (Marketaux)  | 2026-08-06 → 2026-09-09 (daily)     | **~34 days** | **Secondary** |
| `eth_gas_price` (Etherscan)   | 2026-09-06 13:22 → 2026-09-10 12:47 | ~4 days      | Secondary     |
| `btc_dominance` (CoinGecko)   | 2026-09-06 17:45 → 2026-09-10 12:42 | ~4 days      | Secondary     |

**News placement — checked, not assumed.** The task called this out
explicitly: News belongs in the primary group _only_ if its depth is
closer to the deep connectors' than to Etherscan/CoinGecko's shallow end.
It is not. Marketaux has **34 days** of real backfill; the deep connectors
have **8–30 years**; Etherscan/CoinGecko have **4 days**. 34 days is ~30
days from the shallow end and ~3,000+ days from the deep end — an order of
magnitude closer to shallow. The Marketaux connector runs and stores real
data (34 `news_articles`, 25 `news_sentiment` points; connector committed
in `c4d892f`, feature at `app/features/builtin/news_sentiment.py`), but its
history is far too shallow for the primary window. **News is tested in the
secondary comparison.**

### Step 2 — Primary comparison (statistically meaningful)

**Window selection.** The deep connectors (Fear & Greed, FRED, DefiLlama)
all cover the _entire_ ETHUSD/1h candle history. The longest common window
they support is therefore bounded by the candle data itself:
**2024-02-06 08:00 → 2026-09-10 11:00 UTC, the full 22,732-candle
history** (22,711 usable rows after SMA-20 warmup + 1-bar horizon). This is
the literal longest supportable window, not a convenient recent slice.
Server run with `CANDLES_DEFAULT_LIMIT=CANDLES_MAX_LIMIT=25000` so the
training path's dataset rebuild loads the whole window (it passes no
explicit `limit`; only the config default and the pinned date range bound
it). All four variants report an **identical `close` normalization**
(mean `3095.367661`, std `727.567269`, min `1418.55`, max `4933.85`) —
byte-identical windows, a genuinely controlled comparison isolating exactly
one feature change each.

Split sizes (every variant): **n_train 15,897 / n_val 3,406 / n_test
3,408.** Headline `metrics` below = the **validation** split (what
`POST /evaluation/benchmark` ranks on); `test_*` = the held-out test split;
both reported because they disagree in informative ways.

| Variant             | VAL acc | VAL f1 | VAL roc | TEST acc | TEST f1 | TEST roc | TRAIN acc | overfit gap |
| ------------------- | ------- | ------ | ------- | -------- | ------- | -------- | --------- | ----------- |
| **baseline**        | 0.5059  | 0.4492 | 0.5136  | 0.5035   | 0.3699  | 0.5306   | 0.5269    | 0.023       |
| **+ Fear & Greed**  | 0.5070  | 0.4986 | 0.5142  | 0.5038   | 0.3734  | 0.5377   | 0.5276    | 0.024       |
| **+ FRED**          | 0.5094  | 0.4590 | 0.5135  | 0.5056   | 0.3761  | 0.5359   | 0.5265    | 0.021       |
| **+ DefiLlama TVL** | 0.5091  | 0.4590 | 0.5134  | 0.4827   | 0.3511  | 0.5122   | 0.5326    | 0.050       |

Deltas vs baseline, in **percentage points**:

| Variant         | VAL acc | VAL f1    | VAL roc | TEST acc  | TEST f1   | TEST roc  | TRAIN acc |
| --------------- | ------- | --------- | ------- | --------- | --------- | --------- | --------- |
| + Fear & Greed  | +0.12   | **+4.94** | +0.06   | +0.03     | +0.35     | +0.71     | +0.07     |
| + FRED          | +0.35   | +0.99     | −0.01   | +0.21     | +0.62     | +0.53     | −0.04     |
| + DefiLlama TVL | +0.32   | +0.99     | −0.02   | **−2.08** | **−1.88** | **−1.84** | +0.57     |

For a test set of 3,408 rows with accuracy near 0.5, the 95% confidence
half-width is `1.96 · sqrt(0.25 / 3408) ≈ 1.68 pp`. Read against that band:

- **Fear & Greed** — held-out accuracy and ROC-AUC move sub-1 pp. The
  +4.9 pp validation F1 comes entirely from a decision-threshold shift:
  baseline predicts "up" for 81% of validation rows, Fear & Greed for 62%
  (confusion matrix `[[649,0,1058],[0,0,4],[617,0,1078]]` vs baseline
  `[[319,0,1388],…]`). ROC-AUC — the threshold-independent measure — moves
  +0.06 pp on validation, +0.71 pp on test. **No real discrimination gain.**
- **FRED (Fed Funds Rate)** — uniformly tiny positive (+0.2 to +0.8 pp
  across held-out metrics), all inside the noise band. Note this is _not_
  byte-identical to baseline the way it was in the T1 degenerate run and
  the 41-day cross-check below: over 2.6 years the monthly rate actually
  varies, so it contributes a real but negligible slow-moving signal.
- **DefiLlama TVL** — the only variant that clearly moves outside the
  band, and in the **wrong direction**: −2.1 pp test accuracy, −1.8 pp
  test ROC-AUC, while train accuracy _rises_ +0.6 pp and the overfit gap
  roughly doubles (0.023 → 0.050). Signature of a feature the model fits
  in-sample and that then fails to generalize.

`POST /evaluation/benchmark` over the four (ranked on validation `metrics`)
puts them all within a 0.35 pp accuracy spread and a 0.08 pp ROC-AUC
spread; its `best_by_metric` pick is a meaningless tie-break at that
separation.

**Primary verdict: none of Fear & Greed, FRED, or DefiLlama TVL adds
measurable predictive value to the baseline on real, full-history data.
DefiLlama TVL marginally hurts held-out performance.**

#### Step 2 cross-check — recent-regime window (weaker, for robustness only)

The same three primary variants + baseline were also run on a **recent
41-day window** (`2026-07-30 00:00 → 2026-09-10 11:00`, 999 rows, n_train
699 / n_val 149 / n_test 151; server at `CANDLES_DEFAULT_LIMIT=1000`).
Byte-identical windows again (all `close` norm mean `2061.355222`).
`roc_auc` is not reported by the platform for this window's splits (no
"flat" outcomes present in val/test). Deltas vs baseline (pp):

| Variant         | VAL acc   | VAL f1     | TEST acc  | TEST f1   |
| --------------- | --------- | ---------- | --------- | --------- |
| + Fear & Greed  | **−2.68** | **−10.15** | **+3.31** | **+5.05** |
| + FRED          | +0.00     | +0.00      | +0.00     | +0.00     |
| + DefiLlama TVL | +6.04     | +8.28      | +1.32     | −0.03     |

This _reinforces_ the primary verdict rather than complicating it: Fear &
Greed's validation and test deltas have **opposite signs** (a feature with
real signal does not help one split by 3 pp while hurting the other by
3–10 pp — that is split-placement luck on ~150 rows); FRED is exactly inert
(over 41 days the monthly rate is a single forward-filled constant → a
zero-variance column after normalization → identical model); DefiLlama TVL
helps validation but not test F1. On the smaller window the noise is just
louder. Nothing robust survives across both windows.

### Step 3 — Secondary comparison (explicitly lower statistical power)

**Window selection.** Bounded by the shallowest connectors: `eth_gas_price`
(Etherscan) from `2026-09-06 13:22` and `btc_dominance` (CoinGecko) from
`2026-09-06 17:45`. The longest window all secondary connectors support is
**2026-09-06 18:00 → 2026-09-10 11:00 UTC** — 69 usable rows after warmup.
Split: **n_train 48 / n_val 10 / n_test 11.** All variants share an
identical `close` normalization (mean `2488.457292`) — controlled, just
tiny.

| Variant                    | VAL acc | VAL f1 | VAL roc | TEST acc | TEST f1 | TEST roc | overfit?    | gap   |
| -------------------------- | ------- | ------ | ------- | -------- | ------- | -------- | ----------- | ----- |
| **baseline (re-windowed)** | 0.600   | 0.617  | 0.762   | 0.3636   | 0.1939  | 0.464    | **flagged** | 0.282 |
| **+ Etherscan gas price**  | 0.600   | 0.617  | 0.762   | 0.3636   | 0.1939  | 0.500    | **flagged** | 0.261 |
| **+ CoinGecko BTC dom.**   | 0.500   | 0.475  | 0.762   | 0.3636   | 0.1939  | 0.607    | **flagged** | 0.366 |
| **+ Marketaux news**       | 0.700   | 0.710  | 0.762   | 0.3636   | 0.1939  | 0.393    | **flagged** | 0.303 |
| **+ all six**              | 0.600   | 0.600  | 0.762   | 0.3636   | 0.1939  | 0.536    | **flagged** | 0.407 |

**Every variant produces the identical held-out result** — test accuracy
`0.3636`, F1 `0.1939`, precision `0.1322` — i.e. the same predictions on
all 11 test rows regardless of which features are present, including the
all-six variant. Validation numbers wander (news +10 pp accuracy, BTC
dominance −10 pp) but a 10-row validation set moves 10 pp per _single_
reclassified sample. Test ROC-AUC swings ±14 pp on 11 rows. Every model is
overfitting-flagged (train/held-out gap 0.26–0.41).

**Secondary verdict: not measurable — insufficient data depth, not a
pipeline defect.** 69 training-and-eval rows split three ways cannot
support a feature-value judgement for Etherscan gas price, CoinGecko BTC
dominance, or Marketaux news sentiment. This is a genuine, documented
free-tier limit (Etherscan `dailyavggasprice` and CoinGecko historical
market-cap chart are both Pro-only — see the T1 "Update 2026-09-09"
section); the only fix is real-time polling accruing depth by one calendar
day per day. **Re-run this secondary comparison once these connectors have
several months of coverage — not before.** Reported here as lower
statistical power due to sample size, explicitly _not_ as equivalent
evidence to the primary comparison.

### Per-feature verdict (T2)

| Feature                       | Group     | Verdict                                                                                                                                                                                               |
| ----------------------------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Fear & Greed (Alternative.me) | Primary   | **No measurable value.** Sub-1 pp held-out movement over 3,408 test rows; the large validation-F1 delta is a threshold shift, not discrimination. Signs flip between full-history and 41-day windows. |
| FRED (Federal Funds Rate)     | Primary   | **No measurable value.** Uniformly negligible (+0.2–0.8 pp held-out, inside noise); exactly inert on any window short enough that the monthly rate doesn't move.                                      |
| DefiLlama (ETH TVL)           | Primary   | **Marginally negative.** Only variant outside the noise band: −2.1 pp test accuracy, −1.8 pp test ROC-AUC, with a widening overfit gap. Does not generalize.                                          |
| Etherscan (gas price)         | Secondary | **Undetermined — insufficient depth.** ~4 days of real data; 69-row comparison shows byte-identical held-out predictions.                                                                             |
| CoinGecko (BTC dominance)     | Secondary | **Undetermined — insufficient depth.** Same as Etherscan.                                                                                                                                             |
| Marketaux (news sentiment)    | Secondary | **Undetermined — insufficient depth.** ~34 days of real data — checked against the task's own placement criterion and confirmed far closer to the shallow end. Same byte-identical held-out result.   |
| All six together              | Secondary | **Undetermined — insufficient depth.** Inherits the 4-day bound; identical held-out predictions to baseline.                                                                                          |

**Bottom line:** the corrected pipeline turns T1's blanket "UNDETERMINED"
into a real answer _for the three deep connectors_ — and that answer is
that they don't help a simple logistic-regression model on OHLCV+SMA(20).
The three shallow connectors remain unmeasurable, now for the honest
reason that their real backfill is only days deep.

### Evidence trail (T2)

- 13 real experiments/training jobs (4 primary full-history, 4 primary
  41-day, 5 secondary) — all real persisted DB rows, tagged `m4-e3-t2`,
  kept as the record. Primary full-history experiment ids:
  `8ae7e6b8-…` (baseline), `8083874a-…` (Fear & Greed), `5c051c43-…`
  (FRED), `bf6edcb6-…` (DefiLlama TVL).
- Byte-identical windows verified by comparing each variant's reported
  `close` normalization stats (mean/std/min/max), not just row counts.
- All numbers above are read directly from each job's
  `result_summary` (`metrics`, `test_metrics`, `train_metrics`,
  `confusion_matrix`, `overfitting`) and from the
  `POST /evaluation/benchmark` responses — not paraphrased.

---

## Random Forest re-test (ADD-RANDOM-FOREST-RETEST, 2026-09-10)

### Why this exists

The T2 primary finding — no deep connector feature adds measurable value —
carried one visible caveat: the baseline logistic-regression model's own
ROC-AUC was **0.53**, barely above a coin flip. A model with almost no
discriminative skill is a weak instrument for detecting whether a weak
_additional_ signal combines into something better. "These features don't
help" and "this specific weak linear model can't detect whatever signal
exists" are different claims. This re-test removes the confound by running
the identical primary comparison — same four variants, same windows, same
0.7/0.15/0.15 split, same rigor — against a `RandomForestClassifier`
(`app/training/adapters/random_forest.py`), the first model on the platform
able to represent the non-linear feature interactions a linear model
structurally cannot.

Modest, documented, un-tuned hyperparameters: `n_estimators=200`,
`max_depth=8`, `min_samples_leaf=2`, `max_features="sqrt"`,
`random_seed=42`. The question is whether _any_ signal exists that the
linear baseline missed, not maximum performance.

### Primary comparison under Random Forest — full history

Same window as T2 (`2024-02-06 08:00 → 2026-09-10 11:00 UTC`, 22,711 usable
rows, **n_train 15,897 / n_val 3,406 / n_test 3,408**), same byte-identical
windows (all four variants report `close` norm mean `3095.367661`).
Headline `metrics` = validation split; `test_*` = held-out test.

| Variant             | VAL acc | VAL f1 | VAL roc | TEST acc | TEST f1 | TEST roc | TRAIN acc | overfit?    | gap   |
| ------------------- | ------- | ------ | ------- | -------- | ------- | -------- | --------- | ----------- | ----- |
| **baseline**        | 0.5003  | 0.4165 | 0.5020  | 0.4918   | 0.4172  | 0.5095   | 0.6511    | **flagged** | 0.159 |
| **+ Fear & Greed**  | 0.5112  | 0.4502 | 0.5021  | 0.4944   | 0.4321  | 0.5027   | 0.6705    | **flagged** | 0.176 |
| **+ FRED**          | 0.4985  | 0.3955 | 0.5019  | 0.4988   | 0.4193  | 0.5110   | 0.6570    | **flagged** | 0.158 |
| **+ DefiLlama TVL** | 0.4974  | 0.3872 | 0.4996  | 0.4736   | 0.3465  | 0.4974   | 0.6489    | **flagged** | 0.175 |

Deltas vs baseline, in **percentage points**:

| Variant         | VAL acc | VAL f1 | VAL roc | TEST acc  | TEST f1   | TEST roc  | TRAIN acc |
| --------------- | ------- | ------ | ------- | --------- | --------- | --------- | --------- |
| + Fear & Greed  | +1.09   | +3.37  | +0.00   | +0.26     | +1.49     | **−0.69** | +1.94     |
| + FRED          | −0.18   | −2.11  | −0.02   | +0.70     | +0.21     | +0.15     | +0.59     |
| + DefiLlama TVL | −0.29   | −2.94  | −0.25   | **−1.82** | **−7.07** | **−1.22** | −0.22     |

95% noise half-width for n_test = 3,408 at acc ≈ 0.5 is still `±1.68 pp`.
Read against that band:

- **Baseline Random Forest generalizes _worse_ than baseline logistic
  regression** — TEST acc `0.4918` / ROC `0.5095` vs logistic's `0.5035` /
  `0.5306` — and **every full-history RF run is overfitting-flagged**
  (train acc ~0.65 vs held-out ~0.49, gap ~0.16 > the 0.15 threshold). The
  extra model capacity is spent memorizing training-set noise in hourly
  price data, not finding real structure. **This is the key result: giving
  the problem a more expressive model did not surface hidden signal — it
  produced a model that overfits.** The weak-instrument caveat is answered
  by "the signal genuinely isn't there," not by "use a stronger model."
- **Fear & Greed** — VAL F1 +3.37 pp, but VAL ROC-AUC `+0.00` and TEST
  ROC-AUC **−0.69**. Applying the T2 threshold-artifact diagnostic: an F1
  change with no corresponding ROC change is a decision-boundary shift, not
  a discrimination gain (confusion matrix moves from `[[210,0,1497],…]` to
  `[[307,0,1400],…]` — it just predicts "down" more often). **Same
  artifact, same verdict as under logistic regression.**
- **FRED** — every held-out delta inside the noise band (+0.2 to +0.7 pp).
  No effect.
- **DefiLlama TVL** — clearly outside the band and **negative**: −1.8 pp
  test accuracy, **−7.1 pp test F1**, −1.2 pp test ROC-AUC — worse than it
  was under logistic regression (−2.1 / −1.9 / −1.8). The forest's own
  impurity importance assigns `eth_tvl` **0.225** (22.5% of total — second
  only to `volume`), but see the follow-up section below: a
  permutation-importance cross-check shows that number is inflated by
  impurity importance's known bias toward continuous features, and
  `eth_tvl`'s _actual_ contribution on held-out data is ~zero (very
  slightly negative). Adding the feature to the set still makes the model
  ~2 pp worse on test accuracy; it just doesn't carry the ~22% of real
  signal the impurity number implied.

`POST /evaluation/benchmark` over the four (validation `metrics`): all
within a 1.1 pp accuracy / 0.25 pp ROC-AUC spread; `best_by_metric` is a
meaningless tie-break.

### Feature importances (Random Forest impurity, sums to 1)

The forest's own `feature_importances_`, a more direct signal than the
benchmark comparison — reported per variant, full-history window:

| Variant         | Top features by impurity importance                                                                        |
| --------------- | ---------------------------------------------------------------------------------------------------------- |
| baseline        | volume 0.474 · close 0.112 · open 0.110 · high 0.103 · low 0.103 · sma_20 0.099                            |
| + Fear & Greed  | volume 0.412 · close 0.115 · low 0.113 · open 0.112 · high 0.099 · sma_20 0.095 · **fear_greed 0.054**     |
| + FRED          | volume 0.431 · close 0.120 · low 0.119 · open 0.114 · high 0.106 · sma_20 0.097 · **fed_funds_rate 0.015** |
| + DefiLlama TVL | volume 0.328 · **eth_tvl 0.225** · close 0.101 · low 0.091 · open 0.087 · sma_20 0.084 · high 0.084        |

A feature being _split on_ by the forest (non-zero impurity importance) is
not the same as it _helping_: `eth_tvl` at 0.225 impurity importance still
degrades held-out F1 by 7 pp, and `fear_greed` at 0.054 still moves
held-out ROC-AUC by less than 1 pp. Impurity importance measures how often
a feature was split on to reduce _training_ impurity — it says nothing
about generalization, and it is specifically biased toward continuous /
high-cardinality features (Strobl et al. 2007), which is exactly the shape
of `eth_tvl` (a smooth multi-year series with thousands of distinct split
points) versus `fed_funds_rate` (a near-constant monthly step function).
**The follow-up section below replaces these impurity numbers with
permutation importance measured on the held-out test set**, which is not
subject to that bias — and it collapses `eth_tvl`'s apparent 0.225 down to
essentially zero.

### Cross-check — recent 41-day window (weaker, for robustness)

Same window as T2's cross-check (`2026-07-30 → 2026-09-10`, 999 rows,
n_test 151; `roc_auc` not emitted — no "flat" outcomes in val/test).
**n_test = 151 → 95% noise half-width ±7.98 pp.** Deltas vs baseline (pp):

| Variant         | VAL acc | VAL f1 | TEST acc | TEST f1 |
| --------------- | ------- | ------ | -------- | ------- |
| + Fear & Greed  | −2.68   | −2.44  | +1.99    | +2.47   |
| + FRED          | +0.00   | +0.00  | +1.32    | +1.88   |
| + DefiLlama TVL | +0.00   | −0.90  | +3.97    | +4.56   |

Every held-out delta is far inside the ±8 pp band — nothing here is
distinguishable from noise. FRED is byte-identical on validation and has
impurity importance **0.000** (a single forward-filled constant over 41
days → the forest never splits on it). Every recent-window RF run is
overfitting-flagged with a _much_ larger gap than the full-window runs
(train acc ~0.87 vs test ~0.55, gap ~0.31) — 699 training rows and 300
trees is pure memorization.

### Verdict (Random Forest re-test)

| Feature       | Under logistic regression (T2)                            | Under Random Forest                                                                                                                  | Change                  |
| ------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------- |
| Fear & Greed  | No measurable value; VAL-F1 delta is a threshold artifact | No measurable value; **same** threshold artifact (F1 moves, ROC does not)                                                            | None                    |
| FRED          | No measurable value; inert on short windows               | No measurable value; inert on short windows (importance 0.000)                                                                       | None                    |
| DefiLlama TVL | Marginally negative on held-out (−2.1 pp test acc)        | **Still negative** (−1.8 pp acc, −7.1 pp F1), robust to regularization; permutation importance ~zero (impurity's 0.225 was inflated) | Same, better understood |

**Bottom line: the negative finding survives a strictly more expressive
model — two model classes, same windows, same rigor, same conclusion.** The
follow-up work below (a regularization sweep that closes the overfit gap,
and a permutation-importance cross-check) does not change it: with a Random
Forest that generalizes consistently rather than overfitting, the connector
features still add no held-out value, and `eth_tvl`'s real (permutation)
contribution is ~zero despite a large impurity number. The 0.53-ROC-AUC
caveat on the T2 result is resolved in the direction of "the connector
features don't carry next-hour directional signal for this target," not
"the baseline model was too weak to tell."

Per this task's "After This" framing: Random Forest also showing nothing is
the materially-stronger-negative outcome, and the honest move is to stop
testing model classes and shift to Epic 4.2 / Milestone 5 — not to keep
searching for a model that rescues the connectors.

**Follow-on (M4-E3-T3):** before making that call, the one remaining cheap
hypothesis — "wrong horizon, not wrong features" — was tested in
[`HORIZON_SWEEP_ASSESSMENT.md`](./HORIZON_SWEEP_ASSESSMENT.md): baseline
feature set alone at horizons 1 h / 4 h / 12 h / 24 h / 48 h, both model
classes, both windows, this suite's diagnostics plus a block bootstrap for
the overlapping-target problem that only appears at h > 1. No horizon shows
recoverable skill. The apparent rise in ROC-AUC at h24/h48 is a
constant-prediction model (permutation importance exactly 0) ranking one
trending test block, with a per-row bootstrap CI made spuriously narrow by
counting overlapping windows as independent. That closes the cheap
hypotheses.

### Evidence trail (Random Forest re-test)

- 8 real experiments/training jobs (4 full-history, 4 recent-window),
  tagged `add-rf-retest`, kept as DB rows. Full-history experiment ids:
  `553c9976-…` (baseline), `5553c6f1-…` (Fear & Greed), `63b643e6-…`
  (FRED), `d6bc87c7-…` (DefiLlama TVL).
- Same byte-identical windows as T2 (verified via `close` normalization
  stats).
- All numbers read directly from each job's `result_summary` and the
  `POST /evaluation/benchmark` response.
- `random_forest` adapter: `model_kind="classification"`,
  `requires_real_data=True`, registered via the same zero-touch
  `@register` discovery as the two baseline adapters; unit + real-data
  end-to-end tests at `tests/training/test_random_forest.py`,
  `tests/training/test_registry.py`, `tests/api/test_training_api.py`;
  100% line coverage on `app/training/`.

### Follow-up (2026-09-10) — regularization sweep + permutation importance

Two objections to the re-test above were raised and checked directly. Both
are answered in favour of the same conclusion, with real numbers below.

The analysis was run in-process against the exact dataset-build path
`TrainingJobService` uses (`MLDatasetService.build_ml_dataset` →
`build_training_dataset`, `normalize=True`) — the modest-config numbers
reproduce the API runs above to four decimals (baseline full-history
validation `0.5003`, test `0.4918`, test ROC `0.5095`; DefiLlama TVL test
`0.4736`), so the splits are byte-identical and an in-process fit
reproduces the API model.

#### Objection 1 — "every RF run is overfitting-flagged, so it's a noisy instrument"

True of the modest config (`n_estimators=200, max_depth=8,
min_samples_leaf=2`): full-history train/held-out gap ~0.16–0.18, all four
variants flagged. So three progressively more-regularized configs were run,
aimed squarely at closing that gap. Full-history window (n_test 3,408,
95% noise half-width ±1.68 pp), held-out **test** accuracy:

| Config (`n_est / max_depth / min_samples_leaf`) | baseline test acc | overfit gap          | + Fear & Greed (Δ) | + FRED (Δ) | + DefiLlama TVL (Δ) |
| ----------------------------------------------- | ----------------- | -------------------- | ------------------ | ---------- | ------------------- |
| `200 / 8 / 2` (modest, as above)                | 0.492             | **+0.159 (flagged)** | +0.26 pp           | +0.70 pp   | **−1.82 pp**        |
| `300 / 5 / 10`                                  | 0.495             | +0.068               | +0.18 pp           | −0.09 pp   | **−2.32 pp**        |
| `400 / 4 / 25`                                  | 0.494             | +0.054               | −0.03 pp           | +0.12 pp   | **−2.08 pp**        |
| `400 / 3 / 50`                                  | 0.495             | +0.043               | +0.09 pp           | +0.06 pp   | **−2.02 pp**        |

Regularization closes the gap from 0.16 to ~0.04 — **none of the regularized
configs is overfitting-flagged.** And the conclusion is unchanged, in fact
cleaner:

- **Baseline test accuracy barely moves** (0.492 → 0.495) and test ROC-AUC
  stays 0.507–0.510 across every config. The modest RF was not overfitting
  _away_ a real signal — there is no signal at this horizon for a
  better-generalizing model to find. It just stops memorizing noise.
- **Fear & Greed and FRED held-out deltas shrink** from the noisier modest
  run (±0.3–0.7 pp) to well inside ±0.2 pp and straddling zero — no effect,
  measured more precisely.
- **DefiLlama TVL stays ~2 pp negative on test accuracy at every
  regularization level** (−1.8 to −2.3 pp). The harm is real and robust to
  model capacity, not an artifact of the deep unregularized trees.

Recent 41-day cross-check (n_test 151, ±7.98 pp band): every regularized
delta is inside the band; `fed_funds_rate` has impurity importance exactly
`0.000` at every config (constant over 41 days). Nothing distinguishable
from noise, same as before.

#### Objection 2 — "the DefiLlama 'spurious feature' claim leans on impurity importance, which is biased toward continuous features"

Correct, and worth checking properly (Strobl et al. 2007). Permutation
importance was computed on the held-out **test** split (20 shuffles per
feature, same seed): the drop in test accuracy / ROC-AUC when that one
feature's column is randomly permuted. This measure is not subject to the
impurity bias. Full-history window:

| Config     | Feature          | Impurity importance | Permutation Δ test acc | Permutation Δ test ROC-AUC |
| ---------- | ---------------- | ------------------- | ---------------------- | -------------------------- |
| modest     | `fear_greed`     | 0.054               | −0.24 ± 0.25 pp        | −0.57 ± 0.32 pp            |
| modest     | `fed_funds_rate` | 0.015               | **0.000 ± 0.000 pp**   | **0.000 ± 0.000 pp**       |
| modest     | `eth_tvl`        | **0.225**           | **−0.50 ± 0.44 pp**    | −0.09 ± 0.74 pp            |
| modest     | `volume` (ref)   | 0.328               | +0.09 pp               | −0.07 pp                   |
| `400/4/25` | `fear_greed`     | 0.034               | −0.18 ± 0.08 pp        | +0.11 ± 0.27 pp            |
| `400/4/25` | `fed_funds_rate` | 0.019               | **0.000 ± 0.000 pp**   | **0.000 ± 0.000 pp**       |
| `400/4/25` | `eth_tvl`        | **0.323**           | **−0.57 ± 0.21 pp**    | −0.44 ± 0.78 pp            |
| `400/4/25` | `volume` (ref)   | 0.445               | −0.09 pp               | −0.02 pp                   |

(A _negative_ permutation Δ means shuffling the feature _improved_ held-out
accuracy — the feature was net unhelpful.)

**This confirms the bias explanation and strengthens the conclusion:**

- `eth_tvl` — impurity importance **0.225–0.32** (and _rising_ as the trees
  are regularized), but permutation importance **≈ 0, very slightly
  negative** (−0.5 pp, inside the ±1.68 pp noise band). Impurity importance
  was inflating a continuous multi-year series with thousands of split
  points; its actual recoverable signal on held-out data is nil. The
  earlier "the forest spends 22.5% of its capacity on TVL" framing
  overstated it — the correct statement is: the feature carries no signal,
  and adding it to the set still makes the model ~2 pp worse (the model
  wastes splits on noise).
- `fed_funds_rate` — impurity `0.015–0.019`, permutation **exactly
  `0.000`**. A low-cardinality step function gets no impurity inflation, so
  the two measures agree perfectly: inert.
- `fear_greed` — impurity `0.03–0.05`, permutation −0.2 pp (inside noise,
  straddles zero across configs). Small impurity, ~zero real contribution.
- Even **`volume`** — the feature impurity importance calls the model's
  most-used, at 0.33–0.44 — has permutation importance ≈ 0. The _entire_
  feature set's permutation importances are within noise of zero, which is
  the cleanest possible statement of the overall finding: **at a 1-hour
  horizon, none of these features (connector or OHLCV) carries recoverable
  directional signal for this target.**

Permutation importance is a natural candidate to add to the
`random_forest` adapter's own result summary (it currently reports only
impurity importance) — deferred as its own scoped change, since it adds
real compute cost to every training run.

#### Evidence trail (follow-up)

- `scratchpad/rf_followups.py` — the analysis driver (in-process, no new
  application code). 2 windows × 4 variants × 4 RF configs = 32 fits, each
  with impurity + held-out permutation importance.
- Modest-config numbers verified against the API runs above (4-decimal
  match) before trusting the regularized/permutation results.

---

## M4-E3-T1 — Original assessment (superseded by T2 above, kept as record)

## Purpose

Milestone 4's six external data connectors (Fear & Greed, FRED, Etherscan,
DefiLlama, CoinGecko, Marketaux) were confirmed, in a prior verification
pass, to be **REGISTERED-ONLY**: real, tested, live-verified integrations
that compute and store real data, but never used in any real experiment
or training job — the model currently driving the one live, automated
paper-trading strategy is trained purely on OHLCV + SMA(20), the same
feature set that predates Milestone 4 entirely.

This task set out to answer the actual question that leaves open: **if
these six features were used, would they help?** Build one experiment
per feature, plus one with all six together, train a model on each using
the exact same target/split/symbol/timeframe/model/hyperparameters as the
existing baseline, and benchmark all of them for real.

## TL;DR verdict

**Not measurable through the existing platform as it stands today — and
that finding is itself the substantive result of this task.** Attempting
this exactly as specified surfaced two real, compounding platform
limitations (detailed below) that make every real training run land on
the same degenerate, near-two-and-a-half-year-old slice of candle
history, regardless of which features are requested. Every job that
completed training scored a trivial, tied 100% accuracy — not because any
feature helped, but because the training data itself never contained more
than one outcome class. Four of the eight real jobs failed outright with
an explicit, honest platform error rather than a wrong number. No feature
can be honestly verdicted "helped," "hurt," or "no difference" from these
runs — the correct, honest verdict for all six is **UNDETERMINED, blocked
by a real platform limitation**, not "no measurable difference."

This is not a failure to complete the task; it is what the task's own
Definition of Done explicitly asked for when something genuinely can't be
done through existing capability: disclose it, with real evidence, rather
than silently routing around it with new code.

---

## Step 1 — The baseline, confirmed exactly

The experiment currently driving the live, automated paper-trading
strategy was identified via `paper_accounts.strategy_training_job_id`
(confirmed directly against the real database, not assumed):

- **Experiment**: `565ca966-1437-4f28-b7d9-1d58002e38af` ("ETHUSD 1h
  config editor test")
- **Training job**: `8a948fba-8416-4ccb-a020-41628581cd38`
- **`feature_set`**: `[{"feature": "ohlcv", "params": {}}, {"feature":
"sma", "params": {"period": "20", "source": "close"}}]`
- **`target_config`**: `[{"target": "next_direction", "params":
{"horizon": "1"}}]`
- **`split_config`**: `{"train": 0.7, "validation": 0.15, "test": 0.15}`
- **`model_type`**: `logistic_regression`
- **`hyperparameters`**: `{"epochs": 10, "learning_rate": 0.001,
"batch_size": 32, "random_seed": 42, "validation_frequency": 1,
"max_iter": 200}`
- **`symbol`/`timeframe`**: `ETHUSD` / `1h`

Every new experiment below was built to match every one of these fields
exactly, varying only the feature set.

### A real problem found before any comparison could even begin

The baseline's own recorded `result_summary.normalization` stats showed
`open`, `high`, `low`, and `close` sharing **identical** mean, std, min,
and max (`2399.64` / `31.57` / `2340.15` / `2424.0`) across its 100
training rows — only possible if every candle in the window is perfectly
flat. Direct SQL against the real `candles` table confirmed it: a genuine
100-hour run of real, ingested ETHUSD candles, **`2024-02-08 06:00` →
`2024-02-12 09:00`, close price literally `2423.25` for all 100
candles**. Since `next_direction` (`app/ml_datasets/targets
/next_direction.py`) defines "flat" as exact equality between the current
and next close, this window's target is 100% "flat" by construction. The
baseline's own reported "100% accuracy" is a trivial artifact of training
on a dead-flat, non-representative historical stretch — not a real
model, and not something Milestone 4's connector work broke; it predates
all of it.

---

## Step 2 — Building the seven variants

### 2a. Proof that a genuinely controlled comparison is possible, at the dataset level

Real connector coverage in this dev environment, checked directly against
`external_data_points`/`news_articles`:

| Source                       | Real coverage (first → last)                          |
| ---------------------------- | ----------------------------------------------------- |
| `eth_tvl` (DefiLlama)        | 2017-09-27 → 2026-09-08                               |
| `fear_greed`                 | 2018-02-01 → 2026-09-08                               |
| `fed_funds_rate` (FRED)      | 1996-12-03 → 2026-09-01 (monthly, forward-fills fine) |
| `news_sentiment` (Marketaux) | 2026-08-06 → 2026-09-08                               |
| `eth_gas_price` (Etherscan)  | 2026-09-06 13:22 → 2026-09-08 16:07                   |
| `btc_dominance` (CoinGecko)  | 2026-09-06 17:45 → 2026-09-08 15:59                   |

The tightest constraint is `btc_dominance`, whose real data in this
environment only goes back about two days. Using the Dataset Builder's
own `/markets/ETHUSD/ml/dataset` endpoint directly (which **does** accept
an explicit `start`/`end`), a window was hand-tuned so every one of the
eight variants (baseline + six single-feature + all-six) converges on the
exact same final row set — verified **byte-identical**, not just equal
counts, by diffing each variant's own returned `timestamps` array:

- Request window: `2026-09-05T23:00:00Z` → `2026-09-08T15:00:00Z`
  (extra lookback before the connector-safe zone so `SMA(20)` warms up
  exactly in time)
- Final aligned window used by all eight: `2026-09-06T18:00:00Z` →
  `2026-09-08T13:00:00Z`, **44 rows**, real price movement (`2458.40` →
  `2513.45`), real near-balanced target distribution (**19 up / 24 down /
  0 flat** — genuinely non-degenerate)

This proves the platform's Dataset Builder itself is capable of a real,
controlled, non-degenerate comparison. **The blocker is one layer up, in
the Training Framework.**

### 2b. What happens when the seven variants are actually trained

`TrainingJobCreateRequest` (and the `Experiment` it's linked to) exposes
**no field at all** for `start`/`end`/`limit`. Confirmed directly in code
(`app/services/training.py::_make_load_dataset_hook`) and by a real probe
job: a training job always independently re-derives its own dataset from
the experiment's `feature_set`/`target_config`/`split_config` alone, with
none of the pinned-window fields above ever set — landing on whatever
`MLDatasetService`'s own default resolves to.

That default is **not** "the most recent N candles," which would at
least have been current, if narrow. It is the **earliest** N:
`app/services/candle_points.py` calls `candle_repository.get_candles(...,
sort="open_time", direction="asc")` explicitly, and when `start`/`end`
are both omitted, `normalize_range` returns `(None, None)` unchanged — so
the query is a bare `ORDER BY open_time ASC LIMIT 100`, with no lower
bound at all. **Every training job that omits an explicit date range —
which is every job the existing UI/API lets a caller create — trains on
the oldest 100 candles a market has, not the newest.** For `ETHUSD`/`1h`,
that is the exact same February 2024 dead-flat stretch the baseline used.
This is a real, previously-undisclosed platform bug, not a data-freshness
inconvenience — and it is almost certainly not the intended behavior for
a system meant to train a model to predict what happens next.

Eight real experiments and training jobs were created and run through the
existing API exactly as a real user would (`POST /experiments`, `POST
/training-jobs`, `POST /training-jobs/{id}/run`), each matching the
baseline's target/split/model/hyperparameters exactly, varying only the
feature set:

| Variant                    | Experiment id                          | Job id                                 | Result                             |
| -------------------------- | -------------------------------------- | -------------------------------------- | ---------------------------------- |
| Baseline (fresh re-run)    | `955251c8-3f0c-4e18-8227-064ec5148364` | `2fa5be0f-00ed-4cff-adbf-7fa80fd64b5f` | Completed — degenerate (see below) |
| + Fear & Greed             | `f9299c59-1d37-44d0-af83-0907f233e21c` | `c611f679-5e30-4e5d-a45d-115bf4aa471e` | Completed — degenerate             |
| + FRED                     | `0ed3ff1d-6e6f-4dab-b5ad-d51abafce130` | `a9ef2bf7-b2ae-4f97-ab79-b9f2f8c2082b` | Completed — degenerate             |
| + DefiLlama TVL            | `0f3090b8-8ef0-4f85-bc94-4d5d5f1e5468` | `717957ef-9b80-4c7b-8f5c-22b427308664` | Completed — degenerate             |
| + Etherscan gas price      | `272bb078-3449-40ba-80bc-a71ea9a810c0` | `e808f873-cc6b-4118-836a-3bbec9322b26` | **Failed**                         |
| + CoinGecko BTC dominance  | `903004eb-90b5-40a5-a49e-6eaac6c0c1ba` | `c4e6de6c-b3b9-4420-b43c-f0315a728d9f` | **Failed**                         |
| + Marketaux news sentiment | `18d0c9c9-ed80-493d-bd18-4a953c6cf971` | `f8beebeb-2631-483e-8110-6a24a4e48e71` | **Failed**                         |
| + all six                  | `9fef6f33-4da4-433c-914a-624a3a4ca27e` | `d0f89395-adc3-4149-9828-84f4e18b5c5d` | **Failed**                         |

The four failures all returned the identical, honest platform error:

```text
Every row was dropped: 121 candles were loaded but the requested
features need 20 candles of warmup. Widen the date range or reduce
the largest period parameter
```

This is the direct, mechanical consequence of the bug above: the
"earliest 100 (121 with warmup)" candles are from February 2024 — 2.5
years before `eth_gas_price`/`btc_dominance`/`news_sentiment` have any
real data at all in this environment, so every row is null for that
feature and gets dropped. `all_six` fails for the same reason, dragged
down by whichever of its six inputs has the narrowest coverage.

---

## Step 3 — The benchmark, run for real

`POST /evaluation/benchmark` was run comparing all four completed new
jobs plus the original live baseline job(s), filtered by
`experiment_ids` (the request's own `target_column` filter turned out to
require a DB column, `training_jobs.target_column`, that stays blank
unless explicitly set at job-creation time — a second, minor, real API
surprise worth a one-line disclosure of its own, unrelated to the main
finding above).

| Job        | Experiment                      | accuracy | f1  | precision | recall | Samples | Features |
| ---------- | ------------------------------- | -------- | --- | --------- | ------ | ------- | -------- |
| `2fa5be0f` | Baseline (fresh re-run)         | 1.0      | 1.0 | 1.0       | 1.0    | 100     | 6        |
| `c611f679` | + Fear & Greed                  | 1.0      | 1.0 | 1.0       | 1.0    | 100     | 7        |
| `a9ef2bf7` | + FRED                          | 1.0      | 1.0 | 1.0       | 1.0    | 100     | 7        |
| `717957ef` | + DefiLlama TVL                 | 1.0      | 1.0 | 1.0       | 1.0    | 100     | 7        |
| `8a948fba` | Original live baseline          | 1.0      | 1.0 | 1.0       | 1.0    | 100     | 6        |
| `c406b242` | Original baseline (earlier run) | 1.0      | 1.0 | 1.0       | 1.0    | 100     | 6        |

`best_by_metric` named `717957ef` (DefiLlama TVL) as "best" on every
metric. **This is a meaningless tie-break, not a real result** — every
single candidate above is tied at the exact same trivial ceiling (1.0
across all four metrics), because every one of them was trained on the
identical dead-flat window and trivially always predicts "flat." A
benchmark's own best-by-metric pick has to break ties somehow; here it
picked whichever job happened to sort first, which carries no
information about whether DefiLlama TVL is actually better than anything.

The one place a real, non-zero difference did appear: `train_metrics
.roc_auc` was `0.9509` for baseline/FRED, but `0.9014` for Fear &
Greed/DefiLlama TVL. This is a genuine, measurable numeric difference —
but it lives inside a training-set metric on a degenerate, 100-row,
single-outcome-class dataset, and says nothing trustworthy about real
predictive value. It is reported here for completeness, not as a finding
to act on.

---

## Per-feature verdict

| Feature                    | Verdict                                                                                                                                                                      |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Fear & Greed               | **UNDETERMINED** — trained, but on the same degenerate window as baseline; tied at trivial 100% accuracy                                                                     |
| FRED (Federal Funds Rate)  | **UNDETERMINED** — same as above; numerically inert even inside the degenerate run (identical to baseline on every recorded metric)                                          |
| Etherscan (gas price)      | **UNDETERMINED — blocked**: training failed outright (`every row was dropped`), this connector's own real data does not reach back to the platform's default training window |
| DefiLlama (TVL)            | **UNDETERMINED** — same as Fear & Greed/FRED                                                                                                                                 |
| CoinGecko (BTC dominance)  | **UNDETERMINED — blocked**: same failure as Etherscan                                                                                                                        |
| Marketaux (news sentiment) | **UNDETERMINED — blocked**: same failure as Etherscan                                                                                                                        |
| All six together           | **UNDETERMINED — blocked**: same failure, inherited from whichever of the six has the narrowest coverage                                                                     |

No feature above is reported as "helped," "hurt," or "no measurable
difference" — every one of those would overstate what these runs
actually show. The honest verdict, for all six, is that the platform as
it exists today cannot yet produce a trustworthy answer.

---

## Real platform limitations disclosed (not routed around)

1. **The Training Framework's own dataset-rebuild step has no way to
   specify a date range or row limit.** `TrainingJobCreateRequest` and
   `Experiment.feature_set`/`target_config`/`split_config` carry no such
   field; `_make_load_dataset_hook` (`app/services/training.py`)
   constructs its own `MLDatasetRequest` with `start`/`end`/`limit` left
   at their defaults, always. This is the direct reason the careful,
   byte-identical 44-row window proven possible at the Dataset Builder
   level (Step 2a) could not be carried through to an actual trained
   model.
2. **The default candle window (no explicit `start`/`end`) loads the
   _earliest_ candles in a market's history, not the most recent.**
   `app/services/candle_points.py` passes `direction="asc"` explicitly,
   and `normalize_range` leaves both bounds `None` when neither is
   given — so an un-dated query is a bare `ORDER BY open_time ASC LIMIT
N`. For any market with more than `N` candles of history (every real
   market on this platform), this means training on the _oldest_
   available data, not the newest — the opposite of what a system meant
   to predict "what happens next" should default to. This is very likely
   an unintended design flaw, not a deliberate choice, and it directly
   explains why the currently-live paper-trading strategy's own model is
   trained on a dead, 2.5-year-old, single-outcome-class window.
3. A minor, second API surprise: `BenchmarkRequest.target_column`
   filters on `training_jobs.target_column`, a column that stays blank
   unless a caller explicitly passes `target_column` at job-creation time
   (it is not back-filled from `result_summary.target_column`, which
   _is_ always populated). Filtering by `experiment_ids` instead worked
   as expected.

Neither limitation was worked around with new code, per this task's own
explicit instruction — both are reported here as real findings.

## What would actually need to change (not implemented here — out of scope)

- Let `TrainingJobCreateRequest` (or the linked `Experiment`) optionally
  carry an explicit `start`/`end`/`limit`, forwarded into the
  `MLDatasetRequest` `_make_load_dataset_hook` builds.
- Change the _default_ (when neither is given) to the most recent window
  — `direction="desc"` then re-sorted ascending for use, or an implicit
  `end=now()`/`start=end - limit*timeframe` — for any training-oriented
  dataset build. `direction="asc"` may still be the right default
  elsewhere (e.g. a `/candles` browse starting from a market's listing
  date); this recommendation is scoped to the training/dataset-building
  path specifically.
- Once both are fixed, re-run this exact assessment — the methodology
  (control everything except the feature set; verify row-count parity by
  diffing actual timestamps, not just counts; run one baseline + six
  single-feature + one all-six experiment; benchmark all of them
  together) is sound and reusable as-is.

---

## Update 2026-09-09 — both prerequisites resolved (PREP-RETRAIN-AND-BACKFILL)

### Backfill depth: a genuine, unchanged free-tier limit — not extendable

`eth_gas_price` (Etherscan) and `btc_dominance` (CoinGecko) real coverage was
already correctly disclosed, at each connector's own original build time, as
having **no historical query capability on the free tier at all** —
`app/connectors/etherscan.py`'s own module docstring records that
Etherscan's one real historical series, `dailyavggasprice`, is Pro-tier only;
`app/connectors/coingecko.py`'s records the same for CoinGecko's historical
global-market-cap chart endpoint. `scripts/backfill_etherscan.py` and
`scripts/backfill_coingecko.py` both state plainly, in their own module
docstrings, that they are single-poll scripts, not backfills — `--start`/
`--end` only narrow which single live point is accepted, they cannot reach
further into the past.

Re-verified live, today, against both real APIs, rather than trusting the
original investigation as still current:

```text
Etherscan dailyavggasprice (real request, real key):
  {"status":"0","message":"NOTOK","result":"Sorry, it looks like you are
  trying to access an API Pro endpoint. Contact us to upgrade to API Pro."}

CoinGecko /global/market_cap_chart (real request):
  {"status":{"error_code":10005,"error_message":"This request is limited
  to PRO API subscribers. Please visit .../api/pricing ..."}}
```

**Conclusion: this is a genuine platform limit, not an under-extended
backfill — there is nothing to run further back.** The only way either
connector's own real coverage grows is real-time polling since the
connector was first registered; as of this update that is
`2026-09-06 13:22` (Etherscan) / `2026-09-06 17:45` (CoinGecko) → now,
growing by one real day per calendar day, never retroactively. **Any future
re-run of this assessment must design its common comparison window around
this — bounded to "however long these two connectors have been polling as
of the re-run date" — not against it**, exactly as this task's own methodology
already did (§ "2a" above).

### Live model retrained on real, recent data

The exact experiment the live paper-trading account cites
(`565ca966-1437-4f28-b7d9-1d58002e38af`, target/split/model/hyperparameters
unchanged from Step 1 above) was retrained with no explicit date range,
exercising FIX-TRAINING-DATE-RANGE's corrected default directly rather than
pinning a window by hand:

- **New training job**: `6e7fb4ed-7142-4c8b-953e-b95788a4014b`
  (`dataset_version="retrain-2026-09-09-real-recent-data"`)
- **Real, recent price data used** (`normalization` stats, `close`): mean
  `2488.60`, range `2452.65`–`2513.45` — current ETHUSD levels, not the old
  `2423.25` dead-flat window.
- **Real, non-degenerate metrics**: overall accuracy `0.667`, precision
  `0.722`, recall `0.667`, `roc_auc` `0.704`; **test-split** accuracy
  `0.533`, `roc_auc` `0.679` — genuinely between random (`0.5`) and perfect
  (`1.0`), consistent with a simple logistic-regression baseline on
  OHLCV+SMA(20) alone. `confusion_matrix: [[5, 4], [1, 5]]` — real variety
  in both actual and predicted labels, not one class predicted every time.
  Train/test gap (`0.138`) explicitly checked and flagged
  `overfitting.flagged: false`.
- **Prediction samples independently inspected** (not just the summary
  metrics): 15 real test-set predictions, probabilities ranging `0.53`–
  `0.81` (the old degenerate model repeated the identical `0.993`
  probability for every single prediction) — real, non-uniform confidence,
  5 of 15 genuinely wrong, matching the reported 53.3% test accuracy exactly.

This is a real, honestly-mediocre model, not a fabricated ceiling — exactly
what "sane" looks like for a simple feature set on genuinely noisy financial
data, and exactly the caveat the task's own Decision section asked to be
checked for before trusting it with anything automated again.

### Live account updated and re-enabled

A real, concerning discrepancy was found and corrected before retraining:
the live account's `strategy_enabled` had reverted to `true` (still citing
the old degenerate job `8a948fba`) between the prior session's explicit
disable and this one — `updated_at` showed this happened only minutes
before this investigation began, concurrent with a fresh dev-server
process starting. No new paper trades had executed in that window (account
balance unchanged), but it was disabled again immediately as a precaution
before proceeding, per this task's own "leaving it disabled costs nothing,
but it isn't fixing itself either" framing — being _enabled_ on a broken
model, even briefly, is the actual risk that framing was guarding against.

`paper_accounts.strategy_training_job_id` now points to
`6e7fb4ed-7142-4c8b-953e-b95788a4014b`; `strategy_enabled` is `true` —
restored only after the metrics above were read and confirmed sane, not on
the assumption that "retrained" alone meant "fine."

---

## Real evidence trail

- All 8 new experiments/training jobs listed above are real, persisted
  database rows — not deleted, kept as the record of this investigation
  (alongside the 3 experiments that already existed).
- Real benchmark response saved during this investigation; the exact
  request/response shapes and error strings quoted above are verbatim
  from the running dev server, not paraphrased.
- The February 2024 dead-flat window was independently confirmed via
  direct SQL against `candles` (a window-function scan for the longest
  unchanging-close run in the table), not inferred from the model's
  output alone.
- The Dataset Builder's own byte-identical 44-row parity across all 8
  variants was verified by diffing full `timestamps` arrays returned by
  `POST /markets/ETHUSD/ml/dataset`, not just comparing row counts.
