# AI Pipeline — Testing Guide (Real Values, Step by Step)

## Document Information

**Document:** How to actually test Feature Engineering, Dataset Validation, the ML
Dataset Builder (with Dataset History), Experiment Management, and the ML Training
Framework — automated commands and full manual walkthroughs, every value real.

**Status:** Current as of 2026-08-28.

**For how these systems actually work** (the logic, backend/frontend split,
dependencies, and known gaps) **see `ARCHITECTURE.md`, `docs/ai/AI.md`, and
`docs/api/API.md`** — this document is testing only, deliberately not a duplicate of
those.

**Prerequisites for everything below**: Postgres running with the market catalogue
and candles already synced (`ETHUSD`/`BTCUSD` at minimum — §6 below shows exactly how
to populate this from the real Delta Exchange API), the API running
(`uv run fastapi dev app/main.py` from `services/api`), and the dashboard running
(`pnpm dev` from `apps/dashboard`, default `http://localhost:3000`).

---

## 1. Automated tests, per subsystem

### Feature Engineering (`/features`)

```bash
cd services/api
uv run pytest tests/features/ tests/api/test_features_api.py -v
uv run pytest tests/features/ tests/api/test_features_api.py --cov=app.features --cov=app.services.features --cov-report=term-missing
```

Key files: `tests/features/test_registry.py`, `test_pipeline.py`, `test_dataset.py`
(warmup/partial-success/collision logic), `test_service.py` (real-candle integration),
`test_export.py`, `tests/api/test_features_api.py` (HTTP layer).

```bash
cd apps/dashboard
pnpm test -- --run src/features/feature-engineering
```

Key files: `feature-engineering-page.test.tsx`, `dataset-form.test.tsx`,
`feature-selector.test.tsx`, `dataset-preview-table.test.tsx`.

### Dataset Validation (`/validation`)

```bash
cd services/api
uv run pytest tests/dataset_validation/ tests/api/test_dataset_validation_api.py -v
```

Key files: one test file per rule category (`test_rules_structural.py`,
`test_rules_data_quality.py`, `test_rules_time_series.py`, `test_rules_feature.py`),
`test_engine.py`, `test_registry.py`, `test_builtin_discovery.py`, `test_service.py`,
`tests/api/test_dataset_validation_api.py` (a clean dataset and intentionally
corrupted ones over real stored candles).

```bash
cd apps/dashboard
pnpm test -- --run src/features/dataset-validation
```

Key files: `dataset-validation-page.test.tsx`, `validation-report-panel.test.tsx`,
`validation-summary-cards.test.tsx`, `required-columns-selector.test.tsx`,
`quality-score.test.ts`.

### ML Dataset Builder + Dataset History (`/ml-datasets`)

```bash
cd services/api
uv run pytest tests/ml_datasets/ tests/api/test_ml_datasets_api.py -v
uv run pytest tests/ml_datasets/ tests/api/test_ml_datasets_api.py --cov=app.ml_datasets --cov=app.services.ml_datasets --cov=app.repositories.ml_dataset_builds --cov=app.models.ml_dataset_build --cov-report=term-missing
```

Key files: `test_dataset.py` (assembly/leakage/partial-success), `test_split.py`,
`test_targets.py`, `test_export.py`, `test_service.py`'s `TestDatasetHistory` class
(persistence, list/get/delete, that `build_ml_dataset`/`export_dataset` do **not** add
to history), `tests/api/test_ml_datasets_api.py`'s `TestDatasetHistoryEndpoints` class.

```bash
cd apps/dashboard
pnpm test -- --run src/features/ml-datasets
```

Key files: `ml-datasets-page.test.tsx` (its `Dataset History` describe block covers
listing/reopening/deleting/appearing-after-build), `dataset-history-table.test.tsx`,
`dataset-history-detail-dialog.test.tsx`, `target-selector.test.tsx`,
`split-config-form.test.tsx`.

### Experiment Management (`/experiments`)

```bash
cd services/api
uv run pytest tests/experiments/ tests/api/test_experiments_api.py -v
```

Key files: `tests/experiments/test_repository.py`, `test_service.py`,
`tests/api/test_experiments_api.py` (CRUD, tag replace/dedup, cascade-on-delete,
search/filter/sort/pagination against real SQL).

```bash
cd apps/dashboard
pnpm test -- --run src/features/experiments
```

Key files: `experiments-page.test.tsx`, `experiment-detail-page.test.tsx`,
`experiment-metrics-table.test.tsx`, `experiment-artifacts-list.test.tsx`,
`delete-experiment-dialog.test.tsx`.

