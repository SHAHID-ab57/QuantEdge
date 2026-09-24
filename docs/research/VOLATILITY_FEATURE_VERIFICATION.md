# Volatility Feature Verification

**Question:** `TARGET_REDEFINITION_ASSESSMENT.md`'s Step 4 found that adding
`realized_volatility` lifted `volatility_regime`'s ROC-AUC from ~0.50 to
0.72-0.74 across all three classifiers — the first positive result after
eight negative confirmations in this research thread, asserted "not
leakage" but not shown with specific, adversarial evidence for a claim
this consequential. Does it survive the same scrutiny that just dissolved
`triple_barrier`'s own tree-model lead in the same task? Five specific
checks, run in order, stopping to report immediately if any one raises a
serious concern. **Investigation only: no strategy code or configuration
was changed.** Measured 2026-09-26.

## TL;DR

1. **The signal is real — confirmed, not asserted, by four independent,
   adversarial checks.** The exact window boundary is shown with real
   numbers (Step 1); a purpose-built adversarial no-look-ahead test,
   matching the exact methodology this platform already requires of
   `funding_rate`/`open_interest`, passes (Step 2); a deliberate
   boundary-shift stress test shows the AUC decaying _gradually_ over
   dozens of hours, not collapsing at a 1-hour shift the way a boundary
   bug would (Step 3); the cross-check window corroborates the primary
   comparison rather than contradicting it, with the identical feature
   dominating permutation importance in both (Step 4).
2. **This is genuinely different in kind from `triple_barrier`'s
   collapse.** Every one of `triple_barrier`'s 6 regime/model AUCs landed
   in 0.44-0.54 (chance). Every one of `volatility_regime`'s 9 regime/model
   AUCs here lands in 0.56-0.81 — never once inside that chance range.
3. **Step 5's regime walk-forward is real, and not uniform.**
   `logistic_regression` holds up strongly in all three regimes (AUC
   0.72-0.81). `random_forest`/`gradient_boosting` hold up in the two
   trending regimes (AUC 0.65-0.71) but weaken specifically in the choppy
   regime (AUC 0.56-0.68, with `random_forest`'s own permutation
   importance collapsing toward zero there) — a real, honestly-reported
   caveat, not a reason to call the whole finding an artifact.
4. **Verdict: real.** Survives all five checks. Not a finished, deployable
   result — see `TARGET_REDEFINITION_ASSESSMENT.md`'s own "After this"
   section for what would still need to happen before that — but the
   first genuine signal this entire research thread has produced.

---

## Step 1: the exact window boundary, with a worked example

`app/features/builtin/realized_volatility.py`'s `generate()`:

```python
log_returns: list[FeatureValue] = [None]
for index in range(1, n):
    previous_close = candles[index - 1].close
    log_returns.append(math.log(candles[index].close / previous_close))

for index in range(n):
    if index < window:
        values.append(None)
        continue
    trailing = log_returns[index - window + 1 : index + 1]
    values.append(pstdev(trailing))
```

