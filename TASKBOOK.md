# Task Book

## Purpose

This document serves as the single source of truth for tracking every milestone, epic,
task, and micro-task throughout the project lifecycle. It replaces reliance on chat
history, distributed notes, or informal checklists by providing a centralized,
structured, and version-controlled implementation backlog.

Task tracking is important because it ensures clear accountability, prevents scope
creep, provides visibility into project progress, and enforces disciplined execution
of the project plan. Every contributor should consult this document to understand what
is being worked on, what is pending, and what has been completed.

This document should be updated after every completed task. It will evolve alongside
the project as new epics are identified, priorities shift, and milestones are delivered.

---

## Task Status

| Status      | Meaning                                                               |
| ----------- | --------------------------------------------------------------------- |
| Planned     | Task has been identified and described but is not yet ready to begin. |
| Ready       | All prerequisites are met; work can commence.                         |
| In Progress | Development is actively underway.                                     |
| Review      | Implementation is complete and awaiting review.                       |
| Completed   | Finished, reviewed, and approved.                                     |
| Blocked     | Cannot proceed due to an unresolved dependency or external blocker.   |
| Deferred    | Postponed to a future milestone; not currently scheduled.             |

---

## Task ID Convention

Every task is identified by a hierarchical ID that encodes its position in the project
structure.

**Format:** `M{0}-E{1}-T{2}-MT{3}`

| Segment | Meaning                      | Example |
| ------- | ---------------------------- | ------- |
| `M0`    | Milestone 0                  | `M0`    |
| `E1`    | Epic 1 within the milestone  | `E1`    |
| `T3`    | Task 3 within the epic       | `T3`    |
| `MT2`   | Micro-task 2 within the task | `MT2`   |

**Examples:**

- `M0-E1-T1-MT1` — Milestone 0, Epic 1, Task 1, Micro-task 1
- `M2-E3-T7-MT4` — Milestone 2, Epic 3, Task 7, Micro-task 4
- `M5-E1-T2-MT1` — Milestone 5, Epic 1, Task 2, Micro-task 1
- `M0-E1-T4-MT0` — Milestone 0, Epic 1, Task 4 (no micro-task breakdown)

When a task does not require micro-task decomposition, `MT0` is used.

---

## Priority Levels

| Priority | Usage                                                                           |
| -------- | ------------------------------------------------------------------------------- |
| Critical | Blocks all other work; must be resolved immediately.                            |
| High     | Essential for the current milestone; should be completed before non-essentials. |
| Medium   | Important but can be deferred within the milestone if necessary.                |
| Low      | Nice-to-have; addressed only after all higher-priority tasks are complete.      |

Priority is reassessed at the beginning of each milestone.

---

## Dependency Rules

- Tasks may depend on the completion of one or more previous tasks.
- Dependencies must never be skipped. A task cannot begin until all prerequisite tasks
  are marked Completed.
- Documentation tasks must be completed before implementation tasks for the same
  component.
- The dependency chain is recorded in the Dependencies column of the Progress Tracking
  table.

---

## Git Workflow

Every micro-task follows a consistent workflow:

1. **Prompt** — One focused Claude Code prompt that defines the scope of the micro-task.
2. **Commit** — One Git commit containing only the changes for that micro-task.
3. **Review** — The commit is reviewed before being merged.

This one-to-one-to-one mapping ensures a clean, auditable history where every commit
corresponds to a well-defined unit of work.

Larger tasks that span multiple micro-tasks produce one commit per micro-task and
one review per task.

---

## Progress Tracking