### ML Training Framework + Baseline Model Framework (`/ml/training`)

```bash
cd services/api
uv run pytest tests/training/ tests/api/test_training_api.py -v
uv run pytest tests/training/ tests/api/test_training_api.py --cov=app.training --cov=app.services.training --cov=app.schemas.training --cov-report=term-missing
```

Key files: `test_pipeline.py`, `test_registry.py`, `test_state_machine.py`,
`test_serialization.py`, `test_dataset_loader.py`, `test_logistic_regression.py`,
`test_linear_regression.py`, `test_placeholder_adapter.py`, `test_interpretability.py`,
`test_model_metadata.py`, `test_artifact_files.py`, `test_error_reporting.py`,
`test_service.py` (real end-to-end training over seeded candles, in
`TestRealDataTraining`/`TestPredict`/`TestArtifacts`), `tests/api/test_training_api.py`.

```bash
cd apps/dashboard
pnpm test -- --run src/features/ml-training
```

Key files: `ml-training-page.test.tsx` (full create/run/cancel/delete/evaluation
flows), `hyperparameter-editor.test.tsx`, `evaluation-summary.test.tsx`,
`feature-importance-panel.test.tsx`, `roc-pr-curve-charts.test.tsx`,
`confusion-matrix-details-table.test.tsx`, `train-val-test-metrics-table.test.tsx`,
`prediction-samples-table.test.tsx`, `model-metadata-panel.test.tsx`,
`training-artifacts-panel.test.tsx`.

### Everything at once

```bash
# Backend — every subsystem above, one command
cd services/api
uv run pytest tests/features/ tests/dataset_validation/ tests/ml_datasets/ \
  tests/experiments/ tests/training/ \
  tests/api/test_features_api.py tests/api/test_dataset_validation_api.py \
  tests/api/test_ml_datasets_api.py tests/api/test_experiments_api.py \
  tests/api/test_training_api.py --cov=app --cov-report=term-missing

# Frontend — the same five feature areas
cd apps/dashboard
pnpm test -- --run src/features/feature-engineering src/features/dataset-validation \
  src/features/ml-datasets src/features/experiments src/features/ml-training

# Whole-repo gates, either side
cd services/api && uv run ruff check . && uv run ruff format --check .
cd apps/dashboard && pnpm lint && pnpm typecheck && pnpm build
```

---

## 2. End-to-end manual test scenarios — real values, step by step

These are full walkthroughs through the running app, not command references — each
one starts from nothing and ends with a specific, checkable outcome. Run them in
order; each later scenario reuses what an earlier one produced. Every value below is
real — type it verbatim, nothing here is a placeholder.

### Scenario A — Build a feature dataset and read its own honesty report

**Goal**: see the Feature Engineering Engine turn real candles into a numeric matrix,
and see it tell you the truth about what it had to drop.

1. Open `/features`. In **Market**, type `ETH` and pick **ETHUSD**. **Timeframe**
   becomes selectable — pick `1h`. **Range** — pick **Last 30 Days**.
2. In the feature list, check **OHLCV** and **SMA** (leave `period` at its default,
   `20`, and `source` at `close`).
3. Click **Build Dataset**.
4. **What you should see**: a preview table with columns `open, high, low, close,
volume, sma_20`, and — because `sma_20` needs 20 candles of history before its
   first value exists — a caption reading something like _"20 rows dropped
   (warmup)"_. The row count in the preview footer should be `(30 days × 24 candles)
