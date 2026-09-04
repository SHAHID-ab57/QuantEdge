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
| 3         | Paper Trading & Risk                         | IN PROGRESS |
| 4         | Data Breadth                                 | NOT STARTED |
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
and is wired into the running API and dashboard.

Before Milestone 3 began, two items left outstanding from Milestone 2 were
re-verified: the backtesting no-look-ahead adversarial test was re-run
fresh and still passes, and a real training job was created and run
against the real dev database, timed at 0.028s to return `status:
"running"` (not `"completed"`), with the background pipeline finishing
independently moments later. See `ARCHITECTURE.md` § "Paper Trading" for
the full account.

**Milestone 3 — Paper Trading & Risk (IN PROGRESS).** Paper Trading
(`app/paper_trading/`, `/paper-trading`) is the first item and is
complete: a virtual trading account places simulated market orders
against real prices — a modeled slippage and fee always applied, never a
perfect, cost-free fill — tracks materialized positions, and computes
realized/unrealized PnL, long-only with no margin, no shorting, no
leverage, and no automation. Pre-trade risk limits are also complete:
position sizing, total exposure, and a maximum drawdown that halts an
account until an explicit resume — all three checked against current
prices and current balance, never entry prices or a stale balance, and
guarded against concurrent orders by the same atomic-`UPDATE` pattern the
training-job duplicate-run race established. See `ARCHITECTURE.md` §
"Paper Trading". Stop-loss/take-profit orders and a standalone risk
engine beyond these three account-level limits have not been started;
see `docs/architecture/DomainModel.md`/`ContainerArchitecture.md` for the
intended bounded contexts.

**Milestone 4 — Data Breadth.** The additional external data connectors
this platform has designed for but never implemented — Marketaux (news/
sentiment), Etherscan (on-chain), FRED (macro), Alternative.me (Fear &
Greed), DefiLlama (DeFi metrics), CoinGecko (market statistics). Not
started; see `docs/architecture/SystemContext.md`.

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
