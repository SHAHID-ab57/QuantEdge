# Roadmap

## Purpose

The platform's milestone-level roadmap — what's actually done, what's
actively being built, and what comes next. This is a directional plan, not
a committed schedule: no milestone below carries a date. Task-level detail
lives in `TASKBOOK.md`; architectural intent for anything not yet built
lives in `docs/architecture/`.

A milestone is only marked **COMPLETE** once every capability inside it
meets `CLAUDE.md`'s own Definition of Done: real code, at a specific path;
at least one automated test that actually exercises it; and it is actually
wired into the running system — imported, called, or routed, not a
standalone script nobody invokes. Anything short of that is **IN
PROGRESS**, regardless of how much design work precedes it.

## Status

Active.

## Overview

Six milestones, in dependency order: a milestone does not start in earnest
until the one before it is far enough along to build on. Milestone 1 is
the foundation every later milestone reads from (a saved model artifact,
a versioned dataset citation, a recorded experiment) — it is now complete.

## Milestones

| Milestone | Name                                         | Status      |
| --------- | -------------------------------------------- | ----------- |
| 1         | Research & Training Platform                 | COMPLETE    |
| 2         | Prediction & Backtesting                     | COMPLETE    |
| 3         | Paper Trading & Risk                         | COMPLETE    |
| 4         | Data Breadth                                 | IN PROGRESS |
| 5         | Production Hardening                         | NOT STARTED |
| 6         | Live Trading (gated on extensive validation) | NOT STARTED |

**Milestone 1 — Research & Training Platform (COMPLETE).** Market data
ingestion/validation, the Feature Engineering Engine, Dataset Validation &
Quality Engine, ML Dataset Builder, Experiment Management System, ML
Training Framework (with per-column feature normalization) and Baseline
Model Framework (real scikit-learn logistic/linear regression adapters,
plus a non-linear `random_forest` adapter added under
ADD-RANDOM-FOREST-RETEST, `TASKBOOK.md` `M1-E6-T5`), and the Model
Evaluation & Benchmarking Engine. Every capability here has
real code, passing tests, and is wired into the running API and dashboard
— see `ARCHITECTURE.md` for the full per-capability design and
`docs/testing/TESTING.md`/`services/api/TESTING.md` for the full test
inventory.

**A real bug in this milestone's own Training Framework was found and
fixed (FIX-TRAINING-DATE-RANGE, `TASKBOOK.md` `M1-E6-T3`), discovered
while working a Milestone 4 task, not by design.** A training job that
omitted an explicit candle range was silently training on a market's
_oldest_ candles, not its most recent ones — including the job driving
live paper trading — confirmed via direct SQL against a real, dead-flat
February 2024 stretch, not inferred. Fixed at the one shared loader every
dataset build funnels through; a job can now optionally pin an explicit
range too. **Every model trained before this fix needs retraining before
its results can be trusted** — the live strategy was disabled pending
that. See `ARCHITECTURE.md` § "Machine Learning Training Framework" for
the full account.

**Both prerequisites for redoing M4-E3-T1 are now resolved
(PREP-RETRAIN-AND-BACKFILL, `TASKBOOK.md` `M1-E6-T4`).** Etherscan's and
CoinGecko's own ~2-day real coverage is a genuine, unchanged free-tier
limit, re-verified live today against both real APIs — nothing to
extend; this bounds any future comparison's own window rather than being
a bug to fix. The live strategy's own experiment was retrained with no
explicit range (job `6e7fb4ed-7142-4c8b-953e-b95788a4014b`) — real,
non-degenerate metrics (test accuracy `0.533`, a real confusion matrix,
15 real predictions individually inspected with genuinely varying
probabilities) read and confirmed sane before anything was re-enabled. A
real, separate discrepancy was caught first: `strategy_enabled` had
reverted to `true` between sessions on the old, degenerate job — disabled
again immediately, then only restored once the retrain checked out.
`strategy_enabled` is now `true`, pointed at the new job. Full account in
`docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md` § "Update
2026-09-09". **M4-E3-T2 has since consumed both prerequisites and redone
the assessment** — see the Milestone 4 section below and that document's
§ "M4-E3-T2".

