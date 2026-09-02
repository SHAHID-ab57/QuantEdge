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
| 2         | Prediction & Backtesting                     | IN PROGRESS |
| 3         | Paper Trading & Risk                         | NOT STARTED |
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

**Milestone 2 — Prediction & Backtesting (IN PROGRESS).** The Live
Prediction Service (`app/prediction/`, `/ml/predict`) is the first item and
is complete: given a completed training job, reconstruct a live feature
vector, run the model, and return one prediction, persisted to Prediction
History. Second: `POST /training-jobs/{id}/run` no longer blocks for a
training run's duration — it validates and transitions to `running`
synchronously, then executes the pipeline in a background `asyncio.Task`
with its own database session, rejecting a concurrent duplicate call
rather than double-executing it; a job whose background task was still
running at an app restart is left `status="running"` with no
watchdog yet to reconcile it, a disclosed limitation, not a silent one.
This is the seam a real backtesting engine's own (likely many, and
possibly longer-running) prediction/training runs will need — built now
rather than assumed later. See `ARCHITECTURE.md` § "Machine Learning
Training Framework". A backtesting engine — replaying a trained model's
predictions against real historical candles to estimate how it would have
performed — has not been started.

**Milestone 3 — Paper Trading & Risk.** Simulated order execution against
live prices, a risk engine (position sizing, exposure limits, drawdown
guards). Not started; see `docs/architecture/DomainModel.md`/
`ContainerArchitecture.md` for the intended bounded contexts.

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
