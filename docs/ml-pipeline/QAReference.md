# ML Pipeline — Complete QA Reference

> Companion to [`MLPipelineGuide.md`](MLPipelineGuide.md). That document is a
> narrative walkthrough (how to run the automated suites, six manual
> end-to-end scenarios, known gaps). This document is the exhaustive field-
> by-field, endpoint-by-endpoint, rule-by-rule reference: every form field,
> every schema, every error code, every built-in feature/rule/metric, with
> real values read directly from the source on 2026-08-30. Nothing below is
> inferred or invented — where the implementation does not expose something
> asked for, that is stated explicitly rather than guessed.
>
> Source of truth for every claim: `services/api/app/` (engine, schemas,
> services, endpoints) and `apps/dashboard/src/features/` (pages,
> components, hooks, types) as they exist on the `feat/setup` branch at the
> time of writing. Line-referenced file paths are given throughout so a
> claim can be re-verified against the code directly.

---

## Table of Contents

1. [Feature Engineering](#1-feature-engineering)
2. [Dataset Validation](#2-dataset-validation)
3. [ML Dataset Builder](#3-ml-dataset-builder)
4. [Experiment Management](#4-experiment-management)
5. [ML Training Framework](#5-ml-training-framework)
6. [Model Evaluation](#6-model-evaluation)
7. [API Reference](#7-api-reference)
8. [Testing Reference](#8-testing-reference)

---

## 1. Feature Engineering

**Page:** `/features` — `apps/dashboard/src/features/feature-engineering/feature-engineering-page.tsx`
**Backend:** `services/api/app/features/` (engine), `app/services/features.py` (service), `app/api/v1/endpoints/features.py` (routes), `app/schemas/features.py` (DTOs)

### 1.1 Complete page layout

Top to bottom, as rendered by `FeatureEngineeringPage`:

1. **Section: "Dataset Configuration"** (subtitle: "Market, timeframe, and date range to generate features over") — contains `DatasetForm`. Below the form, a caption `"Select at least one feature to build a dataset."` renders only while zero features are selected.
2. Two-column `Grid` below the configuration section:
   - **Left column** (`lg=4`), a vertical stack of `Section`s, each conditionally rendered:
     - **"Features"** (subtitle: `"{n} of {total} selected"`) — always rendered, contains `FeatureSelector`.
     - **"Dataset Information"** (subtitle: "Identity and reproducibility") — rendered only once a dataset exists (`dataset` truthy); contains `DatasetInfoCard`.
     - **"Quality Report"** (subtitle: "How trustworthy this dataset is") — rendered only once a dataset exists; contains `DatasetSummary`.
     - **"Export"** (subtitle: "Download the complete dataset") — rendered only once a dataset exists **and** the request that built it (`built`) is known; contains `DatasetExport`.
     - **"Analysis"** (subtitle: "Full-dataset statistics and a numeric correlation matrix") — rendered under the same `dataset && built` condition; contains `FeatureAnalysisPanel`.
     - **"Dependency Graph"** (subtitle: "Every registered feature's dependencies, resolved") — rendered once the lineage query has data (independent of whether a dataset has been built); contains `FeatureLineagePanel`.
   - **Right column** (`lg=8`): **"Dataset Preview"** (subtitle: "One row per candle, one column per feature output") — contains `DatasetPreviewTable`, a build-in-progress skeleton, a build-error `Alert`, or an empty-state `Paper`, depending on state (see [§1.9](#19-loading-states) / [§1.10](#110-empty-states)).

Source: `apps/dashboard/src/features/feature-engineering/feature-engineering-page.tsx:146-271`.

### 1.2 Every field (Dataset Configuration form)

Component: `DatasetForm` — `apps/dashboard/src/features/feature-engineering/components/dataset-form.tsx`. Rendered as a single `<Box component="form" role="search" aria-label="Configure feature dataset">` with `flexWrap` — not React-Hook-Form/Zod (deliberately; see file docstring). Fields, in DOM order:

| Field                                                               | Component type                                                       | Required?                      | Default value             | Allowed values                                                                                                                                | Validation                                                                                                                                                                                  |
| ------------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------ | ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Market**                                                          | MUI `Autocomplete` over `TextField` (`aria-label="Select a market"`) | Yes                            | `''` (empty)              | Any `Market.symbol` from `GET /api/v1/markets` (~225 Delta products)                                                                          | Submit disabled until non-empty; on blur/submit attempt, shows `error` + helper text `"Select a market"` if still empty. Changing the market clears `timeframe` to `''`.                    |
| **Timeframe**                                                       | MUI `TextField select` (`aria-label="Select a timeframe"`)           | Yes                            | `''`                      | Whatever `useTimeframes(market)` returns for the selected market (subset of `TIMEFRAMES`, e.g. `1m,5m,15m,1h,4h,1d`)                          | Disabled until a market is chosen or while loading (shows `"Loading…"` placeholder item). Helper text `"Select a timeframe"` if empty after a market is chosen.                             |
| **Range**                                                           | MUI `TextField select` (`aria-label="Select a range"`)               | No (always has a value)        | `'all'` (`"All History"`) | One of `all, today, yesterday, 24h, 7d, 30d, custom` (`RANGE_PRESET_LABELS`, `apps/dashboard/src/features/history/lib/resolve-range.ts:5-13`) | None (always a valid selection).                                                                                                                                                            |
| **Start**                                                           | MUI `TextField type="date"` (`aria-label="Start date"`)              | Only when Range = Custom Range | `''`                      | Any calendar date                                                                                                                             | Disabled unless `range === 'custom'`.                                                                                                                                                       |
| **End**                                                             | MUI `TextField type="date"` (`aria-label="End date"`)                | Only when Range = Custom Range | `''`                      | A date `>= start`                                                                                                                             | Disabled unless `range === 'custom'`; shows `error` + `"End date must be on or after the start date"` if `end < start`.                                                                     |
| **Max rows**                                                        | MUI `TextField select` (`aria-label="Maximum dataset rows"`)         | No (always has a value)        | `500`                     | One of `100, 250, 500, 1000` (`DATASET_ROW_OPTIONS`)                                                                                          | None.                                                                                                                                                                                       |
| **Submit button** (`"Build Dataset"` / `"Building…"` while pending) | MUI `Button type="submit"`                                           | —                              | —                         | —                                                                                                                                             | Disabled unless: market set, timeframe set, dates valid (see above), `canSubmit` true (at least one feature selected, enforced by the page, not the form itself), and not already building. |

Every field has an `InfoTooltip` beside it (never inside the `<label>`, to avoid an a11y trap) with four sections: Purpose, Expected values, Validation rules, Example — verbatim text is in `FIELD_TOOLTIPS` (`dataset-form.tsx:54-121`).

### 1.3 Every field (Feature Selector)

Component: `FeatureSelector` — `apps/dashboard/src/features/feature-engineering/components/feature-selector.tsx`.

| Control                                            | Type                                                                                                                                                                                                                                                                                                              | Behavior                                                                                                                                                                                                                                                                                                                     |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Search box                                         | `TextField` (`aria-label="Search features"`)                                                                                                                                                                                                                                                                      | Filters by name/label/category/aliases/description via `matchesCatalogSearch` (`src/lib/search-catalog.ts`).                                                                                                                                                                                                                 |
| Category filter                                    | `TextField select`                                                                                                                                                                                                                                                                                                | Options: `"All categories"` (value `__all__`, default) plus every distinct `feature.category` present in the catalogue, alphabetically.                                                                                                                                                                                      |
| Select All / Clear All / Expand All / Collapse All | `Button`s                                                                                                                                                                                                                                                                                                         | Select All: selects every currently-_filtered_ feature (respects search + category). Clear All: deselects every currently-selected feature, ignoring the filter. Expand/Collapse All: toggles every category group's `Collapse`.                                                                                             |
| "Recently used" chip row                           | `Chip`s, one per name in `useRecentFeaturesStore` (max 8, most-recent first)                                                                                                                                                                                                                                      | Only renders when non-empty. Clicking toggles the feature.                                                                                                                                                                                                                                                                   |
| "Favorites" chip row                               | `Chip`s, one per name in `useFavoriteFeaturesStore` (unordered)                                                                                                                                                                                                                                                   | Only renders when non-empty. Clicking toggles the feature.                                                                                                                                                                                                                                                                   |
| Per-category `ListSubheader`                       | Row with expand/collapse chevron `IconButton`, category label, count `({n})`, and per-category "Select all"/"Clear" `Button`s                                                                                                                                                                                     | —                                                                                                                                                                                                                                                                                                                            |
| Per-feature row (`FeatureRow`)                     | `Checkbox` (`aria-label="Include {label}"`) + favorite-star `IconButton` (`aria-pressed`) + label + `InfoTooltip` + parameter-summary `Chip` (when selected and configurable) + secondary text (`description`, then `v{version} · {category} · {n} column(s)`) + details-toggle `IconButton` (only when selected) | Ticking the checkbox calls `onToggle`, which also records the feature as "recently used" (on both add _and_ remove). Expanding details (only possible once selected) reveals description, warmup, dependencies, and — if the feature has parameters — a `ParameterForm` (shared with Technical Indicators) for editing them. |
| Keyboard navigation                                | `onKeyDown` on the `<List>`                                                                                                                                                                                                                                                                                       | ArrowDown/ArrowUp moves focus among currently-_visible_ (filtered, non-collapsed) checkboxes, wrapping at the ends.                                                                                                                                                                                                          |

Source: `feature-selector.tsx:303-621`.

### 1.4 API endpoints (Feature Engineering)

| Endpoint                                          | Method | Purpose                                                                                                                              |
| ------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `/api/v1/features` (also unversioned `/features`) | GET    | List every registered feature generator.                                                                                             |
| `/api/v1/features/lineage`                        | GET    | The whole registry's dependency graph. Registered _before_ `/features/{feature}` so `"lineage"` is never captured as a feature name. |
| `/api/v1/features/{feature}`                      | GET    | One generator's catalogue entry.                                                                                                     |
| `/api/v1/markets/{symbol}/features/dataset`       | POST   | Build a feature dataset (optionally preview-capped).                                                                                 |
| `/api/v1/markets/{symbol}/features/correlation`   | POST   | Build the same dataset and return its Pearson correlation matrix.                                                                    |
| `/api/v1/markets/{symbol}/features/statistics`    | POST   | Build the same dataset and return full-dataset per-column statistics.                                                                |
| `/api/v1/markets/{symbol}/features/export`        | POST   | Build the same dataset and stream it as CSV/JSON (query param `?format=csv\|json`, default `csv`).                                   |

Source: `services/api/app/api/v1/endpoints/features.py:127-282`. Full request/response detail for each is repeated in [§7 API Reference](#7-api-reference).

### 1.5 Request payload — dataset / correlation / statistics (identical body shape)

`FeatureDatasetRequest` (`app/schemas/features.py:332-357`):

```json
{
  "timeframe": "1h",
  "start": "2026-01-01T00:00:00Z",
  "end": "2026-02-01T00:00:00Z",
  "limit": 500,
  "features": [
    { "feature": "sma", "params": { "period": 20, "source": "close" } },
    { "feature": "candle_shape", "params": { "normalize": true } }
  ],
  "drop_warmup": true,
  "preview_rows": 200
}
```

| Field           | Type                         | Required | Default                                    | Constraints                                                                                                                                                                                               |
| --------------- | ---------------------------- | -------- | ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `timeframe`     | string                       | Yes      | —                                          | Must be one of `TIMEFRAMES`, or `invalid_timeframe` (400).                                                                                                                                                |
| `start` / `end` | datetime or null             | No       | `null`                                     | Must be given together (`invalid_range` 400 otherwise); `end` must be after `start`.                                                                                                                      |
| `limit`         | int or null                  | No       | server's `candles_default_limit` = **100** | `ge=1`; if the resolved value exceeds `candles_max_limit` = **1000**, raises `limit_exceeded` (400). Means "rows in the _returned dataset_", not candles read — extra candles for warmup are read on top. |
| `features`      | array of `{feature, params}` | Yes      | —                                          | `min_length=1, max_length=50`.                                                                                                                                                                            |
| `drop_warmup`   | bool                         | No       | `true`                                     | When `true`, rows where any requested feature is still undefined are dropped.                                                                                                                             |
| `preview_rows`  | int or null                  | No       | `null` (no cap — ignored for `/export`)    | `ge=1, le=5000`.                                                                                                                                                                                          |

### 1.6 Response payload — dataset build

`FeatureDatasetResponse` (`app/schemas/features.py:251-319`):

```json
{
  "dataset_id": "b6f1c2a4-8e3d-4a1b-9c7f-2d5e6a8b9c0d",
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "columns": [
    {
      "name": "open",
      "label": "Open",
      "description": "Opening price of the candle.",
      "dtype": "float"
    },
    {
      "name": "sma_20",
      "label": "SMA",
      "description": "The moving average itself.",
      "dtype": "float"
    }
  ],
  "timestamps": ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"],
  "rows": [
    [3200.5, 3195.12],
    [3201.0, 3196.4]
  ],
  "features": [
    {
      "feature": "sma",
      "label": "Simple Moving Average",
      "version": "1.0.0",
      "parameters": { "period": 20, "source": "close" },
      "columns": ["sma_20"],
      "warmup": 20,
      "execution_time_ms": 1.42,
      "cache_status": "miss"
    }
  ],
  "meta": {
    "row_count": 200,
    "total_rows": 480,
    "candles_analyzed": 500,
    "rows_dropped": 20,
    "warmup_candles": 20,
    "truncated": true,
    "database_time_ms": 4.7,
    "pipeline_version": "1.0.0",
    "generated_at": "2026-01-31T23:00:00Z"
  },
  "quality": {
    "total_rows": 500,
    "rows_returned": 200,
    "rows_removed": 20,
    "null_counts": { "sma_20": 20 },
    "duplicate_timestamps": 0,
    "missing_candles": 0,
    "feature_failures": [],
    "generation_time_ms": 2.1
  }
}
```

`dataset_id` is a **UUID4**, generated fresh on every build (`str(uuid.uuid4())`, `app/features/dataset.py:295`) — it is not a content hash, so rebuilding the identical request twice yields two different ids.

### 1.7 Response payload — correlation

`FeatureCorrelationResponse` (`app/schemas/features.py:360-387`):

```json
{
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "columns": ["open", "high", "low", "close", "volume"],
  "matrix": [
    [1.0, 0.999, 0.999, 0.998, -0.12],
    [0.999, 1.0, 0.998, 0.999, -0.11]
  ],
  "row_count": 480
}
```

`columns`/`matrix` are empty arrays (`[]`) — not an error — when fewer than two numeric columns are present. `matrix[i][j]` is symmetric and every diagonal entry is exactly `1.0`. `row_count` is the **largest** pairwise-complete row count across every column pair compared (`app/features/correlation.py:71`), not a sum. A constant column (zero variance) correlates as `0.0` with everything, never `NaN`.

### 1.8 Response payload — statistics

`FeatureStatisticsResponse` (`app/schemas/features.py:415-433`):

```json
{
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "columns": [
    {
      "column": "sma_20",
      "count": 480,
      "null_count": 0,
      "mean": 3198.42,
      "std": 41.07,
      "minimum": 3050.1,
      "maximum": 3320.9
    },
    {
      "column": "candle_direction",
      "count": 480,
      "null_count": 0,
      "mean": null,
      "std": null,
      "minimum": null,
      "maximum": null
    }
  ],
  "row_count": 480
}
```

`mean`/`std`/`minimum`/`maximum` are `null` for a non-numeric (`categorical`) column, or for a numeric column where every value happens to be non-numeric/null. `std` uses **population variance** (divides by `n`, not `n-1`) — identical formula to the frontend's `computeColumnStats` (`lib/column-stats.ts:22-45`), so the two never disagree for the same column over the same rows. Always computed over the **complete** dataset — never capped by `preview_rows`.

### 1.9 Loading states

| Situation                                                                                                          | UI                                                                                                                                                       |
| ------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Markets or feature catalogue still loading                                                                         | Whole page replaced by `PageSkeleton` — a `Skeleton` bar plus two `Skeleton` panels, `role="status" aria-label="Loading feature engineering"`.           |
| Feature catalogue loading, inside `FeatureSelector` alone (rare — usually caught by the page-level skeleton first) | `SelectorSkeleton` — five `Skeleton variant="rounded"` bars, `role="status" aria-label="Loading feature catalogue"`.                                     |
| Timeframe list loading for the selected market                                                                     | Timeframe `<select>` disabled, showing `"Loading…"` as its placeholder item.                                                                             |
| Dataset build in flight (`build.isPending`)                                                                        | Submit button reads `"Building…"` and is disabled; the Dataset Preview section shows two `Skeleton` bars, `role="status" aria-label="Building dataset"`. |
| Export in flight                                                                                                   | The clicked export button (`CSV` or `JSON`) reads `"Exporting…"` and both export buttons are disabled.                                                   |
| Analyze in flight                                                                                                  | The Analyze button reads `"Analyzing…"` and is disabled.                                                                                                 |

### 1.10 Empty states

| Situation                                                     | UI                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No feature selected yet                                       | Caption under the form: `"Select at least one feature to build a dataset."`; submit button disabled.                                                                                                                                                                                                                                                                            |
| No generators registered at all                               | `FeatureSelector` shows `"No feature generators are registered."`                                                                                                                                                                                                                                                                                                               |
| Search/category filter matches nothing                        | `"No features match "{search}"."`                                                                                                                                                                                                                                                                                                                                               |
| No dataset built yet                                          | Dataset Preview shows a bordered `Paper`: `"Choose a market, timeframe, and features, then build a dataset to preview it here."`                                                                                                                                                                                                                                                |
| Dataset built but produced zero columns                       | `"No columns were produced. Select at least one feature and rebuild."` (`role="status"`)                                                                                                                                                                                                                                                                                        |
| Dataset built but every row was dropped as warmup             | `"The dataset has no rows. Every row was dropped as warmup — widen the date range or reduce the largest period."` (`role="status"`) — this is also the `empty_dataset` (400) error case at the API layer; on the frontend, it can only be reached if `drop_warmup=false` was sent (otherwise the backend itself raises before returning), so in practice this row is defensive. |
| Column search matches nothing / everything matching is hidden | `"No columns match "{search}", or every matching column is hidden."`                                                                                                                                                                                                                                                                                                            |
| Correlation matrix has < 2 numeric columns                    | `FeatureCorrelationMatrix` renders **nothing** (returns `null`) — not an empty table.                                                                                                                                                                                                                                                                                           |
| Statistics has zero columns                                   | `FeatureStatisticsPanel` renders **nothing**.                                                                                                                                                                                                                                                                                                                                   |
| Lineage graph has zero nodes                                  | `FeatureLineagePanel` renders **nothing**.                                                                                                                                                                                                                                                                                                                                      |
| Lineage graph has nodes but zero edges (today's real state)   | Renders a caption: `"No registered feature declares a dependency on another today — every node below is independent."`                                                                                                                                                                                                                                                          |

### 1.11 Preview table columns

Component: `DatasetPreviewTable` (virtualized — only mounts rows scrolled into view plus an 8-row overscan margin; fixed row height 33px, viewport height 460px).

- **Timestamp** column — sticky while scrolling horizontally, `fontVariantNumeric: tabular-nums`.
- One column per built dataset column, right-aligned, header shows: the column name, a `target` `Chip` (only when the column is a declared ML-target, a prop this component accepts but the Feature Engineering page never passes), a `BarChartIcon` stats popover (only for numeric `dtype`), and an `InfoTooltip` (description, dtype, and "Role: Prediction target" when applicable).
- Optional trailing **Split** column (`train`/`validation`/`test` colored `Chip`) — only rendered when the caller supplies `splitLabels`, which the Feature Engineering page never does (this is consumed by the ML Dataset Builder's own preview instead).
- A column-search box (`"Search columns…"`) and a column-visibility menu (`ViewColumnIcon`) let a researcher narrow the visible set — display-only, never affects what an export contains.
- Truncation notice: when `meta.truncated` is true, a `"Preview"` info `Chip` plus `"Showing {row_count} of {total_rows} rows. Exports always contain the full dataset."`

Cell rendering (`formatCell`, `lib/feature-selection.ts:113-127`): `null`/`undefined` → em dash `—`; boolean → `"true"`/`"false"`; integer number → verbatim; non-integer number → rounded to 6 significant digits; string → verbatim.

### 1.12 Export formats

| Format  | Extension | Media type                        | Endpoint                                        | Filename pattern                                                                                                                                                                                                                                                                                      |
| ------- | --------- | --------------------------------- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CSV     | `.csv`    | `text/csv; charset=utf-8`         | `POST .../features/export?format=csv` (default) | `{symbol}-{timeframe}-features-{YYYYMMDDTHHMMSSZ}.csv` (backend, `dataset_filename`) — the frontend's own download uses `{symbol}-{timeframe}-features.csv` instead (`dataset-export.tsx:20-23`), since it names the file at `Content-Disposition` receive time, not from the backend's stamped name. |
| JSON    | `.json`   | `application/json; charset=utf-8` | `POST .../features/export?format=json`          | Same pattern, `.json`.                                                                                                                                                                                                                                                                                |
| Parquet | —         | —                                 | —                                               | **Current implementation does not expose this information** — `EXPORT_FORMATS` is documented as an intentional extension point (`app/features/export.py:25-33`) but only `csv`/`json` are registered today.                                                                                           |

CSV includes an optional `# key,value` comment preamble (dataset id, symbol, timeframe, generated/exported timestamps, pipeline version, row counts, per-feature provenance lines, quality-report lines) before the header row and data — `include_metadata=True` is always used by the API. JSON always includes full provenance (`dataset_id`, `columns`, `features`, `meta`, `quality`) plus `data` (records or column-oriented, per `orient`, though the API always uses the default `"records"` orient). Export always serializes the **complete** dataset — `preview_rows` is stripped by the frontend before the request and ignored by the endpoint's own contract if present.

### 1.13 Error responses

| HTTP | `code`                       | Raised by                       | Message pattern                                                                                                                                                     |
| ---- | ---------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 404  | `market_not_found`           | `MarketNotFoundError`           | `Market '{symbol}' not found`                                                                                                                                       |
| 404  | `candle_not_found`           | `CandleNotFoundError`           | `No candles stored for market '{symbol}' and timeframe '{timeframe}'`                                                                                               |
| 404  | `feature_not_found`          | `FeatureNotFoundError`          | `Feature '{name}' is not registered; available: {sorted names}`                                                                                                     |
| 400  | `invalid_timeframe`          | `InvalidTimeframeError`         | `Unsupported timeframe '{tf}'; supported: {...}`                                                                                                                    |
| 400  | `invalid_range`              | `InvalidRangeError`             | e.g. `start and end must be provided together` / `end must be after start`                                                                                          |
| 400  | `limit_exceeded`             | `LimitExceededError`            | `limit {n} exceeds the configured maximum of {max}`                                                                                                                 |
| 400  | `invalid_feature_parameter`  | `InvalidFeatureParameterError`  | `Feature '{name}': {reason}` e.g. `Parameter 'period' must be >= 1, got 0`                                                                                          |
| 400  | `insufficient_data`          | `InsufficientFeatureDataError`  | `Feature '{name}' needs at least {required} candles for these parameters; only {available} are available in this range`                                             |
| 400  | `duplicate_feature_column`   | `DuplicateFeatureColumnError`   | `Column '{col}' would be produced by both '{a}' and '{b}'; request them with different parameters or drop one`                                                      |
| 400  | `empty_dataset`              | `EmptyDatasetError`             | `Every row was dropped: {n} candles were loaded but the requested features need {m} candles of warmup. Widen the date range or reduce the largest period parameter` |
| 400  | `missing_feature_dependency` | `MissingFeatureDependencyError` | `Feature '{name}' depends on '{dep}', which was not included in this request. Add it to \`features\` alongside this one.`                                           |
| 500  | `feature_execution_failed`   | `FeatureExecutionError`         | `Feature '{name}' failed during generation: {ExceptionType}: {message}`                                                                                             |

`insufficient_data`, `invalid_feature_parameter`, `feature_execution_failed`, and `feature_not_found` on **one requested feature among several** do **not** fail the whole request — they are recorded in `quality.feature_failures[]` (each entry: `feature`, `params`, `error_code`, `error_detail`) and every other requested feature still builds (`app/features/dataset.py:59-64, 212-224`). `duplicate_feature_column` and `missing_feature_dependency` are structural and always fail the entire request — there is no partial result that would make sense for either. Sources: `app/features/errors.py`, `app/services/market_query.py:20-77`.

### 1.14 History

**Current implementation does not expose this information.** The Feature Engineering workbench builds datasets on demand and never persists a build to a database table or a history list — there is no analog to the ML Dataset Builder's "Dataset History" for this page. Every "history"-shaped affordance here is client-session-scoped UI convenience only: `useRecentFeaturesStore` (which _features_ were recently ticked, `sessionStorage`, cap 8) and `useFavoriteFeaturesStore` (which features are starred, `localStorage`, unbounded) — neither stores a built dataset, only feature _selections_.

---

### 1.15 Every built-in feature

Discovered automatically from `app/features/builtin/` (see `app/features/builtin/__init__.py:43-71`); five features are registered today (`ohlcv`, `candle_shape`, `sma`, `ema`, `wma`) — **not eight**, contrary to an older doc's phrasing; `INDICATOR_BACKED_FEATURES = ("sma", "ema", "wma")` (`__init__.py:35`).

#### `ohlcv` — OHLCV

- **Description:** "The raw open, high, low, close, and volume of each candle, passed through unmodified. The baseline inputs every other feature is derived from."
- **Category:** `raw`
- **Parameters:** none.
- **Output columns:** `open`, `high`, `low`, `close`, `volume` — all `dtype: "float"`.
- **Warmup:** `0` ("None; defined from the first candle.")
- **Version:** `1.0.0`. **Complexity:** "O(n) — one pass, no arithmetic." **Aliases:** `raw, candles, price`. **Unit:** "price / base-asset volume". **`is_deterministic`:** `true`. **`missing_values_expected`:** `false`.
- **Example output** (one row, 1h ETHUSD candle): `{"open": 3200.5, "high": 3210.0, "low": 3190.2, "close": 3201.0, "volume": 812.4}`

Source: `app/features/builtin/ohlcv.py`.

#### `candle_shape` — Candle Shape

- **Description:** "Decomposes each candle into its body size, upper wick, lower wick, and direction. Together the body and both wicks span the candle's full high-low range; direction is the sign of the body."
- **Category:** `price_action`
- **Parameters:**

  | Name        | Type | Label     | Default | Choices/Bounds |
  | ----------- | ---- | --------- | ------- | -------------- |
  | `normalize` | bool | Normalize | `false` | —              |

- **Output columns:** `candle_body` (float), `upper_wick` (float), `lower_wick` (float), `candle_direction` (categorical: `"up"` \| `"down"` \| `"flat"`).
- **Warmup:** `0` ("None; every column is defined from the first candle.")
- **Version:** `1.0.0`. **Complexity:** "O(n) — one pass, constant work per candle." **Aliases:** `body, wick, wicks, direction, shape, price action`. **Unit:** "price, or a 0-1 ratio when `normalize` is set". **`is_deterministic`:** `true`. **`missing_values_expected`:** `true` — a flat (zero-range, `high == low`) candle's normalized body/wick fractions are reported as `null` rather than dividing by zero or fabricating `0`.
- **Example output** (`normalize=false`, a candle with `open=3200, high=3210, low=3190, close=3205`): `{"candle_body": 5.0, "upper_wick": 5.0, "lower_wick": 10.0, "candle_direction": "up"}`. With `normalize=true` on the same candle (range = 20): `{"candle_body": 0.25, "upper_wick": 0.25, "lower_wick": 0.5, "candle_direction": "up"}`.

Source: `app/features/builtin/candle_shape.py`.

#### `sma` — Simple Moving Average (indicator-backed)

- **Description:** "The unweighted mean of the last N values. The baseline trend indicator: every point weighs equally, so it is smooth but lags price by roughly half the period."
- **Category:** `trend`
- **Parameters:**

  | Name     | Type   | Label  | Default   | Bounds/Choices           |
  | -------- | ------ | ------ | --------- | ------------------------ |
  | `period` | int    | Period | `20`      | min `1`, max `1000`      |
  | `source` | string | Source | `"close"` | `open, high, low, close` |

- **Output columns:** column name is dynamically built as `sma_{period}` when `source` is the default (`close`), or `sma_{period}_{source}` otherwise (`app/features/builtin/indicator_feature.py:44-60, 133-135`) — e.g. `sma_20`, or `sma_20_high` for a non-default source. `dtype: "float"`.
- **Warmup:** equal to `period` (e.g. `period=20` → warmup `20`).
- **Version:** `1.0.0` (inherited from the SMA indicator). **Complexity:** "O(n) — one running-sum pass over the candle range." **Aliases:** `MA, Moving Average, Simple MA`. **Unit:** "price". **`is_deterministic`:** `true`. **`missing_values_expected`:** `false` (nulls are only the leading warmup, already accounted for).
- **Example output** (`period=3, source=close`, closes `[10, 20, 30, 40]`): `sma_3` = `[null, null, 20.0, 30.0]`.

Source: `app/indicators/builtin/sma.py`, `app/indicators/builtin/common.py:27-49`, `app/features/builtin/indicator_feature.py`.

#### `ema` — Exponential Moving Average (indicator-backed)

- **Description:** "A moving average that weights recent candles more heavily, so it reacts faster than an SMA of the same period at the cost of being noisier. Seeded from the first full simple average of the period, the conventional choice."
- **Category:** `trend`
- **Parameters:** identical shape to `sma` — `period` (int, default `20`, min `1`, max `1000`), `source` (string, default `"close"`, choices `open/high/low/close`).
- **Output columns:** `ema_{period}` (default source) or `ema_{period}_{source}`. `dtype: "float"`.
- **Warmup:** equal to `period` (the SMA seed needs a full window before the recursion starts).
- **Version:** `1.0.0`. **Complexity:** "O(n) — one recursive pass over the candle range after an O(period) seed." **Aliases:** `Exponential MA, Exponentially Weighted Moving Average`. Multiplier: `2 / (period + 1)`.
- **Example output** (`period=3`, closes `[10, 20, 30, 40, 50]`): seed at index 2 = mean(10,20,30) = `20.0`; index 3 = `(40-20)*0.5+20 = 30.0`; index 4 = `(50-30)*0.5+30 = 40.0`. `ema_3` = `[null, null, 20.0, 30.0, 40.0]`.

Source: `app/indicators/builtin/ema.py`.

#### `wma` — Weighted Moving Average (indicator-backed)

- **Description:** "A moving average that weights each candle in the window linearly by recency — the newest candle counts most, the oldest counts least — so it reacts faster than an SMA of the same period without an EMA's unbounded recursive memory."
- **Category:** `trend`
- **Parameters:** identical shape to `sma`/`ema` — `period` (int, default `20`, min `1`, max `1000`), `source` (string, default `"close"`, choices `open/high/low/close`).
- **Output columns:** `wma_{period}` (default source) or `wma_{period}_{source}`. `dtype: "float"`.
- **Warmup:** equal to `period`.
- **Version:** `1.0.0`. **Complexity:** "O(n) — one incremental pass over the candle range after an O(period) seed." **Aliases:** `Weighted MA, Linear Weighted Moving Average, LWMA`. Weight of the newest candle in the window = `period`; oldest = `1`.
- **Example output** (`period=3`, closes `[10, 20, 30]`, weights 1/2/3, weight_sum=6): `wma_3[2]` = `(10*1 + 20*2 + 30*3)/6 = 23.333...` → displayed as `23.3333` (6 significant digits) in the preview table.

Source: `app/indicators/builtin/wma.py`.

> **Feature Versioning.** Every generator above declares `version` in its `FeatureMetadata` (all `"1.0.0"` today) — already fully implemented, not a gap. A version bump signals that previously-built datasets under the old version are not guaranteed reproducible under the new one. Surfaced in the UI as the `v{version}` chip in `DatasetSummary` and the `v{version} · {category} · {n} column(s)` caption in `FeatureSelector`'s row list.
>
> **Feature Dependency Graph / Lineage.** `GET /features/lineage` resolves ancestors/descendants/topological order for the whole registry. As of this writing, **every one of the five generators above declares zero dependencies** (`FeatureMetadata.dependencies == ()`), so a real response has `edges: []` and `topological_order` equal to the alphabetically-sorted registered names: `["candle_shape", "ema", "ohlcv", "sma", "wma"]`. This is the honest current state, not a placeholder — the graph, cycle detection, and topological sort are all real and already exercised by the registry's own startup validation (`FeatureRegistry.validate_dependencies`), simply over an edgeless graph today.
>
> **AI extension points not implemented.** `app/features/ai_extensions.py` documents (but does not wire in) six future capabilities: label/target generation, sliding-window sequencing, feature normalization, train/validation/test splitting _at the feature-engineering layer_, and categorical encoding. **Current implementation does not expose this information** for any of the six — they exist only as typed `Protocol` contracts with no implementation, and no API endpoint or UI surfaces them.

---

## 2. Dataset Validation

**Page:** `/validation` — `apps/dashboard/src/features/dataset-validation/dataset-validation-page.tsx`
**Backend:** `services/api/app/dataset_validation/` (engine + 11 built-in rules), `app/services/dataset_validation.py`, `app/api/v1/endpoints/dataset_validation.py`, `app/schemas/dataset_validation.py`

The engine's own name space is deliberately distinct from two other things this platform also calls "validation": `app/features/validation.py` (request-time feature-dependency checks raised inline during a build) and `app/services/candle_validation.py` (stored-candle integrity checks, no REST surface). This is the third, on-demand quality gate.

### 2.1 Page layout

1. **Section: "Dataset Configuration"** (subtitle: "Market, timeframe, and date range to validate — the same selection a dataset build uses") — contains the **same** `DatasetForm` component the Feature Engineering page uses (submit button relabeled `"Run Validation"` / `"Validating…"` via props), a caption `"Select at least one feature to validate a dataset."` (only while no feature is selected), `RequiredColumnPresets` (a row of preset chips), and `RequiredColumnsSelector` (the multi-select column picker).
2. Two-column `Grid`:
   - **Left** (`lg=4`): **"Features"** section (same `FeatureSelector` component as Feature Engineering) and **"Available Checks"** section (`ValidationRuleCatalog`, reading `GET /validation/rules`).
   - **Right** (`lg=8`): before any run — `GettingStarted` (a bordered `Paper` explaining what validation does, how to start, and a worked example). During a run — a loading skeleton. On error — an error `Alert` with Retry. After a successful run — three stacked sections: **"Validation Summary"** (subtitle `"{symbol} · {timeframe}"`, with a `ValidationReportDownload` button as its header action) containing `ValidationSummaryCards`; **"Validation Report"** containing `ValidationReportPanel`; **"Statistics"** containing `ValidationStatistics`.

Source: `dataset-validation-page.tsx:205-315`.

### 2.2 Fields unique to this page (beyond the reused `DatasetForm`/`FeatureSelector` — see §1.2/§1.3)

| Field                  | Component                                                                                        | Required? | Default      | Allowed values                                                                                                                                                                                  | Validation                                                                                                                                                                    |
| ---------------------- | ------------------------------------------------------------------------------------------------ | --------- | ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Presets** (chip row) | `Chip[]`, `role="group" aria-label="Required column presets"`                                    | No        | none applied | One of 5 keys (see [§2.9](#29-presets))                                                                                                                                                         | Clicking replaces the current feature selection and required-columns list wholesale.                                                                                          |
| **Required columns**   | MUI `Autocomplete` (`multiple, freeSolo, disableCloseOnSelect`, `aria-label="Required columns"`) | No        | `[]`         | Any resolved column name from the catalogue (grouped: Raw Market Data / Technical Indicators / Candle Features / Statistical Features / Future Features), or any free-typed string (`freeSolo`) | None — an unresolvable name is a deliberate way to make `required_columns` fail on purpose. "Select All"/"Clear All" buttons operate on the currently resolvable option list. |

"Recently used" columns (`useRecentColumnsStore`, `sessionStorage`, cap 8 — same shape as the Feature Engineering module's recent-features store) render as a chip row beneath the selector when non-empty.

### 2.3 API endpoints (Dataset Validation)

| Endpoint                                     | Method | Purpose                                                                                   |
| -------------------------------------------- | ------ | ----------------------------------------------------------------------------------------- |
| `/api/v1/markets/{symbol}/features/validate` | POST   | Build a dataset (same path as `/features/dataset`) and run the validation engine over it. |
| `/api/v1/validation/rules`                   | GET    | List every registered validation rule.                                                    |

### 2.4 Request payload

`DatasetValidationRequest` extends `FeatureDatasetRequest` (see [§1.5](#15-request-payload--dataset--correlation--statistics-identical-body-shape)) with two extra fields (`app/schemas/dataset_validation.py:25-35`):

```json
{
  "timeframe": "1h",
  "start": "2026-01-01T00:00:00Z",
  "end": "2026-02-01T00:00:00Z",
  "limit": 500,
  "features": [{ "feature": "sma", "params": { "period": 20 } }],
  "required_columns": ["close", "sma_20"],
  "rules": null
}
```

| Field              | Type               | Required | Default                             | Notes                                                                                                                                            |
| ------------------ | ------------------ | -------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `required_columns` | `string[]`         | No       | `[]`                                | Any name not present in the built dataset's columns raises a `missing_required_column` error (not an HTTP error — a reported `ValidationIssue`). |
| `rules`            | `string[] \| null` | No       | `null` (every registered rule runs) | An unknown rule name raises `validation_rule_not_found` (404) **before anything runs**.                                                          |

Every other field is identical to `FeatureDatasetRequest` — `preview_rows`/`drop_warmup` still apply to the underlying dataset build (validation always runs against the dataset `build_raw` would actually build for `/features/dataset`).

### 2.5 Response payload

`ValidationReportResponse` (`app/schemas/dataset_validation.py:99-147`):

```json
{
  "dataset_id": "b6f1c2a4-8e3d-4a1b-9c7f-2d5e6a8b9c0d",
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "engine_version": "1.0.0",
  "validated_at": "2026-01-31T23:00:05Z",
  "passed": false,
  "rules_run": [
    "data_types",
    "duplicate_rows",
    "duplicate_timestamps",
    "feature_failures",
    "infinite_values",
    "metadata_consistency",
    "missing_values",
    "nan_values",
    "required_columns",
    "time_gaps",
    "timestamp_ordering"
  ],
  "summary": { "total_checks": 2, "errors": 1, "warnings": 1, "info": 0 },
  "categories": {
    "structural": { "errors": 1, "warnings": 0, "info": 0 },
    "data_quality": { "errors": 0, "warnings": 1, "info": 0 },
    "time_series": { "errors": 0, "warnings": 0, "info": 0 },
    "feature": { "errors": 0, "warnings": 0, "info": 0 }
  },
  "issues": [
    {
      "rule": "required_columns",
      "category": "structural",
      "severity": "error",
      "code": "missing_required_column",
      "message": "Required column 'sma_50' is not present in this dataset",
      "column": "sma_50",
      "row_index": null,
      "count": null,
      "details": {}
    }
  ],
  "rows": 480,
  "columns": 6,
  "duration_ms": 1.8
}
```

`rules_run` lists names in **run order** — since the engine iterates `self._registry.names()` (alphabetically sorted) when no subset is given, the default full run always lists the 11 rules in the exact alphabetical order shown above. `categories` always has all four keys present (`structural`, `data_quality`, `time_series`, `feature`) even when a category has zero issues, seeded up front by the engine.

### 2.6 Every validation rule

11 built-in rules, registered automatically from `app/dataset_validation/rules/` (mirrors the Feature Engineering registry's own discovery convention). Confirmed exhaustive list (from the endpoint's own 404 example payload, `dataset_validation.py:52-55`): `data_types, duplicate_rows, duplicate_timestamps, feature_failures, infinite_values, metadata_consistency, missing_values, nan_values, required_columns, time_gaps, timestamp_ordering`.

| Rule ID                | Category       | Default Severity | Error code(s)                                                                 | Description                                                                                                                                 |
| ---------------------- | -------------- | ---------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `required_columns`     | `structural`   | `error`          | `missing_required_column`, `missing_declared_column`                          | Every caller-supplied `required_columns` name, and every column a requested feature declares producing, is actually present in the dataset. |
| `data_types`           | `structural`   | `error`          | `column_dtype_mismatch`                                                       | Every column's cell values match its declared dtype.                                                                                        |
| `missing_values`       | `data_quality` | `warning`        | `missing_values`                                                              | Null cell counts per column in the _delivered_ rows (post-warmup-trim if `drop_warmup=true`).                                               |
| `duplicate_rows`       | `data_quality` | `warning`        | `duplicate_rows`                                                              | Rows whose every value is identical to an earlier row.                                                                                      |
| `duplicate_timestamps` | `data_quality` | `error`          | `duplicate_timestamps`                                                        | Timestamps appearing more than once in the delivered dataset.                                                                               |
| `nan_values`           | `data_quality` | `error`          | `nan_values`                                                                  | Float `NaN` cells — distinct from a `None`.                                                                                                 |
| `infinite_values`      | `data_quality` | `error`          | `infinite_values`                                                             | Float `inf`/`-inf` cells.                                                                                                                   |
| `timestamp_ordering`   | `time_series`  | `error`          | `timestamp_ordering`                                                          | Timestamps are strictly increasing.                                                                                                         |
| `time_gaps`            | `time_series`  | `warning`        | `time_gaps`                                                                   | Gaps in the delivered series at the timeframe's expected cadence.                                                                           |
| `metadata_consistency` | `feature`      | `error`          | `row_timestamp_mismatch`, `row_column_mismatch`, `quality_row_count_mismatch` | The dataset's row/column counts and quality-report totals agree with themselves.                                                            |
| `feature_failures`     | `feature`      | `warning`        | `feature_generation_failed`                                                   | Surfaces any requested feature that failed to generate (from `quality.feature_failures`).                                                   |

Every rule's `version` field is `"1.0.0"` (`ValidationRuleMetadata.version` default, none overridden). `default_severity` is fixed per rule — there is no per-request severity override; a rule always reports at its declared severity.

#### Rule detail: `required_columns`

- **Returned JSON (per issue):** `{"rule": "required_columns", "category": "structural", "severity": "error", "code": "missing_required_column", "message": "Required column 'sma_50' is not present in this dataset", "column": "sma_50", "row_index": null, "count": null, "details": {}}` — or `code: "missing_declared_column"` with message `"Feature 'sma' declares column 'sma_50' but it is not present among the dataset's columns"` (a defect signal, not a caller error).
- **Frontend rendering:** in `ValidationIssueList`, a `Chip` for `code` (colored by severity), a `Chip` for `category`; expanded row shows Affected column, Affected row (`—` here, since this rule never sets `row_index`), and a curated Suggested Fix: _"Select a feature that produces this column, or remove it from Required Columns."_ (for `missing_required_column`) or _"This indicates a defect in the feature that declared this column. Report it."_ (for `missing_declared_column`).
- **Example failed dataset:** request `required_columns: ["sma_50"]` without selecting `sma` at `period=50` → one `missing_required_column` error.
- **Example successful dataset:** request `required_columns: ["close"]` with `ohlcv` selected → zero issues from this rule.

#### Rule detail: `data_types`

- **Returned JSON:** `{"rule": "data_types", "category": "structural", "severity": "error", "code": "column_dtype_mismatch", "message": "Column 'candle_direction' declares dtype 'categorical' but 3 value(s) do not match it", "column": "candle_direction", "count": 3}`.
- **Frontend rendering:** same issue-row shape; Suggested Fix: _"Inspect the generator producing this column — its output doesn't match its declared dtype."_
- **Example failed dataset:** cannot currently be produced by any built-in generator (every shipped generator's output always matches its declared dtype) — this rule exists as a structural safety net rather than one any built-in feature is known to trip.
- **Example successful dataset:** any dataset built from the five built-in generators (all always pass).

#### Rule detail: `missing_values`

- **Returned JSON:** `{"rule": "missing_values", "category": "data_quality", "severity": "warning", "code": "missing_values", "message": "Column 'candle_body' has 4 missing value(s) in the delivered dataset", "column": "candle_body", "count": 4}`.
- **Frontend rendering:** Suggested Fix: _"Expected when the feature declares missing values as normal; otherwise inspect the generator for the affected column."_
- **Example failed dataset:** `candle_shape` with `normalize=true` over a range containing at least one flat (zero-range) candle, requested with `drop_warmup=false` (so the null survives delivery).
- **Example successful dataset:** the default `drop_warmup=true` build — nulls are trimmed before delivery in the normal case, so this rule is typically clean unless `drop_warmup=false` was explicitly requested.

#### Rule detail: `duplicate_rows`

- **Returned JSON:** `{"rule": "duplicate_rows", "category": "data_quality", "severity": "warning", "code": "duplicate_rows", "message": "5 row(s) are exact duplicates of an earlier row", "count": 5}` (no `column`/`row_index` — this is a whole-row check).
- **Frontend rendering:** Suggested Fix: _"Widen the requested feature set, or accept that the underlying market was genuinely flat over this period."_
- **Example failed dataset:** a market with several consecutive identical candles (a stalled/thin market) built with only `ohlcv` selected.
- **Example successful dataset:** any dataset over a normally-varying price series.

#### Rule detail: `duplicate_timestamps`

- **Returned JSON:** `{"rule": "duplicate_timestamps", "category": "data_quality", "severity": "error", "code": "duplicate_timestamps", "message": "2 timestamp(s) appear more than once — each row must be uniquely timestamped", "count": 2}`.
- **Frontend rendering:** Suggested Fix: _"Re-sync or re-validate the stored candle data for this market/timeframe — this should never happen."_
- **Example failed dataset:** **Current implementation does not expose this information** as an achievable state through normal use — the storage layer enforces a unique `(market_id, timeframe, open_time)` constraint, so this should always report `0` in practice; it exists as a defensive check.
- **Example successful dataset:** any normal dataset (expected count: `0`).

#### Rule detail: `nan_values`

- **Returned JSON:** `{"rule": "nan_values", "category": "data_quality", "severity": "error", "code": "nan_values", "message": "Column 'candle_body' contains 1 NaN value(s)", "column": "candle_body", "count": 1}`.
- **Frontend rendering:** Suggested Fix: _"Inspect the generator for the affected column for a division or log by zero."_
- **Example failed dataset:** **Current implementation does not expose this information** as achievable by any built-in generator — every shipped feature reports an undefined value as `None`, never Python `float('nan')` (see `candle_shape`'s own `_UNDEFINED = None` convention); this rule is a safety net for a future generator, not one any built-in feature can trip today.
- **Example successful dataset:** any dataset built from the five built-in generators.

#### Rule detail: `infinite_values`

- **Returned JSON:** `{"rule": "infinite_values", "category": "data_quality", "severity": "error", "code": "infinite_values", "message": "Column 'x' contains 1 infinite value(s)", "column": "x", "count": 1}`.
- **Frontend rendering:** Suggested Fix: _"Inspect the generator for the affected column for a division by a near-zero value."_
- **Example failed dataset:** **Current implementation does not expose this information** as achievable by any built-in generator — same reasoning as `nan_values`.
- **Example successful dataset:** any dataset built from the five built-in generators.

#### Rule detail: `timestamp_ordering`

- **Returned JSON:** `{"rule": "timestamp_ordering", "category": "time_series", "severity": "error", "code": "timestamp_ordering", "message": "1 row(s) are out of chronological order (first at row 42)", "row_index": 42, "count": 1}`.
- **Frontend rendering:** Suggested Fix: _"Re-sync or re-validate the stored candle data for this market/timeframe."_
- **Example failed dataset:** **Current implementation does not expose this information** as achievable through normal use — `load_candle_points` always queries in ascending `open_time` order; this is a defensive check against a future ingestion bug.
- **Example successful dataset:** any normal dataset build.

#### Rule detail: `time_gaps`

- **Returned JSON:** `{"rule": "time_gaps", "category": "time_series", "severity": "warning", "code": "time_gaps", "message": "3 expected 1h interval(s) are missing from the delivered series", "count": 3}`.
- **Frontend rendering:** Suggested Fix: _"Widen the date range, choose a different period, or accept the gap if the market was genuinely inactive."_
- **Example failed dataset:** a market/timeframe with a known ingestion gap (an exchange outage) validated over a range spanning that gap.
- **Example successful dataset:** a fully continuous candle range.

#### Rule detail: `metadata_consistency`

- **Returned JSON (one of three codes):** `{"rule": "metadata_consistency", "category": "feature", "severity": "error", "code": "row_timestamp_mismatch", "message": "480 timestamps but 479 rows — these must be the same length"}`, or `code: "row_column_mismatch"` (only the _first_ offending row is reported — "one instance proves the structural break; more would only repeat it", `feature_rules.py:63`), or `code: "quality_row_count_mismatch"`.
- **Frontend rendering:** Suggested Fix for all three codes: _"This indicates a defect in dataset assembly. Report it."_
- **Example failed dataset:** **Current implementation does not expose this information** as achievable through normal use — this rule checks internal invariants `FeatureDatasetBuilder.build` already guarantees hold; it would only fire from a bug in the dataset builder itself.
- **Example successful dataset:** any dataset built through the normal `build_raw` path (always consistent by construction).

#### Rule detail: `feature_failures`

- **Returned JSON:** `{"rule": "feature_failures", "category": "feature", "severity": "warning", "code": "feature_generation_failed", "message": "Feature 'ema' failed to generate: Feature 'ema' needs at least 200 candles for these parameters; only 50 are available in this range", "details": {"error_code": "insufficient_data", "params": {"period": 200, "source": "close"}}}`.
- **Frontend rendering:** Suggested Fix: _"Adjust the failing feature's parameters (e.g. reduce a period that exceeds the available range), or remove it from the request."_
- **Example failed dataset:** request `ema` with `period=200` over a 50-candle range.
- **Example successful dataset:** every requested feature has enough candles and valid parameters.

### 2.7 Quality Score calculation

**Frontend-only heuristic** (`lib/quality-score.ts:1-35`) — **not** a backend field; the engine's contract is the pass/fail verdict plus the issue list, deliberately not a single blended number.

```text
penalty = errors × 15 + warnings × 5
score   = clamp(round(100 − penalty), 0, 100)
```

`info`-severity issues are never penalized. Bands (`qualityBand`): `score ≥ 90` → `"excellent"`; `≥ 70` → `"good"`; `≥ 40` → `"fair"`; else `"poor"`. Displayed color: excellent/good → `success.main`; fair → `warning.main`; poor → `error.main`. The card's own tooltip states outright: _"A simple heuristic for scanning many datasets quickly — not a scientific metric. Starts at 100 and subtracts 15 per error and 5 per warning, floored at 0."_

**Worked example:** 1 error + 1 warning → `100 − (1×15 + 1×5) = 80` → band `"good"`.

### 2.8 Validation report structure (full field list)

See [§2.5](#25-response-payload) for a full example. Field-by-field:

| Field                 | Type                                                                                       | Notes                                                                                      |
| --------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| `dataset_id`          | string (UUID4)                                                                             | The validated dataset's own build id — a fresh id per build, not a content hash.           |
| `symbol`, `timeframe` | string                                                                                     | —                                                                                          |
| `engine_version`      | string                                                                                     | Validation _engine's_ own version (`"1.0.0"`), independent of any single rule's `version`. |
| `validated_at`        | ISO-8601 UTC datetime                                                                      | —                                                                                          |
| `passed`              | bool                                                                                       | `false` only when `summary.errors > 0`.                                                    |
| `rules_run`           | `string[]`                                                                                 | Names actually run, in run order.                                                          |
| `summary`             | `{total_checks, errors, warnings, info}`                                                   | `total_checks` = total issue count (not rule count).                                       |
| `categories`          | `Record<"structural"\|"data_quality"\|"time_series"\|"feature", {errors, warnings, info}>` | Always all 4 keys present.                                                                 |
| `issues`              | `ValidationIssue[]`                                                                        | See [§2.6](#26-every-validation-rule) for the shape of each.                               |
| `rows`, `columns`     | int                                                                                        | Shape of the _validated_ dataset.                                                          |
| `duration_ms`         | float                                                                                      | Wall-clock time running every rule (not including the dataset build itself).               |

### 2.9 Presets

`COLUMN_PRESETS` (`lib/resolve-required-columns.ts:114-140`) — clicking a preset chip replaces **both** the feature selection and the required-columns list at once:

| Key                 | Label             | Resolves to (features)                                                                                  |
| ------------------- | ----------------- | ------------------------------------------------------------------------------------------------------- |
| `raw_market_data`   | Raw Market Data   | Every `category === "raw"` feature — today just `ohlcv`.                                                |
| `ohlcv_only`        | OHLCV Only        | Just the `ohlcv` feature.                                                                               |
| `trend_indicators`  | Trend Indicators  | Every `category === "trend"` feature — today `sma`, `ema`, `wma`.                                       |
| `ai_basic_features` | AI Basic Features | A hardcoded name list: `["ohlcv", "candle_shape", "sma"]`, filtered against what's actually registered. |
| `full_dataset`      | Full Dataset      | Every registered feature.                                                                               |

Applying a preset also seeds `required_columns` from the same resolved feature set's output columns (`resolveRequiredColumnOptions`) — never a hardcoded column list. A preset whose target category has no registered features resolves to an empty selection rather than erroring.

### 2.10 API endpoint / error responses

| HTTP                                  | `code`                      | Notes                                                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 404                                   | `validation_rule_not_found` | Raised when `rules` names an unregistered rule — **before any rule runs**. Message: `Validation rule '{name}' is not registered; available: {sorted 11 names}`.                                                                                                                                                                                                                                                     |
| (all of §1.13's dataset-build errors) | —                           | Since `/features/validate` builds a dataset first via `build_raw`, every error in [§1.13](#113-error-responses) can also occur here (`market_not_found`, `invalid_timeframe`, `invalid_range`, `limit_exceeded`, `candle_not_found`, `feature_not_found`, `invalid_feature_parameter`, `insufficient_data`, `duplicate_feature_column`, `empty_dataset`, `missing_feature_dependency`, `feature_execution_failed`). |

### 2.11 Loading / empty states

| Situation                               | UI                                                                                                                                   |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Markets or feature catalogue loading    | `PageSkeleton`, `role="status" aria-label="Loading dataset validation"`.                                                             |
| Validation rule catalogue loading       | `CatalogSkeleton` — three `Skeleton` bars, `role="status" aria-label="Loading validation rule catalogue"`.                           |
| Validation run in flight                | Submit button reads `"Validating…"`; right column shows two `Skeleton` bars, `role="status" aria-label="Running validation"`.        |
| No feature selected                     | Caption: `"Select at least one feature to validate a dataset."`                                                                      |
| Before any run                          | `GettingStarted` panel (What validation does / How to start / Example workflow).                                                     |
| Zero issues found                       | `ValidationIssueList` shows `"No issues — every structural, data-quality, time-series, and feature check passed."` (`role="status"`) |
| Filters exclude every issue             | `"No issues match the current filters."`                                                                                             |
| Export Issues with zero filtered issues | Button disabled.                                                                                                                     |

### 2.12 Export formats

Two independent JSON-only downloads (**no CSV export exists for this feature**):

| Button            | Location                                                                      | Content                                                                                                                                                                                               | Filename pattern                                        |
| ----------------- | ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| "Download Report" | `ValidationReportDownload`, header action of the "Validation Summary" section | The **entire** `ValidationReport` object, pretty-printed (`JSON.stringify(report, null, 2)`) — client-side only, no second backend request (the report is never truncated, unlike a feature dataset). | `{symbol}-{timeframe}-validation-{YYYYMMDDHHMMSS}.json` |
| "Export Issues"   | Inside `ValidationReportPanel`, above the issue list                          | Only the **currently filtered** `issues[]` array — narrower than the full report. Disabled when the filtered list is empty.                                                                           | `{symbol}-{timeframe}-issues-{YYYYMMDDHHMMSS}.json`     |

### 2.13 History

**Current implementation does not expose this information.** Like Feature Engineering, a validation run is never persisted server-side — there is no validation-run history list or database table. The only "history"-shaped affordance is `useRecentColumnsStore` (which _column names_ were recently added to Required Columns, `sessionStorage`, cap 8) — it does not store past reports.

---

## 3. ML Dataset Builder

**Page:** `/ml-datasets` — `apps/dashboard/src/features/ml-datasets/ml-datasets-page.tsx`
**Backend:** `services/api/app/ml_datasets/` (targets + composition engine), `app/models/ml_dataset_build.py` + `app/repositories/ml_dataset_builds.py` (Dataset History persistence), `app/services/ml_datasets.py`, `app/api/v1/endpoints/ml_datasets.py`, `app/schemas/ml_datasets.py`

This is the platform's **only supported path for producing a dataset used in AI training** (`ARCHITECTURE.md` § "ML Dataset Builder"). It composes three already-existing engines in a fixed order — it does not reimplement feature building, validation, or splitting:

1. `FeatureDatasetBuilder` builds the input matrix (unchanged, same engine as §1).
2. `TargetPipeline` generates prediction-target (label) columns and appends them onto the same matrix.
3. `DatasetValidator` (§2's engine) runs its full rule suite over the assembled feature+target matrix automatically.
4. `ChronologicalSplitter` slices the validated matrix into contiguous, time-ordered train/validation/test splits.

### 3.1 Page layout

1. **Section: "Dataset Configuration"** — `DatasetForm` (Market/Timeframe/Range/Start/End/Max rows — same component as §1.2, submit relabeled `"Build ML Dataset"`/`"Building…"`), captions for missing features/targets, **"Split Configuration"** subheading with `SplitConfigForm` (three ratio fields + `SplitTimeline` bar), **"Reproducibility"** subheading with `DatasetConfigActions` (Copy/Import Configuration).
2. **Section: "Dataset History"** — `DatasetHistoryTable` (paginated, sortable list of past builds).
3. Two-column `Grid`:
   - **Left** (`lg=4`): **"Features"** (`FeatureSelector`, shared with §1), **"Prediction Targets"** (`TargetSelector`), and — once a dataset is built — **"ML Dataset Information"** (`MLDatasetInfoCard`), **"Dataset Summary"** (`MLDatasetSummary`), **"Dataset Metadata"** (`MLDatasetMetadataPanel`), **"Export"** (`MLDatasetExport`).
   - **Right** (`lg=8`): build-in-progress skeleton / error `Alert` / empty-state `Paper`, or — once built — **"Validation Summary"** (`ValidationSummaryCards`, reused from §2), **"Dataset Preview"** (`DatasetPreviewTable`, with `targetColumns` and `splitLabels` props populated — the only page that uses those two props), **"Validation Report"** (`ValidationReportPanel`, reused from §2).
4. Two dialogs mounted at the page root: `DatasetHistoryDetailDialog` (reopens a past build) and `ConfirmActionDialog` (delete confirmation for a history row).

Source: `ml-datasets-page.tsx:266-476`.

### 3.2 Every field

**Dataset Configuration** — identical to [§1.2](#12-every-field-dataset-configuration-form) (`DatasetForm`), plus:

| Field                | Component                                                   | Required?   | Default | Allowed values       | Validation                                                                                                                                                                                                                                     |
| -------------------- | ----------------------------------------------------------- | ----------- | ------- | -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Train ratio**      | `TextField type="number"` (`aria-label="Train ratio"`)      | Yes (`> 0`) | `0.7`   | `0`–`1`, step `0.05` | Must be `> 0`; sum of all three must equal `1.0` (tolerance `1e-6`), else a `role="alert"` caption: `"Ratios must sum to 1.0 (currently {sum}).`" or `"The train ratio must be greater than zero."` or `"Each ratio must be zero or greater."` |
| **Validation ratio** | `TextField type="number"` (`aria-label="Validation ratio"`) | No          | `0.15`  | `0`–`1`, step `0.05` | May be `0`.                                                                                                                                                                                                                                    |
| **Test ratio**       | `TextField type="number"` (`aria-label="Test ratio"`)       | No          | `0.15`  | `0`–`1`, step `0.05` | May be `0`.                                                                                                                                                                                                                                    |

**Prediction Targets** (`TargetSelector`):

| Field                             | Component                                                                                                                                                                    | Required?    | Default                                                      | Allowed values                                                                                       | Validation                                                                                                              |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Prediction targets**            | MUI `Autocomplete` (`multiple`, `aria-label="Search prediction targets"`)                                                                                                    | At least one | none selected                                                | Any registered target (see [§3.9](#39-every-built-in-target))                                        | Submit disabled until ≥1 target selected.                                                                               |
| **Horizon** (per selected target) | `HorizonPresetSelect` — a `<select>` of presets (`1, 2, 3, 5, 10, 20, 50` candles, filtered to the target's own min/max) plus a `"Custom…"` option revealing a numeric field | No           | The target's `default_horizon` (`1` for all three built-ins) | Presets in range, or any custom integer within the target's declared `minimum`/`maximum` (`1`–`500`) | Same `validateValues` parameter-validation path every parameter form uses; invalid values are never committed to state. |

**Reproducibility** (`DatasetConfigActions`): "Copy Configuration" button (copies `{market, timeframe, range, start, end, limit, features[], targets[], split}` as JSON to the clipboard) and "Import Configuration" button (opens a dialog with a multiline paste field; "Apply" is disabled until non-empty, and a parse/validation failure shows an inline `role="alert"` naming the failing JSON path, e.g. `Invalid configuration at "split.train": ...`).

### 3.3 Every dropdown

| Dropdown                    | Options                                                                                 |
| --------------------------- | --------------------------------------------------------------------------------------- |
| Timeframe                   | Market's own stored timeframes (same as §1).                                            |
| Range                       | `all, today, yesterday, 24h, 7d, 30d, custom` (same as §1).                             |
| Max rows                    | `100, 250, 500, 1000` (same as §1).                                                     |
| Horizon preset (per target) | `1, 2, 3, 5, 10, 20, 50` candles filtered to the target's bounds, plus `"Custom…"`.     |
| Dataset History sort column | `symbol, timeframe, row_count, created_at` (clicking a column header toggles asc/desc). |

### 3.4 Every target (see also §3.9 for full parameter/example detail)

Selecting a target adds a `SelectedTargetCard` showing: label, a Classification/Regression `Chip` (from `value_type`), an `InfoTooltip` (purpose, output columns, horizon compatibility, version), its declared output column chips, the `HorizonPresetSelect`, any other declared parameter (none exist on any built-in target today), and a remove (`×`) button.

### 3.5 Every split configuration

Chronological only — **no random/stratified/k-fold split option exists on this page** (that lives in the Training Framework's cross-validation, §5, which is a separate concept). Fields: `train`, `validation`, `test` (fractions summing to `1.0`, `train > 0` required, `validation`/`test` may each be `0` — confirmed by the backend's own tested behavior `test_a_zero_ratio_split_is_allowed_for_validation_or_test`). Visualized live via `SplitTimeline` (a proportional horizontal bar, segments left-to-right in the actual chronological order applied: train, then validation, then test — never shuffled).

### 3.6 Every dataset metadata field

Three complementary panels, deliberately not merged (mirroring the "identity vs. trust" split from §1):

**`MLDatasetInfoCard`** (identity/versioning): ML Dataset ID (UUID4, fresh per build), Dataset ID (underlying feature build's own id), Market, Timeframe, Builder Version, Pipeline Version, Target Pipeline Version, Rows, Feature Columns (count), Target Columns (count), Split (ratios as `train / validation / test`), Split rows (`train_rows / validation_rows / test_rows`).

**`MLDatasetSummary`** (trust/quality): Validation status, Created at, Split strategy (fixed text: `"Chronological (train → validation → test)"`), Data range, Prediction target (`"{label} (h={horizon})"` per target), Target type (Classification/Regression, derived client-side), Features selected (count), Export formats, Original rows (`total_rows + rows_dropped_warmup + rows_dropped_horizon`), Final rows, Candles read, Rows dropped (warmup), Rows dropped (horizon), Largest horizon, Load time, plus conditional alerts for horizon-trimmed rows, failed features, and failed targets, plus a `Chip` per target (`"{label} v{version} (h={horizon})"`), plus a footer caption `"Builder v{version} · Target pipeline v{version} · generated {timestamp}"`.

**`MLDatasetMetadataPanel`** (provenance for a model card / lab notebook): Dataset UUID, Feature Pipeline Version, Validation Report ID (**honestly reuses** the embedded `ValidationReport.dataset_id`, since the validation engine mints no independent report id of its own), Source Market, Source Timeframe, Source Date Range, Generated Timestamp, Engine Version (validation engine's own), Target Generator (comma-joined target labels), Splitter (fixed text: `"ChronologicalSplitter"`), Export Formats.

### 3.7 Every API request

| Endpoint                                     | Method | Purpose                                                                                |
| -------------------------------------------- | ------ | -------------------------------------------------------------------------------------- |
| `/api/v1/ml/targets`                         | GET    | List every registered target generator.                                                |
| `/api/v1/ml/targets/{target}`                | GET    | One target's catalogue entry.                                                          |
| `/api/v1/markets/{symbol}/ml/dataset`        | POST   | Build, validate, split, and persist an ML dataset.                                     |
| `/api/v1/markets/{symbol}/ml/dataset/export` | POST   | Build the same dataset and stream it as CSV/JSON (`?format=csv\|json`, default `csv`). |
| `/api/v1/ml/dataset-builds`                  | GET    | Dataset History list (paginated, filterable, sortable).                                |
| `/api/v1/ml/dataset-builds/{build_id}`       | GET    | Reopen one past build's full record.                                                   |
| `/api/v1/ml/dataset-builds/{build_id}`       | DELETE | Remove one past build (204 No Content) — never touches underlying candles.             |

**Request payload** — `MLDatasetRequest` extends `FeatureDatasetRequest` (`app/schemas/ml_datasets.py:95-116`):

```json
{
  "timeframe": "1h",
  "start": "2026-01-01T00:00:00Z",
  "end": "2026-02-01T00:00:00Z",
  "limit": 500,
  "features": [{ "feature": "sma", "params": { "period": 20 } }],
  "targets": [{ "target": "next_return", "params": { "horizon": 1 } }],
  "drop_warmup": true,
  "drop_undefined_targets": true,
  "split_train": 0.7,
  "split_validation": 0.15,
  "split_test": 0.15,
  "preview_rows": 200
}
```

| Field                    | Type                        | Required | Default | Constraints                                                        |
| ------------------------ | --------------------------- | -------- | ------- | ------------------------------------------------------------------ |
| `targets`                | array of `{target, params}` | Yes      | —       | `min_length=1, max_length=20`.                                     |
| `drop_undefined_targets` | bool                        | No       | `true`  | Drops trailing rows where any requested target is still undefined. |
| `split_train`            | float                       | No       | `0.7`   | `ge=0.0, le=1.0`.                                                  |
| `split_validation`       | float                       | No       | `0.15`  | `ge=0.0, le=1.0`.                                                  |
| `split_test`             | float                       | No       | `0.15`  | `ge=0.0, le=1.0`.                                                  |

Every field from `FeatureDatasetRequest` (`timeframe`, `start`, `end`, `limit`, `features`, `drop_warmup`, `preview_rows`) applies identically to §1.5.

### 3.8 Every API response

`MLDatasetResponse` (`app/schemas/ml_datasets.py:201-312`) — a superset of `FeatureDatasetResponse` (§1.6) plus target/split/validation fields:

```json
{
  "ml_dataset_id": "1a2b3c4d-...-uuid4",
  "dataset_id": "b6f1c2a4-...-uuid4",
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "columns": [
    { "name": "open", "label": "Open", "dtype": "float" },
    "...",
    { "name": "next_return_1", "label": "Next Return (1)", "dtype": "float" }
  ],
  "feature_columns": ["open", "high", "low", "close", "volume"],
  "target_columns": ["next_return_1"],
  "timestamps": ["2026-01-01T00:00:00Z"],
  "rows": [[3200.5, 3210.0, 3190.2, 3201.0, 812.4, 0.0031]],
  "split": ["train"],
  "features": [
    {
      "feature": "ohlcv",
      "label": "OHLCV",
      "version": "1.0.0",
      "parameters": {},
      "columns": ["open", "high", "low", "close", "volume"],
      "warmup": 0,
      "execution_time_ms": 0.3,
      "cache_status": "miss"
    }
  ],
  "targets": [
    {
      "target": "next_return",
      "label": "Next Candle Return",
      "version": "1.0.0",
      "parameters": { "horizon": 1 },
      "columns": ["next_return_1"],
      "horizon": 1,
      "execution_time_ms": 0.2
    }
  ],
  "target_failures": [],
  "split_ratios": { "train": 0.7, "validation": 0.15, "test": 0.15 },
  "split_bounds": { "train_rows": 336, "validation_rows": 72, "test_rows": 72 },
  "quality": {
    "total_rows": 481,
    "rows_returned": 480,
    "rows_removed": 1,
    "null_counts": {},
    "duplicate_timestamps": 0,
    "missing_candles": 0,
    "feature_failures": [],
    "generation_time_ms": 2.3
  },
  "validation": {
    "dataset_id": "b6f1c2a4-...",
    "passed": true,
    "summary": { "total_checks": 0, "errors": 0, "warnings": 0, "info": 0 },
    "categories": { "structural": { "errors": 0, "warnings": 0, "info": 0 } },
    "issues": [],
    "rules_run": ["data_types", "..."],
    "rows": 480,
    "columns": 6,
    "duration_ms": 1.1,
    "engine_version": "1.0.0",
    "validated_at": "2026-01-31T23:00:05Z",
    "symbol": "ETHUSD",
    "timeframe": "1h"
  },
  "meta": {
    "row_count": 200,
    "total_rows": 480,
    "candles_analyzed": 500,
    "rows_dropped_warmup": 20,
    "rows_dropped_horizon": 1,
    "warmup_candles": 20,
    "max_horizon": 1,
    "truncated": true,
    "database_time_ms": 4.7,
    "pipeline_version": "1.0.0",
    "target_pipeline_version": "1.0.0",
    "builder_version": "1.0.0",
    "generated_at": "2026-01-31T23:00:00Z",
    "created_at": "2026-01-31T23:00:05Z"
  }
}
```

`quality.feature_failures` also carries any **target** failure recorded during assembly (the dataset builder merges `target_failures` into `quality.feature_failures` on the combined dataset — see `app/ml_datasets/dataset.py:297`), while the top-level `target_failures[]` array on the response repeats them in a target-specific shape (`{target, params, error_code, error_detail}`) for the frontend's own target-failure alert.

### 3.9 Every built-in target

Three built-in targets, registered from `app/ml_datasets/targets/` — confirmed exhaustive via the endpoint's own 404 example (`ml_datasets.py:99-100`): `next_close, next_direction, next_return`.

#### `next_close` — Next Closing Price

- **Description:** "The raw closing price `horizon` candles ahead of each row."
- **Category:** `price`. **Problem type (frontend-derived):** Regression (`value_type: "float"`).
- **Parameters:** `horizon` (int, label "Horizon", default `1`, min `1`, max `500`).
- **Output columns:** `next_close_{horizon}` — e.g. `next_close_1`. `dtype: "float"`.
- **Horizon requirement:** the last `horizon` rows of the range have no computable value (mirror image of warmup, at the _end_ of the series) — enforced by `TargetPipeline._verify_forward_looking_contract`.
- **Example output:** closes `[10, 20, 30, 40]`, `horizon=1` → `next_close_1 = [20.0, 30.0, 40.0, null]`.

#### `next_return` — Next Candle Return

- **Description:** "Fractional price change from this row's close to the close `horizon` candles ahead: (future - current) / current."
- **Category:** `return`. **Problem type:** Regression.
- **Parameters:** `horizon` (int, default `1`, min `1`, max `500`).
- **Output columns:** `next_return_{horizon}`, `dtype: "float"`.
- **Special case:** a row whose _current_ close is exactly `0.0` reports `null` (undefined percentage return) rather than raising or dividing by zero — real market data never has a zero close, but the generator must not crash if it somehow did.
- **Example output:** closes `[100, 110, 99]`, `horizon=1` → `next_return_1 = [0.10, -0.10, null]` (row 0: `(110-100)/100`; row 1: `(99-110)/110`; row 2: undefined, no future candle).

#### `next_direction` — Next Candle Direction

- **Description:** "Whether the close `horizon` candles ahead is higher ('up'), lower ('down'), or unchanged ('flat') relative to this row's close."
- **Category:** `direction`. **Problem type:** Classification (`value_type: "categorical"`).
- **Parameters:** `horizon` (int, default `1`, min `1`, max `500`).
- **Output columns:** `next_direction_{horizon}`, `dtype: "categorical"` (values: `"up"`, `"down"`, `"flat"`).
- **Example output:** closes `[100, 110, 100, 100]`, `horizon=1` → `next_direction_1 = ["up", "down", "flat", null]`.

All three share the exact `HORIZON_PARAMETER` spec (`app/ml_datasets/targets/common.py:17-25`): `default=1, minimum=1, maximum=500`. `TargetNotFoundError` message pattern: `Target '{name}' is not registered; available: next_close, next_direction, next_return`.

### 3.10 Dataset ID generation

Two independent, layered ids per build, both fresh UUID4s (never content hashes — a rebuild of the identical request always produces new ids):

- **`dataset_id`** — minted by the underlying `FeatureDatasetBuilder.build` (`str(uuid.uuid4())`, `app/features/dataset.py:295`) — identifies the feature-matrix-only build.
- **`ml_dataset_id`** — minted separately by `MLDatasetBuilder.build` (`str(uuid.uuid4())`, `app/ml_datasets/dataset.py:319`) — identifies the _complete_ artifact (feature build + target generation + validation + split bundled together).

Both persist verbatim into `MLDatasetBuild.ml_dataset_id` (indexed `String(64)`) when a build is recorded to Dataset History; the row's own primary key (`MLDatasetBuild.id`, a separate server-generated UUID via `BaseModel.id`) is the id used by `GET`/`DELETE /ml/dataset-builds/{build_id}` — **three distinct identifiers exist per persisted build**, each answering a different question (this exact artifact / this exact feature build / this history-table row).

### 3.11 Validation summary

Embedded verbatim: `dataset.validation` is the **exact same `ValidationReportResponse` shape** documented in [§2.5](#25-response-payload)/[§2.8](#28-validation-report-structure-full-field-list) — rendered on this page via the identical `ValidationSummaryCards` and `ValidationReportPanel` components §2 uses (imported, not re-implemented). The one difference from a standalone `/features/validate` call: this validation runs automatically over the **feature+target combined matrix**, so its `rules_run`/`issues`/`columns` reflect target columns too (e.g. a `data_types` issue could in principle be reported against a target column, though no built-in target is known to trip it).

### 3.12 Preview table

Same `DatasetPreviewTable` component as §1.11, but invoked with two additional props this page (and only this page) supplies:

- `targetColumns={dataset.target_columns}` — each such column's header renders a `"target"` `Chip` and a tinted background (`action.selected`/`action.hover`), and its `InfoTooltip` gains a `"Role: Prediction target (label), not a model input."` section.
- `splitLabels={dataset.split}` — adds a trailing **Split** column showing a colored `Chip` (`train`/`validation`/`test`) per row.

### 3.13 Export behavior

Two formats (CSV, JSON) — **confirmation-gated**, unlike Feature Engineering's direct-download export: clicking "CSV" or "JSON" opens `ExportSummaryDialog` first (Rows, Columns, Target column names, Split percentages, Format, an _approximate_ size estimate with an explicit "not an exact byte count" disclaimer) before the actual download fires on "Export" confirm.

| Format | Extension | Media type                        | Contents                                                                                                                                                                                                                                                                                                                                                          |
| ------ | --------- | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CSV    | `.csv`    | `text/csv; charset=utf-8`         | `#`-prefixed metadata preamble (ids, versions, row-drop counts, split row counts, per-target provenance lines, validation pass/error/warning counts) + header row (`timestamp, <feature+target columns>, split`) + one data row per surviving candle, **with a trailing `split` column** on every row.                                                            |
| JSON   | `.json`   | `application/json; charset=utf-8` | Full provenance object: `ml_dataset_id`, `dataset_id`, versions (pipeline/target-pipeline/builder), `feature_columns`, `target_columns`, `columns[]`, `features[]`, `targets[]`, `split_ratios`, `split_bounds`, `validation` (passed/engine_version/summary/issues), `meta`, and `data[]` (one record per row, each carrying every column plus a `split` field). |

Both formats are always the **complete, unsplit-file** artifact — concatenating rows labeled `train` → `validation` → `test` in file order exactly reconstructs the pre-split matrix, since `MLDatasetBuilder` never reorders rows. `preview_rows` is stripped by the frontend before an export request and has no effect on `/ml/dataset/export`. Filename pattern (frontend download): `{symbol}-{timeframe}-ml-dataset.{ext}` (backend's own stamped name for `Content-Disposition` differs slightly: `{symbol}-{timeframe}-ml-dataset-{YYYYMMDDTHHMMSSZ}.{ext}`).

### 3.14 Every Dataset History column

`MLDatasetBuildSummaryDTO` (list view, `app/schemas/ml_datasets.py:315-351`) — metadata only, never the full row-including payload:

| Column    | Type                                                                                  | Source                                       |
| --------- | ------------------------------------------------------------------------------------- | -------------------------------------------- |
| Symbol    | string                                                                                | `MLDatasetBuild.symbol`                      |
| Timeframe | string                                                                                | `MLDatasetBuild.timeframe`                   |
| Rows      | int (tooltip: `"{feature_count} feature column(s), {target_count} target column(s)"`) | `row_count`, `feature_count`, `target_count` |
| Built     | datetime (`toLocaleString()`)                                                         | `created_at`                                 |
| Quality   | `Chip` — `"Passed"` (success) / `"Failed"` (error)                                    | `quality_passed`                             |
| Actions   | delete `IconButton`                                                                   | —                                            |

Table is sortable (click a column header) on 4 backend-supported columns (`symbol, timeframe, row_count, created_at`; default `created_at desc`), paginated (`TablePagination`, fixed page size `10` set client-side, `rowsPerPageOptions={[]}` — the page size itself is not user-adjustable in the UI though the API supports any `limit` up to `100`), and every row is clickable (opens `DatasetHistoryDetailDialog`) and keyboard-activatable (`Enter`/`Space`).

### 3.15 Every stored JSON field

`MLDatasetBuild` ORM model (`app/models/ml_dataset_build.py:32-58`), table `ml_dataset_builds`:

| Column                     | Type                      | Notes                                                                                       |
| -------------------------- | ------------------------- | ------------------------------------------------------------------------------------------- |
| `id`                       | UUID (PK)                 | `BaseModel`'s surrogate key, `uuid.uuid4()` default.                                        |
| `created_at`, `updated_at` | `DateTime(timezone=True)` | `TimestampMixin`, server-defaulted `now()`.                                                 |
| `ml_dataset_id`            | `String(64)`, indexed     | The engine's own per-build id, duplicated for lookup.                                       |
| `symbol`                   | `String(50)`, indexed     | —                                                                                           |
| `timeframe`                | `String(20)`              | —                                                                                           |
| `row_count`                | int                       | Denormalized from `payload`, for a cheap list view.                                         |
| `column_count`             | int                       | —                                                                                           |
| `feature_count`            | int                       | —                                                                                           |
| `target_count`             | int                       | —                                                                                           |
| `quality_passed`           | bool                      | The Dataset Validation Engine's verdict for this build.                                     |
| `payload`                  | JSON                      | The **full, untruncated** `MLDatasetResponse` (rows included) as `model_dump(mode="json")`. |

Persistence happens inside `MLDatasetService._record_build`, called by `build_dataset` (the `POST /ml/dataset` path) only — **never** by `build_ml_dataset` (the internal seam the Training Framework uses to get real training data) or `export_dataset` (never by a re-export of an already-recorded build). It is **best-effort**: a persistence failure is logged and swallowed, never failing the build response itself (mirrors `TrainingJobService`'s own "don't let bookkeeping sink the primary outcome" precedent).

### 3.16 Error responses

All of [§1.13](#113-error-responses)'s dataset-build errors apply (this endpoint builds the same underlying feature dataset), plus:

| HTTP | `code`                       | Message pattern                                                                                                                                                                                                                                                                         |
| ---- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 404  | `target_not_found`           | `Target '{name}' is not registered; available: next_close, next_direction, next_return`                                                                                                                                                                                                 |
| 400  | `invalid_target_parameter`   | `Target '{target}': {reason}`                                                                                                                                                                                                                                                           |
| 400  | `insufficient_data`          | `Target '{target}' needs at least {horizon+1} candles for horizon={horizon}; only {available} are available in this range` (shared code with the feature/indicator engines)                                                                                                             |
| 500  | `target_execution_failed`    | `Target '{target}' failed during generation: {ExceptionType}: {message}`                                                                                                                                                                                                                |
| 500  | `target_alignment_error`     | `Target '{target}' violated its forward-looking contract: {reason}` (a generator bug, never triggerable by a normal request)                                                                                                                                                            |
| 400  | `duplicate_target_column`    | `Column '{col}' would be produced by both '{a}' and '{b}'; request them with different parameters or drop one` — between two targets, **or** a target and a feature (a target column silently replacing an input feature or vice versa).                                                |
| 400  | `invalid_split_ratios`       | `Invalid split ratios: {reason}` — e.g. `train + validation + test must sum to 1.0, got 1.1 (train=0.7, validation=0.2, test=0.2)`, or `train must be > 0 — a dataset with no training rows is useless`.                                                                                |
| 400  | `empty_ml_dataset`           | `Every row was dropped: {candles} candles were loaded but the requested features need {warmup} candles of warmup and the requested targets need {horizon} candles of horizon at the end. Widen the date range, reduce the largest feature period, or reduce the largest target horizon` |
| 404  | `ml_dataset_build_not_found` | `ML dataset build {id} not found` (GET/DELETE on an unknown history id)                                                                                                                                                                                                                 |
| 400  | `invalid_sort`               | `Unsupported sort '{sort}' (direction '{dir}'); supported columns: created_at, row_count, symbol, timeframe, directions: asc, desc` (Dataset History list)                                                                                                                              |

`insufficient_data`/`invalid_target_parameter`/`target_not_found`/`target_execution_failed` on **one requested target among several** do not fail the whole request (recorded in `target_failures[]`, the rest still builds — mirrors the Feature Engineering partial-success contract exactly). `duplicate_target_column` and `invalid_split_ratios` still fail the whole request.

### 3.17 Loading / empty states

| Situation                                               | UI                                                                                                                               |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Markets, feature catalogue, or target catalogue loading | `PageSkeleton`, `role="status" aria-label="Loading ML dataset builder"`.                                                         |
| Target catalogue loading (selector alone)               | `SelectorSkeleton`, `role="status" aria-label="Loading target catalogue"`.                                                       |
| No targets registered                                   | `"No target generators are registered."`                                                                                         |
| No feature selected                                     | Caption: `"Select at least one feature to build a dataset."`                                                                     |
| No target selected                                      | Caption: `"Select at least one prediction target to build a dataset."`                                                           |
| Invalid split ratios                                    | Caption (`role="alert"`, red) replaces the `SplitTimeline` visualization entirely.                                               |
| Build in flight                                         | Submit button `"Building…"`; right column shows two `Skeleton`s, `role="status" aria-label="Building ML dataset"`.               |
| No dataset built yet                                    | Right column `Paper`: `"Choose a market, timeframe, features, and prediction targets, then build a dataset to preview it here."` |
| Dataset History loading                                 | `LoadingRows` — 5 skeleton `<TableRow>`s.                                                                                        |
| Dataset History empty                                   | `"No datasets built yet — use the builder above, and it will appear here."` (`role="status"`)                                    |
| Reopening a history entry (loading)                     | `CircularProgress`, `aria-label="Loading dataset build"`, inside the detail dialog.                                              |
| Reopening a history entry (error)                       | `role="alert"`: `"Failed to load this dataset build."` (or the API's own message).                                               |

### 3.18 History (Dataset History — fully implemented, unlike §1/§2)

This is the one workbench of the three covered so far with real, persisted history. Every successful `POST /ml/dataset` call is recorded (best-effort) to the `ml_dataset_builds` table and immediately listable/reopenable/deletable via the three endpoints in [§3.7](#37-every-api-request). The frontend invalidates its own `['ml-datasets', 'history']` TanStack Query cache key on every successful build or delete, so a new build appears in the table without a manual refresh.

---

## 4. Experiment Management

**Pages:** `/experiments` (list) and `/experiments/{id}` (detail) — `apps/dashboard/src/features/experiments/experiments-page.tsx` / `experiment-detail-page.tsx`
**Backend:** `services/api/app/models/experiment.py`, `app/repositories/experiments.py`, `app/services/experiments.py`, `app/api/v1/endpoints/experiments.py`, `app/schemas/experiments.py`

An `Experiment` is a **registry entry**, not a computation: recording one never builds a dataset or trains a model. `feature_set`/`target_config`/`split_config`/`dataset_version` are opaque, copied strings/JSON — a citation of an ML Dataset Builder run (which is never itself persisted as a queryable relation, only as `ml_dataset_id`/`dataset_id` strings — except via Dataset History, §3.18, which an experiment does not reference by foreign key either). **`model_type` on `Experiment` is explicitly documented as "a placeholder label only — no training engine exists yet"** at the model layer; the _real_ model-training concept lives on `TrainingJob` (§5), a separate table.

### 4.1 Every create form field

`CreateExperimentDialog` (`components/create-experiment-dialog.tsx:34-151`):

| Field               | Component                                                      | Required?               | Default   | Allowed values                                                   | Validation                                                                     |
| ------------------- | -------------------------------------------------------------- | ----------------------- | --------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| **Name**            | `TextField` (`aria-label="Experiment name"`, `autoFocus`)      | Yes                     | `''`      | Any non-empty string, ≤200 chars server-side                     | Submit ("Create Experiment") disabled until `name.trim().length > 0`.          |
| **Dataset version** | `TextField`                                                    | No                      | `''`      | Free text (typically an `ml_dataset_id`), ≤200 chars server-side | None client-side.                                                              |
| **Model type**      | `TextField`                                                    | No                      | `''`      | Free text (placeholder label), ≤100 chars server-side            | None.                                                                          |
| **Status**          | `TextField select`                                             | No (always has a value) | `'draft'` | `draft, running, completed, failed, archived`                    | None — any status is directly selectable at creation.                          |
| **Tags**            | `Autocomplete` (`multiple, freeSolo`, no predefined `options`) | No                      | `[]`      | Any typed string (Enter commits it as a chip)                    | Server caps at 32 tags (`max_length=32`); not separately enforced client-side. |
| **Notes**           | `TextField multiline` (4 rows)                                 | No                      | `''`      | Any free text                                                    | None.                                                                          |

Feature set / target config / split config are **not editable in this dialog at all** — the form's own docstring states a researcher is expected to copy those from the ML Dataset Builder's "Copy Configuration" action instead (§3.2) rather than retype them; there is no UI path to set them at creation time (though the API accepts them — see §4.3).

### 4.2 Every edit field

`ExperimentDetailPage` composes four independently-saving panels — there is no single "Save" button; each panel's own action commits immediately via its own `PATCH`:

| Panel                     | Field(s)                                                                                     | Editable?                                                                                                           | Save mechanism                                                                                                            |
| ------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `ExperimentMetadataPanel` | Status                                                                                       | **Yes** — the one metadata field this panel lets a researcher change                                                | `TextField select`, commits immediately on change (`onStatusChange` → `PATCH {status}`).                                  |
| `ExperimentMetadataPanel` | Dataset version, Feature set, Target, Split configuration, Model type, Created, Last updated | **No** — read-only display, rendered from `describeFeatureSet`/`describeTargetConfig`/`describeSplitConfig` helpers | —                                                                                                                         |
| `ExperimentNotesCard`     | Notes                                                                                        | Yes                                                                                                                 | Toggles into an edit `TextField` (4 rows) on pencil-icon click; "Save" (`PATCH {notes}`) / "Cancel" (discards the draft). |
| `ExperimentTagsEditor`    | Tags                                                                                         | Yes                                                                                                                 | Always-live `Autocomplete` — every add/remove commits immediately (`PATCH {tags}`, replaces the full tag set).            |
| `ExperimentMetricsTable`  | Add a metric (Name/Value/Unit inline fields)                                                 | Yes (add/delete only, no in-place edit of an existing metric)                                                       | `POST /experiments/{id}/metrics` / `DELETE .../metrics/{metric_id}`.                                                      |
| `ExperimentArtifactsList` | Add an artifact (Type dropdown/URI/Description)                                              | Yes (add/delete only)                                                                                               | `POST /experiments/{id}/artifacts` / `DELETE .../artifacts/{artifact_id}`.                                                |

There is **no enforced status-transition graph** anywhere in this system (unlike `TrainingJob`'s real state machine, §5.7) — the status `<select>` always offers all 5 values regardless of the current one, and the backend's `ExperimentService.update` applies any submitted status unconditionally (only a DB `CheckConstraint` restricts it to the 5 valid strings, not to a valid _transition_).

### 4.3 Every API endpoint

| Endpoint                                           | Method | Purpose                                                                                                                                                                |
| -------------------------------------------------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/api/v1/experiments`                              | POST   | Register a new experiment (201).                                                                                                                                       |
| `/api/v1/experiments`                              | GET    | Search/filter/sort/paginate experiments.                                                                                                                               |
| `/api/v1/experiments/{id}`                         | GET    | One experiment's full record (metrics + artifacts included).                                                                                                           |
| `/api/v1/experiments/{id}`                         | PATCH  | Partial update (`exclude_unset` semantics — only fields present in the body are changed; sending `tags` replaces the full tag set, omitting it leaves tags untouched). |
| `/api/v1/experiments/{id}`                         | DELETE | Permanently delete (204), cascading to its metrics/artifacts/tags.                                                                                                     |
| `/api/v1/experiments/{id}/metrics`                 | POST   | Record a metric (201).                                                                                                                                                 |
| `/api/v1/experiments/{id}/metrics/{metric_id}`     | DELETE | Delete a metric (204).                                                                                                                                                 |
| `/api/v1/experiments/{id}/artifacts`               | POST   | Record an artifact reference (201).                                                                                                                                    |
| `/api/v1/experiments/{id}/artifacts/{artifact_id}` | DELETE | Delete an artifact reference (204).                                                                                                                                    |

### 4.4 Complete Experiment schema

`ExperimentResponse` (`app/schemas/experiments.py:162-201`):

```json
{
  "id": "6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90",
  "name": "Baseline logistic regression",
  "dataset_version": "1a2b3c4d-...-uuid4",
  "feature_set": [{ "feature": "sma", "params": { "period": "20" } }],
  "target_config": [{ "target": "next_direction", "params": { "horizon": "1" } }],
  "split_config": { "train": 0.7, "validation": 0.15, "test": 0.15 },
  "model_type": "xgboost_baseline",
  "status": "draft",
  "notes": "First attempt, default hyperparameters.",
  "tags": ["baseline"],
  "metrics": [
    {
      "id": "...",
      "name": "accuracy",
      "value": 0.62,
      "unit": null,
      "recorded_at": "2026-01-31T23:10:00Z"
    }
  ],
  "artifacts": [
    {
      "id": "...",
      "artifact_type": "dataset_export",
      "uri": "ETHUSD-1h-ml-dataset.csv",
      "description": "Training export",
      "created_at": "2026-01-31T23:05:00Z"
    }
  ],
  "created_at": "2026-01-31T23:00:00Z",
  "updated_at": "2026-01-31T23:10:00Z"
}
```

Every field's exact type/nullability is restated here for clarity: `id`/`name`/`status`/`tags` (never null); `dataset_version`/`model_type`/`notes` (nullable string); `feature_set`/`target_config`/`split_config` (nullable arrays/object — `null` distinct from `[]`/`{}`, meaning "never recorded" vs. "recorded as empty"); `metrics`/`artifacts` (always arrays, never null, empty when none recorded); `created_at`/`updated_at` (ISO-8601 UTC).

### 4.5 Status transitions

Valid values (`EXPERIMENT_STATUSES`, `app/models/experiment.py:42`): `draft, running, completed, failed, archived`. Default on creation: `draft`. **No transition graph is enforced anywhere** — a DB `CheckConstraint` (`status_valid`) only restricts the _set_ of values, and both the create form and the detail page's status `<select>` always offer all 5 unconditionally. Any status can be set to any other status directly (e.g. `archived` → `draft` is accepted with no special handling), a deliberate contrast with `TrainingJob`'s real state machine (§5.7).

### 4.6 Metric storage

`ExperimentMetric` (`app/models/experiment.py:138-159`) — one row per recorded number, not a JSON blob: `id` (UUID), `experiment_id` (FK, cascade-delete), `name` (string, ≤100 chars), `value` (float, **required, no unit conversion or validation of magnitude**), `unit` (nullable string, ≤32 chars, freeform — e.g. `"%"`, `"USD"`, or omitted), `recorded_at` (server-defaulted `now()` — **not settable by the caller**, always "when the API call happened", not "when the measurement was taken"). Indexed on `(experiment_id, name)`. **No training engine writes these automatically today** — a researcher records them by hand from whatever they measured elsewhere (there is no automatic bridge from a Training Job's own evaluation metrics, §5.11, into an Experiment's metrics table).

### 4.7 Artifacts

`ExperimentArtifact` (`app/models/experiment.py:165-193`) — a **reference only, never file content** (this platform has no object storage wired in — `ARCHITECTURE.md` § "Known Limitations"). Fields: `id`, `experiment_id` (FK, cascade-delete), `artifact_type` (one of `ARTIFACT_TYPES`: `dataset_export, model_checkpoint, report, plot, other`, DB-enforced via `CheckConstraint`), `uri` (string, ≤1024 chars — a file path, export filename, or URL — **not validated as a real, reachable path or URL**), `description` (nullable free text), `created_at`. A `dataset_export` entry would typically be the filename an ML Dataset Builder export was saved as (§3.13), recorded manually.

### 4.8 Tags

`ExperimentTag` (`app/models/experiment.py:113-135`) — normalized as its own table (not a JSON array), `UniqueConstraint(experiment_id, tag)` preventing a duplicate tag on the same experiment. `PATCH .../experiments/{id}` with a `tags` field **replaces the entire tag set** (`ExperimentRepository.replace_tags` — dedupes, order-preserving, deletes any tag no longer present, inserts any new one); omitting `tags` from a `PATCH` body leaves the existing set completely untouched (`exclude_unset` semantics). Max 32 tags per request (`max_length=32` on both create and update schemas).

### 4.9 Filtering

`GET /experiments` query parameters (`app/api/v1/endpoints/experiments.py:103-140`):

| Param             | Type                    | Match                                                                             | Frontend exposure                                                   |
| ----------------- | ----------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `q`               | string                  | Case-insensitive substring, `OR`-ed across `name` **and** `notes` (`ILIKE '%q%'`) | "Search name or notes…" field.                                      |
| `status`          | one of 5 valid statuses | Exact                                                                             | "Status" dropdown (`"All statuses"` + the 5 values).                |
| `model_type`      | string                  | Exact                                                                             | **Not exposed in the UI** — API-only; no filter control renders it. |
| `dataset_version` | string                  | Exact                                                                             | **Not exposed in the UI** — API-only.                               |
| `tag`             | string                  | Exact (single tag only — no multi-tag AND/OR)                                     | "Tag" free-text field.                                              |

### 4.10 Searching

Covered by `q` above — substring, case-insensitive, over `name` OR `notes` only (never over `dataset_version`, `model_type`, `feature_set`, or `tags`' content — a researcher must use the dedicated `tag`/`model_type`/`dataset_version` filters for those).

### 4.11 Sorting

Whitelisted columns (`SORT_COLUMNS`, `app/repositories/experiments.py:30-36`): `name, status, model_type, created_at, updated_at`. Default: `created_at desc`. An invalid column or direction raises `invalid_sort` (400) — see [§4.14](#414-error-responses). The frontend table's column headers (`TableSortLabel`) drive this directly; clicking the active column flips direction, clicking a new column sets it `asc`.

### 4.12 Pagination

`limit`/`offset`, server default `50`, server max `200` (`experiments_default_limit`/`experiments_max_limit`, `app/core/config.py:44-45`). Frontend fixes its own page size at `PAGE_SIZE = 20` (`experiments-page.tsx:19`) via `TablePagination` with `rowsPerPageOptions={[]}` — the page size is not user-adjustable in the UI, though the API itself accepts any value up to 200.

### 4.13 PATCH examples

**Change only status** (notes/tags/everything else untouched):

```json
PATCH /api/v1/experiments/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90
{ "status": "completed" }
```

**Replace notes only:**

```json
{ "notes": "Rerun with period=50 improved accuracy to 0.68." }
```

**Replace the full tag set** (clears any tag not listed):

```json
{ "tags": ["baseline", "sma-only"] }
```

**Clear a nullable field explicitly** (an explicit `null` clears `model_type` — distinguished from omitting the key, which leaves it untouched, via Pydantic's `exclude_unset`):

```json
{ "model_type": null }
```

### 4.14 Error responses

| HTTP | `code`                 | Message pattern                                                                                                                             |
| ---- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| 404  | `experiment_not_found` | `Experiment {id} not found`                                                                                                                 |
| 404  | `metric_not_found`     | `Metric {id} not found`                                                                                                                     |
| 404  | `artifact_not_found`   | `Artifact {id} not found`                                                                                                                   |
| 400  | `invalid_sort`         | `Unsupported sort '{sort}' (direction '{dir}'); supported columns: created_at, model_type, name, status, updated_at, directions: asc, desc` |

### 4.15 Loading / empty states

| Situation                     | UI                                                                          |
| ----------------------------- | --------------------------------------------------------------------------- |
| List page loading             | `LoadingRows` — 5 skeleton `<TableRow>`s in the experiments table.          |
| List page error               | `role="alert"` `Alert` with a Retry button.                                 |
| No experiments match          | `"No experiments match this search/filter."` (`role="status"`, list table). |
| Detail page loading           | `PageSkeleton`, `role="status" aria-label="Loading experiment"`.            |
| Detail page error / not found | `role="alert"` `Alert` with a Retry button.                                 |
| No metrics recorded           | `"No metrics recorded yet."`                                                |
| No artifacts recorded         | `"No artifacts recorded yet."`                                              |
| No notes                      | `"No notes yet."` (shown in muted `text.secondary` color).                  |

### 4.16 Not implemented — explicitly

Per the user's request scope (Compare, Clone, Parent/Child, Timeline, Rich Notes formatting, Templates): **Current implementation does not expose this information** for all six — none of the following exist anywhere in the backend or frontend as of this writing:

- **Experiment Compare** — no multi-experiment comparison view exists for Experiment Management itself (Model Evaluation's own Benchmark page, §6, compares **Training Jobs**, a different entity, not `Experiment` rows).
- **Clone Experiment** — no duplicate/clone action exists; creating a new experiment always starts from the blank `CreateExperimentDialog` form.
- **Parent/Child Experiments** — the `Experiment` model has no self-referential foreign key or lineage field of any kind.
- **Timeline** — no chronological/activity-log view of an experiment's history (status changes, metric additions) exists; only `created_at`/`updated_at` timestamps are tracked, with no audit trail of _what_ changed between them.
- **Rich Notes** — `notes` is a single unformatted `Text` column, rendered/edited as plain text (`TextField multiline`) — no markdown rendering, formatting toolbar, or attachments.
- **Experiment Templates** — no saved-configuration/template mechanism exists for pre-filling `CreateExperimentDialog`; the closest analog is the ML Dataset Builder's own unrelated "Copy/Import Configuration" (§3.2), which only round-trips a dataset-build config, not an experiment record.

---

## 5. ML Training Framework

**Page:** `/ml/training` (list) with an in-page detail dialog (no separate route) — `apps/dashboard/src/features/ml-training/ml-training-page.tsx`
**Backend:** `services/api/app/models/training.py`, `app/training/` (pipeline, registry, base contract, 3 adapters, dataset loader, interpretability, serialization, artifact files, error reporting, state machine), `app/repositories/training.py`, `app/services/training.py`, `app/api/v1/endpoints/training.py`, `app/schemas/training.py`

Three model adapters are registered today (`app/training/adapters/`): **`placeholder`** (fabricates deterministic metrics, `requires_real_data=false`, no real framework runs behind it), **`logistic_regression`** (a real scikit-learn `LogisticRegression` baseline classifier, `requires_real_data=true`), and **`linear_regression`** (a real scikit-learn `LinearRegression` baseline regressor, `requires_real_data=true`). No worker/queue service exists — `POST /training-jobs/{id}/run` blocks synchronously for the run's duration.

### 5.1 Every Training Job field

`TrainingJob` ORM model (`app/models/training.py:48-124`) / `TrainingJobResponse` (`app/schemas/training.py:98-151`):

| Field                         | Type                           | Nullable | Notes                                                                                                                        |
| ----------------------------- | ------------------------------ | -------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `id`                          | UUID                           | No       | —                                                                                                                            |
| `experiment_id`               | UUID (FK, `ON DELETE CASCADE`) | No       | The linked experiment — a real row, not a citation string.                                                                   |
| `dataset_version`             | string                         | Yes      | Defaults from the linked experiment's own `dataset_version` at creation if omitted.                                          |
| `symbol`                      | string                         | Yes      | Required only for a `requires_real_data` adapter.                                                                            |
| `timeframe`                   | string                         | Yes      | Required alongside `symbol`.                                                                                                 |
| `target_column`               | string                         | Yes      | Which built target column to predict; defaults to the first one built if omitted.                                            |
| `model_type`                  | string                         | No       | A registered model adapter name.                                                                                             |
| `hyperparameters`             | JSON object                    | Yes      | Passed verbatim to the adapter; not validated server-side beyond basic type coercion inside each adapter's own `initialize`. |
| `status`                      | string                         | No       | One of `TRAINING_JOB_STATUSES`, default `pending`.                                                                           |
| `current_stage`               | string                         | Yes      | One of `TRAINING_JOB_STAGES`; set while running, frozen at the failing stage on failure, `null` while `pending`.             |
| `error_message`               | text                           | Yes      | `str(exc)` of whatever raised.                                                                                               |
| `error_detail`                | JSON object                    | Yes      | Structured: `{reason, affected_feature, affected_rows, suggested_fix}` (`describe_training_failure`).                        |
| `result_summary`              | JSON object                    | Yes      | `{metrics, artifact_uri, ...adapter.summary}` — see [§5.11](#511-evaluation-fields).                                         |
| `started_at` / `completed_at` | datetime                       | Yes      | Set on `run`/terminal transitions.                                                                                           |
| `logs`                        | `TrainingJobLog[]`             | —        | Always an array, ordered by `logged_at`.                                                                                     |
| `created_at` / `updated_at`   | datetime                       | No       | —                                                                                                                            |

`TrainingJobLog`: `id`, `level` (`debug\|info\|warning\|error`), `stage` (nullable, one of the 6 stages), `message` (text), `logged_at` (server-defaulted `now()`).

### 5.2 Every model

| Adapter (`model_type`) | Label                          | Framework      | `model_kind`     | `requires_real_data` | `hyperparameter_hints`     |
| ---------------------- | ------------------------------ | -------------- | ---------------- | -------------------- | -------------------------- |
| `placeholder`          | Placeholder Model              | `placeholder`  | `placeholder`    | `false`              | `epochs, learning_rate`    |
| `logistic_regression`  | Logistic Regression (Baseline) | `scikit-learn` | `classification` | `true`               | `max_iter, C, random_seed` |
| `linear_regression`    | Linear Regression (Baseline)   | `scikit-learn` | `regression`     | `true`               | `fit_intercept`            |

All three: `version: "1.0.0"`, `is_deterministic: true` on their metadata dataclass (not itself surfaced on `ModelAdapterDTO`). `ModelAdapterNotFoundError` message: `Unknown model adapter '{name}'. Available: {sorted names}`.

### 5.3 Every configurable hyperparameter

**Frontend "known" fields** (`lib/hyperparameter-specs.ts:22-64`) — five dedicated numeric inputs offered regardless of which adapter is selected:

| Key                    | Label                | Default | Min                                                                      | Integer? | Step    |
| ---------------------- | -------------------- | ------- | ------------------------------------------------------------------------ | -------- | ------- |
| `epochs`               | Epochs               | `10`    | `1`                                                                      | Yes      | —       |
| `learning_rate`        | Learning rate        | `0.001` | `0` (exclusive per help text, not enforced as `>` in code — only `>= 0`) | No       | `0.001` |
| `batch_size`           | Batch size           | `32`    | `1`                                                                      | Yes      | —       |
| `random_seed`          | Random seed          | `42`    | `0`                                                                      | Yes      | —       |
| `validation_frequency` | Validation frequency | `1`     | `1`                                                                      | Yes      | —       |

A blank field is valid and means "omit this key" — only non-blank values are sent. Anything not in this list of five is added as a free-form "custom parameter" (Name/Value text pair) — this is the **only** way to set `logistic_regression`'s real `max_iter`/`C`/`random_seed` or `linear_regression`'s real `fit_intercept` through the UI, since none of those four appear as dedicated fields (only `PlaceholderModelAdapter` actually reads `epochs`/`learning_rate`; the two real adapters ignore both and read their own hyperparameters purely from whatever custom entries were typed in, applying their own defaults — `max_iter=200, C=1.0, random_seed=42` / `fit_intercept=true` — when a key is absent).

**Backend defaults actually read** (adapter `initialize()` methods):

| Adapter               | Hyperparameter  | Default                  | Type  |
| --------------------- | --------------- | ------------------------ | ----- |
| `placeholder`         | `epochs`        | `1` (`max(1, int(...))`) | int   |
| `placeholder`         | `learning_rate` | `0.01`                   | float |
| `logistic_regression` | `max_iter`      | `200`                    | int   |
| `logistic_regression` | `C`             | `1.0`                    | float |
| `logistic_regression` | `random_seed`   | `42`                     | int   |
| `linear_regression`   | `fit_intercept` | `true`                   | bool  |

Note the **default mismatch**: the frontend's known-field default for `epochs` is `10` and for `learning_rate` is `0.001`, while `PlaceholderModelAdapter.train()`'s own internal default (used only if the key is entirely absent) is `epochs=1`/`learning_rate=0.01` — in practice irrelevant, since the frontend always sends a value for both unless the researcher blanks the field.

### 5.4 Supported targets

Not a fixed list on `TrainingJob` itself — `target_column` is free text, validated only when the job actually runs, against whatever target columns the linked experiment's `target_config` (built via the ML Dataset Builder, §3.9) actually produces. A `regression`-kind adapter (`linear_regression`) requires a numeric (`float`/`int`/`bool`) target dtype; a `classification`-kind adapter (`logistic_regression`) has no equivalent enforced restriction beyond what scikit-learn itself accepts (string/categorical labels work directly). Errors: `no_target_columns` (dataset produced none), `unknown_target_column` (named column doesn't exist), `incompatible_target_dtype` (regression adapter + non-numeric target).

### 5.5 Feature requirements

Only **numeric-dtype** (`float`/`int`/`bool`) feature columns are usable — a `"categorical"` feature column (e.g. `candle_direction`) is silently excluded from the training matrix by `build_training_dataset` (`app/training/dataset_loader.py:49-53`), since categorical feature encoding is a documented, not-yet-implemented extension point (`CategoricalEncoder`, §1.15). If **every** feature column resolves to categorical, `no_numeric_feature_columns` (400) is raised. `feature_columns` on the completed job's `result_summary` names exactly which columns actually made it into the matrix.

### 5.6 Timeline states

The 8-step visual timeline (`TrainingJobStageTimeline`, `training-job-stage-timeline.tsx:90-97`): **Pending → Dataset Validation → Dataset Loaded → Model Initialized → Training → Saving Results → Experiment Updated → Completed** — the "Pending" and "Completed" bookends wrap the 6 real pipeline stages (`TRAINING_JOB_STAGES`). Each step renders one of 5 icon states: `done` (green check), `active` (spinner), `error` (red X — only the exact stage that failed), `cancelled` (disabled circle-slash), `pending` (empty circle).

### 5.7 State machine

`ALLOWED_TRANSITIONS` (`app/training/state_machine.py:22-28`) — enforced in application code, not a DB constraint (contrast `Experiment.status`, §4.5, which has no transition enforcement at all):

```text
pending  → running, cancelled
running  → completed, failed, cancelled
completed, failed, cancelled → (terminal — no further transition)
```

An illegal transition raises `invalid_training_job_transition` — **HTTP 409**, not 400 (the only 409 in the whole Training Framework besides `training_job_not_cancellable`/`prediction_not_available`). Frontend enforcement mirrors this exactly: the detail dialog's "Run" button only renders when `status === 'pending'`; "Cancel" only when `pending` or `running`; "Delete" is disabled whenever `status === 'running'` (delete is refused server-side too — `training_job_not_cancellable`, also 409).

### 5.8 Prediction endpoint

`POST /training-jobs/{id}/predict` — **`TrainingJobPredictRequest`**: `{"rows": [[3200.5, 0.31, ...], ...]}` (each row must have exactly as many values as the job's own `feature_columns`, `min_length=1`). **`TrainingJobPredictResponse`**: `{"predictions": [...], "feature_columns": [...] | null, "classes": [...] | null, "probabilities": [[...]] | null, "confidence_levels": ["high", ...] | null}`. `probabilities`/`confidence_levels`/`classes` populate only when the adapter overrides `predict_proba` (today: `logistic_regression` only — `linear_regression`/`placeholder` both return `None`, never a fabricated confidence). Requires `status === 'completed'` and a recorded `artifact_uri`, else `prediction_not_available` (409). A row with the wrong column count raises `invalid_prediction_input` (400): `Every row must have exactly {n} values, matching this job's feature_columns`.

**Current implementation does not expose this information in the UI** — grepping the frontend confirms `lib/api/training.ts` has no function calling this endpoint at all; only the training run's own capped **prediction _samples_** (§5.11, from the validation split, read-only) are ever shown. A researcher cannot submit an arbitrary row for live prediction through this platform's UI today, only through the raw API.

### 5.9 Feature importance

`compute_feature_importance` (`app/training/interpretability.py:38-78`) — mean absolute coefficient magnitude per feature, ranked descending. For `logistic_regression` (multi-class), the per-class coefficient rows are averaged; for `linear_regression` (single output), `model.coef_` is wrapped as a one-row matrix. Each row: `{feature, coefficient (signed mean), abs_importance, sign: "positive"|"negative"|"neutral"}`. Frontend (`FeatureImportancePanel`): a sortable table (by Feature/Coefficient/Importance) plus an inline horizontal bar sized proportionally to `abs_importance`, colored green/red/gray by sign; a "Download CSV" button (only wired from the detail dialog's `feature_importance_csv` artifact). Renders nothing for `placeholder` (no coefficients exist).

### 5.10 Artifact generation

Every artifact write returns a `file://` URI (`Path.resolve().as_uri()`), rooted under `Settings.model_artifact_dir` (a `reports/` subdirectory for report files, the bare directory for the serialized model itself). Generated **only** by the two real adapters (`placeholder` writes none beyond its own fabricated `artifact_uri`, `placeholder://training-runs/{dataset_version}` — not a real file):

| Artifact                     | Written by                                     | File                                | Format                                            |
| ---------------------------- | ---------------------------------------------- | ----------------------------------- | ------------------------------------------------- |
| `model_joblib`               | Both real adapters (`default_serializer.save`) | `{name}-{uuid}.joblib`              | `joblib.dump` binary                              |
| `metrics_json`               | Both                                           | `{name}-metrics.json`               | JSON: `{metrics, train_metrics, test_metrics}`    |
| `training_report_json`       | Both                                           | `{name}-training_report.json`       | JSON: the full `report` dict                      |
| `feature_importance_csv`     | Both                                           | `{name}-feature_importance.csv`     | CSV: `feature, coefficient, abs_importance, sign` |
| `confusion_matrix_png`       | `logistic_regression` only                     | `{name}-confusion_matrix.png`       | Matplotlib heatmap                                |
| `roc_curve_png`              | `logistic_regression` only                     | `{name}-roc_curve.png`              | Matplotlib, one line per class + AUC labels       |
| `precision_recall_curve_png` | `logistic_regression` only                     | `{name}-precision_recall_curve.png` | Matplotlib, one line per class                    |

Every artifact (report files included) is also automatically recorded onto the linked **Experiment**'s own artifact list (§4.7) when the training pipeline's `update_experiment` stage runs — mapped onto `Experiment`'s fixed 5 categories (`_EXPERIMENT_ARTIFACT_CATEGORY`: the three JSON/CSV report types → `"report"`, the three PNGs → `"plot"`, the model itself → `"model_checkpoint"`), never a new category, with the specific artifact type preserved in the `description` text instead.

### 5.11 Evaluation fields

`result_summary` (JSON, merged as `{metrics, artifact_uri, **adapter.summary}`) — content depends on `model_kind`:

**Every real adapter (`logistic_regression` and `linear_regression`) records:** `target_column`, `feature_columns`, `train_metrics`, `test_metrics` (empty `{}` if no test split), `overfitting` (`{flagged: bool, gap: float, threshold: 0.15, message: str}` — train vs. held-out gap, a fixed heuristic not a statistical test), `feature_importance`, `prediction_samples` (capped at 25 rows), `model_metadata` (`{sklearn_version, joblib_version, training_duration_seconds, cpu_time_seconds, memory_usage_mb (or null on non-POSIX), feature_count, sample_count}`), `n_train`/`n_validation`/`n_test`, `hyperparameters` (resolved), `artifacts` (the file map, §5.10).

**`logistic_regression` additionally records:** `classes` (sorted label list), `confusion_matrix` (raw 2D array), `confusion_matrix_details` (per-class `{class, true_positive, false_positive, true_negative, false_negative, support}`), `roc_pr_curves` (`{curves: {label: {roc: {fpr, tpr}, pr: {precision, recall}}}, auc: {label: float}, average_precision: {label: float}, macro_auc: float|null}`).

**Headline `metrics`** (validation split): classification → `accuracy, precision, recall, f1` (labels rendered by `CLASSIFICATION_METRIC_LABELS`); regression → `mae, mse, rmse, r2` (`REGRESSION_METRIC_LABELS`, `r2` displayed as `R²`). **`placeholder` records only** `placeholder_loss`, `placeholder_accuracy` (both deterministic functions of `epochs`/`learning_rate` alone — reproducible, never random) plus a `summary` of `{epochs, learning_rate, dataset_version, note: "Fabricated..."}`.

Frontend prediction-confidence buckets (`interpretability.py:16-17,29-35`, fixed heuristic thresholds): `probability >= 0.7` → `"high"`; `>= 0.5` → `"medium"`; else `"low"`.

### 5.12 Downloadable files

`GET /training-jobs/{id}/artifacts` lists every entry from [§5.10](#510-artifact-generation) that the job actually produced (`model_joblib` first if `artifact_uri` is set, then every key in `result_summary.artifacts`), each as `{artifact_type, filename, content_type, download_url}` — `content_type` via `mimetypes.guess_type` (fallback `application/octet-stream`), `download_url` = `"/api/v1/training-jobs/{id}/artifacts/{artifact_type}"`. `GET .../artifacts/{artifact_type}` streams the actual file (`FileResponse`). Frontend labels (`ARTIFACT_LABELS`, `training-artifacts-panel.tsx:20-28`): `"Trained model (model.joblib)"`, `"Metrics (metrics.json)"`, `"Full training report (training_report.json)"`, `"Feature importance (feature_importance.csv)"`, `"Confusion matrix (confusion_matrix.png)"`, `"ROC curve (roc_curve.png)"`, `"Precision-Recall curve (precision_recall_curve.png)"`. `training_artifact_not_found` (404) if the type doesn't exist for this job or its file is missing from disk.

### 5.13 Error cases

| HTTP | `code`                             | Message pattern                                                                                                                                                                                   |
| ---- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 404  | `training_job_not_found`           | `Training job {id} not found`                                                                                                                                                                     |
| 404  | `model_adapter_not_found`          | `Unknown model adapter '{name}'. Available: {...}`                                                                                                                                                |
| 409  | `invalid_training_job_transition`  | `Cannot move a training job from '{current}' to '{target}'`                                                                                                                                       |
| 409  | `training_job_not_cancellable`     | `Training job {id} cannot be modified while status is '{status}'`                                                                                                                                 |
| 409  | `prediction_not_available`         | `Training job {id} has no trained model available for prediction (status is '{status}'; a job must be completed)`                                                                                 |
| 400  | `missing_dataset_version`          | `This job has no dataset_version, and its experiment does not record one either; a training job must cite the dataset it trains over`                                                             |
| 400  | `missing_training_data_source`     | `This model adapter requires real training data, but the job has no symbol/timeframe recorded to build a dataset from`                                                                            |
| 400  | `missing_feature_or_target_config` | `...the linked experiment has no recorded feature_set/target_config to build a dataset from`                                                                                                      |
| 400  | `no_target_columns`                | `The built dataset has no target columns to train against`                                                                                                                                        |
| 400  | `unknown_target_column`            | `Unknown target_column '{name}'. Available: {...}`                                                                                                                                                |
| 400  | `no_numeric_feature_columns`       | `None of this dataset's feature columns are numeric...`                                                                                                                                           |
| 400  | `undefined_feature_value`          | `Feature column '{col}' has an undefined or non-numeric value where a number was expected (row {n})` — defensive; should never occur given `drop_warmup`/`drop_undefined_targets` default `true`. |
| 400  | `empty_training_split`             | `The {split} split has zero rows — widen the candle range or adjust the split ratios`                                                                                                             |
| 400  | `incompatible_target_dtype`        | `Model kind '{kind}' is not compatible with target column '{name}''s dtype '{dtype}'`                                                                                                             |
| 400  | `invalid_sort`                     | Standard whitelisted-column message; valid: `status, model_type, created_at, updated_at, started_at, completed_at`.                                                                               |
| 400  | `model_initialization_failed`      | `Model adapter '{name}' failed to initialize: {detail}`                                                                                                                                           |
| 400  | `training_execution_failed`        | `Model adapter '{name}' failed during training: {detail}`                                                                                                                                         |
| 400  | `invalid_prediction_input`         | `Every row must have exactly {n} values, matching this job's feature_columns`                                                                                                                     |
| 404  | `training_artifact_not_found`      | `Training job {id} has no '{type}' artifact available`                                                                                                                                            |
| 400  | `prediction_execution_failed`      | `Model adapter '{name}' failed during prediction: {detail}`                                                                                                                                       |
| 500  | `duplicate_model_adapter`          | Startup-time only — two adapters registered under the same name.                                                                                                                                  |

Every failure during a `run()` also writes `error_message`/`error_detail` onto the job (never propagated as the HTTP response for `POST .../run` itself, which always returns `200` with the job's `failed` state — `run` never 4xx/5xxs for an adapter-side failure, only for a pre-flight issue like an illegal transition) and best-effort marks the linked experiment `status: "failed"` (swallowed if that update itself fails, logged only).

### 5.14 Loading / empty / other UI states

| Situation                                         | UI                                                                                                                                                     |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Job list loading                                  | `LoadingRows` — 5 skeleton rows.                                                                                                                       |
| No jobs match filter (experiments exist)          | `"No training jobs match this filter."`                                                                                                                |
| No experiments exist at all                       | `"No experiments exist yet — create one before registering a training job."` (distinct message, `hasExperiments` prop)                                 |
| Create dialog: no experiments                     | `EmptyStateNotice` — "No experiments exist" + link to `/experiments`.                                                                                  |
| Create dialog: no dataset citations               | `EmptyStateNotice` — "No datasets available" + link to `/ml-datasets`.                                                                                 |
| Create dialog: no model adapters registered       | `EmptyStateNotice` — "No model adapters registered" (no action link — a backend deploy issue).                                                         |
| Detail dialog loading                             | `CircularProgress`, `aria-label="Loading training job"`.                                                                                               |
| Job `status === 'running'`                        | Detail dialog polls every **3000ms** (`refetchInterval`) and shows a small spinner beside the status chip: `"Refreshing automatically while running"`. |
| No logs yet                                       | `"No logs yet — run the job to execute the pipeline."`                                                                                                 |
| Log search matches nothing                        | `"No log lines match "{search}"."`                                                                                                                     |
| Evaluation summary present but model_kind unknown | Falls back to a bare `name: value` list of every `metrics` entry.                                                                                      |

### 5.15 Not covered elsewhere — cross-references

- Async Training Queue / Retry / Resume — **Current implementation does not expose this information.** No queue exists; `run` is synchronous and blocking. "Resume" has no meaning since a failed/cancelled job is terminal (§5.7) — the only recovery path is creating a brand-new job.
- Cross Validation / Hyperparameter Search — **Current implementation does not expose this information.** Only a single train/validation/(test) split per job (via the linked experiment's `split_config`); no k-fold, no grid/random search over hyperparameters exists anywhere in `app/training/`.
- Random Seed Control — Exposed only as the generic `random_seed` known-hyperparameter field (§5.3) and, for `logistic_regression`, as its own `random_seed` hyperparameter (default `42`) passed straight to `sklearn.linear_model.LogisticRegression(random_state=...)`. `linear_regression`/`placeholder` have no seed-dependent behavior (`LinearRegression` is deterministic; `PlaceholderModelAdapter` never calls a random number generator).
- Model Version Metadata — Covered fully in [§5.11](#511-evaluation-fields)'s `model_metadata` (library versions, timing, memory, shape) — this **is** implemented, just not under a "version" heading anywhere in the UI.

---

## 6. Model Evaluation

**Page:** `/ml/evaluation` — `apps/dashboard/src/features/ml-evaluation/ml-evaluation-page.tsx`
**Backend:** `services/api/app/evaluation/` (engine, 9 built-in metrics, benchmark comparison), `app/models/evaluation_benchmark_run.py`, `app/repositories/evaluation_benchmark_runs.py`, `app/services/evaluation.py`, `app/api/v1/endpoints/evaluation.py`, `app/schemas/evaluation.py`

This engine **computes nothing new at request time** beyond the comparison itself — every metric value it compares was already produced during training (`logistic_regression`/`linear_regression` adapters, via the shared `app.evaluation.engine.default_engine`, the exact same engine those adapters call internally). A benchmark is a **read-only comparison** over `TrainingJob.result_summary["metrics"]` for jobs whose `status == "completed"`.

### 6.1 Benchmark page layout

1. **Section: "Benchmark Comparison"** — `BenchmarkFiltersBar` (Dataset version / Target column / Experiments + "Compare" button); before any run, an `EmptyStateNotice` ("No comparison run yet"); on error, an `Alert` (severity `info` if the message contains "No completed", else `error`) with Retry. Once a result exists: an info banner if viewing a reopened history run (dismissible), a row with `MetricSelector` + `BenchmarkExportMenu`, `BestModelSummary` (one card per metric), `BenchmarkComparisonTable`, and one `MetricComparisonChart` per metric name (small bar charts, laid out in a wrapping row).
2. **Section: "Benchmark History"** — `BenchmarkHistoryTable` (paginated, Reopen/Delete actions).
3. **Section: "Available Metrics"** — `MetricCatalogPanel` (grouped Classification/Regression reference table).
4. `CandidateDetailDialog` and a delete-confirmation `ConfirmActionDialog`, both mounted at the page root.

### 6.2 Every filter

`BenchmarkFiltersBar` (`components/benchmark-filters-bar.tsx:34-110`):

| Field               | Component               | Required?                             | Notes                                                                                                                   |
| ------------------- | ----------------------- | ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Dataset version** | `Autocomplete freeSolo` | No (but ≥1 of the 3 filters required) | Options = every distinct non-null `dataset_version` across all fetched experiments (up to 200, `sort=updated_at desc`). |
| **Target column**   | `TextField`             | No                                    | Free text, e.g. `next_direction`, `next_close`.                                                                         |
| **Experiments**     | `Autocomplete multiple` | No                                    | Narrows an already-matching set further (an intersection with the dataset/target filters, never an alternative).        |
| **Compare button**  | `Button type="submit"`  | —                                     | Disabled unless at least one of the three fields has a value, or while `submitting`.                                    |

Submitting sends `dataset_version`/`target_column` as `undefined` when blank (trimmed) and `experiment_ids` as `undefined` when empty (never an empty array) — matching the backend's own `at least one of three` gate exactly.

### 6.3 Every metric

9 built-in metrics — 5 classification, 4 regression — registered from `app/evaluation/metrics/`:

| Name        | Label     | Category       | Higher is better? | Requires probabilities? |
| ----------- | --------- | -------------- | ----------------- | ----------------------- |
| `accuracy`  | Accuracy  | classification | Yes               | No                      |
| `precision` | Precision | classification | Yes               | No                      |
| `recall`    | Recall    | classification | Yes               | No                      |
| `f1`        | F1 Score  | classification | Yes               | No                      |
| `roc_auc`   | ROC-AUC   | classification | Yes               | **Yes**                 |
| `mae`       | MAE       | regression     | No                | No                      |
| `mse`       | MSE       | regression     | No                | No                      |
| `rmse`      | RMSE      | regression     | No                | No                      |
| `r2`        | R²        | regression     | Yes               | No                      |

### 6.4 Metric definitions

- **Accuracy**: "Fraction of predictions that exactly matched the true label." (`sklearn.metrics.accuracy_score`)
- **Precision**: "Of every prediction for a class, the fraction that were actually that class (weighted across classes by support)." (`precision_score(average="weighted", zero_division=0)`)
- **Recall**: "Of every true instance of a class, the fraction the model actually found (weighted across classes by support)." (`recall_score`, same averaging)
- **F1 Score**: "The harmonic mean of Precision and Recall (weighted across classes)." (`f1_score`, same averaging)
- **ROC-AUC**: "Area under the ROC curve — how well the model ranks the true class above the others, independent of any decision threshold." One-vs-rest for 3+ classes (`roc_auc_score(multi_class="ovr", average="weighted")`); binary case uses the positive-class column directly. **Skipped** (not errored) whenever `y_proba` is `None`.
- **MAE**: "Mean Absolute Error — the average absolute size of every prediction's miss." (`mean_absolute_error`)
- **MSE**: "Mean Squared Error — like MAE, but penalizes large misses more heavily." (`mean_squared_error`)
- **RMSE**: "Root Mean Squared Error — MSE brought back to the target's own units." (`sqrt(mean_squared_error)`)
- **R²**: "Coefficient of determination — the fraction of variance in the target the model explains; 1.0 is a perfect fit, 0.0 is no better than the mean." (`r2_score`)

A metric that raises during `compute()`, or that requires probabilities that weren't given, is recorded as **skipped** (with a reason) rather than aborting the report — `EvaluationReport.skipped: dict[str, str]` — never surfaced anywhere in the current frontend (no UI reads `.skipped`, only `.metrics`).

### 6.5 Comparison algorithm

`app/evaluation/benchmark.py:72-113`'s `compare()`:

1. Collect every metric _name_ that appears on **at least one** candidate's `metrics` dict (`sorted(set(...))` — a candidate missing a given metric simply has no cell for it, rendered `—`).
2. For each such name, look up `higher_is_better` from the **live metric registry** if the name is still registered; **fall back to `higher_is_better=True`** if the name is unknown (e.g. a metric later removed, or a hand-typed custom name) — a documented, conservative default rather than silently excluding it.
3. Pick the winner via `max`/`min` (by direction) over every candidate that recorded that metric.

### 6.6 Winner selection

One `BenchmarkBestEntry` per metric name: `{metric, training_job_id, model_type, value, higher_is_better}`. Ties are broken by Python's own `max`/`min` stability (the **first** candidate in comparison order — server-side order is `completed_at desc` before any experiment-id narrowing — that attains the extreme value wins; no explicit secondary tiebreaker is implemented). Rendered as `BestModelSummary`'s one card per metric (trophy icon, metric name, an up/down arrow keyed to `higher_is_better`, the winning `model_type` chip, and the value to 4 decimals).

### 6.7 Ranking

`BenchmarkComparisonTable`'s row order and optional "Rank" column (`components/benchmark-comparison-table.tsx:60-195`): with **no** `rankMetric` chosen (`MetricSelector` default, labeled "None (most recent first)"), rows sort by `completed_at` **descending**; choosing a metric ranks by that metric's value, direction-aware (`higher_is_better` from `best_by_metric`, defaulting to `true` if absent), and a numbered "Rank" column appears (a candidate missing the ranking metric sorts to the bottom, showing `—` instead of a rank number). The winning cell **per metric column** is always bolded green via `best_by_metric`, independent of which metric is currently driving the rank/row-order — i.e. two different highlighting mechanisms coexist: row order (one active ranking metric) and cell highlighting (every metric's own winner, always shown).

### 6.8 Charts

- **`MetricComparisonChart`** — one per metric name present on at least one candidate; plain SVG horizontal bars (this codebase's "small on-page chart, not a charting library" convention), one bar per candidate that recorded that metric, sized against the **largest value among the candidates shown** (not a fixed [0,1] domain — correct for a regression metric like RMSE that can exceed 1), labeled with the model type and the value to 3 decimals.
- Inside `CandidateDetailDialog` → `EvaluationSummary` (reused verbatim from the Training Framework, §5.9/§5.11): confusion matrix, ROC/PR curves (classification only), feature importance bars, prediction samples table, model metadata.

### 6.9 History (Benchmark History)

Persisted table `evaluation_benchmark_runs` (`app/models/evaluation_benchmark_run.py`) — every successful `POST /evaluation/benchmark` call is recorded best-effort (same "never let bookkeeping sink the primary outcome" pattern as `MLDatasetBuild`, §3.15/§3.18). Fields: `id`, `dataset_version` (nullable), `target_column` (nullable), `candidate_count` (int), `request` (JSON, the full `BenchmarkRequest` verbatim), `response` (JSON, the full `BenchmarkResponse` verbatim), `created_at`/`updated_at`. List view (`BenchmarkHistoryTable`) columns: Dataset Version, Target Column, Candidates (count chip), Compared (timestamp), Actions (Reopen/Delete). Reopening (`GET /evaluation/history/{id}`) restores the **exact** filter bar state the run was made with (via a `useEffect` on the fetched `request`) and displays the exact persisted `response` — not a re-run. Sort columns (`SORT_COLUMNS`): `dataset_version, target_column, candidate_count, created_at` (default `created_at desc`); page size fixed client-side at 10 (`HISTORY_PAGE_SIZE`), server default/max `20`/`100` (`evaluation_history_default_limit`/`evaluation_history_max_limit`).

### 6.10 Export

Two formats via `BenchmarkExportMenu` → `BENCHMARK_EXPORTERS` (`lib/benchmark-export.ts:98-101`) — a small Strategy+Registry extension point (adding a future format, e.g. PDF, is one new entry):

#### 6.10.1 CSV format

```text
Best accuracy,logistic_regression,0.6234
Best f1,logistic_regression,0.6108

Training Job ID,Experiment,Model Type,Model Kind,Dataset Version,Target Column,Symbol,Timeframe,Completed At,accuracy,f1
6f1e4a2c-...,Baseline logistic regression,logistic_regression,classification,1a2b3c4d-...,next_direction,ETHUSD,1h,2026-01-31T23:10:00Z,0.6234,0.6108
```

Structure: one `Best {metric},{model_type},{value}` line per entry in `best_by_metric`, a blank line, then a standard header row (`Training Job ID, Experiment, Model Type, Model Kind, Dataset Version, Target Column, Symbol, Timeframe, Completed At`, plus every collected metric name) and one data row per candidate (a missing metric renders as an empty CSV field, not `—`). Uses the platform's shared `csvLine`/`sanitizeFilenamePart` helpers — no separate escaping logic.

#### 6.10.2 JSON format

The **entire `BenchmarkResponse` verbatim**, pretty-printed — `{candidates: [...], best_by_metric: [...]}` — every candidate's complete `report` (its training job's full `result_summary`) included, so the export can feed a downstream tool exactly what the comparison page itself saw.

Filename pattern (both): `benchmark-{sanitized dataset_version or "unknown"}.{csv|json}` (`benchmarkExportFileName`).

### 6.11 Available Metrics table

`MetricCatalogPanel` renders `GET /evaluation/metrics`'s response as two grouped tables (Classification metrics / Regression metrics), columns: Metric (label chip), Category (outlined chip), Description, Direction (↑/↓ icon + "Higher is better"/"Lower is better" text), Requires probabilities (Yes/No). Populates automatically for any future `@register`-decorated `Metric` subclass — no frontend change needed.

### 6.12 Every API endpoint

| Endpoint                              | Method | Purpose                                                   |
| ------------------------------------- | ------ | --------------------------------------------------------- |
| `/api/v1/evaluation/metrics`          | GET    | The full metric catalogue.                                |
| `/api/v1/evaluation/benchmark`        | POST   | Compare completed training jobs matching a request.       |
| `/api/v1/evaluation/history`          | GET    | Benchmark History list (paginated, filterable, sortable). |
| `/api/v1/evaluation/history/{run_id}` | GET    | Reopen one past run's exact request/response.             |
| `/api/v1/evaluation/history/{run_id}` | DELETE | Remove one past run (204) — training jobs untouched.      |

**Request** (`BenchmarkRequest`): `{"dataset_version": "1a2b...", "target_column": "next_direction", "experiment_ids": ["6f1e4a2c-..."]}` — all three optional individually, but **at least one required**.

**Response** (`BenchmarkResponse`): `{"candidates": [BenchmarkCandidateDTO, ...], "best_by_metric": [BenchmarkBestEntryDTO, ...]}`. `BenchmarkCandidateDTO` full field list: `training_job_id, experiment_id, experiment_name, model_type, model_kind (or "unknown" if the model_type is no longer a registered adapter), dataset_version, target_column, completed_at, metrics: {name: value}, symbol, timeframe, feature_count, sample_count, model_artifact_url (the same deterministic /training-jobs/{id}/artifacts/model_joblib path §5.12 computes), report (the full result_summary verbatim)`.

### 6.13 Error responses

| HTTP | `code`                       | Message                                                                                                                                                                                      |
| ---- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 400  | `no_benchmark_target`        | `Provide at least one of dataset_version, target_column, or experiment_ids to compare training jobs`                                                                                         |
| 404  | `empty_benchmark`            | `No completed training jobs matched this benchmark request` — rendered with `severity="info"` on the frontend (message-sniffed via `.includes('No completed')`), not styled as a hard error. |
| 404  | `metric_not_found`           | `Metric '{name}' is not registered. Available: {...}` — not reachable from the current UI (no endpoint accepts an arbitrary metric name as a path/query param).                              |
| 404  | `benchmark_run_not_found`    | `Benchmark run {id} not found`                                                                                                                                                               |
| 400  | `invalid_benchmark_run_sort` | `Invalid sort '{sort}'/'{dir}'. Available sort columns: {...}; direction must be 'asc' or 'desc'`                                                                                            |
| 500  | —                            | `DuplicateMetricError` (`RuntimeError`, startup-time only — two metrics registered under the same name).                                                                                     |

A completed job with **no recorded metrics** (e.g. one that used `placeholder`, which never writes real metrics, or a completed job that somehow never reached `update_experiment`) is silently **excluded** from `candidates` rather than shown as an empty row — if excluding it leaves zero candidates, `empty_benchmark` (404) results.

### 6.14 Loading / empty states

| Situation                                                     | UI                                                                                                                                      |
| ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| No comparison run yet                                         | `EmptyStateNotice`: "No comparison run yet" / "Choose a dataset version, target column, and/or experiments above, then select Compare." |
| Comparison in flight                                          | Compare button disabled (no separate skeleton for the result area).                                                                     |
| `empty_benchmark` returned                                    | Info-styled `Alert` with Retry.                                                                                                         |
| Metric catalogue failed to load                               | `role="alert"` `Alert`: "Could not load the metric catalogue."                                                                          |
| Benchmark History loading                                     | 3 skeleton rows.                                                                                                                        |
| Benchmark History empty                                       | `"No past comparisons yet — run one above, and it will appear here."` (`role="status"`)                                                 |
| `best_by_metric` empty (no metrics recorded by any candidate) | `BestModelSummary` renders nothing (`return null`).                                                                                     |
| No candidate recorded a given metric                          | That metric's `MetricComparisonChart` renders nothing.                                                                                  |

---

## 7. API Reference

Every route below is mounted **twice** — under `/api/v1/*` and unversioned at `/*` (`app/api/router.py:9-13`) — matching this platform's existing convention for every other endpoint. No authentication exists on any route. Full request/response JSON for most of these is already given in full in §1–§6 (cross-referenced below rather than repeated); this section is the master index plus examples for the endpoints not yet fully exampled elsewhere.

### 7.1 Feature Engineering (7 endpoints)

| Method | Route                                                | Request                 | Response                     | Detail                                                                                                                           |
| ------ | ---------------------------------------------------- | ----------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| GET    | `/features`                                          | —                       | `FeatureCatalogResponse`     | [§1.6](#16-response-payload--dataset-build) catalogue analog; see §1.15 for the 5 features listed.                               |
| GET    | `/features/lineage`                                  | —                       | `FeatureLineageResponse`     | [§1.15](#115-every-built-in-feature)                                                                                             |
| GET    | `/features/{feature}`                                | —                       | `FeatureDTO`                 | One catalogue entry.                                                                                                             |
| POST   | `/markets/{symbol}/features/dataset`                 | `FeatureDatasetRequest` | `FeatureDatasetResponse`     | [§1.5](#15-request-payload--dataset--correlation--statistics-identical-body-shape) / [§1.6](#16-response-payload--dataset-build) |
| POST   | `/markets/{symbol}/features/correlation`             | `FeatureDatasetRequest` | `FeatureCorrelationResponse` | [§1.7](#17-response-payload--correlation)                                                                                        |
| POST   | `/markets/{symbol}/features/statistics`              | `FeatureDatasetRequest` | `FeatureStatisticsResponse`  | [§1.8](#18-response-payload--statistics)                                                                                         |
| POST   | `/markets/{symbol}/features/export?format=csv\|json` | `FeatureDatasetRequest` | File download                | [§1.12](#112-export-formats)                                                                                                     |

**Example success** (`GET /api/v1/features/sma`):

```json
{
  "name": "sma",
  "label": "Simple Moving Average",
  "category": "trend",
  "parameters": [
    { "name": "period", "type": "int", "default": 20, "minimum": 1, "maximum": 1000 },
    {
      "name": "source",
      "type": "string",
      "default": "close",
      "choices": ["open", "high", "low", "close"]
    }
  ],
  "outputs": ["sma_{period}"],
  "version": "1.0.0",
  "author": "Eth AI Platform",
  "value_type": "float",
  "dependencies": [],
  "is_deterministic": true,
  "missing_values_expected": false
}
```

**Example error** (`GET /api/v1/features/macd`, unregistered): `404 {"code": "feature_not_found", "detail": "Feature 'macd' is not registered; available: candle_shape, ema, ohlcv, sma, wma"}`

### 7.2 Dataset Validation (2 endpoints)

| Method | Route                                 | Request                                                                              | Response                        | Detail                                                     |
| ------ | ------------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------- | ---------------------------------------------------------- |
| POST   | `/markets/{symbol}/features/validate` | `DatasetValidationRequest` (= `FeatureDatasetRequest` + `required_columns`, `rules`) | `ValidationReportResponse`      | [§2.4](#24-request-payload) / [§2.5](#25-response-payload) |
| GET    | `/validation/rules`                   | —                                                                                    | `ValidationRuleCatalogResponse` | [§2.6](#26-every-validation-rule)                          |

**Example error**: `404 {"code": "validation_rule_not_found", "detail": "Validation rule 'made_up_rule' is not registered; available: data_types, duplicate_rows, duplicate_timestamps, feature_failures, infinite_values, metadata_consistency, missing_values, nan_values, required_columns, time_gaps, timestamp_ordering"}`

### 7.3 ML Dataset Builder (7 endpoints)

| Method | Route                                                  | Request                                                              | Response                       | Detail                                                         |
| ------ | ------------------------------------------------------ | -------------------------------------------------------------------- | ------------------------------ | -------------------------------------------------------------- |
| GET    | `/ml/targets`                                          | —                                                                    | `TargetCatalogResponse`        | [§3.9](#39-every-built-in-target)                              |
| GET    | `/ml/targets/{target}`                                 | —                                                                    | `TargetDTO`                    | One catalogue entry.                                           |
| POST   | `/markets/{symbol}/ml/dataset`                         | `MLDatasetRequest`                                                   | `MLDatasetResponse`            | [§3.7](#37-every-api-request) / [§3.8](#38-every-api-response) |
| POST   | `/markets/{symbol}/ml/dataset/export?format=csv\|json` | `MLDatasetRequest`                                                   | File download                  | [§3.13](#313-export-behavior)                                  |
| GET    | `/ml/dataset-builds`                                   | Query: `symbol, timeframe, quality_passed, sort, dir, limit, offset` | `MLDatasetBuildListResponse`   | [§3.14](#314-every-dataset-history-column)                     |
| GET    | `/ml/dataset-builds/{build_id}`                        | —                                                                    | `MLDatasetBuildDetailResponse` | [§3.15](#315-every-stored-json-field)                          |
| DELETE | `/ml/dataset-builds/{build_id}`                        | —                                                                    | 204                            | Deletes the persisted record only.                             |

**Example error** (`GET /ml/targets/next_high`): `404 {"code": "target_not_found", "detail": "Target 'next_high' is not registered; available: next_close, next_direction, next_return"}`
**Example error** (`GET /ml/dataset-builds/{unknown-uuid}`): `404 {"code": "ml_dataset_build_not_found", "detail": "ML dataset build 6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90 not found"}`

### 7.4 Experiment Management (9 endpoints)

| Method | Route                                       | Request                                                                        | Response                   | Detail                                         |
| ------ | ------------------------------------------- | ------------------------------------------------------------------------------ | -------------------------- | ---------------------------------------------- |
| POST   | `/experiments`                              | `ExperimentCreateRequest`                                                      | `ExperimentResponse` (201) | [§4.1](#41-every-create-form-field)            |
| GET    | `/experiments`                              | Query: `q, status, model_type, dataset_version, tag, sort, dir, limit, offset` | `ExperimentListResponse`   | [§4.9](#49-filtering)–[§4.12](#412-pagination) |
| GET    | `/experiments/{id}`                         | —                                                                              | `ExperimentResponse`       | [§4.4](#44-complete-experiment-schema)         |
| PATCH  | `/experiments/{id}`                         | `ExperimentUpdateRequest` (all fields optional)                                | `ExperimentResponse`       | [§4.13](#413-patch-examples)                   |
| DELETE | `/experiments/{id}`                         | —                                                                              | 204                        | Cascades to metrics/artifacts/tags.            |
| POST   | `/experiments/{id}/metrics`                 | `MetricCreateRequest`                                                          | `MetricDTO` (201)          | [§4.6](#46-metric-storage)                     |
| DELETE | `/experiments/{id}/metrics/{metric_id}`     | —                                                                              | 204                        | —                                              |
| POST   | `/experiments/{id}/artifacts`               | `ArtifactCreateRequest`                                                        | `ArtifactDTO` (201)        | [§4.7](#47-artifacts)                          |
| DELETE | `/experiments/{id}/artifacts/{artifact_id}` | —                                                                              | 204                        | —                                              |

**Example payload** (`POST /experiments`):

```json
{
  "name": "Baseline logistic regression",
  "dataset_version": "1a2b3c4d-...",
  "model_type": "logistic_regression",
  "status": "draft",
  "notes": null,
  "tags": ["baseline"]
}
```

**Example success**: `201` + full `ExperimentResponse` (see [§4.4](#44-complete-experiment-schema)).
**Example error** (`GET /experiments/{unknown-uuid}`): `404 {"code": "experiment_not_found", "detail": "Experiment 6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90 not found"}`
**Example error** (`GET /experiments?sort=score`): `400 {"code": "invalid_sort", "detail": "Unsupported sort 'score' (direction 'asc'); supported columns: created_at, model_type, name, status, updated_at, directions: asc, desc"}`

### 7.5 ML Training Framework (10 endpoints)

| Method | Route                                               | Request                                                              | Response                       | Detail                                                |
| ------ | --------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------ | ----------------------------------------------------- |
| GET    | `/training-jobs/models`                             | —                                                                    | `ModelAdapterCatalogResponse`  | [§5.2](#52-every-model)                               |
| POST   | `/training-jobs`                                    | `TrainingJobCreateRequest`                                           | `TrainingJobResponse` (201)    | [§5.1](#51-every-training-job-field)                  |
| GET    | `/training-jobs`                                    | Query: `experiment_id, status, model_type, sort, dir, limit, offset` | `TrainingJobListResponse`      | —                                                     |
| GET    | `/training-jobs/{job_id}`                           | —                                                                    | `TrainingJobResponse`          | [§5.1](#51-every-training-job-field)                  |
| DELETE | `/training-jobs/{job_id}`                           | —                                                                    | 204                            | Refuses a `running` job.                              |
| POST   | `/training-jobs/{job_id}/run`                       | —                                                                    | `TrainingJobResponse`          | [§5.6](#56-timeline-states)/[§5.7](#57-state-machine) |
| POST   | `/training-jobs/{job_id}/cancel`                    | —                                                                    | `TrainingJobResponse`          | [§5.7](#57-state-machine)                             |
| POST   | `/training-jobs/{job_id}/predict`                   | `TrainingJobPredictRequest`                                          | `TrainingJobPredictResponse`   | [§5.8](#58-prediction-endpoint)                       |
| GET    | `/training-jobs/{job_id}/artifacts`                 | —                                                                    | `TrainingArtifactListResponse` | [§5.12](#512-downloadable-files)                      |
| GET    | `/training-jobs/{job_id}/artifacts/{artifact_type}` | —                                                                    | File download                  | [§5.12](#512-downloadable-files)                      |

**Example payload** (`POST /training-jobs`):

```json
{
  "experiment_id": "6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90",
  "model_type": "logistic_regression",
  "dataset_version": null,
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "target_column": "next_direction_1",
  "hyperparameters": { "max_iter": 200, "C": 0.5, "random_seed": 7 }
}
```

**Example success**: `201` + a `TrainingJobResponse` with `status: "pending"`, `logs: []`.
**Example error** (`POST /training-jobs/{id}/run` on an already-`completed` job): `409 {"code": "invalid_training_job_transition", "detail": "Cannot move a training job from 'completed' to 'running'"}`
**Example error** (`POST /training-jobs/{id}/predict` before completion): `409 {"code": "prediction_not_available", "detail": "Training job {id} has no trained model available for prediction (status is 'pending'; a job must be completed)"}`

### 7.6 Model Evaluation (5 endpoints)

| Method | Route                          | Request                                                           | Response                     | Detail                                |
| ------ | ------------------------------ | ----------------------------------------------------------------- | ---------------------------- | ------------------------------------- |
| GET    | `/evaluation/metrics`          | —                                                                 | `MetricCatalogResponse`      | [§6.3](#63-every-metric)              |
| POST   | `/evaluation/benchmark`        | `BenchmarkRequest`                                                | `BenchmarkResponse`          | [§6.12](#612-every-api-endpoint)      |
| GET    | `/evaluation/history`          | Query: `dataset_version, target_column, sort, dir, limit, offset` | `BenchmarkRunListResponse`   | [§6.9](#69-history-benchmark-history) |
| GET    | `/evaluation/history/{run_id}` | —                                                                 | `BenchmarkRunDetailResponse` | [§6.9](#69-history-benchmark-history) |
| DELETE | `/evaluation/history/{run_id}` | —                                                                 | 204                          | —                                     |

**Example payload** (`POST /evaluation/benchmark`): `{"dataset_version": null, "target_column": "next_direction_1", "experiment_ids": []}`
**Example error** (empty body, all three omitted): `400 {"code": "no_benchmark_target", "detail": "Provide at least one of dataset_version, target_column, or experiment_ids to compare training jobs"}`
**Example error** (well-formed but nothing matched): `404 {"code": "empty_benchmark", "detail": "No completed training jobs matched this benchmark request"}`

### 7.7 Summary — 40 endpoints across 6 subsystems

Feature Engineering (7) + Dataset Validation (2) + ML Dataset Builder (7) + Experiment Management (9) + ML Training Framework (10) + Model Evaluation (5) = **40 distinct routes**, each served at both its `/api/v1/*` path and its unversioned equivalent (80 total registered paths). Every domain error across all 40 follows the identical `{"code": str, "detail": str}` JSON envelope (`app/core/exceptions.py`'s `AppError` → the application's one shared exception handler) — no endpoint has bespoke error shape.

---

## 8. Testing Reference

Every field name below is the exact `aria-label`/`label` string a test would query by in this codebase's own component tests (Testing Library `getByLabelText`/`getByRole`), or the exact wire field name for an API-level test. Every value is one already established earlier in this document — nothing here is invented. Automated backend tests referenced by file already exist under `services/api/tests/`; automated frontend tests already exist as `*.test.tsx` beside each component named. Manual walkthroughs below assume the `seeded_varied` fixture's shape (`ETCUSD`, 1h, 3 candles) or a locally-ingested `ETHUSD` 1h market with real history, matching `MLPipelineGuide.md`'s own convention.

### 8.1 Feature Engineering

1. **Happy path.** On `/features`: select Market `ETHUSD`, Timeframe `1h`, Range `"All History"`, Max rows `500 rows`. Tick `OHLCV` and `Simple Moving Average` (leave `period=20`, `source=close` at their defaults). Click **"Build Dataset"**. Expect the Dataset Preview table to show a `sma_20` column alongside `open/high/low/close/volume`, `DatasetSummary`'s "Rows dropped" `Metric` reading `20` (SMA's warmup), and `DatasetInfoCard`'s "Pipeline Version" reading `1.0.0`.
2. **Validation tests.** Set `period` on `sma` to `0` via its `ParameterForm` field — `validateValues` must block the request client-side (the field shows an inline error, `onParamsChange` is never called with the invalid value) before any network call; confirm server-side by posting `{"feature": "sma", "params": {"period": 0}}` directly and asserting `400 invalid_feature_parameter`.
3. **Boundary tests.** `period=1` (minimum) and `period=1000` (maximum) both succeed; `period=1001` returns `invalid_feature_parameter`. `Max rows` boundary: request `limit=1000` (the form's ceiling) succeeds; a raw API request with `limit=1001` returns `limit_exceeded` (`limit 1001 exceeds the configured maximum of 1000`).
4. **Negative tests.** Request feature name `"macd"` (unregistered) → `404 feature_not_found` listing `candle_shape, ema, ohlcv, sma, wma`. Request `sma` + `sma` both at `period=20` (identical params, same feature twice) → `400 duplicate_feature_column` naming `sma_20`.
5. **Error recovery.** Trigger a build failure (e.g. an unreachable market symbol `"NOPE"` → `market_not_found`), confirm the Dataset Preview section shows the error `Alert` with a **"Retry"** button, click it, and confirm the identical request re-fires (`build.mutate` called again with the same `built.params`).
6. **API verification.** `POST /api/v1/markets/ETHUSD/features/dataset` with `{"timeframe": "1h", "features": [{"feature": "ohlcv"}]}` → `200`, `meta.pipeline_version == "1.0.0"`, `quality.duplicate_timestamps == 0`.
7. **Database verification.** **Current implementation does not expose this information** — Feature Engineering builds nothing to a database table (§1.14); there is no row to inspect.
8. **Export verification.** Click **"CSV"** in the Export section; confirm the downloaded file's header row exactly matches the preview table's visible columns plus a leading `timestamp` column, and that its row count equals `meta.total_rows`, not the previewed `200`.
9. **History verification.** **Current implementation does not expose this information** — no build history exists for this feature (§1.14).
10. **Performance expectations.** `tests/features/test_performance.py` (opt-in, `--run-performance`) asserts a 100,000-row, 5-feature dataset builds within its documented time budget and that the quality report's duplicate/missing-candle counting scales linearly.

### 8.2 Dataset Validation

1. **Happy path.** On `/validation`: click preset **"AI Basic Features"** (seeds `ohlcv, candle_shape, sma`), pick Market `ETHUSD`, Timeframe `1h`, Range `"Last 30 Days"`, click **"Run Validation"**. Expect `ValidationSummaryCards`' "Result" card to read **"Passed"** and Quality Score `100` (zero errors, zero warnings on a clean build).
2. **Validation tests.** Add `sma_50` to **"Required columns"** without selecting `sma` at `period=50` in the Feature Selector; run validation; expect exactly one issue: `rule: "required_columns"`, `code: "missing_required_column"`, `column: "sma_50"`.
3. **Boundary tests.** Request `rules: ["required_columns"]` (a single named rule) — `rules_run` must equal exactly `["required_columns"]`, not all 11. Request `rules: ["made_up_rule"]` — `404 validation_rule_not_found` before any rule executes.
4. **Negative tests.** Build over a range too short for a selected feature's warmup (e.g. `sma` at `period=200` over a 50-candle range) — expect the `feature_failures` rule to report `code: "feature_generation_failed"`, severity `warning`, not a hard 400 (the underlying `insufficient_data` failure is absorbed into `quality.feature_failures`, per §1.13's partial-success contract).
5. **Error recovery.** Same Retry-button pattern as §8.1 item 5, scoped to the Validation Report section's own error `Alert`.
6. **API verification.** `POST /api/v1/markets/ETHUSD/features/validate` with `{"timeframe": "1h", "features": [{"feature": "ohlcv"}], "required_columns": ["close"]}` → `200`, `passed: true`, `rules_run` containing all 11 alphabetically-sorted names.
7. **Database verification.** **Current implementation does not expose this information** — no validation run is persisted (§2.13).
8. **Export verification.** Click **"Download Report"** — confirm the downloaded JSON's `dataset_id` matches the on-screen `ValidationStatistics` panel's "Dataset ID" field exactly, and that the filename matches `{symbol}-{timeframe}-validation-{YYYYMMDDHHMMSS}.json`. Separately, in the Validation Report panel, toggle the `error` severity chip off, click **"Export Issues"**, and confirm the downloaded JSON contains only `warning`/`info` issues.
9. **History verification.** **Current implementation does not expose this information** (§2.13).
10. **Performance expectations.** No dedicated opt-in performance suite exists for this engine specifically (it reuses the feature dataset build, whose own performance suite is §8.1 item 10); `duration_ms` on every response reports the engine's own wall-clock rule-execution time, excluding the dataset build.

### 8.3 ML Dataset Builder

1. **Happy path.** On `/ml-datasets`: select Market `ETHUSD`, Timeframe `1h`, tick feature `ohlcv`, select prediction target **"Next Candle Direction"** (leave Horizon at its default preset `1 candle`), leave Split at `0.7`/`0.15`/`0.15`, click **"Build ML Dataset"**. Expect `MLDatasetInfoCard`'s "Split rows" field to show three counts summing to `meta.total_rows`, and the new row to appear at the top of the "Dataset History" table (`created_at desc` default sort) without a manual refresh.
2. **Validation tests.** Set Split fields to `0.7` / `0.5` / `0.5` (sum `1.7`) — `SplitConfigForm`'s inline `role="alert"` caption must read `"Ratios must sum to 1.0 (currently 1.7000)."` and the `SplitTimeline` bar must not render while invalid.
3. **Boundary tests.** Set Validation and Test both to `0` (Train `1.0`) — `validateSplitRatios` explicitly allows this (`test_a_zero_ratio_split_is_allowed_for_validation_or_test`); confirm the build still succeeds with `split_bounds.validation_rows == 0`. Set Train to `0` — must be rejected client-side (`"The train ratio must be greater than zero."`) and server-side (`invalid_split_ratios`).
4. **Negative tests.** Select target **"Next Closing Price"** (regression) against a target column whose dtype is categorical — expect `incompatible_target_dtype` surfaced as this build's own error, not a generic failure. Select two targets that would produce the same column (`next_close` twice at the same horizon) — expect `duplicate_target_column`.
5. **Error recovery.** Same Retry pattern; additionally, reopening a Dataset History row that fails to load (network error) shows `role="alert"`: `"Failed to load this dataset build."` inside `DatasetHistoryDetailDialog`.
6. **API verification.** `POST /api/v1/markets/ETHUSD/ml/dataset` with `{"timeframe": "1h", "features": [{"feature": "ohlcv"}], "targets": [{"target": "next_direction", "params": {"horizon": 1}}]}` → `200`, `target_columns == ["next_direction_1"]`, `split.length == meta.total_rows`, `validation.passed` present and boolean.
7. **Database verification.** Query `ml_dataset_builds` after a build and confirm exactly one new row whose `ml_dataset_id` matches the response's own `ml_dataset_id`, `quality_passed` matches `response.validation.passed`, and `payload` deserializes back into an identical `MLDatasetResponse` (round-trip fidelity — the same assertion `MLDatasetBuildDetailResponse.from_model` relies on).
8. **Export verification.** Click **"CSV"**, confirm the Export Summary dialog first (Rows/Columns/Target/Split percentages/Format/an "Approximate size" value with the disclaimer "Size is a rough estimate, not an exact byte count."), then click **"Export"**; confirm the downloaded file's last column is `split` and that filtering rows where `split == "train"` reproduces exactly `split_bounds.train_rows` rows.
9. **History verification.** Delete a Dataset History row via its trash-can icon; confirm the `ConfirmActionDialog`'s description names the exact `{symbol} · {timeframe} ({row_count} rows)` being removed, confirm, and assert the row disappears from the table (via the `['ml-datasets', 'history']` query-cache invalidation) without a page reload.
10. **Performance expectations.** **Current implementation does not expose this information** as a dedicated opt-in suite — `MLDatasetBuilder`'s own performance characteristics are bounded by the underlying `FeatureDatasetBuilder`'s (§8.1 item 10) plus `ChronologicalSplitter`'s O(n) slice, but no `--run-performance` test targets the composed builder specifically.

### 8.4 Experiment Management

1. **Happy path.** On `/experiments`, click **"New Experiment"**, fill **Name** `"Baseline logistic regression"`, leave **Status** at its default `"Draft"`, click **"Create Experiment"**. Expect a `201` and immediate navigation to `/experiments/{id}`, where **Status** now shows a `default`-colored `"Draft"` chip.
2. **Validation tests.** Leave **Name** blank — **"Create Experiment"** stays disabled (`canSubmit = name.trim().length > 0`). Submit via the raw API with an empty `name` — expect `422` (Pydantic `min_length=1`, not an `AppError` domain code).
3. **Boundary tests.** Add exactly 32 tags (the server's `max_length=32`) — succeeds; add a 33rd — `422` from Pydantic validation (not a domain `AppError` — the cap is schema-level, not application-level).
4. **Negative tests.** `PATCH /experiments/{id}` with `{"status": "not_a_status"}` — rejected by Pydantic's `Literal` validation before reaching the service (422), distinct from `TrainingJob`'s own runtime-enforced state machine (§5.7) — **no transition is illegal here**, only an invalid _value_ is.
5. **Error recovery.** Delete an experiment mid-edit (e.g. from another tab) then attempt `PATCH` from the first — expect `404 experiment_not_found`; the detail page's own `role="alert"` Retry button re-fires `GET /experiments/{id}`, which itself then also 404s (expected — the row is genuinely gone).
6. **API verification.** `PATCH /api/v1/experiments/{id}` with `{"tags": ["baseline", "sma-only"]}` — confirm the response's `tags` is exactly `["baseline", "sma-only"]` sorted, and that a _second_ `GET` (not part of the same call) shows the same set persisted, proving `replace_tags`'s commit actually took.
7. **Database verification.** After adding one metric (`name: "accuracy", value: 0.62, unit: null`) and one artifact (`artifact_type: "dataset_export", uri: "ETHUSD-1h-features.csv"`), query `experiment_metrics`/`experiment_artifacts` directly and confirm exactly one row each, both foreign-keyed to the experiment's `id`; delete the experiment and confirm both child rows cascade-delete (`ON DELETE CASCADE`).
8. **Export verification.** **Current implementation does not expose this information** — no dedicated export button exists anywhere on `/experiments` or `/experiments/{id}` (contrast the ML Dataset Builder's CSV/JSON export).
9. **History verification.** **Current implementation does not expose this information** — no timeline/audit log of an experiment's own changes exists (§4.16); only `created_at`/`updated_at` bookend timestamps are tracked.
10. **Performance expectations.** **Current implementation does not expose this information** — no opt-in performance suite targets `ExperimentService`; it is a straightforward CRUD service over a small, unbounded-growth-unlikely table.

### 8.5 ML Training Framework

1. **Happy path.** On `/ml/training`, click **"New Training Job"**, select **Experiment** (the one created in §8.4), leave **Dataset version** auto-populated from the experiment, select **Model type** `"Logistic Regression (Baseline)"`, select **Symbol** `ETHUSD`, **Timeframe** `1h` (both required once `requires_real_data` is true), leave **Target column** blank (defaults to the first built target), leave every known hyperparameter at its default (`epochs=10, learning_rate=0.001, batch_size=32, random_seed=42, validation_frequency=1` — none of which `logistic_regression` actually reads), click **"Create Training Job"**. In the resulting detail dialog, click **"Run"**; expect the 8-step `TrainingJobStageTimeline` to progress to **"Completed"** and `EvaluationSummary` to render a Confusion Matrix, Train/Validation/Test Metrics table, and ROC/PR curves.
2. **Validation tests.** With `logistic_regression` selected, clear **Symbol** — the create dialog's warning `Alert` must list `"Select a market symbol."` and **"Create Training Job"** stays disabled. Type a non-numeric string into a known hyperparameter field (e.g. `learning_rate = "abc"`) — `validateHyperparameterValue` returns `"Must be a number."` inline, and `knownHyperparametersAreValid` must gate the submit button.
3. **Boundary tests.** Set **Epochs** to `0` — expect `"Must be 1 or greater."` (its `min: 1`). Set **Random seed** to `0` — valid (its own `min: 0`, distinct from Epochs' `min: 1`). Attempt to add a custom hyperparameter named `"epochs"` (already known) — expect the inline warning `'"epochs" is already one of the fields above.'`
4. **Negative tests.** Run a job whose experiment has no `feature_set`/`target_config` recorded — expect `400 missing_feature_or_target_config`. Attempt `POST /training-jobs/{id}/run` on a `completed` job — `409 invalid_training_job_transition` (`Cannot move a training job from 'completed' to 'running'`). Attempt `DELETE` on a `running` job — `409 training_job_not_cancellable`.
5. **Error recovery.** Force a failure (e.g. select `linear_regression` against a categorical target) — expect `status: "failed"`, the stage timeline frozen with a red X at the exact failing stage, `error_message` shown in a `role="alert"` Alert, and `error_detail.suggested_fix` visible below it (e.g. _"Choose a target_column whose dtype matches this model's model_kind..."_). Confirm the linked Experiment's own status also became `"failed"` (§4.5/§5.13's `_mark_experiment_failed`).
6. **API verification.** `POST /api/v1/training-jobs/{id}/run` on a `pending` job → `200` always (never 4xx/5xx for an adapter-side failure — only the job's own `status` field reflects success/failure). Confirm `result_summary.metrics` contains `accuracy, precision, recall, f1` for `logistic_regression` specifically.
7. **Database verification.** Query `training_job_logs` for a completed job and confirm exactly 12 rows (`"Starting stage"` + `"Completed stage"` per each of the 6 stages) plus the two bookend `"Training job started"` lines — verify `stage` is `null` only on the bookend lines, one of the 6 stage names on every other.
8. **Export verification.** For a completed `logistic_regression` job, `GET /training-jobs/{id}/artifacts` must list exactly 7 entries (`model_joblib, metrics_json, training_report_json, feature_importance_csv, confusion_matrix_png, roc_curve_png, precision_recall_curve_png`); for `linear_regression`, exactly 4 (no PNGs); for `placeholder`, exactly 1 (`model_joblib`, pointing at a `placeholder://` URI that is **not** a real downloadable file — confirm `GET .../artifacts/model_joblib` for a placeholder job returns `404 training_artifact_not_found`, since its "uri" never starts with `file://`).
9. **History verification.** **Not applicable as a separate concept** — every `TrainingJob` row _is_ itself the persisted history (there is no separate "training run history" beyond the job list itself, unlike Dataset History/Benchmark History which sit atop a stateless builder). The list at `/ml/training` **is** the history view; verify pagination (`TablePagination`, fixed page size 20) and sort (`model_type, status, created_at, updated_at` — note `started_at`/`completed_at` are API-sortable but not exposed as clickable columns in the UI).
10. **Performance expectations.** **Current implementation does not expose this information** — no opt-in performance suite; `run()` is synchronous with no documented timing budget, and `model_metadata.training_duration_seconds`/`cpu_time_seconds` are reported per-run but never asserted against a threshold anywhere in the test suite.

### 8.6 Model Evaluation

1. **Happy path.** On `/ml/evaluation`, enter the completed job's `dataset_version` from §8.5 (or leave blank and instead pick its **Experiment** in the "Experiments" multi-select), click **"Compare"**. Expect `BestModelSummary` to show one card for each of `accuracy, precision, recall, f1` (and `roc_auc` if probabilities were available), each naming `"logistic_regression"` as the winner (trivially, with only one candidate), and the run to appear at the top of "Benchmark History".
2. **Validation tests.** Leave **all three** filter fields blank and click **"Compare"** — the button itself is disabled (`canSubmit` gate) before any request is even sent; confirm via a raw API call that an empty `{}` body independently returns `400 no_benchmark_target`.
3. **Boundary tests.** Compare against a `dataset_version` that matches **more candidates than exist** (trivially satisfied — no server-side cap is hit until `evaluation_benchmark_max_candidates = 100`); confirm a request matching more than 100 completed jobs is capped at the 100 most recently completed (`sort="completed_at", direction="desc", limit=100`).
4. **Negative tests.** Compare against a `dataset_version` matching only `placeholder`-adapter jobs (which record no real `metrics`) — expect `404 empty_benchmark`, rendered with `severity="info"` (not a hard error styling) since the message contains `"No completed"`.
5. **Error recovery.** Same info-styled Retry pattern; separately, reopening a deleted-in-another-tab Benchmark History row — `GET /evaluation/history/{id}` returns `404 benchmark_run_not_found`, surfaced via `reopenedRun.error?.message` in the same `Alert`.
6. **API verification.** `POST /api/v1/evaluation/benchmark` with `{"target_column": "next_direction_1"}` → `200`, `candidates` non-empty, `best_by_metric` containing one entry per metric name present on at least one candidate, each entry's `higher_is_better` matching the metric catalogue's own declared direction (e.g. `accuracy: true`, `mae: false` if a regression job were also included).
7. **Database verification.** Query `evaluation_benchmark_runs` after a successful compare and confirm one new row whose `request`/`response` JSON columns deserialize back into the exact `BenchmarkRequest`/`BenchmarkResponse` the API call produced (byte-for-byte round-trip via `model_dump(mode="json")`/`model_validate`).
8. **Export verification.** Click **"Export"** → **"Export CSV"**; confirm the first line(s) are `Best {metric},{model_type},{value}` for every entry in `best_by_metric`, followed by a blank line, then the header row, then one data row per candidate. Click **"Export JSON"**; confirm the downloaded file is byte-identical (modulo pretty-printing) to the exact `BenchmarkResponse` the page rendered.
9. **History verification.** Reopen a past run via the `Restore` icon in "Benchmark History"; confirm the filter bar's **Dataset version**/**Target column**/**Experiments** fields are restored to exactly the persisted `request`'s own values (via the page's `useEffect` on `reopenedRun.data`), and that the comparison table shows the _exact_ persisted `response`, not a freshly re-run one (verifiable by checking `completed_at` values match the original run's timestamps even if the underlying job has since been deleted).
10. **Performance expectations.** **Current implementation does not expose this information** — no opt-in performance suite exists; the engine's own cost is bounded by `evaluation_benchmark_max_candidates = 100` candidates, each a dict lookup/comparison over already-computed metrics (no per-request model inference or recomputation of any kind).
