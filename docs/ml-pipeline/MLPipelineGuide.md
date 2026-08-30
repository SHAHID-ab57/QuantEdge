# AI Pipeline — Testing Guide (Real Values, Step by Step)

## Document Information

**Document:** How to actually test Feature Engineering, Dataset Validation, the ML
Dataset Builder (with Dataset History), Experiment Management, the ML Training
Framework, and the Model Evaluation & Benchmarking Engine (with Benchmark History) —
automated commands, full manual walkthroughs with real values on every screen, and
what each of these six systems is honestly still missing.

**Status:** Current as of 2026-08-29. Written to be self-contained — everything you
need to test this platform and know its real limitations is in this one file, nothing
here assumes you can also open `ARCHITECTURE.md`/`docs/ai/AI.md`/`docs/api/API.md`.

**Prerequisites for everything below**: Postgres running with the market catalogue
and candles already synced (`ETHUSD`/`BTCUSD` at minimum — §4 below shows exactly how
to populate this from the real Delta Exchange API), the API running
(`uv run fastapi dev app/main.py` from `services/api`), and the dashboard running
(`pnpm dev` from `apps/dashboard`, default `http://localhost:3000`).

**Sections**: §1 automated test commands per subsystem · §2 manual walkthroughs with
real values (Scenarios A–F) · §3 known gaps / missing scope, per feature · §4
importing real historical market data.

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

### Model Evaluation & Benchmarking Engine + Benchmark History (`/ml/evaluation`)

```bash
cd services/api
uv run pytest tests/evaluation/ tests/api/test_evaluation_api.py -v
uv run pytest tests/evaluation/ tests/api/test_evaluation_api.py --cov=app.evaluation --cov=app.services.evaluation --cov=app.repositories.evaluation_benchmark_runs --cov=app.models.evaluation_benchmark_run --cov-report=term-missing
```

