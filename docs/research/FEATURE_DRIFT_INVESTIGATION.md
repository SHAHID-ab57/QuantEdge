# Feature-Scale Drift Investigation

Investigates whether M4-E3-T5's finding — job `733082cc`'s `volume` normalization
sits 58 standard deviations stale relative to its evaluation window, confirmed
causal for its near-constant-"down"/saturated-confidence behavior by ablation —
also affects the model actually trading live today, then re-characterizes what
that means for `REGIME_WALKFORWARD_ASSESSMENT.md` (which evaluated the same
job), and designs a general fix. No application code was changed; this is an
investigation and design document, per the task's own instruction not to
implement yet. Measured 2026-09-22.

## TL;DR verdict

1. **Both currently-live training jobs are severely feature-drifted, right
   now, and both are producing near-saturated live predictions as a result.**
   Not a hypothetical: real predictions from the running scheduler, checked
   directly.
2. **The mechanism generalizes beyond `volume`.** Job `733082cc` drifts
   through `volume` (today: z = +89, worse than the +58 found in M4-E3-T5).
   Job `6e7fb4ed` — trained 13 days ago, not two years — drifts through
   **price and SMA(20)** instead (z = +15 to +18), because its training
   window was so narrow (100 candles, price std ≈ \$15) that a normal two-week
   price move is already many standard deviations away. A coefficient
   contribution breakdown confirms price/SMA, not volume, drives its
   saturation. **The root cause is "any feature normalized on a window that
   stops matching live input scale," not "volume specifically."**
3. **The regime-walkforward's own mechanism narrative needs correcting, its
   verdict does not.** Re-running its exact three regime windows with and
   without `volume`, on the identical training window, shows the
   near-constant-"down" description is the drift artifact (removing `volume`
   drops "down" calls from 99.6–99.9% to 7.5–44.5% and eliminates every
   above-99%-confidence prediction). But ROC-AUC ≈ 0.5 — "no discrimination
   distinguishable from chance" — **survives removing the saturating feature
   in 5 of 6 cases**, on the exact same windows, and is separately corroborated
   by the horizon sweep's independently-trained, much-less-drifted h=1
   baseline. The regime-invariant "no skill" conclusion holds; the "it
   learned a down prior and carries it unchanged" explanation does not.