− 20`, e.g. `720 − 20 = 700` rows if the range landed on exactly 30 daily buckets.
5. Open your browser's Network tab, find the `POST .../features/dataset` request, and
   confirm the response's `meta.rows_dropped` field is exactly `20` and
   `meta.warmup_candles` is `20` — the UI caption and this field must always agree.
6. Click **Export → CSV**. Open the downloaded file — its row count must be the
   **full** un-truncated dataset (up to 500, per the `limit` you set), never just the
   on-screen preview cap of 200.

### Scenario B — Make Dataset Validation actually fail, on purpose

**Goal**: see a validation rule fire for a real reason, not just a happy-path pass.

1. Open `/validation`. Pick `ETHUSD` / `1h` / **Last 30 Days** again.
2. Check **OHLCV** only (skip SMA this time).
3. In **Required Columns**, use `freeSolo` to type a column that does **not** exist —
   e.g. `rsi_14` — and press Enter to add it as a chip alongside `close`.
4. Click **Run Validation**.
5. **What you should see**: the summary card shows **Failed** (red), with at least
   **1 error**. Open the Validation Report — you should find one issue with
   `rule: "required_columns"`, `code: "missing_required_column"`,
   `column: "rsi_14"`, and a message naming the missing column explicitly. The
   Quality Score (a client-side heuristic) should read `85` (100 − 15 for that one
   error).
6. Remove the `rsi_14` chip, keep `close`, click **Run Validation** again — now it
   should pass.

### Scenario C — The full pipeline: build → validate → cite → train → evaluate

**Goal**: walk one real classifier from raw candles to a confusion matrix.

1. **Build the ML dataset.** Open `/ml-datasets`. Pick `ETHUSD` / `1h` / **Last 30
   Days**. Features: **OHLCV** + **SMA** (`period=20`). Targets: search and pick
   **Next Direction (Classification)**, leave horizon at `1`. Split: leave
   `0.7` / `0.15` / `0.15`. Click **Build ML Dataset**.
   - **Check**: the Validation Summary embedded in this page should say **Passed**.
   - **Copy the `ml_dataset_id`** shown in the ML Dataset Information card — it looks
     like `b6f1c2a4-8e3d-4a1b-9c7f-2d5e6a8b9c0d`. You'll paste this in step 2.
   - Scroll to **Dataset History** — this exact build should be the top row, with a
     green **Passed** chip.
2. **Record an Experiment.** Open `/experiments` → **New Experiment**:
   - Name: `ETHUSD 1h next_direction baseline`
   - Dataset version: paste the `ml_dataset_id` from step 1
   - Model type: `logistic_regression`
   - Status: `draft`
   - Tags: `baseline`, `classification`
   - Click **Create**.
   - Open the created Experiment's detail page and set its `feature_set`/
     `target_config` (via `PATCH /experiments/{id}` if the UI doesn't expose this
     directly yet) to:
     `feature_set: [{"feature":"ohlcv","params":{}},{"feature":"sma","params":{"period":"20"}}]`,
     `target_config: [{"target":"next_direction","params":{"horizon":"1"}}]` — a real
     Training Job needs these to actually rebuild the matrix in step 3.
3. **Register and run the Training Job.** Open `/ml/training` → **New Training Job**:
   - Experiment: `ETHUSD 1h next_direction baseline`
   - Model type: **Logistic Regression (Baseline)** — the Configuration panel appears
   - Symbol: `ETHUSD`, Timeframe: `1h`, Target column: leave blank
   - Leave hyperparameters at their defaults; add two custom entries (no dedicated
     field for these yet): key `max_iter` value `200`, key `C` value `1.0`
   - Click **Create Training Job**, then open it and click **Run**.
4. **Check the outcome.** The 8-step timeline should reach **Completed** within a
   second or two (no worker/queue — it's a blocking, fast call). You should see:
   - A **Metrics** table with real, non-fabricated `accuracy`/`precision`/`recall`/`f1`
     — a healthy value here is anywhere from `0.4`–`0.7` on 30 days of real hourly
     data with one weak feature; don't expect `0.9+`.
   - A **Confusion Matrix** whose rows sum to the validation split's row count.
   - **Train / Validation / Test Metrics** — if Train accuracy is far above
     Validation/Test (e.g. `0.95` vs `0.55`), the **overfitting banner** should appear.
   - **Feature Importance** — 6 rows (`open`, `high`, `low`, `close`, `volume`,
     `sma_20`), ranked by `abs_importance`.
   - **ROC & PR curves** with a real AUC per class (`up`/`down`/`flat`).
5. **Confirm the write-back.** Return to the Experiment's detail page — its Status
   should now be `completed`, its Metrics table should have the same
   `accuracy`/`precision`/`recall`/`f1` values you just saw, and its Artifacts list
   should include a `model_checkpoint` plus several `report`/`plot` entries.
6. **Download an artifact.** Back on the Training Job's detail dialog, click
   `feature_importance.csv` in Downloadable Artifacts — the file should open with a
   header row `feature,coefficient,abs_importance,sign` and real numbers.

### Scenario D — A regression baseline, and reopening it later via Dataset History

**Goal**: prove Dataset History actually reopens the exact dataset, not a re-fetch.

1. Repeat Scenario C step 1, but pick **Next Close Price** as the target instead of
   Next Direction (still horizon `1`).
2. Note the row count and the first two `Timestamp` values in the preview table.
3. Go to **Dataset History**, open the entry you just built, and confirm the preview
   table shows the **identical** row count and the same first two timestamps —
   nothing was re-fetched from candles to render this dialog.
4. Create an Experiment citing this build's `ml_dataset_id`, `model_type:
linear_regression`, and a Training Job with Model type **Linear Regression
   (Baseline)**, Target column `next_close_1`.
5. Run it. Expect `mae`/`mse`/`rmse`/`r2` instead of a confusion matrix, and no
   ROC/PR section (regression has neither).
6. In Dataset History, click the delete icon on this build, confirm — it should
   disappear from the list, but the Training Job you already ran is unaffected (its
   `result_summary` was copied at run time, not linked live).

### Scenario E — Predict with a completed model

**Goal**: exercise `POST /training-jobs/{id}/predict` directly (no frontend page calls
this outside the evaluation view's own sample table).

Using the completed classification job from Scenario C (find its id in the Network
tab or the URL when its detail dialog is open):

```bash
curl -s -X POST http://localhost:8000/api/v1/training-jobs/<job-id>/predict \
  -H 'Content-Type: application/json' \
  -d '{"rows": [[3055.25, 3061.0, 3050.1, 3058.75, 812.4, 3050.0]]}' | python3 -m json.tool