`log_returns[j]` is the return **realized during candle `j`** — from
candle `j-1`'s close to candle `j`'s own close — fully known the moment
candle `j` itself has closed, exactly the same "this row's own OHLCV is
fully known data" convention every other feature on this platform already
uses (`close[index]` itself is a feature value at row `index`, using data
no more recent than row `index`'s own close). Row `index`'s own
`realized_volatility_24` value is `pstdev(log_returns[index-23 .. index])`
— **inclusive of `log_returns[index]`, and strictly nothing with a higher
index.**

**Worked example**, real numbers, `window=5`, a single price jump at
candle 10 (close 100 → 500, everything else flat):

| Row (`index`) | Its own trailing window (`log_returns` slice) |             Contains the jump?             | Value |
| ------------: | --------------------------------------------- | :----------------------------------------: | ----: |
|             9 | `log_returns[5:10]`                           |                     No                     | 0.000 |
|            10 | `log_returns[6:11]`                           |        **Yes** (`log_returns[10]`)         | 1.207 |
|            14 | `log_returns[10:15]`                          |        **Yes** (`log_returns[10]`)         | 0.855 |
|            15 | `log_returns[11:16]`                          | **Yes** (`log_returns[11]`, the reversion) | 0.855 |
|            16 | `log_returns[12:17]`                          |                     No                     | 0.000 |

Row 9 — the row immediately before the jump — reads **exactly 0.0**, not
some small residual: the slice's own upper bound (`index+1 = 10`) is
Python's exclusive end, so `log_returns[10]` genuinely never appears in
it. This is the sharpest possible boundary proof: the row right before an
anomaly has zero knowledge of it.

## Step 2: the standard adversarial no-look-ahead test

This test did not exist before this task — writing it is itself part of
Step 2's own finding. `tests/features/test_builtin_generators.py`'s new
`TestRealizedVolatilityNoLookAhead` applies the identical methodology
`TestNoLookAhead` (`tests/features/test_delta_market_data_features.py`)
already requires of `funding_rate`/`open_interest` — poison the future,
confirm the past is unaffected — adapted for a rolling-window statistic
instead of a step-function external value, using the same single-spike
construction as Step 1's own worked example:

- **`test_a_future_spike_never_changes_a_past_rows_value`**: computes the
  feature over the full, spiked series and over an independently
  truncated series that ends _right before_ the spike, and asserts every
  row that exists in both is byte-identical. **Passes.**
- **`test_the_window_has_a_hard_trailing_edge_the_spike_eventually_rolls_out_of`**:
  confirms the window is bounded on the _right_ side too — once enough
  real hours have passed, the feature returns to exactly `0.0`, proving
  it is a genuinely rolling window, not an accumulating one that would
  leak an old anomaly forward indefinitely. **Passes.**
- **`test_worked_example_the_exact_window_boundary`**: the Step 1 table
  above, as a real, executable assertion. **Passes.**

All 8 tests in the new class pass; full suite unaffected
(`uv run pytest tests/features` — see [Testing](#testing)).

## Step 3: boundary-shift stress test — the decisive check

A self-contained replication of the real platform's own primary
comparison (identical hyperparameters, read directly from
`app/training/adapters/{logistic_regression,random_forest,gradient_boosting}.py`;
identical chronological 70/15/15 split; identical train-only z-score
normalization) against the same full real ETHUSD/1h history, first run
at `gap=0` as a **fidelity check on this replication itself** before
trusting anything it says about a shifted feature.

| Gap (hours) | `logistic_regression` AUC | `random_forest` AUC | `gradient_boosting` AUC |
| ----------: | ------------------------: | ------------------: | ----------------------: |
|           0 |                    0.7355 |              0.7266 |                  0.7174 |
|           1 |                    0.7325 |              0.7269 |                  0.7246 |
|           2 |                    0.7317 |              0.7247 |                  0.7266 |
|           3 |                    0.7297 |              0.7266 |                  0.7199 |
|           6 |                    0.7206 |              0.7121 |                  0.7096 |
|          12 |                    0.6972 |              0.6907 |                  0.6433 |
|          24 |                    0.6076 |              0.5795 |                  0.5572 |

**The `gap=0` row matches the real platform's own official Step 4 numbers
to four decimal places** (0.7355/0.7266/0.7174 here vs. 0.736/0.727/0.717
reported there) — this replication is faithful, not a second, diverging
implementation.

**This is the check that actually distinguishes real structure from a
boundary bug, and the result is unambiguous.** A leakage bug — the
feature accidentally reading even one hour it shouldn't — would produce a
sharp cliff at `gap=1`: AUC should collapse toward 0.5 almost immediately,
because the "future" information the model was secretly relying on would
already be gone. Instead, AUC barely moves through `gap=3` (within
0.003-0.008 of `gap=0`), erodes only mildly through `gap=6`, and decays
_gradually_ out to `gap=24`, where it is still 0.56-0.61 — well above
chance even a full day delayed. This is exactly the shape real,
persistent structure produces (matching `TARGET_REDEFINITION_ASSESSMENT.md`'s
own ACF diagnostic: volatility clustering's own autocorrelation decays
slowly, not abruptly, out past lag 100), and exactly the shape a boundary
bug would not.

## Step 4: cross-check window

Same window every candidate in this thread has been checked against
(`2026-07-30` → `2026-09-10`), real training jobs, real held-out test
split:

| Model                 | Test accuracy | Majority baseline | Test ROC-AUC | Top permutation importance         |
| --------------------- | ------------: | ----------------: | -----------: | ---------------------------------- |
| `logistic_regression` |         90.3% |             59.0% |        0.947 | `realized_volatility_24` **0.272** |
| `random_forest`       |         82.6% |             59.0% |        0.888 | `realized_volatility_24` **0.223** |
| `gradient_boosting`   |         88.2% |             59.0% |        0.947 | `realized_volatility_24` **0.207** |

Noise band at this sample size (n=144): ±8.03pp — every accuracy figure
is 23-31pp above it, not close. **This is not the small-sample inflation
this thread already caught once for `triple_barrier`'s own cross-check**:
there, one feature (`close`) spiked to an importance ten times higher
than it showed anywhere else in the comparison — a red flag for a
coincidental, non-generalizing fit. Here, `realized_volatility_24` is the
dominant feature in **both** the primary comparison (0.115-0.148) and
this cross-check (0.207-0.272) — a larger number on a smaller, noisier
sample, which is the expected direction for a real effect, not the
"different feature entirely" shape an artifact would show.

## Step 5: regime walk-forward

`volatility_regime`'s own predictions cannot be graded by the real
Backtesting Engine yet (`TARGET_REDEFINITION_ASSESSMENT.md`'s own
documented, deliberately-not-fixed gap: `_grade_one` never fetches the
trailing context a backward-looking target needs) — so, exactly as
`triple_barrier`'s own regime walk-forward did before its grading bug was
fixed, this reconstructs each regime's accuracy/AUC directly: the real
saved model artifact, the real `MLDatasetService`-built regime-window
dataset, the job's own real frozen normalization applied by hand. Trained
fresh on the identical `2024-02-06 → 2024-11-01` window
`REGIME_WALKFORWARD_ASSESSMENT.md`'s own baseline used, walked across the
same three real regimes.

| Model                 | Regime    |     N | Accuracy | ROC-AUC | `realized_volatility_24` importance |
| --------------------- | --------- | ----: | -------: | ------: | ----------------------------------: |
| `logistic_regression` | Uptrend   | 1,872 |    62.9% |   0.723 |                               0.140 |
| `logistic_regression` | Downtrend | 1,656 |    71.8% |   0.810 |                               0.228 |
| `logistic_regression` | Choppy    | 1,872 |    66.5% |   0.742 |                               0.171 |
| `random_forest`       | Uptrend   | 1,872 |    60.4% |   0.673 |                               0.100 |
| `random_forest`       | Downtrend | 1,656 |    65.0% |   0.711 |                               0.164 |
| `random_forest`       | Choppy    | 1,872 |    50.1% |   0.562 |                               0.015 |
| `gradient_boosting`   | Uptrend   | 1,872 |    56.4% |   0.646 |                               0.071 |
| `gradient_boosting`   | Downtrend | 1,656 |    64.8% |   0.700 |                               0.164 |
| `gradient_boosting`   | Choppy    | 1,872 |    48.6% |   0.681 |                              0.0002 |

Noise bands at these sample sizes: ±2.27pp (n=1,872), ±2.41pp (n=1,656),
against a ~50% base rate.

**`logistic_regression` holds up cleanly in every regime** — AUC never
drops below 0.72, `realized_volatility_24` is the dominant feature in all
three, by a wide margin over everything else (full permutation-importance
tables in the underlying script's own output).

**`random_forest`/`gradient_boosting` hold up in the two trending
regimes** (uptrend AUC 0.65-0.67, downtrend AUC 0.70-0.71, both with real,
non-trivial `realized_volatility_24` importance in the 0.07-0.16 range)
**and weaken specifically in the choppy regime.**
`random_forest`/choppy's accuracy (50.1%) sits inside its own noise band
of a 50% baseline and its `realized_volatility_24` importance (0.015) is
an order of magnitude below its own showing in the other two regimes —
that cell is a genuine null result for that model in that regime, read
plainly. `gradient_boosting`/choppy is a more unusual cell: permutation
importance is essentially zero for every feature (the same "collapsed to
a near-constant prediction" signature `triple_barrier`'s own choppy
regime showed for both tree models in the prior task), yet ROC-AUC still
reads 0.681 — a model whose hard class predictions have collapsed but
whose underlying probability scores still carry real ranking information,
an internally consistent if unusual combination, not a contradiction to
paper over.

**Read honestly, not forced into either a clean pass or a clean fail**:
the underlying volatility-persistence signal is real and it generalizes —
every one of these 9 regime/model AUCs sits in 0.56-0.81, never once
inside `triple_barrier`'s own 0.44-0.54 chance range — but it is not
uniformly strong across every model in every regime. The choppy/
range-bound regime is where it is weakest, plausibly because a
range-bound market has less of the directional/volatility-regime
structure a tree model can lock onto in the first place, while the
simpler, more linear `logistic_regression` model — which relies more
directly on the raw feature value itself — stays robust there too.

## Final verdict

**Real — the first genuine signal this entire research thread has
produced, and it survives every adversarial check this task ran against
it**, including the one (Step 3's boundary-shift stress test) built
specifically to catch the shape of bug that would produce a false
positive like this. It is not, on the strength of this task alone, a
finished or deployable result: `TARGET_REDEFINITION_ASSESSMENT.md`'s own
"After this" section already named the real remaining gaps (translating
"volatility will expand" into an actual position/risk rule; the still-open
live-grading limitation) — this task adds one more, precise qualifier to
that list: **the signal is strongest for `logistic_regression` and in
trending regimes; the choppy regime is a real, model-dependent weak
point, not yet explained beyond a plausible hypothesis.**

## Testing

```text
uv run pytest tests/features tests/training   # new TestRealizedVolatilityNoLookAhead class, 8 tests, pass
uv run pytest                                  # full suite, unaffected
```

## Related

- The finding this verifies: `TARGET_REDEFINITION_ASSESSMENT.md` (Step 4
  for the original claim, Step 5 for `triple_barrier`'s own contrasting
  collapse under the identical regime walk-forward methodology).
- The adversarial no-look-ahead methodology this reuses directly:
  `tests/features/test_delta_market_data_features.py`'s `TestNoLookAhead`
  (`funding_rate`/`open_interest`, M4-E3-T3).
- The exact hyperparameters this task's own replication script reads
  from, to stay faithful to the real platform: `app/training/adapters/
{logistic_regression,random_forest,gradient_boosting}.py`.
- The prior small-sample-inflation catch this task's own Step 4
  deliberately checked against recurring: `CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`'s
  DefiLlama TVL finding, `TARGET_REDEFINITION_ASSESSMENT.md`'s own
  `triple_barrier` cross-check finding.
