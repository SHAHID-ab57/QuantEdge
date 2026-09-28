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
| 4         | Data Breadth                                 | COMPLETE    |
| 5         | Production Hardening                         | COMPLETE    |
| 6         | Live Trading (gated on extensive validation) | NOT STARTED |

**Milestone 1 — Research & Training Platform (COMPLETE).** Market data
ingestion/validation, the Feature Engineering Engine, Dataset Validation &
Quality Engine, ML Dataset Builder, Experiment Management System, ML
Training Framework (with per-column feature normalization) and Baseline
Model Framework (real scikit-learn logistic/linear regression adapters,
plus non-linear `random_forest` (ADD-RANDOM-FOREST-RETEST, `TASKBOOK.md`
`M1-E6-T5`) and `gradient_boosting` (ADD-GRADIENT-BOOSTING, `TASKBOOK.md`
`M1-E6-T6`) adapters), and the Model
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

**Milestone 3, Epic 3.5 — Futures Mechanics and Leverage (manual mechanics and automated long/short built).** Milestone 3's original scope above is unchanged and remains complete. Epic 3.5 extends it. M3-E5-T1 was a research and design spike (no application code): Delta Exchange India's real perpetual-futures mechanics and a design for shorts, margin, liquidation and funding, with the leverage decisions presented for a human (`docs/research/FUTURES_MECHANICS_AND_LEVERAGE_DESIGN.md`). **M3-E5-T2 built it for manually placed orders only:** short positions, isolated-margin leverage, liquidation on the mark price (whole margin forfeited), and funding settled from Delta's real funding history, with position size, exposure and drawdown re-derived on equity and notional. **Decisions in force, none re-opened:** D1 automated trades get no leverage; D2 the automated strategy may not short; D3 drawdown measures equity (an announced behaviour change); D4 a halt blocks new risk and alerts (flattening on a halt is not built); D5 isolated margin only; D6 full margin forfeiture; D7 the exposure caps are not raised. **M3-E5-T3 then extended the automated strategy** (an explicit, twice-confirmed user decision that revisited D1/D2): it now trades **both long and short** from the model's directional call at **one fixed, per-account `strategy_leverage` (default 2) that is never derived from the prediction's confidence**, because confidence was measured to carry no reliable relationship to being right (mean 0.889 against accuracy 0.460). Every automated position carries a mandatory, direction-aware stop-loss, every existing risk limit and the halt apply identically to both directions, and every cycle is logged with its direction and leverage. **Disclosed consequence:** the live model calls "down" in over 99% of cases, so this will very likely be an almost-always-short strategy; existing accounts with the strategy enabled start trading at 2x and may short on their next tick. Open items: the linear liquidation formula is derived from Delta's documented condition and has **not** been verified against a linear-contract figure from Delta (one calculator reading closes it); the next step is watching the strategy run for a real stretch and grading its realized results against the backtest and regime-walkforward framework, not assuming that more active means better. See `ARCHITECTURE.md` § "Paper Trading".

**Milestone 4 — Data Breadth (COMPLETE).** The additional external data
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
Connectors), this milestone's first epic.
**A second epic, M4-E2 (Delta REST/WS Completion & Liquidation Heatmap
Investigation), is now also complete — closing Milestone 4 itself.**
M4-E2-T1: confirmed directly
against the real Delta client/parser code and Delta's live API — ticker
and mark price were already fully wired; open interest was parsed and
held in `MarketStateManager` but silently dropped when the WebSocket
gateway built its outbound ticker payload; funding rate was parsed by the
low-level parser and then went nowhere (`LIVE_CHANNELS` never subscribed
it, the normalizer returned `unsupported`, no domain model or bus event).
Now funding rate runs end to end (domain `FundingRateEvent` +
`FundingRateUpdated` bus event + normalizer + state manager + a new
`funding` WebSocket message), open interest reaches the ticker payload
and frontend, and `DeltaClient.get_ticker` backs a new
`GET /markets/{symbol}/ticker` endpoint (with a Delta REST fill-in for
funding rate / open interest). The same task also **started order-flow
data capture** (`OrderFlowCapture`, `trade_flow` / `orderbook_snapshots`
tables): a capture mechanism only — no backfill, nothing reads it yet, no
analysis — kept deliberately minimal so a future microstructure research
task has real historical depth to work from.