**Milestone 2 — Prediction & Backtesting (COMPLETE).** The Live
Prediction Service (`app/prediction/`, `/ml/predict`) is the first item:
given a completed training job, reconstruct a live feature vector, run the
model, and return one prediction, persisted to Prediction History. Second:
`POST /training-jobs/{id}/run` no longer blocks for a training run's
duration — it validates and transitions to `running` synchronously, then
executes the pipeline in a background `asyncio.Task` with its own database
session, rejecting a concurrent duplicate call rather than
double-executing it; a job whose background task was still running at an
app restart is left `status="running"` with no watchdog yet to reconcile
it, a disclosed limitation, not a silent one. This seam
(`app/services/background_tasks.py`, generalized once the Backtesting
Engine needed it too) is what every longer-running prediction/training run
on this platform now schedules through. See `ARCHITECTURE.md` §
"Machine Learning Training Framework". Third: Prediction Grading — for
every persisted prediction whose target horizon has actually arrived,
determine what really happened (via the exact target-generation logic that
produced its training label) and record whether it was right, reusing the
existing evaluation metrics for correctness/error. Runs periodically
(`PredictionGradingScheduler`, mirroring `CandleSyncScheduler`) and
on-demand (`scripts/grade_predictions.py`); Prediction History now shows
graded outcomes and pending ones distinctly. See `ARCHITECTURE.md` §
"Prediction Grading". Fourth and last: the Backtesting Engine
(`app/backtest/`, `/ml/backtest`) — given a trained model and a historical
date range, walk it one step at a time, calling the Live Prediction
Service and its grading logic completely unmodified in a loop (proven
identical to a live call by test, not asserted), verified adversarially to
have no look-ahead bias, and reporting aggregate performance via the exact
same evaluation metrics every other milestone already reads from. Runs
asynchronously through the same shared background-task registry training
jobs use — no second mechanism. See `ARCHITECTURE.md` § "Backtesting
Engine". Every capability in this milestone has real code, passing tests,
and is wired into the running API and dashboard. **Independently
re-verified 2026-09-06**, against real code and live test runs rather
than re-asserted from this document's own prior status — see
`docs/audits/MILESTONE_2_3_VERIFICATION.md`.

Before Milestone 3 began, two items left outstanding from Milestone 2 were
re-verified: the backtesting no-look-ahead adversarial test was re-run
fresh and still passes, and a real training job was created and run
against the real dev database, timed at 0.028s to return `status:
"running"` (not `"completed"`), with the background pipeline finishing
independently moments later. See `ARCHITECTURE.md` § "Paper Trading" for
the full account.

**Milestone 3 — Paper Trading & Risk (COMPLETE).** Paper Trading
(`app/paper_trading/`, `/paper-trading`) is the first item and is
complete: a virtual trading account places simulated market orders
against real prices — a modeled slippage and fee always applied, never a
perfect, cost-free fill — tracks materialized positions, and computes
realized/unrealized PnL, long-only with no margin, no shorting, no
leverage. Pre-trade risk limits are also complete: position sizing, total
exposure, and a maximum drawdown that halts an account until an explicit
resume — all three checked against current prices and current balance,
never entry prices or a stale balance, and guarded against concurrent
orders by the same atomic-`UPDATE` pattern the training-job duplicate-run
race established. Stop-loss/take-profit are also complete: a threshold
set on an open position is watched via the existing event bus (no new
polling loop) and closed automatically — through the same fill model and
atomic concurrency guard, applied to a third occurrence of the same
race — the instant it's crossed, at a wider modeled slippage than a
manual order. **Automated Strategy, the milestone's last item, is
complete too**: an account may opt into a single automated strategy
(off by default) that places an order through this exact same
order-placement path on a fresh, above-threshold prediction — the fourth
occurrence of the same atomic concurrency guard, proven by test to share
every existing risk limit rather than bypass it, every automated position
carrying a stop-loss structurally, and every cycle logged whether it
acted or not. See `ARCHITECTURE.md` § "Paper Trading". This does **not**
change anything about Milestone 6's own gate below. A standalone risk
engine beyond these account-level limits has not been started; see
`docs/architecture/DomainModel.md`/`ContainerArchitecture.md` for the
intended bounded contexts. **Independently re-verified 2026-09-06**, the
same way as Milestone 2 — see
`docs/audits/MILESTONE_2_3_VERIFICATION.md`.