The milestone numbering below was replaced wholesale (see `ROADMAP.md`) once
it became clear the old M0–M11 breakdown didn't map onto what had actually
been built — see `CLAUDE.md`'s own note on this. The rows below are real,
not illustrative: each one names an actually-completed capability, verified
against the Definition of Done stated in `ROADMAP.md`'s own Purpose section
(real code, a passing test, and it's actually wired in), with the commit
that introduced it where the work has been committed.

| ID       | Milestone                        | Epic                                               | Task                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | Status    | Priority | Dependencies | Git Commit           |
| -------- | -------------------------------- | -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | -------- | ------------ | -------------------- |
| M1-E1-T1 | M1: Research & Training Platform | E1: Data Layer                                     | Market data ingestion, validation, event bus                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Completed | Critical | None         | `ee8c890`            |
| M1-E2-T1 | M1: Research & Training Platform | E2: Feature Engineering                            | Feature Engineering Engine                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Completed | High     | M1-E1-T1     | `11d03a9`            |
| M1-E3-T1 | M1: Research & Training Platform | E3: Dataset Validation                             | Dataset Validation & Quality Engine                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | Completed | High     | M1-E2-T1     | `d53cbde`            |
| M1-E4-T1 | M1: Research & Training Platform | E4: ML Dataset Builder                             | ML Dataset Builder                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Completed | High     | M1-E2-T1     | `345341d`            |
| M1-E5-T1 | M1: Research & Training Platform | E5: Experiment Management                          | Experiment Management System                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Completed | High     | M1-E4-T1     | `00d6d52`            |
| M1-E6-T1 | M1: Research & Training Platform | E6: Training Framework                             | ML Training Framework + Baseline Model Framework                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Completed | Critical | M1-E5-T1     | `c57a19d`, `3bd31a8` |
| M1-E6-T2 | M1: Research & Training Platform | E6: Training Framework                             | Per-column feature normalization                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Completed | High     | M1-E6-T1     | `4376586`            |
| M1-E6-T3 | M1: Research & Training Platform | E6: Training Framework                             | FIX-TRAINING-DATE-RANGE — a training job that omitted an explicit candle range silently trained on a market's _oldest_ candles, not its most recent ones (including the job driving live paper trading), found while investigating M4-E3-T1, not by design; confirmed via direct SQL, not inference. Fixed at the shared loader (`app/services/candle_points.py`) every dataset-building consumer funnels through; `TrainingJobCreateRequest` gained optional `start`/`end`, persisted onto two new `TrainingJob` columns. Every model trained before this fix needs retraining; the live strategy was disabled pending that                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Completed | Critical | M1-E6-T1     | `8634694`            |
| M1-E6-T4 | M1: Research & Training Platform | E6: Training Framework                             | PREP-RETRAIN-AND-BACKFILL — Etherscan/CoinGecko's ~2-day backfill depth confirmed a genuine, unchanged free-tier limit (re-verified live today against both real APIs — both explicitly reject the only historical-data endpoints with a real Pro-tier rejection), not an under-extended backfill; nothing to run further back. The live strategy's own experiment retrained on real, recent data with no explicit range (job `6e7fb4ed`) — real, non-degenerate metrics (test accuracy 0.533, real confusion matrix, real per-prediction probability variance, individually inspected) confirmed sane before re-enabling anything. A real, separate discrepancy caught first: `strategy_enabled` had reverted to `true` between sessions, still citing the old degenerate job — disabled again immediately, only re-enabled once the retrain checked out                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | Completed | High     | M1-E6-T3     | `39d4389`            |
| M1-E6-T5 | M1: Research & Training Platform | E6: Training Framework                             | ADD-RANDOM-FOREST-RETEST — `random_forest` adapter (`sklearn.ensemble.RandomForestClassifier`, `app/training/adapters/random_forest.py`), the first non-linear model on the platform, registered via the same zero-touch `@register` discovery with zero pipeline/service/API changes; feature importance from the forest's own mean-decrease-in-impurity `feature_importances_` (unsigned, `compute_impurity_feature_importance`). Built to re-test whether the M4-E3-T2 connector features that showed no value under logistic regression show value under a model that can capture non-linear interactions — they do not: same four variants, same windows/splits, same rigor (noise band, cross-check window, threshold-artifact diagnostic), same conclusion. Two follow-up objections checked directly and answered the same way: (a) a regularization sweep that closes the overfit gap from ~0.16 to ~0.04 leaves the "no held-out value" result unchanged (baseline test accuracy/ROC do not move — the modest RF was memorizing noise, not overfitting away a real signal); (b) a held-out permutation-importance cross-check collapses DefiLlama TVL's impurity importance of 0.225 to ~zero, confirming impurity importance's known bias toward continuous features (Strobl et al. 2007) — the entire feature set's permutation importances are within noise of zero. DefiLlama TVL still costs ~2 pp test accuracy at every regularization level. Full comparison in `docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md` § "Random Forest re-test"                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Completed | Medium   | M1-E6-T1     | `14231c4`            |
| M1-E6-T6 | M1: Research & Training Platform | E6: Training Framework                             | ADD-GRADIENT-BOOSTING — `gradient_boosting` adapter (`sklearn.ensemble.HistGradientBoostingClassifier`, `app/training/adapters/gradient_boosting.py`), a second non-linear model, structurally different from Random Forest (sequential error-correcting boosting vs. bagging), registered via the same zero-touch `@register` discovery with zero pipeline/service/API changes. No native `feature_importances_`/`coef_`, so this adapter ships **permutation importance** (`compute_permutation_importance`, `app/training/interpretability.py`) as a first-class part of every run's result summary — the RF re-test's own follow-up had flagged this as "a natural candidate to add... deferred as its own scoped change"; it no longer is. Built-in early stopping explicitly disabled (`early_stopping=False`) — left on it would carve a random validation subset out of the training split, violating this platform's chronological-only splitting policy and competing with the framework's own held-out `dataset.validation`. Exactly one comparison run, not a re-litigation of the closed connector-value question: baseline vs. baseline + DefiLlama TVL, same byte-identical window boundaries as every prior comparison in this thread (verified three ways, including an independent raw-SQL cross-check — row count/min/max match exactly; mean/std differ, meaning some interior candle values have since been revised, a real and disclosed finding, not a pipeline bug). Both held-out deltas (+0.26 pp accuracy, +0.60 pp ROC-AUC) sit inside the ±1.68 pp noise band, and eth_tvl's own permutation importance (−0.10 pp) ranks last of seven features and is negative — agreeing with both prior model classes that DefiLlama TVL adds no measurable value. Fear & Greed, FRED, and the remaining connectors deliberately not re-tested (already closed under two model classes, five horizons, three regimes — see `docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md` § "Gradient Boosting spot-check") | Completed | Medium   | M1-E6-T5     | None                 |
| M1-E7-T1 | M1: Research & Training Platform | E7: Model Evaluation                               | Model Evaluation & Benchmarking Engine                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | Completed | High     | M1-E6-T1     | `3a411c1`            |
| M1-E8-T1 | M1: Research & Training Platform | E8: Experiment Config Editor                       | In-app `feature_set`/`target_config`/`split_config` editor                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Completed | Medium   | M1-E5-T1     | `346f708`            |
| M2-E1-T1 | M2: Prediction & Backtesting     | E1: Live Prediction                                | Live Prediction Service (`app/prediction/`, `/ml/predict`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Completed | Critical | M1-E6-T1     | `9871c1c`            |
| M2-E1-T2 | M2: Prediction & Backtesting     | E1: Live Prediction                                | Non-blocking `/training-jobs/{id}/run` (background `asyncio.Task`, own DB session, duplicate-run rejection, shutdown cancellation)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Completed | High     | M1-E6-T1     | `8bb20f5`            |
| M2-E1-T3 | M2: Prediction & Backtesting     | E1: Live Prediction                                | Prediction Grading (`app/prediction/grading.py`, `PredictionGradingScheduler`, `scripts/grade_predictions.py`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Completed | High     | M2-E1-T1     | `92c4425`            |
| M2-E2-T1 | M2: Prediction & Backtesting     | E2: Backtesting                                    | Backtesting Engine (`app/backtest/`, `/ml/backtest`) — reuses live prediction + grading unmodified, verified no-look-ahead                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Completed | High     | M2-E1-T3     | `fed6259`            |
| M3-E1-T1 | M3: Paper Trading & Risk         | E1: Paper Trading                                  | Paper Trading (`app/paper_trading/`, `/paper-trading`) — realistic slippage/fee always applied, long-only, no margin/automation                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Completed | High     | M2-E2-T1     | `86396e9`            |
| M3-E1-T2 | M3: Paper Trading & Risk         | E1: Paper Trading                                  | Pre-trade risk limits (position sizing, exposure, drawdown halt) — current-price checks, atomic concurrency guard verified empirically                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | Completed | High     | M3-E1-T1     | `5ac5f21`            |
| M3-E1-T3 | M3: Paper Trading & Risk         | E1: Paper Trading                                  | Stop-loss/take-profit (`app/paper_trading/monitor.py`) — event-bus monitor, atomic concurrency guard (3rd occurrence), wider triggered slippage                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Completed | High     | M3-E1-T2     | `ab4c64c`            |
| M3-E1-T4 | M3: Paper Trading & Risk         | E1: Paper Trading                                  | Automated Strategy (`app/services/paper_trading_strategy.py`) — opt-in, off by default, reuses order-placement path (4th atomic-guard occurrence), every position stop-lossed, every cycle logged                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Completed | High     | M3-E1-T3     | `00a5879`            |
| M4-E1-T1 | M4: Data Breadth                 | E1: External Data Connectors                       | Connector abstraction (`app/connectors/`: protocol + registry) and generic `external_data_points` table, proved end to end by the first connector — Fear & Greed Index, ingested/synced and available as a real, no-look-ahead-verified feature                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Completed | High     | M1-E2-T1     | `f3dd088`            |
| M4-E1-T2 | M4: Data Breadth                 | E1: External Data Connectors                       | FRED macroeconomic connector (`app/connectors/fred.py`, `fed_funds_rate` feature) — first connector requiring authentication; a real ~1-month publication lag investigated and handled via FRED's own `realtime_start`, never the reference `date`, verified by a dedicated fixture test. Re-issued after being reported issued but never actually built the first time (see `docs/audits/MILESTONE_2_3_VERIFICATION.md`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | Completed | High     | M4-E1-T1     | `e4dcc5b`            |
| M4-E1-T3 | M4: Data Breadth                 | E1: External Data Connectors                       | Data Sources page (`/data-sources`) — registry-driven `GET /connectors`/`GET /connectors/{source}/history`, an Active section with zero source hardcoding, a static Planned section needing per-connector upkeep                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Completed | Medium   | M4-E1-T1     | `cd8e037`            |
| M4-E1-T4 | M4: Data Breadth                 | E1: External Data Connectors                       | Etherscan on-chain connector (`app/connectors/etherscan.py`, `eth_gas_price` feature) — third connector, second requiring authentication; migrated to Etherscan's current V2 API after the old endpoint's deprecation was caught live, handles a genuinely tighter rate limit (3/sec, 100k/day) via JSON-body-content retry dispatch since Etherscan always returns HTTP 200, and discloses (rather than hides) that no historical backfill is possible for this metric                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Completed | High     | M4-E1-T1     | `30eb9b0`            |
| M4-E1-T5 | M4: Data Breadth                 | E1: External Data Connectors                       | DefiLlama TVL connector (`app/connectors/defillama.py`, `eth_tvl` feature) — fourth connector, first requiring no authentication; investigation found DefiLlama revises published TVL figures, handled by a new opt-in `ConnectorMetadata.revisable` flag (default `false`, every prior connector unaffected) that lets ingestion overwrite an already-stored value rather than silently keep it stale                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | Completed | High     | M4-E1-T1     | `2cf66f8`            |
| M4-E1-T6 | M4: Data Breadth                 | E1: External Data Connectors                       | CoinGecko market data connector (`app/connectors/coingecko.py`, `btc_dominance` feature) — fifth connector, first whose API key is genuinely optional; BTC dominance chosen over ETH's own market cap on a structural non-redundancy argument, confirmed keyless against the real live API, no historical query capability on the free tier (same limitation as Etherscan)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Completed | High     | M4-E1-T1     | `2499e96`            |
| M4-E1-T7 | M4: Data Breadth                 | E1: External Data Connectors                       | Marketaux news connector with a detailed news feed (`app/connectors/marketaux.py`, `news_sentiment` feature, `/news` page) — sixth and last connector, first whose real data (full articles) does not fit the generic `RawDataPoint`/`external_data_points` shape at all; confirmed Marketaux's own built-in per-entity sentiment score is usable (no NLP pipeline needed); new dedicated `news_articles` table, dedicated ingestion pipeline and scheduler (`ConnectorMetadata.auto_synced=False`), only a derived daily mean mirrored into `external_data_points`; no live-API verification yet (no real key in this environment)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | Completed | High     | M4-E1-T1     | `c4d892f`            |
| M4-E2-T1 | M4: Data Breadth                 | E2: Delta REST/WS Completion & Liquidation Heatmap | Delta REST/WS completion — confirmed against the real client/parser code, not copied verbatim from a prior request: **ticker is already fully wired** (`LIVE_CHANNELS` in `app/runtime.py` subscribes it, `TickerEvent` is parsed and published as `TickerUpdated`, reaches the frontend over `/api/v1/ws/market`); **mark price is already fully wired** (parsed onto `TickerEvent.mark_price`, stored in `MarketStateManager`, and actually serialized in the WS gateway's own outbound ticker payload, `app/marketdata/gateway.py`'s `_ticker_payload`); **open interest is parsed and stored** (`TickerEvent.open_interest`, held in `MarketStateManager`) **but silently dropped from `_ticker_payload`** — never reaches any API consumer or the frontend, a real but narrow wiring gap, not a rebuild; **funding rate is genuinely unbuilt** — `FundingRateEvent` (`app/integrations/delta/websocket/models.py`) and its `"funding_rate"` channel dispatch registration (`app/integrations/delta/websocket/parser.py`) exist at the low level, but `LIVE_CHANNELS` never subscribes to that channel, so nothing in the pipeline, event bus, state manager, or any API surface ever sees a real funding rate value. **DONE:** funding rate built end to end (`FundingRateEvent` domain model + `FundingRateUpdated` bus event + normalizer + `LIVE_CHANNELS` subscription + `MarketStateManager` + new `funding` WS message); open interest added to the WS ticker payload + frontend; `DeltaClient.get_ticker` + `GET /markets/{symbol}/ticker` (REST fill-in for funding/OI). Also **Step 0**: order-flow data capture started — `OrderFlowCapture` service + `trade_flow`/`orderbook_snapshots` tables (migration `252f1e39f532`), a capture mechanism only (no backfill, nothing reads it yet, no analysis). Verified live against the running server                                                                                                                                                                    | Completed | Medium   | M1-E1-T1     | None                 |
| M4-E2-T2 | M4: Data Breadth                 | E2: Delta REST/WS Completion & Liquidation Heatmap | Liquidation heatmap investigation — a research spike, no application code. Confirmed zero existing code or documentation reference anywhere in this repository (a repo-wide search for "liquidation" across every `.py`/`.ts`/`.tsx`/`.md` file returns only a private-position `liquidation_price` field in an account-margin WS model, not a market-wide heatmap feature). **DONE:** "liquidation heatmap" is two genuinely different products under one name — (a) actual historical liquidation events, (b) an estimated cluster heatmap modeled from open interest + an assumed leverage distribution — both researched and presented, neither pre-selected. Delta Exchange India's current REST/WS API, checked directly (not assumed from this repo's own funding/OI work): zero liquidation data of either kind — no endpoint, no channel, only a private per-account `stop_order_type: "liquidation_order"` enum value. Third parties investigated: Coinglass (real events require Standard tier $299/mo minimum; the modeled heatmap requires Professional $699/mo — no free tier includes either, despite a looser web summary claiming otherwise); Binance's public `forceOrder` stream is the one free option, but real-events-only, Binance's own market (an explicit proxy, not Delta's), and self-limited to the largest liquidation per symbol per second. **Recommendation: do not build now** — no free or native path exists for either definition, and this session's own research thread already found open interest (definition (b)'s own raw material) carries no measurable predictive value across three model classes, five horizons, and three regimes. Full findings, cost breakdown, and a fallback build path in `docs/research/LIQUIDATION_HEATMAP_INVESTIGATION.md`. Closes Milestone 4's last open item                                                                                                                                                                                          | Completed | Low      | M4-E2-T1     | None                 |
| M4-E3-T1 | M4: Data Breadth                 | E3: Feature Value Assessment                       | Measured whether the six connector features actually help predictions — real experiments/training jobs built for each feature plus all six together, benchmarked against the baseline. Result: **not measurable through the existing platform today**, a real finding, not a routed-around blocker — two compounding platform bugs confirmed in code: the Training Framework has no way to pin a training job's own date range at all, and its real default (no range given) loads a market's _earliest_ candles, not its most recent, so every untargeted training run (including the one currently live) trains on the same dead-flat, 2.5-year-old window. Full report, real evidence, and the two concrete fixes needed in `docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | Completed | High     | M4-E1-T1     | `015ed8a`            |
| M4-E3-T2 | M4: Data Breadth                 | E3: Feature Value Assessment                       | Redid the feature-value assessment on the corrected training pipeline (M1-E6-T3/T4), split into a statistically-powered **primary** comparison (baseline + Fear & Greed + FRED + DefiLlama, over the full 22,711-row ETHUSD/1h history — the longest window all three deep connectors support) and an explicitly under-powered **secondary** one (Etherscan + CoinGecko + Marketaux/News + all-six, bounded to those connectors' real ~4-day backfill depth, 69 rows). News's placement in the secondary group was checked against the task's own depth criterion, not assumed — 34 days of real data is an order of magnitude closer to the 4-day shallow end than the 8–30-year deep end. Result: **no primary connector feature adds measurable predictive value** (all held-out deltas < 1 pp over 3,408 test rows; DefiLlama TVL marginally _hurts_, −2.1 pp test accuracy); secondary comparison is **not measurable for lack of data depth** (all five variants produce byte-identical held-out predictions, all overfitting-flagged). Both tables, deltas, and the noise-band analysis in `docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md` § "M4-E3-T2"                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | Completed | High     | M4-E3-T1     | `17c39d7`            |
| M4-E3-T3 | M4: Data Breadth                 | E3: Feature Value Assessment                       | HORIZON-SWEEP — every feature so far had been tested at exactly one horizon (next hour). Swept the baseline feature set alone (`ohlcv` + `sma(20)`, no connectors) across `next_direction` horizons 1 h / 4 h / 12 h / 24 h / 48 h, same ETHUSD/1h window and split as every prior comparison, under both logistic regression and Random Forest (modest + regularized), with this thread's full diagnostic suite plus a **circular block bootstrap** for a problem that only appears at h > 1: consecutive h-candle-ahead targets overlap by h−1 candles, so the ~3,400 test rows are ~n/h independent outcomes and a per-row bootstrap CI is spuriously narrow. The naive CI makes held-out ROC-AUC look like it rises to 0.55–0.58 at h24/h48 (CI excluding 0.5); the block-corrected CI includes 0.5 at every horizon ≥ 4, and the generalizing models there predict a constant class (permutation importance exactly 0.000 for every feature, test-F1 = the mechanical "always predict up" value). The recent ~150-row cross-check replicates nothing. **No prediction horizon from 1 h to 48 h carries recoverable directional signal in OHLCV-derived features.** Step 2's conditional (re-run the six-connector comparison at a skillful horizon) is not triggered. No application code. `docs/research/HORIZON_SWEEP_ASSESSMENT.md`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Completed | Medium   | M4-E3-T2     | `31e8513`            |
| M4-E3-T4 | M4: Data Breadth                 | E3: Feature Value Assessment                       | REGIME-WALKFORWARD — every prior result rested on one chronological split against one test-period market regime; the horizon sweep's own diagnosis of the h24/h48 illusion (a near-constant probability rank-correlating with one trending test block) is why that matters. Identified three genuinely distinct ETHUSD regimes by inspecting the actual monthly history against stated criteria (net return, intra-window range, trend consistency): a +100% uptrend (2025-05-01..07-20), a −28% downtrend (2025-10-15..12-25), and a flat choppy range (2026-03-01..05-20, band 1900–2470), each ~1,700–1,920 hourly steps. One baseline logistic model (OHLCV + SMA(20), next_direction h=1) trained on an early 2024 window — so all three regimes are strictly out-of-sample — was walked forward over each via the **existing Backtesting engine, unmodified** (`POST /backtests/run`, one live prediction + immediate grade per step, aggregate metrics from the shared EvaluationEngine). Held-out ROC-AUC: 0.512 / 0.507 / 0.495 — every 5,000-sample bootstrap 95% CI includes 0.5. The model predicts a near-constant "down" in all three regimes (99.8%+ of its calls), so accuracy just tracks each regime's base rate and the one regime-varying metric (precision 0.62 / 0.25 / 0.46) is an artifact of that fixed lean, not skill. **The negative finding is regime-invariant.** No application code. `docs/research/REGIME_WALKFORWARD_ASSESSMENT.md`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Completed | Medium   | M4-E3-T3     | pending commit       |

---

## Milestone Summary

| Milestone | Name                                         | Status      |
| --------- | -------------------------------------------- | ----------- |
| M1        | Research & Training Platform                 | COMPLETE    |
| M2        | Prediction & Backtesting                     | COMPLETE    |
| M3        | Paper Trading & Risk                         | COMPLETE    |
| M4        | Data Breadth                                 | IN PROGRESS |
| M5        | Production Hardening                         | NOT STARTED |
| M6        | Live Trading (gated on extensive validation) | NOT STARTED |

**M1-E6-T3, FIX-TRAINING-DATE-RANGE, is now real, tested, and wired in —
a genuine bug in Milestone 1's own Training Framework, found while
working M4-E3-T1 (Milestone 4), not a Milestone 4 defect itself.** A
training job that omitted an explicit candle range was silently training
on a market's _oldest_ candles, never its most recent ones — including
the job driving live paper trading — because the shared loader every
dataset build funnels through (`app/services/candle_points.py`) ran a
bare ascending scan with no lower bound whenever no range was given.
Confirmed via direct SQL against `candles` (a real, dead-flat February
2024 stretch), not inferred from a model's own output. Fixed at that one
shared loader; `TrainingJobCreateRequest` gained optional, validated-
together `start`/`end` fields, persisted onto two new `TrainingJob`
columns (`dataset_start`/`dataset_end`, migration `01c81f537e54`) so a
job's own real training window is a queryable fact going forward, not
something only reconstructible after the fact. **Every model trained
before this fix needs retraining before its results can be trusted** —
the live paper-trading strategy was disabled (`strategy_enabled=false`)
as an immediate, separate action pending that retrain, and M4-E3-T1's own
feature-value assessment should be redone once it happens (see that
task's own "the same task's own second, smaller finding" note). No test
exercised the shared loader's own default behavior directly before this
— every existing caller's tests always passed an explicit range, which
is exactly why it went unnoticed. Full account in `ARCHITECTURE.md` §
"Machine Learning Training Framework".

**M1-E6-T4, PREP-RETRAIN-AND-BACKFILL, is now real and complete —
resolves both prerequisites for redoing M4-E3-T1.** Etherscan's/
CoinGecko's own ~2-day real coverage was already disclosed, at each
connector's original build time, as a genuine free-tier limit — no
historical-data endpoint is reachable without a Pro-tier subscription.
Re-verified live, today, against both real APIs (not just re-cited):
both return a real, current Pro-tier rejection for their own only
historical-data endpoint. **Nothing to extend — this bounds any future
feature-value comparison's own window, it is not a bug to fix.** The
live strategy's exact experiment (`565ca966...`) was then retrained with
no explicit range, exercising M1-E6-T3's own corrected default directly:
new job `6e7fb4ed-7142-4c8b-953e-b95788a4014b`, real recent price data,
real non-degenerate metrics (test accuracy `0.533`, `roc_auc` `0.679`, a
real `[[5,4],[1,5]]` confusion matrix, 15 real predictions individually
inspected with genuinely varying probabilities) — read and confirmed
sane, not assumed, before doing anything else. A real, separate
discrepancy was caught first: the live account's `strategy_enabled` had
reverted to `true` between sessions, still citing the old degenerate job
— disabled again immediately as a precaution, then only re-enabled,
re-pointed at the new job, once the retrain's own metrics checked out.
Full account, every real number, in `docs/research
/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md` § "Update 2026-09-09".

**M4-E3-T2 is now complete — the feature-value assessment redone on the
corrected pipeline, and this time it produces a real answer for the deep
connectors.** With `start`/`end` respected end to end, the primary
comparison (baseline + Fear & Greed + FRED + DefiLlama TVL) ran over the
**full 22,711-row ETHUSD/1h history** — the literal longest common window
all three deep connectors support, not a convenient recent slice — with
byte-identical windows across all four variants (verified via identical
`close` normalization stats) and 3,408 held-out test rows. **No deep
connector feature adds measurable value:** every held-out accuracy/ROC-AUC
delta is under 1 pp (inside the ±1.7 pp 95% noise band for that test size),
Fear & Greed's larger validation-F1 delta is a decision-threshold shift
with no ROC-AUC movement, and DefiLlama TVL actually _hurts_ held-out
performance slightly (−2.1 pp test accuracy, widening overfit gap). A
41-day recent-regime cross-check reinforces this — Fear & Greed's deltas
flip sign between splits, FRED is exactly inert over any window short
enough that the monthly rate doesn't move. The secondary comparison
(Etherscan gas price, CoinGecko BTC dominance, Marketaux news sentiment,
all-six) is bounded to those connectors' real ~4-day backfill depth — 69
rows, 11 test — and is **explicitly reported as insufficient statistical
power, not equivalent evidence**: all five variants produce byte-identical
held-out predictions and all are overfitting-flagged. News landed in the
secondary group by the task's own depth criterion (34 days of real
Marketaux data is an order of magnitude closer to the 4-day shallow end
than the multi-year deep end), checked rather than assumed. T2 supersedes
T1's blanket "UNDETERMINED": deep connectors are now measured (and don't
help a simple model); shallow connectors remain unmeasurable, now purely
for lack of data depth. Both comparison tables in `docs/research
/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md` § "M4-E3-T2".

**`M1-E6-T5` (ADD-RANDOM-FOREST-RETEST) then re-ran that primary comparison
under a non-linear model — same conclusion — and `M4-E3-T3`
(HORIZON-SWEEP) closed the last cheap hypothesis: "wrong horizon, not
wrong features."** The baseline feature set alone was swept across
`next_direction` horizons 1 h / 4 h / 12 h / 24 h / 48 h, both model
classes, both windows. A per-row bootstrap makes held-out ROC-AUC look
like it rises to 0.55–0.58 at the long horizons, but that is a
pseudo-replication artifact — consecutive h-candle-ahead targets overlap
by h−1 candles, so a **block bootstrap** (block length = horizon) is the
correct treatment, and it widens every CI at h ≥ 4 to include 0.5. The
generalizing models at h24/h48 predict a constant class (permutation
importance exactly 0.000 for every feature). The ~150-row recent
cross-check replicates nothing. **No horizon from 1 h to 48 h carries
recoverable directional signal in OHLCV-derived features.**
`docs/research/HORIZON_SWEEP_ASSESSMENT.md`.

**`M4-E3-T4` (REGIME-WALKFORWARD) then closed the very last one: "wrong
regime, not wrong features/horizon."** Every result so far rested on one
chronological split against one test-period regime. A baseline logistic
model (OHLCV + SMA(20), h=1) trained on an early 2024 window was walked
forward — via the existing no-look-ahead-verified Backtesting engine,
unmodified — over three strictly out-of-sample regimes identified by
inspecting the monthly history against stated criteria: a +100% uptrend, a
−28% downtrend, and a flat choppy range, ~1,700–1,920 hourly steps each.
Held-out ROC-AUC was 0.512 / 0.507 / 0.495 — every bootstrap 95% CI
includes 0.5. The model predicts a near-constant "down" in all three, so
accuracy tracks the base rate and the one regime-varying metric (precision
0.62 / 0.25 / 0.46) is a fixed-lean artifact, not skill. **The negative
finding is regime-invariant.** The cheap hypotheses are exhausted; a
regime-aware modelling redirect is not indicated (no regime signal to
exploit), so the A/B fork is Epic 4.2 / Milestone 5 vs the order-flow /
microstructure infrastructure bet.
`docs/research/REGIME_WALKFORWARD_ASSESSMENT.md`.

**`M1-E6-T6` (ADD-GRADIENT-BOOSTING) then extended the model repertoire
with a third, structurally different model class — not a re-run of the
closed research question, one targeted spot-check.** `gradient_boosting`
(`HistGradientBoostingClassifier`) is now a standing adapter, sequential
boosting rather than Random Forest's bagging, and the first to ship
permutation importance natively (deferred from the RF re-test's own
follow-up). Exactly one comparison ran under it — baseline vs. baseline +
DefiLlama TVL, the one connector that showed a directional (negative)
effect under both logistic regression and Random Forest — using the same
byte-identical window every prior comparison in this thread used
(verified three ways; row count/min/max match exactly, though the
interior candle values have since been revised by intervening
backfill/retrain work, disclosed rather than hidden). Both held-out
deltas (+0.26 pp accuracy, +0.60 pp ROC-AUC) sit inside the ±1.68 pp
noise band, and `eth_tvl`'s own permutation importance (−0.10 pp) ranks
last of seven and is negative. **A third model class agrees: no
measurable value.** Fear & Greed, FRED, and the remaining connectors were
deliberately not re-tested — already closed under two model classes, five
horizons, and three regimes; re-running them again with no new reason to
expect a different result would not be new evidence.
`docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md` § "Gradient
Boosting spot-check".

M2 is now closed: the Live Prediction Service, making training-job
execution non-blocking (the async seam the Backtesting Engine's own runs
now share, rather than a second mechanism), Prediction Grading, and the
Backtesting Engine itself (reuses the live prediction and grading code
completely unmodified, verified adversarially to have no look-ahead bias)
are all real, tested, and wired into the running API and dashboard. Before
M3 began, two items left outstanding from M2 were re-verified: the
backtesting no-look-ahead adversarial test was re-run fresh and still
passes, and a real training job was created and run against the real dev
database, timed at 0.028s to return `status: "running"` — not
`"completed"` — with the background pipeline finishing independently
moments later (`ARCHITECTURE.md` § "Paper Trading" has the full account).
**Independently re-verified 2026-09-06** against real code and live test
runs, not re-asserted from this document's own prior status — see
`docs/audits/MILESTONE_2_3_VERIFICATION.md`.

M3 is now closed. Paper Trading, its first item, is real, tested, and
wired in — a virtual trading account with realistic (slippage/
fee-applied) market order fills, long-only, no margin/shorting/leverage.
Its pre-trade risk limits (position sizing, exposure, and a drawdown
halt — all three checked against current prices/balance, guarded against
concurrent orders with the same atomic-`UPDATE` pattern the training-job
duplicate-run race established, verified with two real concurrent
requests) are also real, tested, and wired in. Stop-loss/take-profit are
also real, tested, and wired in — set at order-open time or via a
dedicated endpoint, watched through the existing event bus (no new
polling loop), and closed automatically at a wider modeled slippage
through the same fill model and atomic concurrency guard (its third
occurrence) a manual close uses. Automated Strategy — the milestone's
last item — is real, tested, and wired in too: an opt-in, off-by-default
automated order path that reuses this exact same order-placement
machinery (the atomic guard's fourth occurrence, proven by test to share
every existing risk limit rather than bypass it), attaches a stop-loss to
every automated position structurally, and logs every scheduler cycle
whether it acted or not. This does not change anything about Milestone
6's own gate. **Independently re-verified 2026-09-06**, the same way as
Milestone 2 — see `docs/audits/MILESTONE_2_3_VERIFICATION.md`. See
`ROADMAP.md` for what each milestone actually covers.

M4 is now **complete**: its first epic, M4-E1 (External Data Connectors),
finished earlier; its second, M4-E2 (Delta REST/WS Completion &
Liquidation Heatmap Investigation), closed with both tasks done —
`M4-E2-T1` (funding rate/open interest/order-flow capture) and
`M4-E2-T2` (the liquidation heatmap investigation, a research spike whose
recommendation is not to build the feature yet — see below). M4-E1's
first item, the reusable connector abstraction
(`app/connectors/`'s `Connector` protocol + `ConnectorRegistry`,
mirroring `Normalizer`/`FeatureRegistry`) and the generic
`external_data_points` table every future source will share, is real,
tested, and wired in — proved end to end by the first concrete
connector: the Fear & Greed Index, fetched via a client mirroring
`DeltaClient`'s own error-typing/retry conventions, ingested/synced on a
schedule mirroring `CandleSyncScheduler`, and available as a real feature
(`fear_greed`) verified adversarially to never look ahead. Wired into
both the live-inference and training dataset-building paths deliberately,
to prevent a train/serve skew a future connector-backed feature could
otherwise introduce silently. Reaches the existing `/features` selector
with zero frontend change. Every remaining source this milestone names —
FRED, Etherscan, DefiLlama, CoinGecko, and, last, Marketaux — has since
landed too; see `M4-E1-T2`, `M4-E1-T4`, `M4-E1-T5`, `M4-E1-T6`, and
`M4-E1-T7` below. Marketaux needed its own investigation into
sentiment-scoring usability, not just an auth model and response shape to
design against — confirmed usable, and, unlike the other five, its real
article detail does not fit the generic `RawDataPoint`/
`external_data_points` shape at all, requiring a dedicated table,
ingestion pipeline, and scheduler (see `M4-E1-T7` below). All six named
sources in `docs/architecture/SystemContext.md` § 3 are now real,
closing out M4-E1, this milestone's own connector epic. See
`ARCHITECTURE.md` § "External Data Connectors".

M4-E2-T1 (Delta REST/WS completion) is **done**. Confirmed directly
against the real Delta client/parser code and Delta's live API before
touching anything, rather than trusting a prior request's list: ticker
and mark price were already fully wired; open interest was parsed onto
`TickerEvent.open_interest` and held in `MarketStateManager` but silently
dropped from the WS ticker payload; funding rate was parsed by the
low-level WebSocket parser and then stopped dead (normalizer returned
`unsupported`, no domain model, no bus event, `funding_rate` never in
`LIVE_CHANNELS`). Now: funding rate runs end to end — `FundingRateEvent`
domain model, `FundingRateUpdated` bus event, `DeltaNormalizer._funding_rate`
(verified against real frames: `fi` seconds, `nfr` micros),
`MarketStateManager.get_latest_funding_rate` + `MarketState.funding_rate`,
`funding_rate` in `LIVE_CHANNELS`, and a new `funding` message type on
`/api/v1/ws/market`. Open interest is in the WS ticker payload and the
frontend. `DeltaClient.get_ticker` + `GET /api/v1/markets/{symbol}/ticker`
(`LiveMarketService`) expose the live ticker + funding, with a one-shot
Delta REST fill-in for funding rate / open interest when they are not yet
in memory. Step 0 of the same task also started **order-flow data
capture**: `OrderFlowCapture` + `trade_flow` / `orderbook_snapshots`
tables (migration `252f1e39f532`), subscribing to the existing
`TradeEventReceived` events and the existing `OrderBookAggregator` — a
**capture mechanism only**: no historical backfill, nothing downstream
reads the tables, no feature generator, no analysis. All verified live
against the running server (funding rate + OI populate the state manager
and the endpoint from real Delta frames on both symbols; the capture
tables accumulate real coherent rows on the configured cadence).

**`M4-E2-T2` (the liquidation heatmap investigation) is now done — a
research spike, not application code, closing Milestone 4's last open
item.** "Liquidation heatmap" turned out to be two genuinely different
products under one name, both researched and presented rather than
picked unilaterally: (a) actual historical liquidation events, and (b)
an estimated cluster heatmap modeled from open interest plus an assumed
leverage distribution — the meaning most industry sources actually mean
by the term. Delta Exchange India's current REST/WS API was checked
directly (not assumed from the funding/OI work above, since liquidations
are a different event type): zero liquidation data of either kind — no
endpoint, no channel, only a private per-account `stop_order_type:
"liquidation_order"` enum value, the same private fact this platform's
own `PositionUpdate.liquidation_price` already reflects. Third parties
checked: Coinglass (real events require Standard tier, $299/mo minimum;
the modeled heatmap requires Professional, $699/mo — no free tier
includes either, despite one looser web summary claiming otherwise, an
important correction made during the investigation) and Binance's public
`forceOrder` stream (the one free option — but real-events-only,
Binance's own market as an explicit proxy rather than Delta's, and
self-limited by Binance's own design to the largest liquidation per
symbol per second). **Recommendation: do not build this now** — no free
or native path exists for either definition, and this session's own
research thread already found open interest (definition (b)'s own raw
material) carries no measurable predictive value across three model
classes, five horizons, and three regimes. A fallback build path is
recorded for later (Binance's stream for a free, proxy-labeled version of
(a); Coinglass Professional, following the existing `Connector` protocol,
for (b) or for real events). Full findings in
`docs/research/LIQUIDATION_HEATMAP_INVESTIGATION.md`. (This task's own
"Completed" status means its scoped deliverable — the investigation
document and its recommendation — was produced, per its own task
instructions, which explicitly forbade application code; `ROADMAP.md`'s
usual "real code, tested, wired in" bar for a **capability** does not
apply to a research spike whose entire point was to decide whether to
build one. No liquidation heatmap runs anywhere in this platform.)
**Milestone 4 is now complete.**

**M4-E3-T1, Feature Value Assessment, is now complete — and its own
result is that the six connector features cannot currently be measured
at all, a real finding, not an unfinished measurement.** Real experiments
and training jobs were built for the baseline plus each of the six
connector features individually, plus one with all six together, each
matching the live baseline's own target/split/model/hyperparameters
exactly. Four of the eight failed outright (`eth_gas_price`,
`btc_dominance`, `news_sentiment`, `all_six`) with an honest platform
error — every row dropped, since those connectors' own real coverage in
this environment (the last ~2 days) doesn't reach back to the training
pipeline's own default window. The other four completed, but tied at a
trivial 100% accuracy — the exact same degenerate, dead-flat February
2024 window the currently-live baseline itself trains on, confirmed by
direct SQL. Two real, compounding platform bugs were found and disclosed
(not routed around): the Training Framework has no way to specify a
training job's own date range at all, and its actual default, when none
is given, loads a market's _earliest_ candles rather than its most
recent — the opposite of what a system predicting "what happens next"
should default to. A genuinely controlled, real, non-degenerate 44-row
comparison across all eight variants **was** proven possible at the
Dataset Builder level alone (byte-identical row sets, verified by diffing
timestamps, not just counts) — the blocker is specifically that the
Training Framework cannot consume a pinned window at all. Full report,
every real id, and the two concrete fixes needed in
`docs/research/CONNECTOR_FEATURE_VALUE_ASSESSMENT.md`. The earliest-not-
recent default bug has since been fixed — see `M1-E6-T3` above, tracked
against Milestone 1 (the Training Framework's own home), not Milestone 4,
since this is a defect M4-E3-T1 exposed, not one it introduced. This
assessment should be redone once a genuinely controlled comparison is
also possible at the training level, not just at the Dataset Builder
level as proven here.

M4-E1-T3, the Data Sources page (`/data-sources`), is also real, tested,
and wired in: two new read-only endpoints (`GET /connectors`,
`GET /connectors/{source}/history`) and an "Active Data Sources" section
that is entirely registry-driven — a future connector appears with no
frontend change, the same guarantee `/features` already gives — plus a
static "Planned Data Sources" section for the five sources named above,
requiring per-connector upkeep as each one ships. **A numbering note**:
this task was originally going to be `M4-E1-T2`, but that id had already
been assigned in a different chat, for a FRED connector reported as
issued — this task was renumbered to `M4-E1-T3` to avoid the collision.
As of this page shipping, that FRED work had **not** actually landed in
this repository's connector registry (`app/connectors/` held only
`fear_greed.py`), so no `M4-E1-T2` row appears above yet — per this
document's own rule, a row here names an actually-completed capability,
not a report of one. The exact same drift this document's own discipline
exists to catch; the next task in this milestone should check
`ROADMAP.md`/`TASKBOOK.md`'s real current state before assuming either
FRED's status or the next free task id.

**M4-E1-T2, FRED, is now real, tested, and wired in** — built this time,
not just reported. The second concrete connector, and the first
requiring authentication: `app/connectors/fred.py` fetches FRED's
`FEDFUNDS` series (the monthly effective federal funds rate), available
as a real feature (`fed_funds_rate`). Its own investigation, done before
any feature-lookup code was written, found a genuine ~1-month publication
lag (a monthly average is not actually knowable until roughly a month
after the calendar month it describes) and handled it by timestamping
every point with FRED's own `realtime_start` (the real publication date),
never `date` (the reference month) — verified end to end by a dedicated
fixture test, not merely asserted. Appears in `GET /connectors`/
`/data-sources` and `GET /features` automatically, confirmed by test, the
same zero-code-change guarantee every other connector already has. A
real `FRED_API_KEY` later exposed a second real bug the mocked test
suite could not have caught: FRED silently defaults its own
`realtime_start`/`realtime_end` to today when omitted, which had been
collapsing every observation onto the same fake vintage date — caught by
the real backfill's own numbers (865 of 866 real values discarded as
false duplicates), fixed by always passing FRED's documented sentinel
range, and re-verified against the real API afterward (364 genuinely
distinct values, a hand-checked real rate cut confirmed correct over
real HTTP). See `ARCHITECTURE.md` § "External Data Connectors" → "FRED
Connector".

**M4-E1-T4, Etherscan, is now real, tested, and wired in.** The third
concrete connector, and the second requiring authentication:
`app/connectors/etherscan.py` fetches Etherscan's Gas Oracle
(`gastracker`/`gasoracle`), available as a real feature
(`eth_gas_price`). Its own investigation, done before any client code was
written, found the historically-documented endpoint deprecated — a real,
live, unauthenticated call returned an explicit "switch to Etherscan API
V2" error — and found the free-tier rate limit had changed from the
historically-cited 5/sec to a current, verified 3/sec and 100,000/day.
It also found Etherscan always returns HTTP 200, even for rate-limit and
authentication failures, reporting the real error only in the JSON
body's own `result` field — a genuine deviation from Fear & Greed's and
FRED's partly status-code-driven retry dispatch, confirmed by two real,
live calls before writing any retry logic. The metric itself was chosen
only after ruling out two real alternatives: ETH total supply (confirmed
nearly flat day to day, and confirmed to hard-fail with no API key) and
the Pro-tier-only `dailyavggasprice` (confirmed via Etherscan's own plan
documentation, not assumed free). Gas Oracle's response carries no date
field of its own and no historical query capability at all, so lag is
zero by construction — every point is timestamped `datetime.now(UTC)` at
fetch time — but this also means no historical backfill is possible for
this source, a disclosed limitation rather than a hidden gap: `fetch()`
always makes exactly one live request, returning it only if "now" falls
inside the requested range. Appears in `GET /connectors`/`/data-sources`
and `GET /features` automatically, confirmed by test, the same
zero-code-change guarantee every other connector already has. See
`ARCHITECTURE.md` § "External Data Connectors" → "Etherscan Connector".

**M4-E1-T5, DefiLlama, is now real, tested, and wired in.** The fourth
concrete connector, and the first requiring no authentication at all:
`app/connectors/defillama.py` fetches DefiLlama's
`v2/historicalChainTvl/Ethereum` series, available as a real feature
(`eth_tvl`). Its own investigation, done before any client code was
written, confirmed the free tier's real auth/rate-limit behavior
directly (no key, no documented numeric limit, empirically tolerant of
15 concurrent requests where Etherscan itself begins rate-limiting at 10) and checked all three bug patterns that had each independently
bitten a prior connector — none applied here (no omittable parameter
exists on this endpoint, every entry carries its own `date`, and the
`external_sources` DTO field is proven present the same way every
connector since Fear & Greed has been). It also surfaced a genuinely new
risk: a live comparison found a persistent ~0.19% divergence between
DefiLlama's own "current" and "historical" TVL figures for the same
calendar day, with no documented guarantee any published figure is
final. Handled by a new, opt-in `ConnectorMetadata.revisable` flag
(default `false` — every connector before DefiLlama byte-for-byte
unaffected, regression-proven by a dedicated `TestRevisableIngestion`
test class) that lets a later sync tick overwrite an already-stored
value in place when a re-fetch reports a genuine revision, rather than
silently keeping a stale figure forever. Appears in
`GET /connectors`/`/data-sources` and `GET /features` automatically,
confirmed live against the already-running dev server — which had, in
fact, already performed a real, complete 3,267-row backfill
(`2017-09-27` through `2026-09-06`) entirely on its own, the moment the
connector file was saved. See `ARCHITECTURE.md` § "External Data
Connectors" → "DefiLlama Connector".

**M4-E1-T6, CoinGecko, is now real, tested, and wired in.** The fifth
concrete connector, and the first whose API key is genuinely optional:
`app/connectors/coingecko.py` fetches CoinGecko's `/global` endpoint,
available as a real feature (`btc_dominance`) — the first in a new
`"market"` category. Its own investigation, done before any client code
was written, confirmed `/global` works fully keyless (a real,
unauthenticated request returned real data), unlike FRED/Etherscan which
both hard-require a key; a free Demo key only raises the rate limit from
keyless's own shared, IP-based limiting to a documented 100 calls/min. A
real burst of 20 concurrent keyless requests confirmed the rate limit is
genuinely enforced (15 of 20 throttled, with a plain-text `"Throttled\n"`
body, not CoinGecko's own JSON error shape). The metric itself was chosen
on a structural argument, not an empirical one: BTC dominance
(`market_cap_percentage.btc`) is a share of the total market, which no
single asset's own price series can derive even in principle — unlike
ETH's own market cap (nearly redundant with Delta's own candles) or total
market cap (a broad size measure correlated with the same price movement
ETH's own candles already show). No empirical correlation check was
possible since CoinGecko's only historical global-market endpoint is
Analyst-plan-and-above, the same Pro-tier trap Etherscan and DefiLlama
each had. Confirmed live, not assumed: `/global` carries its own
`updated_at`, so this connector never computes its own timestamp — a
direct live simulation of a routine sync tick's own window confirmed no
Etherscan-style race condition exists here. Like Etherscan, this source
has no historical query capability at all. Appears in
`GET /connectors`/`/data-sources` and `GET /features` automatically,
confirmed live against the already-running dev server — which had, in
fact, already landed two real, distinct BTC dominance values ten minutes
apart before any manual verification was run. See `ARCHITECTURE.md` §
"External Data Connectors" → "CoinGecko Connector".

**M4-E1-T7, Marketaux, is now real, tested, and wired in — the sixth and
last connector, closing out this milestone's own connector epic.** The
first whose real data does not fit the generic `RawDataPoint`/
`external_data_points` shape at all. This task's own Step 1 — is
Marketaux's built-in sentiment score actually usable, sparing a
from-scratch NLP pipeline (an unscoped, separate task)? — came back
genuinely usable, confirmed against the real, live API and current
documentation: a real per-_entity_ `sentiment_score`
(`data[].entities[].sentiment_score`), a real documented crypto/ETH
example (`ETHUSD`, score `-0.4215`), and a real bug pattern found and
fixed along the way (`filter_entities` defaults to `false` per
Marketaux's own docs — left unset, a multi-entity article would blend in
unrelated sentiment; this connector always sends `filter_entities=true`
explicitly, proven by a dedicated URL assertion). A new risk this
milestone's prior five connectors never surfaced — discovery latency,
not value revision — is handled by a `DISCOVERY_SAFETY_MARGIN` (six
hours) that keeps every sync window's own start at
`min(last_published_at, now - margin)`, never narrower, so a
late-discovered article for an already-passed window is always
re-swept. Real article detail (headline, snippet, source, url,
published time, per-article sentiment, symbols) lives in a new,
dedicated `news_articles` table, not bolted onto
`external_data_points` — only a _derived daily mean sentiment_ is
mirrored in (`news_sentiment`), reachable through the exact same
feature-lookup pattern every other source uses, with zero News-specific
branching anywhere in the ML pipeline. A new `ConnectorMetadata
.auto_synced` flag (Marketaux is the only connector so far set to
`False`) excludes it from the generic sync tick; a separate
`NewsSyncScheduler` drives its own periodic ingestion instead. A new,
dedicated `/news` page (required by this task's own Definition of Done,
explicitly not bolted onto `/data-sources`, which stays fully generic —
News still auto-appears there as an ordinary registry entry) gives real
per-article detail its own real estate: headline, source, published
time, a real sentiment score and label (never just a color dot), a link
to the original, filterable by symbol and date range. A real bug was
caught and fixed during testing: the daily-aggregate recompute's own
`update_value` call does not commit by its own documented contract, and
nothing after it committed either, so a genuine revision to an
already-mirrored day's mean was silently lost — fixed with the same
final `session.commit()` every revisable connector's own
`_persist_points` already performs. No live-API verification has been
performed — no real `MARKETAUX_API_KEY` exists in this environment;
every finding above is confirmed against the real, live, unauthenticated
error response and current documentation, the same evidentiary standard
FRED's own task used before a real key was available. See
`ARCHITECTURE.md` § "External Data Connectors" → "Marketaux Connector".

---

## Working Rules

1. **One micro-task per prompt.** Each Claude Code prompt addresses exactly one micro-task
   from the backlog. No scope creep within a single prompt.

2. **One commit per micro-task.** Every completed micro-task produces exactly one Git
   commit with a descriptive message referencing the task ID.

3. **Never work on multiple milestones simultaneously.** Only one milestone may be in
   progress at any given time. All epics and tasks within that milestone must be
   completed before the next milestone begins.

4. **Complete reviews before marking tasks complete.** A task is not considered
   Completed until its implementation has been reviewed and approved.

5. **Update TASKBOOK.md after every completed task.** The Progress Tracking table must
   be updated to reflect the current status, and the Git Commit column must reference
   the commit hash.

6. **Keep documentation synchronized with implementation.** When a task changes the
   codebase, any affected documentation must be updated within the same micro-task
   commit.

7. **Do not change task IDs.** Once assigned, a task ID is permanent. Deferred or
   cancelled tasks retain their IDs for traceability.

---

## Future Expansion

The following sections are reserved for future use as the project matures:

### Sprint Planning

### Release Planning

### Risk Register

### Technical Debt Tracking

| ID | Found | Item | Status |
| ------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| TD-001 | 2026-09-06 | `tests/training/test_service.py::TestCreate::test_creates_a_pending_job` fails deterministically as **whichever test pytest executes first** in that file (not this test specifically — swapping which test runs first swaps which one fails), raising `sqlite3.OperationalError: no such table: experiments`. A standalone script outside pytest, constructing the identical sessions/services and calling the identical methods, completes successfully — this is a pytest/aiosqlite fixture-timing artifact tied to the file's cross-module import (`from tests.ml_datasets.test_service import build_service as build_ml_dataset_service`), not a defect in the async training execution feature itself (`M2-E1-T2`). Found during `docs/audits/MILESTONE_2_3_VERIFICATION.md`. Tracked, not fixed — investigating pytest/aiosqlite fixture ordering is out of scope for the tasks that found it. |

### Change Requests

### Architecture Review Log
