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
Model Framework (real scikit-learn logistic/linear regression adapters),
and the Model Evaluation & Benchmarking Engine. Every capability here has
real code, passing tests, and is wired into the running API and dashboard
— see `ARCHITECTURE.md` for the full per-capability design and
`docs/testing/TESTING.md`/`services/api/TESTING.md` for the full test
inventory.

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
historical backfill capability at all). The remaining source (Marketaux)
has not been started — it needs its own investigation into
sentiment-scoring usability, not just auth/response shape. Whether Fear &
Greed, FRED, Etherscan, DefiLlama, CoinGecko (or any future source)
actually improves predictions has deliberately not been evaluated — that
depends on the backtest loop being independently confirmed reliable
first. A Data Sources page (`/data-sources`) is also done: two read-only
endpoints and a registry-driven "Active" section (zero frontend change
for a future connector, the same guarantee `/features` already gives)
alongside a static "Planned" section for the sources not yet built —
needing per-connector upkeep as each ships (FRED came off that list the
same change it landed in the registry). See `ARCHITECTURE.md` §
"External Data Connectors".

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