**Milestone 4 — Data Breadth (IN PROGRESS).** The additional external data
connectors this platform has designed for but never implemented —
Marketaux (news/sentiment), Etherscan (on-chain), FRED (macro),
Alternative.me (Fear & Greed), DefiLlama (DeFi metrics), CoinGecko (market
statistics); see `docs/architecture/SystemContext.md`. The reusable
abstraction every one of these will sit on top of is now built — a
`Connector` protocol and registry (mirroring `Normalizer`/`FeatureRegistry`),
a generic `external_data_points` table (one table for every source, not
one per source), and periodic ingestion mirroring `CandleSyncScheduler` —
proved end to end by the first, lowest-risk connector: **Fear & Greed is
done**, fetched, stored, and available as a real feature
(`fear_greed`, verified to never look ahead), reaching the existing
`/features` selector with zero frontend change. **FRED is also done** —
the second connector, and the first requiring authentication:
`fed_funds_rate` (FRED's `FEDFUNDS` series), with a real ~1-month
publication lag investigated up front and handled correctly by
timestamping every point with FRED's own real publication date, never
the reference month it describes (see `ARCHITECTURE.md` § "FRED
Connector" for the full account). This task was previously reported as
issued elsewhere without ever actually landing in this repository — see
`docs/audits/MILESTONE_2_3_VERIFICATION.md`, which found this the one
real gap while independently confirming Milestones 2–3 were genuinely
complete. **Etherscan is also done** — the third connector: `eth_gas_price`
(Etherscan's Gas Oracle `ProposeGasPrice`), chosen only after confirming
which of the free tier's narrower endpoints was actually usable (ETH
supply too flat to be informative and hard-fails with no key;
`dailyavggasprice` confirmed Pro-tier-only), migrated to Etherscan's
current V2 API after the old endpoint's deprecation was caught live, and
handling a genuinely tighter rate limit (3/sec, 100k/day, reverified
against Etherscan's current docs) via a JSON-body-content retry dispatch
since Etherscan always answers HTTP 200 even on failure (see
`ARCHITECTURE.md` § "Etherscan Connector" for the full account, including
why no historical backfill is possible for this source). **DefiLlama is
also done** — the fourth connector, and the first requiring no
authentication at all: `eth_tvl` (DefiLlama's `v2/historicalChainTvl`
for Ethereum), confirmed free/unauthenticated and empirically rate-limit
-tolerant against the real live API, and the first connector whose own
investigation surfaced a genuinely new risk — already-published
historical data can itself be revised. A live comparison found a
persistent divergence between DefiLlama's own "current" and "historical"
TVL figures for the same day; handled by a new, opt-in
`ConnectorMetadata.revisable` flag (default `false`, every other
connector unaffected) that lets a later sync tick overwrite an
already-stored value in place, rather than silently keeping a
stale/uncorrected figure forever (see `ARCHITECTURE.md` §
"DefiLlama Connector" for the full account). **CoinGecko is also done**
— the fifth connector, and the first whose API key is genuinely optional
rather than merely unconfigured: `btc_dominance` (CoinGecko's `/global`,
`market_cap_percentage.btc`), confirmed fully keyless against the real
live API, with a Demo key only raising the rate limit. Chosen over ETH's
own market cap or total market cap on a structural argument (a share of
the total market cannot be derived from any single asset's own price
series, unlike ETH's own market cap or total market cap's own broad
correlation with price-like movement) rather than an empirical
correlation check, since no free historical BTC-dominance series exists
to run one against (see `ARCHITECTURE.md` § "CoinGecko Connector" for the
full account, including why this source — like Etherscan — has no
historical backfill capability at all). **Marketaux is also done** —
the sixth and last connector, and the first whose real data (full
articles, not a single numeric value) does not fit the generic
`RawDataPoint`/`external_data_points` shape at all. Its own required
Step 1 — is Marketaux's built-in per-entity sentiment score actually
usable, sparing a from-scratch NLP pipeline — came back genuinely
usable, confirmed against the real, live API and current documentation.
Real article detail lives in a new, dedicated `news_articles` table;
only a derived daily mean sentiment is mirrored into
`external_data_points` (`news_sentiment`), reachable through the same
feature-lookup pattern every other source uses. A new
`ConnectorMetadata.auto_synced` flag (Marketaux is the only connector so
far opted out) excludes it from the generic sync tick in favor of its
own dedicated scheduler, since its `fetch()` shape (zero, one, or many
articles per call) never fit that generic tick's own "one point per
call" assumption. A new, dedicated `/news` page gives real per-article
detail (headline, source, published time, a real sentiment score and
label, a link to the original) its own real estate, deliberately not
bolted onto `/data-sources`, which stays fully generic (see
`ARCHITECTURE.md` § "Marketaux Connector" for the full account,
including the discovery-latency risk this source's own investigation
surfaced — a risk none of the prior five connectors had). No live-API
verification has been performed for this connector — no real
`MARKETAUX_API_KEY` exists in this environment. All six sources named in
`docs/architecture/SystemContext.md` § 3 are now real, closing out this
milestone's own connector epic. Whether Fear & Greed, FRED, Etherscan,
DefiLlama, CoinGecko, Marketaux (or any future source) actually improves
predictions has deliberately not been evaluated — that depends on the
backtest loop being independently confirmed reliable first. A Data
Sources page (`/data-sources`) is also done: two read-only endpoints and
a registry-driven "Active" section (zero frontend change for a future
connector, the same guarantee `/features` already gives) alongside a
static "Planned" section, now empty — every source it once named has
shipped, most recently Marketaux, the same per-connector upkeep every
prior connector's own task already followed. See `ARCHITECTURE.md` §
"External Data Connectors". This closes M4-E1 (External Data
Connectors), this milestone's first epic — but not the milestone itself.
**A second epic, M4-E2 (Delta REST/WS Completion & Liquidation Heatmap
Investigation), is not started.** Confirmed directly against the real
Delta client/parser code, not assumed: of the four items originally
named, ticker and mark price are already fully wired end to end
(subscribed, parsed, published, and reaching the frontend); open interest
is parsed and held in `MarketStateManager` but silently dropped when the
WebSocket gateway builds its outbound ticker payload — a real but narrow
wiring gap; funding rate is the one genuinely unbuilt item — a
`FundingRateEvent` model and its channel-dispatch registration exist at
the low WebSocket-parser level, but nothing subscribes to that channel,
so no funding rate value ever reaches the event bus, state manager, or
any API. The liquidation heatmap investigation is deferred, not
started — a repo-wide search found zero existing code or documentation
for it. See `TASKBOOK.md` `M4-E2-T1`/`M4-E2-T2` for the full task
breakdown.

**A third epic, M4-E3 (Feature Value Assessment), is now complete.** Its
first pass (M4-E3-T1) found the six connector features could not be
measured at all through the platform as it then stood; its second pass
(M4-E3-T2, after the pipeline fix) measured the three deep connectors for
real and found none of them help. Taking the first pass first: real
experiments and training jobs were built for
the baseline plus each connector feature individually, plus all six
together, matching the live baseline's own target/split/model/
hyperparameters exactly. Four of the eight failed outright with an
honest platform error (their own real data coverage in this environment,
the last ~2 days, doesn't reach the training pipeline's default window);
the other four completed but tied at a trivial 100% accuracy — the same
dead-flat, February 2024 window the currently-live baseline itself
already trains on. Two real, compounding platform bugs were found and
disclosed rather than routed around: the Training Framework has no way
to specify a training job's own date range, and its actual default (none
given) loads a market's _earliest_ candles, not its most recent. A
genuinely controlled, real 44-row comparison across all eight variants
**was** proven possible at the Dataset Builder level alone — the blocker
is specifically that the Training Framework cannot consume a pinned
window. See `docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md` for
the full report and `TASKBOOK.md` `M4-E3-T1`. The earliest-not-recent
default bug this exposed has since been fixed under Milestone 1's own
Training Framework (`M1-E6-T3` above), and its own two prerequisites —
resolving the Etherscan/CoinGecko backfill question and retraining the
live model — are also both now resolved (`M1-E6-T4` above).

**M4-E3-T2 then redid the assessment on that corrected pipeline, and this
time it produced a real answer.** The training path now respects a pinned
`start`/`end` end to end, so the primary comparison (baseline + Fear &
Greed + FRED + DefiLlama TVL) ran over the **full 22,711-row ETHUSD/1h
history** — the longest common window all three deep connectors support —
with byte-identical windows across all four variants and 3,408 held-out
test rows. **No deep connector feature adds measurable predictive value:**
every held-out accuracy/ROC-AUC delta is under one percentage point (inside
the noise band for that test size), and DefiLlama TVL slightly _hurts_
held-out performance. The secondary comparison (Etherscan gas price,
CoinGecko BTC dominance, Marketaux news sentiment, all-six) is bounded to
those connectors' real ~4-day backfill depth — 69 rows — and is
**explicitly reported as insufficient statistical power, not equivalent
evidence**: all five variants produce byte-identical held-out predictions.
News landed in the secondary group by the task's own depth criterion (34
days of real data, an order of magnitude closer to the 4-day shallow end
than the multi-year deep end), checked rather than assumed. T2 supersedes
T1's "UNDETERMINED" verdict for the three deep connectors; the three
shallow ones remain unmeasurable until their real-time polling accrues
months of depth. See `docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`
§ "M4-E3-T2" and `TASKBOOK.md` `M4-E3-T2`. **Epic M4-E3's core comparison
is complete** (T3, the horizon sweep, is a cheap research follow-on — see
below).

**One caveat on the T2 result was then closed (ADD-RANDOM-FOREST-RETEST,
`TASKBOOK.md` `M1-E6-T5`).** T2's baseline logistic-regression model had a
ROC-AUC of 0.53 — barely above a coin flip, a weak instrument for
detecting whether a weak connector signal helps. So a non-linear
`random_forest` adapter was added and the identical primary comparison
(same four variants, same windows/splits, same noise band, cross-check
window, and threshold-artifact diagnostic) was re-run under it. **The
negative finding survives:** no connector feature adds held-out value
outside the noise band; DefiLlama TVL is negative under the forest too
(−7 pp held-out F1). Two further objections were then checked directly: a
**regularization sweep** that closes the overfit gap from ~0.16 to ~0.04
leaves the result unchanged (baseline held-out accuracy/ROC do not move —
the model was memorizing noise, not overfitting away a signal), and a
**held-out permutation-importance cross-check** collapses DefiLlama TVL's
impurity importance of 0.225 to ~zero, confirming impurity importance's
known bias toward continuous features — the whole feature set's permutation
importances sit within noise of zero. Two model classes, multiple
robustness checks, same conclusion. Full numbers in
`docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md` § "Random Forest
re-test".

**The last cheap hypothesis was then tested and also came back negative
(HORIZON-SWEEP, `TASKBOOK.md` `M4-E3-T3`).** Every feature had been tested
at exactly one horizon — next hour. So the baseline feature set alone was
swept across horizons 1 h / 4 h / 12 h / 24 h / 48 h, both model classes,
both windows, with this thread's diagnostic suite plus a **block
bootstrap** for a problem that only appears at h > 1: consecutive
h-candle-ahead targets overlap by h−1 candles, so the ~3,400 test rows are
~n/h independent outcomes and a per-row bootstrap CI is spuriously narrow.
The naive CI makes ROC-AUC look like it rises to 0.55–0.58 at h24/h48; the
block-corrected CI includes 0.5 at every horizon ≥ 4, and the generalizing
models there predict a constant class (permutation importance exactly
0.000 for every feature). The recent cross-check window (~150 rows)
replicates nothing. **No prediction horizon from 1 h to 48 h carries
recoverable directional signal in OHLCV-derived features.** The cheap
hypotheses are exhausted; the honest next move is Epic 4.2 / Milestone 5,
or — the one untested hypothesis with real theoretical grounding —
historical order-flow / microstructure persistence, which carries an
infrastructure cost this sweep was the prerequisite for deciding to pay.
`docs/research/HORIZON_SWEEP_ASSESSMENT.md`.

**Milestone 5 — Production Hardening.** Authentication/authorization (none
exists on any route today), CI/CD (none exists — all quality gates are
local git hooks today), structured logging/tracing/metrics/error tracking
(today: plain `logging.basicConfig` only), inbound rate limiting, and a
real background job/task queue (today: in-process `asyncio` loops only).
Not started.

**Milestone 6 — Live Trading (gated on extensive validation).** Real order
execution against a live exchange. Deliberately last, and deliberately
gated: this platform produces analytical decision support, not financial
advice, and nothing here should route real capital until Milestones 2–5
have been validated thoroughly. Not started.

## Dependencies

Milestone 2 depends on Milestone 1 (a trained, evaluated model to predict
and backtest from) — satisfied. Milestone 3 depends on Milestone 2's
backtesting item (paper trading without a validated backtest is
guesswork). Milestone 6 depends on Milestones 2–5 all being substantially
complete, not just Milestone 5 — see the gating note above.

## Timeline

None committed — see Purpose above.