```

(Six values because that job's `feature_columns` was `open, high, low, close, volume,
sma_20` — check the job's own `result_summary.feature_columns` first; a row with the
wrong length gets a `400 invalid_prediction_input`, not a silent misalignment.)

**Expected response shape**:

```text
predictions: ["up"]                      # one label per input row
classes: ["down", "flat", "up"]
probabilities: [[0.18, 0.21, 0.61]]      # aligned with classes, sums to ~1.0
confidence_levels: ["medium"]            # 0.61 falls in [0.5, 0.7)
```

Try it again with a completed **regression** job's id and a matching row length —
expect `probabilities`/`confidence_levels`/`classes` to all be `null`, and
`predictions` to hold one real numeric value (a predicted price), never a fabricated
one.

---

## 3. Importing real historical data (Delta Exchange REST API)

This platform ships with a market catalogue sync and a candle ingestion service that
both hit Delta Exchange India's real, live REST API — nothing here is simulated.

**Sync the market catalogue** (idempotent — safe to re-run any time):

```bash
cd services/api
uv run python scripts/sync_markets.py
```

This upserts every product Delta currently lists (as of this writing, 225 perpetual
markets) into `exchanges`/`markets`, including each market's own `listing_date` — the
earliest a `candles` row for it could possibly exist.

**Backfill full history for one symbol/timeframe** (idempotent — the
`(market_id, timeframe, open_time)` unique constraint means re-running never
duplicates a row, it just reports `duplicates_skipped`):

```bash
uv run python scripts/ingest_candles.py \
  --symbol ETHUSD --timeframe 1h --start 2024-02-05 --end 2026-08-28
```

Use each market's own `listing_date` (from the sync above) as `--start` to import
everything Delta actually has — requesting further back than a market's real history
simply returns fewer candles, never an error. Repeat once per `(symbol, timeframe)`
pair you need.

**A real timing note from actually running this**: the ingest script fetches every
window first, then persists the whole batch in one pass — for a coarse timeframe
(`1d`, `4h`, `1h`, `30m`, `15m`) over 2+ years this is seconds to a few minutes per
symbol; for `5m` it's roughly 10 minutes per symbol, and for `1m` roughly 45–60
minutes per symbol (millions of rows). Run `1m`/`5m` one symbol at a time, and expect
it to take real wall-clock time — don't run it inside a command with a short timeout,
and don't run two ingests for the same symbol concurrently.

**Ongoing catch-up** (bounded, recent-only — not a backfill):

```bash
uv run python scripts/sync_candles.py --symbols ETHUSD,BTCUSD --timeframes 1h,1d
```

Mirrors what `CandleSyncScheduler` already does automatically every
`candle_sync_interval_seconds` (default 300s) when `MARKET_DATA_LIVE=true`.

**Migrations.** Check pending migrations before and after any data work:

```bash
uv run alembic current   # what's actually applied
uv run alembic heads     # what the codebase expects
uv run alembic upgrade head   # apply anything missing
```

Importing candle _data_ never requires a migration on its own (the schema doesn't
change) — only a code change that adds/alters a table does. Run this simply as a
sanity check any time you're about to rely on a fresh checkout.

**Verify what actually landed**, per symbol/timeframe, real SQL:

```sql
select symbol, timeframe, count(*), min(open_time), max(open_time)
from candles c join markets m on m.id = c.market_id
where m.symbol in ('BTCUSD', 'ETHUSD')
group by symbol, timeframe
order by symbol, timeframe;
```