**M4-E2-T2, the liquidation heatmap investigation, is done — a research
spike, not application code, and Milestone 4's last open item.**
"Liquidation heatmap" turned out to mean two genuinely different
products under one name — (a) actual historical liquidation events, and
(b) an estimated heatmap of likely liquidation clusters modeled from open
interest and an assumed leverage distribution (the meaning most industry
sources actually mean by the term) — both researched and presented, not
picked unilaterally. Delta Exchange India's current REST/WS API was
checked directly for liquidation data specifically (not assumed from the
funding/OI work above): it exposes **zero liquidation data of either
kind** — no endpoint, no channel, only a private per-account
`stop_order_type: "liquidation_order"` enum value. Third parties
checked: Coinglass (real events require its $299/mo Standard tier; the
modeled heatmap requires its $699/mo Professional tier — no free tier
includes either) and Binance's free public `forceOrder` stream (the one
zero-cost option, but real-events-only, an explicit proxy for Binance's
own market rather than Delta's, and self-limited to the largest
liquidation per symbol per second). **Recommendation: do not build this
now** — no free or native path exists for either definition, and open
interest (definition (b)'s own raw material) has already been shown, in
this same research thread, to carry no measurable predictive value
across three model classes, five horizons, and three regimes. Full
findings and a fallback build path (for if this decision is revisited) in
`docs/research/LIQUIDATION_HEATMAP_INVESTIGATION.md`. See `TASKBOOK.md`
`M4-E2-T1`/`M4-E2-T2` for the full task breakdown.

**A note on what "complete" means for this specific task, since this
document's own Definition of Done (real code, tested, wired in) is
written for capabilities, not investigations.** M4-E2-T2 was scoped from
the start as a research spike whose stated deliverable was the
investigation document itself, not a shipped feature — its own task
instructions explicitly forbade application code. "Done" here means
that document exists, is well-sourced, and reaches a stated
recommendation, exactly as scoped; it does not mean a liquidation heatmap
now runs anywhere in this platform. No capability was skipped to call
this complete — the recommendation reached (do not build it now) is
itself the substantive outcome the investigation was commissioned to
produce. **Milestone 4 — Data Breadth is now complete.**

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
`docs/research/HORIZON_SWEEP_ASSESSMENT.md`. **(Update: M4-E2-T1 has since
started the capture side of that bet — `trade_flow` / `orderbook_snapshots`
now accumulate in real time. It is a capture mechanism only; the research
pipeline on top of it is still unbuilt.)**

**And a regime walk-forward closed the very last one (REGIME-WALKFORWARD,
`TASKBOOK.md` `M4-E3-T4`).** Every prior result rested on one chronological
split against one test-period regime. A baseline model trained on an early
2024 window was walked forward — via the existing, no-look-ahead-verified
Backtesting engine, unmodified — over three genuinely distinct
out-of-sample regimes: a +100% uptrend (2025-05..07), a −28% downtrend
(2025-10..12), and a flat choppy range (2026-03..05), each ~1,700–1,920
hourly steps. Held-out ROC-AUC was 0.512 / 0.507 / 0.495 — **every 95% CI
includes 0.5.** The model predicts a near-constant "down" in all three
(99.8%+ of its calls), so its accuracy just tracks each regime's base
rate. The one regime-varying metric (precision 0.62 / 0.25 / 0.46) is an
artifact of that fixed lean meeting different outcome distributions, not
skill. **The negative finding is regime-invariant.** A regime-aware
modelling redirect is not indicated (no regime signal to exploit); the
A/B fork is now Epic 4.2 / Milestone 5 vs the order-flow / microstructure
infrastructure bet — whose capture half M4-E2-T1 has now started.
`docs/research/REGIME_WALKFORWARD_ASSESSMENT.md`.

**The model repertoire was then extended with a third, structurally
different model class (ADD-GRADIENT-BOOSTING, `TASKBOOK.md` `M1-E6-T6`) —
one targeted spot-check, not a re-run of the closed research thread.**
`gradient_boosting` (`HistGradientBoostingClassifier`, sequential boosting
rather than Random Forest's bagging) is now a standing adapter, and the
first to ship permutation importance natively. Exactly one comparison ran
under it — baseline vs. baseline + DefiLlama TVL, the one connector that
showed a directional effect under both prior model classes — on the same
byte-identical window every prior comparison used. Both held-out deltas
(+0.26 pp accuracy, +0.60 pp ROC-AUC) sit inside the noise band, and
`eth_tvl`'s permutation importance (−0.10 pp) ranks last and is negative.
**A third model class agrees: no measurable value.** Fear & Greed, FRED,
and the remaining connectors were deliberately not re-tested — already
closed under two model classes, five horizons, and three regimes.
`docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md` § "Gradient
Boosting spot-check".

**Funding rate and open interest were then tested as features
(M4-E3-T5, `TASKBOOK.md`), the one Delta-native signal pair the connector thread
had never covered, and the result is the fourth negative confirmation.**
Delta serves real hourly history for both (`FUNDING:ETHUSD` from 2024-02-05,
`OI:ETHUSD` from 2024-02-06), so two connectors and two features were built and
backfilled, and the identical primary comparison was run under logistic
regression, Random Forest and Gradient Boosting. All nine model x variant cells
sit inside the +-1.68 pp noise band on accuracy and ROC-AUC, and permutation
importance is within noise. The live model's behavior was reproduced exactly
(stored probabilities matched to 2e-15) and re-scored with the features:
funding changes nothing, while open interest makes the near-constant "down" call
_worse_ (99.7% to 100%, 27% to 77% of predictions above 0.99 confidence). The
cause is not the features: it is the live model's `volume` column, which sits at
a mean of 58 standard deviations from its 2024 training window on the backtest
bars, and removing it ends the saturation. **The next step is target
redefinition** (volatility or triple-barrier), preceded by fixing how
scale-drifting inputs are handled. The live strategy's feature set is
unchanged. `docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md` § "M4-E3-T5".

**That "fixing how scale-drifting inputs are handled" step was then scoped
directly, and it found the live model already needs it (M4-E3-T6).** Checked
first, before anything else: both currently strategy-enabled training jobs are
already drifted and already producing saturated live predictions — `733082cc`
through `volume` (z=+89 today) and `6e7fb4ed`, retrained only 13 days earlier,
through price/SMA(20) instead, because its own 100-candle training window's
std was too tight for an ordinary two-week move. Re-running
`REGIME_WALKFORWARD_ASSESSMENT.md`'s exact regime windows with and without
`volume` confirmed the near-constant-"down" behavior is the same artifact
again, while its ROC-AUC ~0.5 "no skill" verdict survives removing that
artifact and is independently corroborated by the horizon sweep — a precise
correction, not a retraction, was added to that document. A general fix (a
connector-health-style monitoring check, recommended first; rolling
retraining with an enforced minimum window; rolling normalization as
defense-in-depth) was designed, not implemented. Both live accounts are
unchanged pending a follow-up task. `docs/research/FEATURE_DRIFT_INVESTIGATION.md`.

**That recommended monitoring check was then built (M5-E5-T3), mirroring the
connector-health pattern this platform had already proven once.** Every live
prediction is now z-scored against its own job's stored normalization
(`app/prediction/feature_drift.py`), with a threshold (10σ) derived from the
same real data the investigation gathered — a healthy reading never exceeds
9.32, both real incidents measured 15.4-89. The response policy was the one
genuine judgment call the task carried, and it was put to the user rather
than assumed: **auto-pause**. A drifted prediction is now checked before the
confidence/signal gate — a drifted model's own saturated confidence is
exactly the failure this exists to catch — and immediately disables that
account's strategy, logs why, and alerts via Sentry, mirroring the drawdown
kill switch's own no-audit-row-for-an-automated-action precedent exactly.
Not self-healing: clearing it is a human's own explicit decision through
`PATCH .../strategy`, surfaced as a distinct banner on the Strategy panel.
`ARCHITECTURE.md` § "Feature Drift Monitoring".

**A fourth epic, M4-E4 (Reddit Sentiment/Volume Connector), reopens
Milestone 4 after it was already marked complete — its own capability
is real and shipped, but the research question it was built to answer
is deliberately left open, not answered weakly.** The connector
(Arctic Shift, a free keyless historical mirror, chosen after Reddit's
own API was found newly gated behind a manual-approval queue), its
dedicated `reddit_comments` table, and its two features
(`reddit_volume`, `reddit_sentiment`, VADER-scored) are real, tested,
and wired in exactly like every other connector in this milestone. What
is not done is Step 3 — testing whether either feature adds anything
`volatility_regime` does not already get from `realized_volatility` —
because a real, full-depth backfill attempt found Arctic Shift's
informal rate limit has a session-cumulative component that no per-
request pacing or cooldown length could clear (25 minutes of patient
retry did not clear one chunk), capping one real session at roughly 56
days of history. This project's own `TARGET_REDEFINITION_ASSESSMENT.md`
treats anything short of the full ~2.6-year history as explicitly
weaker, cross-check-only evidence, specifically because a single
recent window has previously been mistaken for a durable finding in
this same research thread. Rather than repeat that mistake by running
only the window Reddit's real depth can reach and reporting it as the
answer, this epic stops at "investigated and built" — see
`ARCHITECTURE.md` § "External Data Connectors" → "Reddit Connector" and
`docs/research/REDDIT_SENTIMENT_CONNECTOR_ASSESSMENT.md` for the full
account and what would unblock Step 3 (patient multi-session backfilling,
or support for Arctic Shift's monthly bulk dumps, neither built here).

**Milestone 5 — Production Hardening (COMPLETE, against the scope
below).** Delivered: authentication and an audit trail, inbound rate
limiting and login lockout, Redis (rate limiting, lockout, token
revocation), CI/CD (GitHub Actions), connector health monitoring, and
structured logging with error tracking. **This milestone was originally
scoped wider, and three of those items were not built:** distributed
tracing, metrics collection, and a real background job/task queue (the
schedulers are still in-process `asyncio` loops inside the single API
process, which is also why the API cannot run multiple workers; see
`docs/deployment/DEPLOYMENT.md`). They are recorded here as deliberately
out of this milestone's delivered scope, not forgotten: nothing was
descoped silently, and a future task can reopen any of them. Also not
done, and not part of "complete": nothing here is deployed to the
production droplet yet, and no uptime monitor or external check of the API
exists.

**Epic 5.1 — Authentication & Audit Trail (M5-E1-T1) is done.**
Basic bearer-token authentication for a small number of real users
(deliberately no roles/organizations/permission tiers), applied to
every one of the 22 mutating endpoints found by an exhaustive sweep of
the entire API, plus a real `audit_log` table upgrading the existing
LOG-ACCOUNT-CONFIG-CHANGES log lines into queryable, attributed rows —
closing both motivating gaps: no way to trace API-key exposure, and no
way to attribute the earlier `strategy_enabled` reversion to a person.
Verified live against the real dev server and Postgres, not just by
unit test. See `ARCHITECTURE.md` § "Authentication & Audit Trail",
`CHANGELOG.md`, and `TASKBOOK.md` `M5-E1-T1`.

**Epic 5.2 — Rate Limiting (M5-E2-T1) is done.** Closes the one required
fix M5-E1-T1 left open (JWT secret now fails the app at startup, not
lazily on first use — a deliberate, explicitly-documented departure from
this codebase's "missing configuration degrades gracefully" convention)
and both of that task's own disclosed gaps except token revocation:
general in-process rate limiting (a token bucket, keyed by user or IP,
120 req/min default) and a dedicated login lockout (5 failures/5 min
locks a submitted email or IP out for 15 minutes). Verified live,
repeating the exact eight-wrong-password sequence M5-E1-T1 disclosed as
unlimited — it now locks out at attempt 6, and the correct password is
rejected too until the cooldown expires. See `ARCHITECTURE.md` §
"Rate Limiting" and § "Login Lockout", `CHANGELOG.md`, and
`TASKBOOK.md` `M5-E2-T1`.

**Epic 5.3 — Redis (Finally Used) (M5-E3-T1) is done.** Redis has been
provisioned since Milestone 1 and used for nothing — now backs all
three mechanisms that specifically wanted a fast, TTL-capable,
restart-surviving store: rate limiting and login lockout (moved off
their original in-process implementations) plus token revocation (new
— a `jti` claim added to every token, `POST /auth/logout` blocklists
it). A soft dependency, not a hard requirement: unconfigured falls back
to the original in-process behavior exactly as before, configured-but-
unreachable-at-startup fails loudly (mirroring `DATABASE_URL`'s own
precedent), reachable-then-dropped is handled per mechanism, not
uniformly: rate limiting and login lockout fall back to a real,
independently-complete in-process limiter/tracker (never a bare "allow
everything" — for lockout specifically, an attacker can't turn a Redis
blip into unlimited login attempts), while token revocation fails
closed — a real `503` rather than a silent pass-through for a token
whose status can't be verified. That fail-closed design was corrected
mid-task after directly measuring the original fail-open version's
actual behavior rather than trusting its own stated intent; its real
cost (near-total authenticated-API unavailability during a Redis outage
once `REDIS_URL` is configured, not just rejected replays) is deliberate
and documented, not minimized. Verified live against the real dev server
and a real Redis instance: the exact replay scenario M5-E1-T1 disclosed
(issue a token, log out, replay it) is now rejected where it used to
succeed; a real lockout survived a genuine `kill -9` process restart,
the opposite of what M5-E2-T1 found. Found and fixed a real bug along
the way — the rate limiter's own pruning never actually fired, caught
by a test written to exercise it. A
deployment-readiness note (uvicorn's default `X-Forwarded-For` trust)
added to `ARCHITECTURE.md` § "Deployment View" for whoever configures a
future reverse proxy. See `ARCHITECTURE.md` § "Redis", § "Token
Revocation", `CHANGELOG.md`, and `TASKBOOK.md` `M5-E3-T1`.

**Epic 5.4 — CI/CD (M5-E4-T1) is done.** A GitHub Actions workflow runs
the exact checks previously run by hand on every push and pull request,
against real PostgreSQL and Redis service containers. Its first real run
failed, correctly, exposing 55 real `pyright` errors a locally piped
command had been hiding; the fix pushed after it passed both jobs. Live
external-API verification is deliberately excluded. See `ARCHITECTURE.md`
§ "CI/CD Pipeline" and `TASKBOOK.md` `M5-E4-T1`.

**Epic 5.5 — Monitoring (M5-E5-T1, M5-E5-T2) is done.** Connector health:
per-tick sync outcomes are persisted, and each connector is `healthy`,
`stale`, `failing` or `never_ingested` against its own real cadence
(thresholds checked against real gap data, which changed two decisions).
Logging and error tracking: logs are one JSON object per line; unhandled
exceptions and a connector entering `failing` reach an error tracker over
the Sentry protocol, with request bodies, local variables and API keys
deliberately never sent. Two verification steps remain the operator's
own: confirming an event and its notification in the chosen hosted tracker
(verified here only against a local Sentry-compatible server), and the
`/data-sources` health pill in a browser. See `ARCHITECTURE.md`
§ "Connector Health Monitoring" and § "Structured Logging & Error
Tracking".

**M5-E5-T7 closes the "surfacing the reason belongs with the error-
tracking piece" gap M5-E5-T1 itself had flagged as a known limitation —
found for real, not anticipated, on 2026-09-27.** A user report of four
connectors reading `Stale` on both a local dev session and the production
server turned out to be two different real causes wearing an identical
badge: locally, the standalone `scheduler_main` process introduced by
M5-E5-T6's own API/scheduler split had simply never been started in that
session (every source it owns had been frozen at whatever it last synced
before the split — a real, direct consequence of that split landing with
no corresponding update to the dev quickstart, now fixed in
`services/api/README.md` and a new `make run-scheduler` target),
while on the server the scheduler was running correctly the whole time
and Marketaux's live API itself confirmed, via a direct query, zero new
ETHUSD articles in four real days — `success=true` on every attempt.
Both looked identical as a bare `Stale` pill; nothing on the card said
which one was true. `app.connectors.health.describe_health` (pure,
tested the same way `compute_health_status` already is) now derives a
plain-English reason from data the platform already collected but never
surfaced: `next_sync_at` relative to now tells a stalled scheduler
(overdue) apart from one still ticking against a quiet source (not
overdue), and `ConnectorSyncRun.error_message` — stored per attempt since
M5-E5-T1 but never threaded past the database until now — names the real
error for a `failing` connector. Reaches `GET /connectors` as two new
fields (`health_reason`, `last_attempt_error`) and a new note on each
`/data-sources` card. Separately checked, not assumed: whether a stale
connector's frozen value could be silently degrading a live prediction.
It cannot today — the currently live, actively-retrained experiment
trains on `ohlc`/`volume_log`/`sma(20)` only, confirmed directly against
its stored `feature_set`, and consumes no external-data connector feature
at all — but `resolve_external_data`'s own feature-lookup path has no
staleness guard of any kind, so this is a real latent risk for the day a
future retraining does include one, not a closed question. See
`ARCHITECTURE.md` § "Connector Health Monitoring" and `TASKBOOK.md`
`M5-E5-T7`.

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
