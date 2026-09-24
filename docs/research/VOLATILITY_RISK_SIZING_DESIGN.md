# Volatility-Forecast-Informed Risk Sizing — Design

**Question:** `VOLATILITY_FEATURE_VERIFICATION.md` confirmed, with five
adversarial checks, that `realized_volatility` genuinely predicts
`volatility_regime` (near-term volatility expansion vs. contraction) —
the first validated model output this research thread has produced, after
eight negative confirmations on direction. How, if at all, should that
inform risk sizing in paper trading? **Investigation and design only: no
code was changed.** Measured 2026-09-27.

## TL;DR

1. **This validates volatility predictability, not price direction.**
   Every directional finding in this thread — `next_direction` across
   connectors, horizons, regimes, funding/open interest, confidence
   ranking, and `volatility_regime`'s own directional cousin — remains
   negative. Nothing here reopens D1 or D2
   (`FUTURES_MECHANICS_AND_LEVERAGE_DESIGN.md`): the automated strategy
   still does not, and should not, size leverage from directional
   confidence. This is a different model output, answering a different
   question, for a different purpose — [see below](#how-this-differs-from-d1-and-why-it-doesnt-reopen-it)
   for exactly why that distinction holds and isn't a side door.
2. **Scoped to `logistic_regression`, the only model that held up in
   every regime.** `random_forest`/`gradient_boosting` weakened
   specifically in the choppy regime in verification (AUC 0.56-0.68,
   `random_forest`'s own permutation importance collapsing near zero
   there) — real enough to disqualify them as an interchangeable
   reference implementation, not real enough to disqualify the finding
   itself.
3. **The 24-hour forecast horizon is a reasonable match for real
   position-holding timescales, checked against actual data, not
   assumed.** The four real paired open→close events found in this
   platform's own `paper_strategy_decisions` log span 4.5 to 48.2 hours
   (median ≈19h) — a small, pre-drift-fix sample, but it brackets 24
   hours rather than being an order of magnitude off in either
   direction.
4. **Two real option families, with real tradeoffs, presented explicitly
   — nothing is being built by this task**: (A) scale position size or
   leverage from the forecast, always _within_ today's existing caps,
   never raising `max_exposure_pct` (D7 stays untouched); (B) scale
   stop-loss/take-profit width from the forecast, using the position
   update path that already exists. Neither is free of real
   complications, laid out below.
5. **This is genuinely a new kind of decision for this platform**: the
   first time a validated model output would change a live risk
   parameter rather than only gate whether a trade happens. It gets the
   same explicit, no-default sign-off every other consequential decision
   in this thread has gotten.

---

## Step 1: scoping — which model, which conditions, which horizon

### Reference model: `logistic_regression` only, not "the ensemble" or "whichever model is live"

`VOLATILITY_FEATURE_VERIFICATION.md`'s own regime walk-forward is the
reason this has to be explicit, not a footnote:

| Model                 | Uptrend AUC | Downtrend AUC | Choppy AUC |
| --------------------- | ----------: | ------------: | ---------: |
| `logistic_regression` |       0.723 |         0.810 |      0.742 |
| `random_forest`       |       0.673 |         0.711 |      0.562 |
| `gradient_boosting`   |       0.646 |         0.700 |     0.681* |

*(`gradient_boosting`/choppy's own permutation importance was
essentially zero for every feature — a collapsed, near-constant
prediction whose probability scores still happened to rank reasonably;
see that document's own Step 5 for the full caveat.)

`logistic_regression` is the only one of the three with **no regime
below 0.72**. A design that let "whichever model happens to be
configured on this experiment" drive live risk parameters would silently
inherit `random_forest`'s own near-chance choppy-regime behavior on any
account pointed at that model — exactly the kind of thing this whole
research thread exists to catch before it reaches a live account, not
after. **Any implementation of either option below should require the
specific `logistic_regression`-trained job for volatility forecasting**,
independent of whatever model is used for the (currently gated, currently
firing on nothing) directional strategy — these are two separate model
lineages serving two separate purposes, and should stay that way
explicitly rather than accidentally sharing a training job.

### Forecast horizon vs. real position-holding timescale

`volatility_regime`'s own `window_hours=24` parameter means the
validated forecast answers "will realized volatility over the _next 24
hours_ exceed the _trailing 24 hours_" — a specific timescale that has to
actually match what a position sizing/width decision made _now_ is meant
to protect against.

**Checked against this platform's own real data, not assumed.** The
`paper_strategy_decisions` log (the automated strategy's own recorded
opens/closes, from before the confidence gate started blocking
everything — see `CONFIDENCE_RECHECK_POST_FIX.md`) has exactly **4 real,
paired open→close events**:

| Duration (hours) |
| ---------------: |
|             4.48 |
|             9.65 |
|            28.97 |
|            48.20 |

Median ≈19 hours. This is a genuinely small sample from a period whose
own model was later found to be drift-affected (`FEATURE_DRIFT_INVESTIGATION.md`),
so it should not be over-read as a precise distribution — but it directly
answers the question this step asks: is 24 hours wildly mismatched to how
long a position actually stays open here? **No.** Two of four durations
sit below 24 hours, two above, bracketing it rather than missing it by an
order of magnitude in either direction. The platform's own mandatory
stop-loss (`strategy_default_stop_loss_pct`, 5% default) and ETH's own
measured volatility (`RETRAIN_WINDOW_ANALYSIS.md`: 7-day realized vol
37-101% annualized) independently suggest a similar timescale: a 5% move
is order-of-magnitude a 1-3 day event at ETH's typical volatility, so the
stop-loss itself — usually the more binding constraint on how long a
position survives than a reversing signal, given the (gated) strategy's
own historically near-constant directional bias — already operates on
roughly this timescale. **24 hours is a reasonable, not a mismatched,
choice** — close enough that no re-parameterization of `window_hours`
is obviously required before using it here, though it is worth
re-checking once real post-fix position data accumulates (see
[What this does not resolve](#what-this-does-not-resolve)).

---

## Step 2: what currently determines size, leverage, and stop width (today's real mechanism)

For grounding, not for change — every option below is a variation on
this real, already-shipped code path
(`app/services/paper_trading_strategy.py::_open_position`):

```python
target_pct = account.max_position_size_pct * Decimal("0.5")   # half the cap, headroom for slippage/fee
quantity = (account.balance * target_pct / 100) / current_price
stop_loss_pct = account.strategy_default_stop_loss_pct / 100   # fixed, e.g. 5%
stop_loss_price = current_price * (1 - stop_loss_pct)          # long; mirrored for short
order = place_order(..., leverage=account.strategy_leverage,   # fixed, e.g. 2x
                     stop_loss_price=stop_loss_price)
```

Three numbers are fixed, per-account, human-set, and untouched by any
model output today: `max_position_size_pct` (default 10%),
`strategy_leverage` (default 2x, capped by `max_leverage`, default 5x),
`strategy_default_stop_loss_pct` (default 5%). A position's own
stop-loss/take-profit can also be adjusted _after_ it opens, via the
already-existing `PATCH .../positions/{symbol}` (`stop_loss_price`/
`take_profit_price`, both optional, either settable independently) — this
matters because it means Option B below needs no new mutation path, only
a new caller of one that already exists.

---

## Step 3: the real options

### Option A — position-size / leverage scaling from the forecast

Scale `target_pct` and/or `strategy_leverage` down ahead of a forecast
**expansion**, up (never past the account's own existing
`max_position_size_pct`/`max_leverage` caps) ahead of a forecast
**contraction**. This is, explicitly, **D1's own "Option 1"
(volatility-targeted sizing), upgraded from a backward-looking realized-volatility
estimator to a validated forward-looking forecast** — D1 considered and
set aside pure volatility-targeted sizing partly because, at the time, it
"adds moving parts (a volatility estimator, a target to choose, a data
dependency)" with no established predictive value behind the estimator.
That specific objection is now addressed for the forecast half of it (the
estimator has demonstrated real, adversarially-checked predictive value)
— though every other part of D1's own caution about Option 1 still
applies unchanged: it manufactures no directional edge, and it does not
change the platform's own liquidation-distance mechanics or margin model.

**Real tradeoffs:**

- **What it protects against**: entering (or staying in) a full-size
  position right as volatility is forecast to expand widens the expected
  range of outcomes — including the fastest path to a stop-loss or
  liquidation — without proportionally widening posted margin. Sizing
  down ahead of that is a standard, principled risk-management practice
  (volatility targeting), not a speculative bet on the forecast's own
  direction.
- **What it does not do**: it does not, and must not, raise
  `max_exposure_pct`. D7's own framing — "this is the decision that
  actually determines whether the account can lose more than it would
  today" — stays untouched; every scaled size/leverage value here is
  still bounded by the account's own existing, human-set ceiling, exactly
  matching the task's own explicit instruction. Nothing here reopens D7.
- **A real complication D1 already named, worth repeating exactly**:
  leverage amplifies round-trip cost (0.30% of notional per D1's own
  measurement) as much as it amplifies exposure. Scaling leverage _up_
  ahead of a forecast contraction, even capped at the account's existing
  `max_leverage`, increases that fixed cost on every trade taken during
  that window — a real, quantifiable drag this option should be measured
  against, not just the forecast's own accuracy.
- **A genuinely new failure mode this thread hasn't had to consider
  yet**: every prior model output on this platform either produces a
  trading decision (direction) or is descriptive (drift status). This
  would be the first time a model output changes _how much_ is at risk on
  a trade that a separate, human-set decision already chose to make. A
  bug in the volatility model's own pipeline (a stale job, a drifted
  feature — exactly the class of failure `FEATURE_DRIFT_INVESTIGATION.md`/
  `RETRAIN_WINDOW_ANALYSIS.md` built real monitoring for) would now also
  silently mis-size real positions, not just mis-predict a direction
  nothing acts on. Any implementation must wire this through the
  _already-built_ feature-drift monitor (`app/prediction/feature_drift.py`)
  as a hard gate — a drifted volatility forecast should fall back to the
  account's own fixed default, never silently continue sizing from a
  reading the platform's own tooling would otherwise flag.

### Option B — stop-loss / take-profit width scaling from the forecast

Widen the mandatory stop-loss (and any take-profit) ahead of a forecast
**expansion** — so ordinary, forecastable noise doesn't trigger an exit
that a genuine reversal would have — and tighten ahead of a forecast
**contraction**, via the existing `PATCH .../positions/{symbol}` path,
either at open time or as a live adjustment to an open position.

**Real tradeoffs:**

- **What it protects against**: a fixed-percent stop-loss is a fixed bet
  on "normal" volatility. Forecast-expansion periods are exactly when a
  fixed-width stop is most likely to be clipped by noise rather than
  signal — this option directly targets that specific, well-understood
  failure mode, arguably more precisely than Option A does (Option A
  changes how much is at risk; this changes _when_ the position exits).
- **A real complication specific to this platform's own margin model**:
  widening a stop-loss on a leveraged position moves it closer to (or, if
  widened enough, past) the position's own liquidation price. This
  platform's own `EngineeringStandards`-level safety property — a
  position's stop-loss must fire before liquidation would — is already
  enforced at order-placement time
  (`strategy_stop_beyond_liquidation`, a real 400 error). Any
  forecast-driven widening must run through that exact same check, not
  bypass it; a "widen the stop to survive expected noise" rule that
  widens it past the liquidation price is not a safer stop, it's a
  disabled one.
- **Narrower in scope, and arguably the more conservative option of the
  two**: it changes _when_ an existing, already-sized position exits, not
  how much capital is deployed in the first place — a smaller surface
  area for something to go wrong than Option A, at the cost of not
  addressing Option A's own concern (a full-size position entered right
  before a forecast expansion is still full-size).
- **The same feature-drift gating requirement as Option A** applies here
  too, for the identical reason.

**Options A and B are not mutually exclusive** — they address different
halves of the same risk (how much is deployed vs. how far it can move
against you before exiting) and could both be built, sequentially, once
one is validated in practice.

---

## How this differs from D1, and why it doesn't reopen it

D1's own prohibition is specific: **do not size leverage from the
model's directional confidence**, because directional confidence was
measured, repeatedly, to carry no information about correctness (AUC
≈0.5 wherever checked, most recently and most definitively
`CONFIDENCE_RECHECK_POST_FIX.md`'s own reconfirmation on the fixed
model). Sizing risk from a _discredited_ signal would manufacture a false
sense of edge from noise.

This proposal sizes risk from a _different model, answering a different
question, with a different, adversarially-validated evidence base_:
`volatility_regime`'s own forecast says nothing about which way price
will move — it has no `predicted_value` of "up" or "down" at all, only
"expand" or "contract" — so it cannot be, and under either option above
is not, used to decide _whether_ to trade or _which direction_. Those
decisions stay exactly where D1/D2 already left them: a human-set
threshold gate (currently blocking everything, per
`CONFIDENCE_RECHECK_POST_FIX.md`) and a directional call from a model
whose own directional skill remains unvalidated. **Both options above are
strictly downstream of that already-made decision** — they only ever
adjust the size or the exit width of a trade the existing, unchanged
directional logic already decided to place. If neither option were built
at all, the strategy's own trading decisions would be identical; only how
much is risked, or how far it can move before exiting, would differ. That
is the precise, checkable boundary that keeps this from being D1's own
prohibited pattern under a new name.

---

## Scope: manual, automated, or both

- **Automated strategy**: the natural first target, since it already has
  a fixed, per-account default for every parameter either option would
  touch, and already runs on a schedule where a forecast could be
  refreshed each tick alongside the existing directional prediction.
- **Manual trades**: `PaperOrderRequest` already exposes `leverage`/
  `stop_loss_price`/`take_profit_price` as caller-supplied values for a
  human-placed order — a volatility forecast could, at most, be
  _surfaced_ to a person placing a manual trade (e.g. a dashboard
  indicator: "near-term volatility forecast: expanding") so they can
  choose to size down themselves, exactly mirroring how D1 already
  reserves variable leverage for manual trades a person reviews. **Not
  recommended: automatically overriding a human-supplied `leverage`/
  `stop_loss_price` on a manual order** — a person who explicitly set
  those values did so deliberately, and silently adjusting them would be
  a different, much less defensible kind of "model changes a live risk
  parameter" than adjusting a strategy's own unattended defaults.

---

## What this does not resolve

- **Which option, if either, to build.** That is your decision, per this
  task's own instruction — this document presents both with real
  tradeoffs, not a default.
- **The still-open live-grading gap.** `volatility_regime`'s own
  predictions cannot yet be graded by the real grading pipeline
  (`TARGET_REDEFINITION_ASSESSMENT.md`'s own documented, deliberately-not-fixed
  limitation: `_grade_one` never fetches the trailing context this
  target needs) — meaning a _live_ deployment of either option would
  have no automatic accuracy tracking for the forecast driving it until
  that gap is closed. Worth fixing before, not after, either option goes
  live.
- **The 24-hour horizon's own precision.** The real-data check above used
  4 data points from a pre-fix period. Once the (currently idle, pending
  your separate confidence-gate decision) accounts resume trading on the
  fixed model, this should be re-checked against a real, larger,
  post-fix sample.
- **The unrelated, still-pending confidence-gate decision from
  `CONFIDENCE_RECHECK_POST_FIX.md`.** All three accounts remain idle for
  that separate reason regardless of anything in this document.

## Related

- The finding this designs around: `VOLATILITY_FEATURE_VERIFICATION.md`
  (the five adversarial checks), `TARGET_REDEFINITION_ASSESSMENT.md`
  (the original discovery and the still-open grading gap).
- D1/D2/D7's own exact text, including D1's own "Option 1" this proposal
  extends: `FUTURES_MECHANICS_AND_LEVERAGE_DESIGN.md`.
- The real, current sizing/leverage/stop-loss mechanism this designs
  against: `app/services/paper_trading_strategy.py::_open_position`.
- The confidence-gate finding this document does not touch or reopen:
  `CONFIDENCE_RECHECK_POST_FIX.md`.