4. **A general fix has three complementary parts, none implemented here**:
   a monitoring check (cheap, mirrors the existing connector-health pattern,
   closes today's silent-failure gap on its own), rolling retraining on a
   window with an enforced minimum length (naive "retrain more often" alone
   can reproduce job `6e7fb4ed`'s own too-narrow-window problem), and
   optional rolling/online normalization as a robustness layer between
   retrains. Recommendation below.

---

## Step 1 — Does the live model have the same problem? (checked immediately)

**Three accounts currently run the automated strategy** (`strategy_enabled =
true`, checked directly against `paper_accounts`), referencing two different
training jobs:

| Account    | Training job | Trained on                                    | Trained    |
| ---------- | ------------ | --------------------------------------------- | ---------- |
| `2cff34d9` | `6e7fb4ed`   | Most recent 100 ETHUSD/1h candles at fit time | 2026-09-09 |
| `37b2d8da` | `733082cc`   | `2024-02-06 → 2024-11-01` (the M4-E3-T5 job)  | 2026-09-10 |
| `d790e9ec` | `733082cc`   | (same)                                        | 2026-09-10 |

For each job, today's real latest ETHUSD/1h candle (`2026-09-22 15:00 UTC`)
and a 20-candle `sma_20` were converted to a z-score against that job's own
stored `result_summary.normalization` (mean/std actually fit on its own
training split — nothing recomputed or assumed).

**`733082cc` (accounts `37b2d8da`, `d790e9ec`) — `volume` drift, worse than
M4-E3-T5's own finding:**

| Feature    | Today         | Train mean | Train std  | **z**      |
| ---------- | ------------- | ---------- | ---------- | ---------- |
| open       | 2,741.75      | 3,290.17   | 374.63     | −1.46      |
| close      | 2,742.95      | 3,290.03   | 374.57     | −1.46      |
| sma_20     | 2,748.73      | 3,289.49   | 373.32     | −1.45      |
| **volume** | **1,690,478** | **12,708** | **18,860** | **+88.96** |

Price has partly reverted toward the 2024 training range (mild, in-band z),
but `volume` — driven by two years of real market growth, not by this job's
choice of window — is **89 standard deviations** from what the model was
fit on. (M4-E3-T5 measured 58σ against the confidence-gate audit's frozen
backtest set; today's live figure is worse, as expected — the job has not
been retrained since, and time has kept passing.)

**`6e7fb4ed` (account `2cff34d9`) — a different feature group, same root
cause:** trained only 13 days ago, so this is **not** "the job is old" —
it is "the window was too narrow." Its own training std for every price
column is ≈ \$15–17 (100 candles spanning a placid ~4-day stretch), so an
ordinary two-week price move is already extreme in z-terms:

| Feature | Today     | Train mean | Train std | **z**      |
| ------- | --------- | ---------- | --------- | ---------- |
| open    | 2,741.75  | 2,488.33   | 15.37     | **+16.48** |
| high    | 2,754.95  | 2,495.22   | 16.48     | **+15.76** |
| low     | 2,735.50  | 2,481.71   | 14.34     | **+17.70** |
| close   | 2,742.95  | 2,488.60   | 14.96     | **+17.00** |
| sma_20  | 2,748.73  | 2,484.35   | 15.74     | **+16.79** |
| volume  | 1,690,478 | 882,611    | 562,040   | +1.44      |

Note the reversal from `733082cc`: here `volume` is the well-behaved one
(+1.44, unremarkable) and **price/SMA are the extreme outliers**. A
coefficient-contribution breakdown (refitting the identical job, applying
its own real coefficients to today's real z-vector) confirms which features
are doing this, not just correlating with it:

```text
today's z-vector:      open +16.5  high +15.8  low +17.7  close +17.0  volume +1.4  sma_20 +16.8
contribution to logit(up):  +10.57      -5.66     -12.66     -6.99       -0.47        +8.66
sum + intercept = -6.56  ->  P(up) = 0.0014  (matches the live prediction below)
```

Volume's contribution (−0.47) is negligible; the five price/SMA terms, each
worth several units of logit on their own, are what push the score to −6.56.

**Both jobs' real, current, live predictions are already saturated** — read
directly from `predictions` for the scheduler's most recent cycle, not
recomputed:

| Job        | Latest live prediction (2026-09-22 14:00 UTC cycle) |
| ---------- | --------------------------------------------------- |
| `6e7fb4ed` | `down`, confidence **0.996**                        |
| `733082cc` | `down`, confidence **>0.9999**                      |

**This is urgent in the sense the task means, and unsurprising in the sense
this thread has now shown twice: nothing on this platform currently detects
or flags either condition.** Both accounts have been placing real (paper)
trades on these calls with no visible warning anywhere in the API or
dashboard. This investigation does not pause or change either account — that
is a remediation decision for Step 3's design to inform, not something this
task was asked to do — but it is reported here exactly as found, immediately,
per the task's own instruction.

---

## Step 2 — Re-characterizing the regime-walkforward finding

`REGIME_WALKFORWARD_ASSESSMENT.md` evaluated exactly job `733082cc` — the
same job identified above and in M4-E3-T5 — across three regime windows, all
strictly after its `2024-02-06 → 2024-11-01` training window. Real volume in
every regime window was checked directly against the same job:

| Regime    | Window                    | Mean volume z | Max volume z |
| --------- | ------------------------- | ------------- | ------------ |
| Uptrend   | `2025-05-01 → 2025-07-20` | +49.1         | +281         |
| Downtrend | `2025-10-15 → 2025-12-25` | +63.6         | +411         |
| Choppy    | `2026-03-01 → 2026-05-20` | +62.8         | +430         |

Every regime the document walked forward over was already running the same
drift condition M4-E3-T5 found — confirming the document's own observation
("it predicts down almost every step, mean P(up) ≈ 0.09–0.12, in every
regime") is very likely the same artifact, not a separate, regime-specific
finding.

### The controlled re-test

Exactly the original setup — same training window, same feature set, same
hyperparameters (`C=1.0, max_iter=200, seed=42`), same three regime windows,
built through the same dataset-build seam this whole thread uses — run twice:
**with `volume`** (reproduces the document almost exactly, see below) and
**without it** (the same ablation M4-E3-T5 used to establish causality).

| Regime    | Variant       | Pred. "down" | Conf > 0.99 | Accuracy | ROC-AUC | 95% CI (5,000-resample bootstrap) |
| --------- | ------------- | ------------ | ----------- | -------- | ------- | --------------------------------- |
| Uptrend   | + volume      | 99.8%        | 13.3%       | 0.481    | 0.511   | [0.484, 0.536]                    |
| Uptrend   | **no volume** | **23.8%**    | **0.0%**    | 0.467    | 0.506   | [0.479, 0.533]                    |
| Downtrend | + volume      | 99.9%        | 24.1%       | 0.496    | 0.505   | [0.478, 0.532]                    |
| Downtrend | **no volume** | **44.5%**    | **0.0%**    | 0.524    | 0.529   | **[0.501, 0.556]**                |
| Choppy    | + volume      | 99.6%        | 21.9%       | 0.495    | 0.492   | [0.466, 0.518]                    |
| Choppy    | **no volume** | **7.5%**     | **0.0%**    | 0.507    | 0.509   | [0.484, 0.534]                    |

**Reproduction check**: the "+ volume" row's accuracy (0.481/0.496/0.495) and
ROC-AUC (0.511/0.505/0.492) match the original document's own 0.481/0.498/0.498
and 0.512/0.507/0.495 to within 0.003 — the small difference is consistent
with this thread's documented candle revisions, not a methodology mismatch.
This re-test reproduces the original finding faithfully before changing
anything.

**What changes when `volume` is removed:**

- **The near-constant-"down" behavior is the artifact, confirmed causal a
  second time, on these exact windows.** "Down" calls fall from 99.6–99.9%
  to 7.5–44.5% — no longer near-constant, and now genuinely regime-sensitive
  (more "down" in the downtrend, far less in the choppy range) in a way the
  saturated version could never show. Every prediction above 99% confidence
  disappears (13–24% of predictions, down to exactly 0%, in all three
  regimes).
- **The ROC-AUC ≈ 0.5 verdict does not depend on the artifact.** Five of six
  intervals still include 0.5 after removing the saturating feature. The
  sixth — downtrend, no-volume, `[0.501, 0.556]` — clears 0.5 by 0.001 at
  the boundary. Read honestly: one boundary-adjacent interval out of six is
  not a meaningfully different picture, and it is the opposite direction a
  "the artifact was hiding real skill" story would need (it barely excludes
  chance, it doesn't show a real edge). No regime shows the kind of margin
  the original document's own accuracy/precision numbers might have
  suggested if taken at face value.
- **Independent corroboration, not just this ablation**: `HORIZON_SWEEP_ASSESSMENT.md`'s
  own h=1 baseline was trained on the _full_ history (through mid-2026, not
  a frozen 2024 slice), so it carries far less normalization staleness by
  construction, and it _also_ found ROC-AUC ≈ 0.5 with a CI including 0.5.
  Two structurally different sources of staleness-robustness — one from
  directly removing the drifted feature, one from training on fresher
  data — agree.

### What this means for the document's own claims

| Claim in `REGIME_WALKFORWARD_ASSESSMENT.md`                                                                                                                                     | Status after this check                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "No regime shows discrimination distinguishable from chance" (ROC-AUC ≈ 0.5, CIs include 0.5)                                                                                   | **Holds.** Survives removing the artifact on the identical windows (5/6 CIs), and is independently corroborated by the horizon sweep's own freshly-trained model.                                                      |
| "The negative finding is regime-invariant"                                                                                                                                      | **Holds**, for the same reason.                                                                                                                                                                                        |
| "It predicts 'down' almost every step... trained on the 2024 window, it learned a 'down' prior and carries it, unchanged, into an uptrend, a downtrend, and a flat range alike" | **Needs revising.** This is a plausible-sounding narrative for a real, different phenomenon (`volume` z = +49 to +64 across all three regimes) — not a learned directional bias from the training data's own outcomes. |
| Precision varying by regime (0.62/0.25/0.46) is "an artifact, not skill"                                                                                                        | **Already correct**, and now mechanically explained rather than merely inferred from the confusion matrix.                                                                                                             |
| The A/B fork decision ("no remaining cheap hypothesis...") and its consequences                                                                                                 | **Holds**, since it rests on the ROC-AUC finding, which holds.                                                                                                                                                         |

The correction is narrow and precise: **what the near-constant-"down" behavior
_is caused by_ needs revising (a normalization artifact, not a learned prior);
what it _means for the verdict_ does not (the verdict was already correctly
read from ROC-AUC, not from the accuracy/precision numbers the artifact
distorts, and ROC-AUC is now shown to survive the artifact's removal).** A
precise correction note has been added directly to
`REGIME_WALKFORWARD_ASSESSMENT.md`, not a retraction — see that document's
own "Correction" section.

---

## Step 3 — Designing a general fix (not implemented)

Three real approaches, investigated on their actual merits and actual costs
against this codebase as it exists today — not implemented, per this task's
own instruction.

### What exists today (checked directly, not assumed)

- **No automatic retraining exists at all.** The only periodic schedulers in
  `app/services/` are `ExternalDataSyncScheduler`, `CandleSyncScheduler`,
  `PredictionGradingScheduler`, `NewsSyncScheduler`,
  `PaperTradingStrategyScheduler`, and `PaperFundingScheduler` — none of them
  ever create or refresh a `TrainingJob`. Both drifting jobs above will stay
  exactly as stale as they are today until a person manually creates a new
  one and manually repoints an account's `strategy_training_job_id` at it.
- **Every training job already stores what a drift check needs.**
  `result_summary.normalization` (mean/std per feature column, fit once at
  training time) is already persisted for every completed job — nothing new
  to compute or store to detect drift; the number is already sitting in the
  database for both jobs above.
- **`PaperTradingStrategyScheduler` already calls `PredictionService.run`
  once per account per cycle** — the one place a live feature vector is
  already being assembled before a decision is made, and therefore the one
  natural place to compare it against the job's own stored normalization
  before acting on it.
- **A directly analogous pattern already exists and already proved itself**:
  `app/connectors/health.py`'s `compute_health_status` was built for the
  identical shape of problem — "no error raised, no crash, no alert," three
  real, previously-silent bugs found only because someone eventually asked
  "how long since this last moved forward?" That module's own opening
  paragraph could be republished verbatim for this one.

### Option A — Rolling-schedule retraining

Periodically create a fresh `TrainingJob` on a rolling recent window and
repoint `strategy_training_job_id` at it (or an equivalent auto-promote
policy), the same shape `CandleSyncScheduler` already uses for candles.

- **Pros**: directly fixes staleness for every feature at once, not just the
  one currently worst; keeps the model's absolute price/volume scale close
  to current market conditions without any change to how prediction or
  normalization work.
- **Cons, found directly in this investigation, not hypothetical**: a naive
  "retrain often" policy is not automatically safe. Job `6e7fb4ed` _is_ a
  rolling-retrain outcome — trained 13 days ago on the most recent 100
  candles — and it is **already** as saturated as the two-year-old job, just
  through a different feature group, because a 100-candle window is narrow
  enough that its own std is tiny and a routine two-week move already clears
  15–18σ. A retraining cadence therefore needs an **enforced minimum
  training-window length** (wide enough that ordinary near-term price
  movement stays within a few σ of the fitted std), not just "more frequent."
  Also needs: a promotion policy (auto-swap, or require review — this thread's
  own "silently reverted `strategy_enabled` to `true`, caught only by chance"
  history is a reason to be deliberate here), and a decision about whether a
  retrain silently changes live behavior or requires the same kind of
  explicit, logged, one-action-at-a-time discipline `PATCH .../strategy`
  already enforces for every other config change.

### Option B — Rolling-window (online) normalization instead of a fixed historical fit

Instead of freezing mean/std at training time, compute each feature's
normalization from a trailing window at _prediction_ time (an online/rolling
z-score), so the model's coefficients can stay fixed while the scale its
inputs are measured against keeps tracking the live market.

- **Pros**: decouples "how stale is the fit" from "how stale is the
  scaling" — directly addresses the mechanism, not just the symptom, and
  needs no retraining cadence decision to fix the immediate saturation
  problem. Standard technique in quantitative/time-series ML for this exact
  failure mode.
- **Cons**: introduces a different, new train/serve mismatch — the model's
  decision boundary was shaped by _training-window-normalized_ inputs;
  feeding it _live-rolling-normalized_ inputs at serve time is not obviously
  equivalent, and this thread's whole finding is that these features carry
  no real signal to begin with, so there is no clean way to check "did this
  preserve real skill" here — only "did this stop the saturation," which is
  a narrower, weaker guarantee. Needs a rolling-window length choice with
  the same narrow-window trap as Option A (a very short rolling window
  reintroduces a tiny, fast-moving std). Adds genuine implementation
  surface: a new normalization mode alongside the existing fixed-fit one in
  `app/training/normalization.py`, and a decision about what a too-short
  rolling history at serve time should do (this platform's own
  `missing_values_expected` convention for connector-backed features is a
  reasonable template — degrade explicitly, never guess).

### Option C — A monitoring check flagging extreme live-input drift (mirrors connector health monitoring)

At each `PaperTradingStrategyScheduler` cycle (or any live prediction),
compute each feature's z-score against the job's own already-stored
`result_summary.normalization`, and surface a status — `healthy` /
`drifted` — the same shape `ConnectorHealthStatus` already gives the Data
Sources page, at a threshold to be chosen (this investigation's own numbers
— 15–90σ on the two live jobs, versus an ordinary healthy value of low
single digits — suggest a threshold in the range of a handful of σ would
catch both real cases with enormous margin, not a fine judgment call).

- **Pros**: by far the cheapest of the three — the input data already
  exists, the pattern already exists and is already proven in this
  codebase, and it requires no decision yet about retraining cadence or
  normalization strategy. It is a **prerequisite for safely operating
  either A or B**, not a competing alternative: any retraining schedule can
  itself silently stop (exactly what happened to the external-data sync
  scheduler in M4-E3-T5 — a real, already-observed failure mode on this
  platform, not a hypothetical one), and rolling normalization can itself
  be misconfigured or run out of history; both need a way to notice when
  they've failed. It closes today's actual, live, unmonitored gap on its
  own, without waiting on a design decision for A or B.
- **Cons**: detection, not correction — a `drifted` status by itself does
  not stop a bad trade; it needs a response policy (log-only, alert, or
  auto-pause the account's `strategy_enabled`) decided alongside it, which
  is itself a real product/risk decision, not a pure engineering one.

### Recommendation

**Build Option C first, on its own, regardless of what's decided about A or
B.** It is cheap, it uses data that already exists, it mirrors a pattern
this codebase has already built and validated once, and — unlike A or B —
it closes the actual gap this investigation found (two live accounts
trading on saturated predictions with no visible signal anywhere) without
needing to first decide a training-window length or a normalization
redesign. Ship it, then decide A vs. B with the safety net already in
place.

**Between A and B, prefer A (rolling retraining with an enforced minimum
window) as the primary long-term fix**, with B considered later as a
defense-in-depth layer, not a replacement: A fixes the _coefficients_ going
stale, which B does not touch at all, and A is the more direct, more legible
fix to reason about and to log/audit (a new `TrainingJob` row is a concrete,
inspectable event, the same way this whole platform already treats a config
change). B is worth real consideration specifically as protection _between_
retrains, and as a mitigation if a chosen retraining cadence still proves
too infrequent in practice — not as a way to avoid deciding a cadence at all.

**One thing a fix does _not_ do**: this thread's own accumulated
finding — now four independent negative results (deep connectors, horizon
sweep, regime walk-forward, funding rate/open interest) plus this
investigation's own re-confirmation — is that OHLCV-derived features carry
no recoverable directional signal at h=1 regardless of drift. Fixing drift
makes the live strategy behave as its own already-negative expected value
honestly (a real, moderate-confidence coin flip) instead of an artificially
overconfident, saturated one — it does not reinstate an edge that was never
measured to exist. The next research step remains what M4-E3-T5 already
concluded: target redefinition (volatility or triple-barrier labeling), not
another feature or another fix to this one.

---

## Consequences

- **No application code changed.** Per this task's own instruction, nothing
  was implemented — not the monitoring check, not a retraining schedule, not
  rolling normalization, and neither live account was paused or reconfigured.
- **Both `733082cc`-backed accounts and the `6e7fb4ed`-backed account remain
  exactly as configured**, trading on saturated predictions, until a
  follow-up task builds Option C (recommended first) and/or Option A.
- `REGIME_WALKFORWARD_ASSESSMENT.md` gets a precise correction note (below),
  not a retraction — its verdict and the A/B research fork it fed into both
  stand.

## Evidence trail

- Step 1: direct queries against `paper_accounts`, `training_jobs.result_summary`,
  `candles`, and `predictions` (no synthetic data) — three enabled accounts,
  two jobs, both drifted, both saturated in their most recent real scheduler
  cycle.
- Step 2: a controlled re-test (with/without `volume`) reusing the exact
  training window, feature set, hyperparameters, and three regime windows
  `REGIME_WALKFORWARD_ASSESSMENT.md` used, through the same dataset-build seam
  this whole research thread uses (`MLDatasetService.build_ml_dataset`,
  `build_training_dataset`, the registered `logistic_regression` adapter) —
  a research script, not committed application code, matching this thread's
  own established convention. Reproduction of the original document's
  `+volume` numbers to within 0.003 verifies the setup faithfully matches
  before drawing any conclusion from the ablation.
- Step 3: read directly from `app/services/` (which schedulers exist),
  `app/training/normalization.py`, and `app/connectors/health.py` — no
  option here is proposed against an assumed codebase shape.
- `uv run pytest tests/training tests/paper_trading` passes unchanged (no
  code was touched).