Key files: `test_metrics.py` (every builtin metric's math), `test_registry.py`,
`test_engine.py` (skip-on-no-probabilities, skip-on-exception), `test_benchmark.py`
(`compare`'s winner-picking), `test_service.py` (real end-to-end `benchmark()` over
seeded `TrainingJob` rows, 3–4 experiments at once, every `BenchmarkCandidate` field,
and the full Benchmark History list/get/delete/best-effort-persist flow),
`tests/api/test_evaluation_api.py` (the same over real HTTP, plus history endpoints).

```bash
cd apps/dashboard
pnpm test -- --run src/features/ml-evaluation
```

Key files: `ml-evaluation-page.test.tsx` (empty state, metric catalogue, a full
benchmark run, an `empty_benchmark` info message), `benchmark-filters-bar.test.tsx`,
`benchmark-comparison-table.test.tsx` (ranking both directions, deep links, artifact
link presence/absence), `best-model-summary.test.tsx`, `metric-comparison-chart.test.tsx`,
`metric-selector.test.tsx`, `dataset-summary-card.test.tsx`,
`candidate-detail-dialog.test.tsx`, `benchmark-export-menu.test.tsx`,
`benchmark-history-table.test.tsx`, `metric-catalog-panel.test.tsx`,
`lib/benchmark-export.test.ts`, `lib/model-kind.test.ts`.

### Everything at once

```bash
# Backend — every subsystem above, one command
cd services/api
uv run pytest tests/features/ tests/dataset_validation/ tests/ml_datasets/ \
  tests/experiments/ tests/training/ tests/evaluation/ \
  tests/api/test_features_api.py tests/api/test_dataset_validation_api.py \
  tests/api/test_ml_datasets_api.py tests/api/test_experiments_api.py \
  tests/api/test_training_api.py tests/api/test_evaluation_api.py \
  --cov=app --cov-report=term-missing

# Frontend — the same six feature areas
cd apps/dashboard
pnpm test -- --run src/features/feature-engineering src/features/dataset-validation \
  src/features/ml-datasets src/features/experiments src/features/ml-training \
  src/features/ml-evaluation

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

### Scenario F — Benchmark two models against each other, then reopen it from history

**Goal**: use the Model Evaluation & Benchmarking Engine to answer "which model
actually performs better," exercise every field on `/ml/evaluation`, and prove
Benchmark History reopens an exact past comparison rather than re-querying.

This scenario reuses the completed classification job from **Scenario C** — you need
its `ml_dataset_id` (copied in Scenario C step 1) and its Experiment (`ETHUSD 1h
next_direction baseline`).

1. **Create a second Training Job to compare against the first.** Open `/ml/training`
   → **New Training Job**:
   - Experiment: `ETHUSD 1h next_direction baseline` (the same one from Scenario C)
   - Model type: **Logistic Regression (Baseline)**
   - Symbol: `ETHUSD`, Timeframe: `1h`, Target column: leave blank
   - Dataset Version: paste the same `ml_dataset_id` from Scenario C step 1 (so both
     jobs are directly comparable — same rows, same split)
   - Custom hyperparameter: key `C` value `0.1` (Scenario C's job used `C=1.0` — a
     stronger regularization penalty here should move accuracy a little, giving you
     two genuinely different results to compare, not two identical rows)
   - Click **Create Training Job**, open it, click **Run** — wait for **Completed**.
2. **Open the comparison page.** Go to `/ml/evaluation`.
3. **Fill in the filter bar** (`Benchmark Comparison` section):
   - **Dataset version**: paste the `ml_dataset_id` from Scenario C step 1 (e.g.
     `b6f1c2a4-8e3d-4a1b-9c7f-2d5e6a8b9c0d`) — this is a `freeSolo` field, so typing it
     verbatim is enough, no dropdown selection required.
   - **Target column**: leave blank (neither job has one explicitly recorded — see §3
     "ML Training Framework" gap below on why this is an easy field to leave empty and
     still get a correct comparison).
   - **Experiments**: leave empty (dataset version alone already narrows to exactly
     these two jobs).
   - Click **Compare**.
4. **What you should see**: the page shows two Best Model Summary cards (one for
   `accuracy`, one for each other metric both jobs recorded — `precision`, `recall`,
   `f1`, `roc_auc`), each naming the winning `logistic_regression` run and its value
   (e.g. `accuracy: 0.6200`), with a small green up-arrow next to each (all these
   metrics are "higher is better"). Below that, the **Model Comparison** table has
   exactly 2 rows, one column per metric, the winning cell in each metric column
   bolded and green.
5. **Rank by a specific metric.** In the **Rank by metric** dropdown (top of the
   table), select `accuracy`. **What changes**: a new **Rank** column appears on the
   left (`1`, `2`), the higher-accuracy row moves to rank `1`, and the row order in the
   table now matches that ranking rather than "most recently completed first."
6. **Open one row's full detail.** Click the ⓘ ("View details") icon on the rank-`1`
   row. **What you should see** in the dialog that opens:
   - A **Dataset Summary** card: Dataset Version = the `ml_dataset_id` you typed,
     Symbol = `ETHUSD`, Timeframe = `1h`, Dataset Size = e.g. `700 rows`, Feature Count
     = `6`, Target Column = `—` (blank, since neither job set one explicitly).
   - Below it, the exact same evaluation view Scenario C step 4 already showed for
     this job — Metrics table, raw Confusion Matrix grid, Confusion Matrix Details
     (per-class TP/FP/TN/FN/Support), Train/Validation/Test Metrics, **ROC & PR
     curves**, Feature Importance, Prediction Samples, Model Metadata — nothing
     recomputed, this is the identical data Scenario C already produced.
   - Three buttons above that: **Open Experiment** (opens `/experiments/{id}` in a new
     tab — the Experiment detail page), **Open Training Job** (opens
     `/ml/training?jobId=<that job's id>` in a new tab, which auto-opens that exact
     job's detail dialog on load, no manual click needed), and **Download Model
     Artifact** (downloads `model.joblib` directly — a real, loadable scikit-learn
     pickle, not a placeholder file).
   - Close the dialog.
7. **Export the comparison.** Click **Export** (top of the table area) → **Export
   CSV**. Open the downloaded `benchmark-<sanitized-dataset-version>.csv` — it should
   have a `Best accuracy,...` metadata line per metric near the top, then this header
   row (exact metric column order may vary — it's alphabetical), then exactly 2 data
   rows:

   ```text
   Training Job ID,Experiment,Model Type,Model Kind,Dataset Version,Target Column,Symbol,Timeframe,Completed At,accuracy,f1,precision,recall,roc_auc
   ```

   Repeat with **Export JSON** — the downloaded file should be the identical response
   body you'd get from `POST /api/v1/evaluation/benchmark` with the same request.

8. **Check Benchmark History.** Scroll down to the **Benchmark History** section — the
   comparison you just ran should be the top row: Dataset Version = your
   `ml_dataset_id`, Target Column = `—`, Candidates = `2`, Compared = just now.
9. **Reopen it.** Click the ↺ ("Reopen") icon on that row. **What you should see**: a
   blue info banner reading _"Viewing a reopened comparison from Benchmark History,"_
   the filter bar's Dataset Version field repopulated with the same `ml_dataset_id`
   automatically, and the exact same 2-row table/summary/charts as step 4 — reloaded
   from the persisted response, not a fresh query (you can prove this to yourself by
   stopping the API server first, then clicking Reopen again — it still works, because
   `GET /evaluation/history/{id}` only reads the `evaluation_benchmark_runs` table,
   never `TrainingJob` rows).
10. **Delete it.** Click the 🗑 ("Delete") icon on the same row — a confirm dialog
    reading _"Remove this benchmark run? This only removes the persisted comparison
    from Benchmark History — the underlying training jobs are untouched."_ appears.
    Confirm. **What you should see**: the row disappears from Benchmark History, but
    both Training Jobs are completely unaffected — reopen `/ml/training` and confirm
    both still show **Completed** with their full result summaries intact.
11. **Check the Available Metrics reference table.** Scroll to the bottom **Available
    Metrics** section. Find the `accuracy` row under **Classification metrics**: it
    should show a `classification` Category chip, an up-arrow with the text "Higher is
    better," and "No" under Requires probabilities. Find `roc_auc` in the same table —
    same Category chip, "Higher is better," but "Yes" under Requires probabilities
    (this is the one metric that needs `predict_proba`, which is why it doesn't appear
    at all for a job whose adapter has none — `linear_regression` never shows
    `roc_auc`). Find `rmse` under **Regression metrics** — it should show a down-arrow
    and the text "Lower is better."

---

## 3. Known gaps / missing scope — per feature

Every gap below is real and current, not a guess — each one reflects what the actual
code does today, not what a future milestone intends. If you're testing this platform
and something doesn't do what you'd expect, check here first before assuming a bug.

### Feature Engineering (`/features`)

- Only 8 generators exist today: `ohlcv`, `candle_shape`, `sma`, `ema`, `wma`, and
  `rsi` (via the indicator-wrapping bridge) — no MACD, Bollinger Bands, ATR, or any
  volume-derived feature beyond raw `volume` itself.
- No sequence windowing (`WindowSpec`/`SequenceWindower` — turning a feature matrix
  into fixed-size, strided windows for an LSTM/Transformer-style model) — every
  feature row today is a single flat timestep, never a sequence.
- No per-column normalization/scaling (`NormalizationStats`/`FeatureNormalizer`) — a
  model adapter that needs standardized inputs must do this itself; the platform
  hands it raw values (e.g. `close` in the thousands, `sma_20` similarly, unscaled).
- No categorical encoding (`CategoricalEncoding`/`CategoricalEncoder`) — a feature
  that produces a `"categorical"`-dtype column (none of the 8 built-in ones do today)
  would need manual one-hot/ordinal encoding downstream; nothing does this
  automatically yet.
- These three are documented, typed `Protocol`/`dataclass` pairs in
  `app/features/ai_extensions.py` with **no implementer** — a future feature can
  satisfy them, but nothing in the running system does yet.

### Dataset Validation & Quality Engine (`/validation`)

- Validation rules exist for structural issues, data-quality issues (nulls,
  duplicates), time-series issues (gaps, ordering), and feature-specific checks — but
  there is no statistical/outlier-detection rule category (e.g. flagging a candle
  whose price moved 50 standard deviations in one bar).
- The Quality Score shown in the frontend is a **client-side heuristic**
  (`100 − 15 per error − 5 per warning`, floored at `0`) — it is not returned by the
  backend and does not factor into any pass/fail decision; only `validation.passed`
  (a real boolean from the backend) does.
- There is no per-`dataset_version` persisted "was this validated" flag — validating
  a dataset and then citing that same `dataset_version` in a Training Job later
  re-validates nothing; the platform trusts the citation.

### ML Dataset Builder + Dataset History (`/ml-datasets`)

- The builder itself still stores nothing durable per build — only **Dataset
  History** (a separate, additive table) persists a build, and only when triggered by
  an explicit "Build ML Dataset" click on `/ml-datasets` itself; a Training Job's
  internal reuse of the same builder (to load real training data) does **not** add a
  new Dataset History entry, and neither does a CSV/JSON re-export of an
  already-built dataset.
- Dataset History stores the **entire** built matrix (every row, verbatim) in one
  JSON column, which only stays cheap because every build is already row-capped at
  1000 rows (`Settings.candles_max_limit`) — this would not scale to a 100k-row
  dataset without first moving that payload to object storage, which hasn't been
  built.
- Only chronological (never random) train/validation/test splitting exists —
  intentional, to avoid leaking future information into training, but there is no
  k-fold cross-validation option anywhere on this platform.

### Experiment Management (`/experiments`)

- An Experiment's `dataset_version` field is an **intentionally uninterpreted
  citation string** — the platform never validates that the string you type actually
  corresponds to a real Dataset History entry, a real `ml_dataset_id`, or anything at
  all. Typing `"whatever-i-want"` is accepted silently; only a Training Job that
  later tries to load real data from it would fail (with a clear error), not the
  Experiment itself.
- `feature_set`/`target_config`/`split_config` currently have **no dedicated frontend
  form** to set on creation or edit — the `/experiments` UI creates an Experiment with
  just name/dataset_version/model_type/status/tags/notes; setting the three JSON
  config fields today requires a direct `PATCH /experiments/{id}` call (curl or the
  API docs at `/docs`), not a page you click through. This is exactly why Scenario C
  step 2 above tells you to do this via `PATCH`, not the UI.

### Machine Learning Training Framework (`/ml/training`)

- Every training run is **synchronous and blocking** — `POST /training-jobs/{id}/run`
  does not return until the (small, fast) job finishes. There is no worker/queue
  service, so a training job that took minutes instead of milliseconds would hold the
  HTTP connection open the whole time; nothing on this platform handles that today.
- `TrainingJob.target_column` is only ever set when you **explicitly type one** into
  the "Target column" field at job-creation time — leaving it blank does not mean
  "undefined," it means the job's own `target_column` column stays `NULL` in the
  database forever, even though the pipeline itself still resolved and used a real
  target (defaulting to the first one the dataset builder produced) to actually
  train. This is a legible, not a fabricated, gap: `GET /training-jobs/{id}` will
  honestly show `"target_column": null` for such a job, and a benchmark comparison
  filtered by `target_column` will not match it — you must filter by `dataset_version`
  or `experiment_ids` instead for such jobs (exactly what Scenario F above does).
- Only two real model families exist: `logistic_regression` and `linear_regression`
  (plus the fabricated `placeholder`) — no gradient-boosted trees, no neural network,
  nothing beyond a linear baseline.
- `POST /training-jobs/{id}/predict` is a **per-job convenience**, not a platform
  inference service — it loads one already-completed job's own serialized model and
  predicts for rows you supply by hand. There is no "predict on live market data,"
  no model registry, and no promotion of a trained model to any kind of serving path.

### Model Evaluation & Benchmarking Engine + Benchmark History (`/ml/evaluation`)

- Benchmarking is a **read-only comparison over already-recorded metrics** — it does
  not re-run, re-validate, or re-score anything; a job whose adapter never called the
  shared evaluation engine (there are none today, but a future third-party adapter
  could exist) would simply have no metrics to compare.
- There is no backtesting against historical trading outcomes anywhere on this
  platform — "which model performs best" here means "which model scored higher on
  accuracy/precision/recall/F1/ROC-AUC or lower on MAE/MSE/RMSE over its own held-out
  validation split," never "which model would have made more money."
- Benchmark History is filterable **only** by `dataset_version`/`target_column` (the
  same two fields a benchmark request itself accepts) — there is no general-purpose
  query across every metric ever recorded on the platform, and no way to search
  history by, say, "every run where accuracy exceeded 0.7."
- A completed job whose model adapter is no longer registered (e.g. removed in a
  later deploy) shows up in a comparison with `model_kind: "unknown"` rather than
  being excluded — it still compares by its recorded metrics, but the frontend can't
  tell you whether it was originally a classifier or a regressor beyond that.
- Export is CSV or JSON only — there is no PDF export yet (the export code is
  deliberately structured so adding one later is a small, additive change, not a
  redesign, but today only the two formats exist).
- No authentication exists anywhere on this platform (every endpoint above,
  including all of `/evaluation/*`), so anyone who can reach the API can read, run,
  and delete any benchmark comparison or history entry.

---

## 4. Importing real historical data (Delta Exchange REST API)

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
