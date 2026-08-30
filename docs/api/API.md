# API

## Purpose

HTTP API of the AI-powered Ethereum Market Analysis Platform, served by the
FastAPI service in `services/api` (OpenAPI docs at `/docs`).

## Status

Draft — unauthenticated throughout. Market data, feature engineering,
dataset validation, and the ML dataset builder are read-only/build-only;
Experiment Management and the Machine Learning Training Framework are the
platform's genuinely persistent, full-CRUD surfaces. The Training
Framework implements no real model training — see its section below.

## Overview

The API exposes historical market data and operational monitoring:

- Liveness and metadata: `GET /health`, `GET /api/v1/health`
- Market data (read-only): `GET /api/v1/markets`, `/api/v1/markets/{symbol}/candles`, ...
- Feature engineering: `GET /api/v1/features`, `POST /api/v1/markets/{symbol}/features/dataset|export`
- Dataset validation: `POST /api/v1/markets/{symbol}/features/validate`, `GET /api/v1/validation/rules`
- ML dataset builder: `GET /api/v1/ml/targets`, `POST /api/v1/markets/{symbol}/ml/dataset|dataset/export`
- Experiment management (full CRUD): `GET|POST /api/v1/experiments`, `GET|PATCH|DELETE /api/v1/experiments/{id}`, plus nested metrics/artifacts
- Machine Learning Training Framework (full CRUD + lifecycle + baseline models): `GET|POST /api/v1/training-jobs`, `GET|DELETE /api/v1/training-jobs/{id}`, `POST /api/v1/training-jobs/{id}/run|cancel|predict`, `GET /api/v1/training-jobs/models`
- Model Evaluation & Benchmarking Engine (read-only, plus persisted history): `GET /api/v1/evaluation/metrics`, `POST /api/v1/evaluation/benchmark`, `GET /api/v1/evaluation/history`, `GET|DELETE /api/v1/evaluation/history/{id}`
- Platform health monitoring: `GET /api/v1/system/health|status|metrics`

## Endpoints

### Liveness

| Method | Path             | Purpose                                    |
| ------ | ---------------- | ------------------------------------------ |
| GET    | `/health`        | Liveness + DB connectivity (503 when down) |
| GET    | `/api/v1/health` | Versioned alias of `/health`               |

### Market data

| Method | Path                                     | Purpose                                                                                                                  |
| ------ | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| GET    | `/api/v1/markets`                        | All tracked markets, ordered by symbol                                                                                   |
| GET    | `/api/v1/markets/{symbol}/timeframes`    | Timeframes with stored candles                                                                                           |
| GET    | `/api/v1/markets/{symbol}/candles`       | Paginated candle history (limit/offset)                                                                                  |
| GET    | `/api/v1/markets/{symbol}/candles/stats` | Aggregate stats for a timeframe/range (count, min/max price, avg volume, first/last candle); 404 when the range is empty |
| GET    | `/api/v1/markets/{symbol}/latest`        | Newest candle for a market/timeframe                                                                                     |

### Technical indicators

| Method | Path                                         | Purpose                                                       |
| ------ | -------------------------------------------- | ------------------------------------------------------------- |
| GET    | `/api/v1/indicators`                         | Catalogue of every registered indicator, with parameter specs |
| GET    | `/api/v1/indicators/{indicator}`             | One indicator's metadata, parameters, and output series       |
| GET    | `/api/v1/markets/{symbol}/indicators/{name}` | Run one indicator over the market's stored candles            |
| POST   | `/api/v1/markets/{symbol}/indicators/batch`  | Run several indicators over one shared candle load            |

Registered today: the **Trend Indicator Package** — `sma`, `ema`, `wma`
(all `category: "trend"`) — plus `rsi` (`category: "momentum"`). The set
is queried from `GET /api/v1/indicators` at runtime, never hardcoded by a
client; see `ARCHITECTURE.md` § "Technical Indicator Engine" for how a new
indicator joins this list with no API change.

**The catalogue is the contract.** Each entry publishes every parameter's
type, label, description, default, required-ness, inclusive `minimum`/
`maximum`, and permitted `choices` — enough for a client to build a
complete, correctly-constrained input form without hardcoding anything
about any particular indicator. That is deliberate: registering a new
indicator on the backend must not require a frontend change (the dashboard's
`/indicators` page generates its whole parameter form from this response).

Each entry also carries engineering metadata: `version` (an
indicator-level semver, independent of the platform's own release
version), `author`, `complexity` (a free-form Big-O note), and
`warmup_description` (how the warmup relates to this indicator's
parameters, e.g. "Equal to the period parameter"). "Output type" and
"supported price sources" are deliberately not separate fields — they are
already derivable from `outputs` and from the `source` parameter's
`choices`, and a client should derive them rather than assume a second,
possibly-drifting source of the same fact.

Each entry also carries `aliases: string[]` (default `[]`) — alternate
names a client's search should also match, e.g. `["MA", "Moving Average",
"Simple MA"]` for `sma`. Purely a discoverability aid: an indicator with no
aliases is unaffected, and a client is free to ignore the field entirely.

**Calculation parameters are ordinary query parameters.** Beyond the
reserved `timeframe`, `start`, `end`, and `limit`, every query key is
passed to the indicator and validated against its own declared specs:

```http
GET /api/v1/markets/ETHUSD/indicators/sma?timeframe=1h&period=20&source=close
```

An unknown parameter is **rejected, not ignored** — a typo that silently
fell back to a default would return a plausible-looking but wrong series,
the worst failure mode for a research tool.

**Response shape.** `timestamps` holds the candle open times, and every
entry in `series` is aligned index-for-index with it. A `null` value marks
a warmup position where the indicator is not yet defined — never a
calculation failure, which arrives as an error response instead:

```jsonc
{
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "indicator": {
    "name": "sma",
    "label": "Simple Moving Average",
    "version": "1.0.0",
    "author": "Eth AI Platform",
    "complexity": "O(n) — one running-sum pass over the candle range.",
    "warmup_description": "Equal to the period parameter.",
    "...": "...",
  },
  "parameters": { "period": 20, "source": "close" }, // fully resolved, defaults applied
  "timestamps": ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"],
  "series": [{ "name": "sma", "label": "SMA(20)", "values": [null, 3055.25] }],
  "meta": {
    "candles_analyzed": 2,
    "warmup_candles": 1,
    "execution_time_ms": 0.08,
    "database_time_ms": 3.2,
    "cache_status": "miss",
    "generated_at": "2026-01-01T02:00:00Z",
  },
}
```

Indicator values serialize as JSON **numbers**, not the decimal-as-string
convention the candle endpoints use. An EMA or RSI is a float
approximation by construction, and a lossless decimal string would imply a
precision the calculation does not have. No rounding is applied
server-side — every value is the raw float the calculation produced;
display-only rounding is strictly a frontend concern.

An `invalid_indicator_parameter` for an out-of-range value recommends the
parameter's own declared default, e.g.
`"Parameter 'period' must be >= 1, got 0 (recommended: 20)"` — reusing the
one value the spec already vouches for as sane, never a fabricated
suggestion. No recommendation is offered for a required parameter (it has
no default to recommend).

Indicator-specific error codes: `indicator_not_found` (404),
`invalid_indicator_parameter` (400), `insufficient_data` (400 — the range
is shorter than the indicator's warmup), and `indicator_execution_failed`
(500 — a bug inside one indicator, named so it is obvious which). The
shared `market_not_found`, `candle_not_found`, `invalid_timeframe`,
`invalid_range`, and `limit_exceeded` codes apply here too.

**Batch calculation — the chart overlay API.** `POST
/api/v1/markets/{symbol}/indicators/batch` runs up to 50 indicators over the
same shared candle load — the backend behind the dashboard's Indicator
Management & Chart Overlay System (`ARCHITECTURE.md` § "Indicator
Management & Chart Overlay System"). Request body:

```jsonc
{
  "timeframe": "1h",
  "start": "2026-01-01T00:00:00Z", // optional, same semantics as the single-indicator endpoint
  "end": "2026-01-02T00:00:00Z", // optional
  "limit": 500, // optional
  "requests": [
    { "indicator": "sma", "params": { "period": "20" } },
    { "indicator": "ema", "params": { "period": "20" } },
    { "indicator": "nope" }, // an unknown indicator — see below
  ],
}
```

The candles are loaded **once** for the whole batch, not once per requested
indicator. The response shares one `timestamps` array across every result,
and each entry in `results` succeeds or fails **independently**:

```jsonc
{
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "timestamps": ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"],
  "results": [
    {
      "indicator": "sma",
      "success": true,
      "label": "Simple Moving Average",
      "parameters": { "period": 20 },
      "series": [{ "name": "sma", "label": "SMA(20)", "values": [null, 3055.25] }],
      "cache_status": "miss",
      "warmup_candles": 19,
      "execution_time_ms": 0.06,
      "error_code": null,
      "error_detail": null,
    },
    {
      "indicator": "nope",
      "success": false,
      "label": null,
      "parameters": null,
      "series": null,
      "cache_status": null,
      "warmup_candles": null,
      "execution_time_ms": null,
      "error_code": "indicator_not_found",
      "error_detail": "No indicator registered as 'nope'.",
    },
  ],
  // Shared by every result in the batch (one candle load, one engine):
  "candles_analyzed": 2,
  "database_time_ms": 1.4,
  "engine_version": "1.0.0",
  "generated_at": "2026-01-01T02:00:00Z",
}
```

`warmup_candles`/`execution_time_ms` are per-item (present only on
success, like `cache_status`) since each indicator in a batch still runs,
warms up, and is cached independently. `candles_analyzed`,
`database_time_ms`, `engine_version`, and `generated_at` are reported once
for the whole batch, the same "share what's shared" convention
`timestamps` already follows — `engine_version` versions the _execution
pipeline itself_, independent of any individual indicator's own `version`.

One bad indicator name or an out-of-range parameter in one request item
never fails the other items — this is deliberate, since a research UI
managing several overlays must not lose every other correctly-configured
overlay because of one mistake. A failure that means there is no candle
data to compute _anything_ from (unknown market, invalid timeframe/range/
limit — the same `market_not_found`/`invalid_timeframe`/`invalid_range`/
`limit_exceeded` codes as every other endpoint here) still fails the whole
request with a 404/400, since no per-item result would be meaningful
without candles to compute over. This endpoint is purely additive: `GET
/markets/{symbol}/indicators/{name}` and every other indicator route are
unchanged.

### Feature engineering

| Method | Path                                            | Purpose                                                       |
| ------ | ----------------------------------------------- | ------------------------------------------------------------- |
| GET    | `/api/v1/features`                              | Catalogue of every registered generator, with parameter specs |
| GET    | `/api/v1/features/lineage`                      | The whole registry's dependency graph, resolved               |
| GET    | `/api/v1/features/{feature}`                    | One generator's metadata, parameters, and output columns      |
| POST   | `/api/v1/markets/{symbol}/features/dataset`     | Build a feature dataset (optionally truncated for preview)    |
| POST   | `/api/v1/markets/{symbol}/features/export`      | Build the same dataset and stream it as a CSV or JSON file    |
| POST   | `/api/v1/markets/{symbol}/features/correlation` | Build the same dataset and correlate its numeric columns      |
| POST   | `/api/v1/markets/{symbol}/features/statistics`  | Build the same dataset and summarize every column, complete   |

Registered today: `ohlcv` (`category: "raw"`), `candle_shape`
(`price_action`), and `sma`/`ema`/`wma` (`trend`). The set is queried from
`GET /api/v1/features` at runtime, never hardcoded by a client; see
`ARCHITECTURE.md` § "Feature Engineering Engine" for how a new generator
joins this list with no API change.

**The catalogue is the contract**, exactly as for indicators — each entry
publishes every parameter's type, bounds, choices, default, and
required-ness, so a client builds a correctly-constrained selection form
from this response alone. Entries carry the same engineering metadata
(`version`, `author`, `complexity`, `warmup_description`, `aliases`) plus
`outputs`, the column-name templates the generator produces (e.g.
`["sma_{period}"]`), and five additive fields from the production-hardening
pass: `unit` (e.g. `"price"`, `""` when not applicable), `value_type`
(`"float"` / `"categorical"` / `"mixed"`), `dependencies` (other feature
names this one requires in the same request — empty for every generator
shipped today), `is_deterministic` (always `true` currently — reserved for
a future stochastic generator), and `missing_values_expected` (whether nulls
beyond warmup are a normal outcome, e.g. `candle_shape`'s normalized wick
ratios on a flat candle). A feature declaring `dependencies` that is
requested without them yields `missing_feature_dependency` (400) — see
"Feature-specific error codes" below.

`version` is a **generator-level** semver, bumped when a change would alter
previously-computed values — so a dataset recorded against 1.0.0 is known
not to be reproducible under 2.0.0.

**`sma`/`ema`/`wma` are the same implementations the indicator API serves.**
They are not reimplemented here; the feature wraps the registered indicator
and delegates to the same engine, so `label`, `complexity`, `aliases`, and
the computed values are identical to `GET /api/v1/indicators/{name}`. This
is what guarantees a dataset column and a chart overlay can never disagree.

**Dataset requests use a JSON body**, unlike the indicator endpoints'
query parameters, because a dataset request is inherently a _list_ of
feature/parameter pairs that a flat query string cannot express:

```jsonc
{
  "timeframe": "1h",
  "start": "2026-01-01T00:00:00Z", // optional, half-open [start, end)
  "end": "2026-02-01T00:00:00Z", // optional
  "limit": 500, // rows in the dataset, not candles read — see below
  "drop_warmup": true, // default; drop rows where any feature is undefined
  "preview_rows": 200, // optional cap on the response only
  "features": [
    { "feature": "ohlcv" },
    { "feature": "candle_shape", "params": { "normalize": "true" } },
    { "feature": "sma", "params": { "period": "20" } },
  ],
}
```

**Response shape.** Row-oriented: `rows` is parallel to `timestamps`, and
each row's values are ordered exactly as `columns`. Repeating column names
per row (a records-oriented shape) would roughly double the payload for a
wide dataset.

```jsonc
{
  "dataset_id": "6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90", // fresh uuid4 per build — never a content hash
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "columns": [
    { "name": "close", "label": "Close", "description": "...", "dtype": "float" },
    { "name": "candle_direction", "label": "...", "dtype": "categorical" },
    { "name": "sma_20", "label": "SMA(20)", "dtype": "float" },
  ],
  "timestamps": ["2026-01-01T19:00:00Z", "2026-01-01T20:00:00Z"],
  "rows": [
    [3055.25, "up", 3010.11],
    [3180.5, "down", 3021.44],
  ],
  "features": [
    {
      "feature": "sma",
      "label": "Simple Moving Average",
      "version": "1.0.0",
      "parameters": { "period": 20, "source": "close" }, // fully resolved
      "columns": ["sma_20"],
      "warmup": 20,
      "execution_time_ms": 0.06,
      "cache_status": "miss", // "hit" | "miss" | "disabled" — see the Feature Cache
    },
  ],
  "meta": {
    "row_count": 2, // rows in _this_ response
    "total_rows": 481, // rows in the full dataset
    "truncated": true, // capped by preview_rows
    "candles_analyzed": 500,
    "rows_dropped": 19,
    "warmup_candles": 20,
    "database_time_ms": 8.1,
    "pipeline_version": "1.0.0",
    "generated_at": "2026-01-01T21:00:00Z",
  },
  "quality": {
    "total_rows": 500, // candles read, before warmup trimming
    "rows_returned": 481,
    "rows_removed": 19,
    "null_counts": { "sma_20": 0 }, // computed before trimming, so a mid-series null is never hidden
    "duplicate_timestamps": 0,
    "missing_candles": 0,
    "feature_failures": [], // see "Partial-success dataset building" below
    "generation_time_ms": 4.7,
  },
}
```

**`dataset_id` identifies one specific build, not one specific request
shape.** Rebuilding an identical request later — over data that may itself
have changed — yields a new `dataset_id`; it is a build-time snapshot
identifier, not a hash a caller can use to detect "did anything change."
Reproducibility instead comes from the existing provenance fields
(`pipeline_version`, each feature's `version` and resolved `parameters`).

**`quality` reports the dataset's own trustworthiness.** It is present on
every dataset response (build and export alike) and is what makes a
partially-failed or partially-trimmed dataset legible without a caller
having to infer it from row counts alone. `null_counts` is computed
**before** `drop_warmup` trims anything, so a column whose nulls extend
past the warmup boundary (e.g. a normalized wick ratio on a flat candle)
still shows up. `duplicate_timestamps` and `missing_candles` are computed
over the full candle series actually read, independent of any feature.

`dtype` is published per column because a consumer needs to know whether a
column is continuous or categorical _before_ deciding how to encode it —
the difference between scaling and one-hot encoding — and the column name
rarely says which.

**Column names encode the parameters that produced them**, so requesting
the same generator twice at different periods yields `sma_20` and `sma_50`
rather than a collision. A non-default `source` is always visible
(`sma_20_high`): a column must never hide a parameter that changes its
values. Two requested features that _would_ collide are rejected with
`duplicate_feature_column` naming both — a silently overwritten column is
the worst possible dataset defect.

**`limit` counts dataset rows, not candles read.** The server widens its
candle window by the largest requested warmup, then trims back, so asking
for 500 rows with an SMA(50) returns 500 — not 450. Without this, adding a
longer-period feature would silently shrink an existing dataset.
`candles_analyzed` reports the wider figure.

**Warmup rows are dropped by default.** A training matrix must not contain
nulls, and imputing them is a modelling decision this API must not make
silently — so any row where a requested feature is still undefined is
removed, and `rows_dropped`/`warmup_candles` always report what happened.
Pass `"drop_warmup": false` to keep full alignment with the candle range,
in which case warmup positions appear as `null`.

**Export is a separate endpoint and always complete.** `preview_rows` is
ignored by `/features/export`: an export truncated to what a preview
happened to show would silently produce a partial training set. Both
formats carry `dataset_id`, `exported_at` (when the file was written —
distinct from the dataset's own `generated_at`), the pipeline version, each
feature's version, its resolved parameters, and the full `quality` summary,
so an exported file is reproducible and self-describing without the
original API response. CSV writes that provenance as `#`-prefixed comment
lines (one `# feature.<name>,version=... params=(...) columns=(...)
warmup=...` line per feature, one `# quality.*` line per metric), which
`pandas.read_csv(..., comment='#')` skips natively; `?format=json` emits
one object per row plus the same metadata under a `quality` key.

Supported formats are driven by an internal `ExportFormat` registry
(`extension`, `media_type`, `serialize`), not a hardcoded branch — the
`format` query parameter's valid values (currently `csv`|`json`) are
generated from that registry, so a future format (Parquet) is one registry
entry with no change to this endpoint's contract beyond a new accepted
value.

**Partial-success dataset building — a per-feature failure no longer fails
the request.** `feature_not_found`, `invalid_feature_parameter`,
`insufficient_data`, and `feature_execution_failed` (the same situations
that are hard 404/400/500 errors on the single-feature `GET
/api/v1/features/{feature}` lookup) do **not** raise on `/features/dataset`
or `/features/export`. Instead each is recorded as one entry in
`quality.feature_failures` — `{ "feature": "ema", "params": {...},
"error_code": "insufficient_data", "error_detail": "..." }` — and the
response still returns `200` with every other requested feature's columns
intact. This mirrors the indicator batch endpoint's already-established
partial-success contract: a ten-feature request with one bad feature
returns nine good columns and one explained failure, not a blanket 4xx that
discards the nine.

⚠️ **Behavior change from the initial Feature Engineering Engine release**:
those four codes previously aborted the whole dataset build with a matching
HTTP error status. A client written against that earlier behavior that
branches on a 4xx/5xx status for a bad feature request must be updated to
instead check `quality.feature_failures` on an otherwise-200 response.

Two error codes still hard-fail the whole request, because there is no
partial result that makes sense: `duplicate_feature_column` (400 — two
requested features collided on one output column, naming both) and
`missing_feature_dependency` (400, new — a requested feature's declared
`dependencies` were not also included in the request). `empty_dataset` (400)
is narrower than before: it now fires only when columns exist but every row
was legitimately trimmed as warmup, not when every requested feature failed
outright (that case is instead a `200` with zero columns and a fully
populated `quality.feature_failures`). The shared `market_not_found`,
`candle_not_found`, `invalid_timeframe`, `invalid_range`, and
`limit_exceeded` codes apply here too.

**Feature dependency graph** (`GET /features/lineage`) — resolves every
registered generator's `dependencies` into a full graph. Registered
_before_ `GET /features/{feature}` in the router so the literal path
`lineage` is never matched as a `{feature}` path parameter.

```jsonc
{
  "nodes": [
    {
      "name": "sma",
      "label": "Simple Moving Average",
      "category": "trend",
      "dependencies": [], // this feature's own declared dependencies
      "depended_on_by": [], // features that declare a dependency on this one
      "ancestors": [], // the full transitive closure of `dependencies`
      "descendants": [], // the full transitive closure of `depended_on_by`
    },
    // ... one entry per registered generator
  ],
  "edges": [], // (dependency, dependent) pairs — empty today, see below
  "topological_order": ["candle_shape", "ema", "ohlcv", "sma", "wma"],
}
```

No shipped generator declares a dependency today (see `FeatureMetadata.dependencies`'s
own docstring), so a real response has `"edges": []` and every node's
`dependencies`/`depended_on_by`/`ancestors`/`descendants` empty — the
honest current state, not a placeholder. The graph, cycle detection, and
topological order are all real and already exercised by the registry's own
startup validation.

**Feature correlation matrix** (`POST /markets/{symbol}/features/correlation`)
and **feature statistics** (`POST /markets/{symbol}/features/statistics`) —
both accept the exact same request body as `/features/dataset` and build
the identical dataset server-side (via the same `FeatureService.build_raw`
every dataset/export request already shares), then run a pure, read-only
computation over it — nothing here recomputes a feature or issues a
second database query.

```jsonc
// POST .../features/correlation
{
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "columns": ["open", "high", "low", "close", "volume"], // numeric columns only
  "matrix": [[1.0, 0.99, 0.98, 0.97, 0.42], ["..."]], // matrix[i][j] = correlation(columns[i], columns[j])
  "row_count": 481, // rows actually used (pairwise-complete per column pair)
}
```

Empty (`"columns": []`) when fewer than two numeric columns are present —
not an error, since a single-feature or all-categorical dataset is a
perfectly valid dataset to have built.

```jsonc
// POST .../features/statistics
{
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "columns": [
    {
      "column": "close",
      "count": 481,
      "null_count": 0,
      "mean": 3061.4,
      "std": 42.7,
      "minimum": 2980.1,
      "maximum": 3199.9,
    },
    {
      "column": "candle_direction",
      "count": 481,
      "null_count": 0,
      "mean": null, // categorical/boolean columns get count/null_count only
      "std": null,
      "minimum": null,
      "maximum": null,
    },
  ],
  "row_count": 481,
}
```

Unlike `/features/dataset`'s own response, `/features/statistics` is
**never** capped by `preview_rows` — it always describes the complete
dataset, the same "preview vs. export" distinction this API already draws
for CSV/JSON downloads. Both endpoints surface the exact same error codes
as `/features/dataset` (`market_not_found`, `invalid_feature_parameter`,
etc.), since both build through the identical path.

### Dataset validation

| Method | Path                                         | Purpose                                                          |
| ------ | -------------------------------------------- | ---------------------------------------------------------------- |
| POST   | `/api/v1/markets/{symbol}/features/validate` | Build a dataset and run every registered validation rule over it |
| GET    | `/api/v1/validation/rules`                   | Catalogue of every registered validation rule                    |

This surface is the platform's mandatory quality gate ahead of AI
training, backtesting, or research use — see `ARCHITECTURE.md` § "Dataset
Validation & Quality Engine" for the rule architecture and `AI.md` for how
it fits the AI-readiness pipeline. It builds nothing new: `POST
.../validate` builds the _same_ dataset `/features/dataset` and
`/features/export` build (via the shared `FeatureService.build_raw`), then
runs the validation engine's rules over it.

**The request body extends the dataset-build request, rather than
redeclaring it.** `DatasetValidationRequest` is a `FeatureDatasetRequest`
(the identical `timeframe`/`start`/`end`/`limit`/`features`/`drop_warmup`
body `/features/dataset` accepts) plus two validation-only fields:

```jsonc
{
  "timeframe": "1h",
  "features": [{ "feature": "ohlcv" }, { "feature": "sma", "params": { "period": "20" } }],
  "required_columns": ["close", "sma_20"], // optional — additionally require these columns
  "rules": ["required_columns", "duplicate_timestamps"], // optional — run only this subset
}
```

Omitting `rules` runs every registered rule. Naming an unregistered rule
returns `validation_rule_not_found` (404), listing every valid name.

**Response shape.** A structured, JSON quality report:

```jsonc
{
  "dataset_id": "6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90",
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "engine_version": "1.0.0", // the validation engine's own version, independent of any rule's
  "validated_at": "2026-01-01T21:00:05Z",
  "passed": false, // false only when at least one error-severity issue was found
  "rules_run": ["required_columns", "data_types", "..."],
  "summary": { "total_checks": 2, "errors": 1, "warnings": 1, "info": 0 },
  "categories": {
    "structural": { "errors": 0, "warnings": 0, "info": 0 },
    "data_quality": { "errors": 1, "warnings": 0, "info": 0 }, // every category is present, even at zero
    "time_series": { "errors": 0, "warnings": 1, "info": 0 },
    "feature": { "errors": 0, "warnings": 0, "info": 0 },
  },
  "issues": [
    {
      "rule": "duplicate_timestamps",
      "category": "data_quality",
      "severity": "error",
      "code": "duplicate_timestamps",
      "message": "1 timestamp(s) appear more than once — each row must be uniquely timestamped",
      "column": null,
      "row_index": null,
      "count": 1,
      "details": {},
    },
    {
      "rule": "time_gaps",
      "category": "time_series",
      "severity": "warning",
      "code": "time_gaps",
      "message": "1 expected 1h interval(s) are missing from the delivered series",
      "count": 1,
    },
  ],
  "rows": 480,
  "columns": 6,
  "duration_ms": 3.2,
}
```

**Severity is three-tier, like a linter's**: `error` (fails the gate, in
`summary.errors` and `passed`), `warning` (reported, never blocks),
`info` (context only). `duplicate_rows` and `time_gaps` default to
`warning` — a repeated row or a gap in the series is worth a researcher's
attention but is not automatically disqualifying the way a NaN, an
infinity, or a duplicate/out-of-order timestamp is (every other rule
defaults to `error`).

**Eleven builtin rules across four categories** — `GET /validation/rules`
is the live catalogue (name, category, description, default severity);
today's set:

| Category       | Rules                                                                                       |
| -------------- | ------------------------------------------------------------------------------------------- |
| `structural`   | `required_columns`, `data_types`                                                            |
| `data_quality` | `missing_values`, `duplicate_rows`, `duplicate_timestamps`, `nan_values`, `infinite_values` |
| `time_series`  | `timestamp_ordering`, `time_gaps`                                                           |
| `feature`      | `metadata_consistency`, `feature_failures`                                                  |

Adding a rule requires no change to this endpoint's contract — a new rule
file with `@register` appears in `rules_run`/`GET /validation/rules`
automatically.

Error codes specific to this endpoint: `validation_rule_not_found` (404 —
an unregistered name in `rules`). Every error code from `/features/dataset`
(`market_not_found`, `invalid_timeframe`, `invalid_range`,
`limit_exceeded`, `duplicate_feature_column`, `missing_feature_dependency`)
also applies here, since building the dataset is the first step; the four
partial-success feature codes (`feature_not_found`,
`invalid_feature_parameter`, `insufficient_data`,
`feature_execution_failed`) never surface as HTTP errors here either — a
failed feature is recorded in `quality.feature_failures` during the build
and then, distinctly, surfaced again as a `feature_generation_failed`
validation issue by the `feature_failures` rule.

### ML dataset builder

| Method | Path                                         | Purpose                                                              |
| ------ | -------------------------------------------- | -------------------------------------------------------------------- |
| GET    | `/api/v1/ml/targets`                         | Catalogue of every registered prediction-target generator            |
| GET    | `/api/v1/ml/targets/{target}`                | One target generator's full metadata                                 |
| POST   | `/api/v1/markets/{symbol}/ml/dataset`        | Build a versioned, split, validated ML dataset                       |
| POST   | `/api/v1/markets/{symbol}/ml/dataset/export` | Export the complete dataset (`?format=csv\|json`) with a split label |

This is the platform's one supported path for producing a dataset used in
AI training — see `ARCHITECTURE.md` § "ML Dataset Builder" and `AI.md` §
"ML Dataset Builder" for the full leakage-prevention design. It builds
nothing new by itself: features come from the same `FeatureDatasetBuilder`
`/features/dataset` uses, and the embedded `validation` verdict comes from
the same `DatasetValidator` `/features/validate` uses.

**`GET /ml/targets`** — the target catalogue, in the same shape as `GET
/features`:

```jsonc
{
  "targets": [
    {
      "name": "next_close",
      "label": "Next Close Price",
      "description": "The close price N candles ahead.",
      "category": "price",
      "parameters": [
        {
          "name": "horizon",
          "type": "int",
          "label": "Horizon",
          "default": 1,
          "minimum": 1,
          "maximum": 500,
          "required": false,
          "choices": [],
        },
      ],
      "outputs": ["next_close_{horizon}"],
      "version": "1.0.0",
      "author": "Eth AI Platform",
      "value_type": "float",
      "default_horizon": 1,
      "is_deterministic": true,
    },
    // next_return (value_type "float"), next_direction (value_type "categorical") — same shape
  ],
  "total": 3,
  "categories": ["price", "return", "direction"],
}
```

**The request body extends the dataset-build request, rather than
redeclaring it.** `MLDatasetRequest` is a `FeatureDatasetRequest` (the
identical `timeframe`/`start`/`end`/`limit`/`features`/`drop_warmup` body
`/features/dataset` accepts) plus targets and a split:

```jsonc
{
  "timeframe": "1h",
  "features": [{ "feature": "ohlcv" }],
  "targets": [
    { "target": "next_close", "params": { "horizon": "1" } },
    { "target": "next_direction" }, // horizon defaults to the generator's own default_horizon
  ],
  "drop_undefined_targets": true, // default; drops trailing rows with no future candle to label them from
  "split_train": 0.7,
  "split_validation": 0.15,
  "split_test": 0.15,
}
```

At least one target is required. `split_train`/`split_validation`/
`split_test` must each be non-negative, `split_train` must be greater than
zero, and the three must sum to `1.0` within a `1e-6` tolerance, or the
request 400s with `invalid_split_ratios` before any building happens.

**Response shape** — a target-appended, split `FeatureDataset` plus its
versioning and validation record:

```jsonc
{
  "ml_dataset_id": "9c1e4a2c-...", // this exact ML artifact's identity
  "dataset_id": "6f1e4a2c-...", // the underlying feature build's own identity
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "columns": [
    { "name": "close", "label": "Close", "dtype": "float", "description": "..." },
    { "name": "next_close_1", "label": "Next Close (h=1)", "dtype": "float", "description": "..." },
  ],
  "feature_columns": ["close"], // model inputs (X)
  "target_columns": ["next_close_1"], // prediction labels (y)
  "timestamps": ["2026-01-01T00:00:00Z", "..."],
  "rows": [[3055.25, 3180.5]],
  "split": ["train"], // per-row label, parallel to rows/timestamps — "train" | "validation" | "test"
  "features": [
    {
      "feature": "ohlcv",
      "label": "OHLCV",
      "version": "1.0.0",
      "parameters": {},
      "columns": ["close"],
      "warmup": 0,
      "execution_time_ms": 0.1,
    },
  ],
  "targets": [
    {
      "target": "next_close",
      "label": "Next Close Price",
      "version": "1.0.0",
      "parameters": { "horizon": 1 },
      "columns": ["next_close_1"],
      "horizon": 1,
      "execution_time_ms": 0.2,
    },
  ],
  "target_failures": [], // partial-success record — a failed target never blocks the others
  "split_ratios": { "train": 0.7, "validation": 0.15, "test": 0.15 },
  "split_bounds": { "train_rows": 700, "validation_rows": 150, "test_rows": 149 },
  "quality": {
    "total_rows": 999,
    "rows_returned": 999,
    "rows_removed": 0,
    "null_counts": {},
    "duplicate_timestamps": 0,
    "missing_candles": 0,
    "feature_failures": [],
    "generation_time_ms": 0.4,
  },
  "validation": {
    "dataset_id": "6f1e4a2c-...",
    "symbol": "ETHUSD",
    "timeframe": "1h",
    "engine_version": "1.0.0",
    "validated_at": "2026-01-01T21:00:05Z",
    "passed": true,
    "rules_run": ["..."],
    "summary": { "total_checks": 11, "errors": 0, "warnings": 0, "info": 0 },
    "categories": {},
    "issues": [],
    "rows": 999,
    "columns": 2,
    "duration_ms": 3.1,
  }, // the same ValidationReport shape /features/validate returns
  "meta": {
    "row_count": 999,
    "total_rows": 999,
    "candles_analyzed": 1001,
    "rows_dropped_warmup": 0, // rows removed because a feature was still in warmup
    "rows_dropped_horizon": 1, // trailing rows removed because a target had no future candle yet — the leakage-prevention trim
    "warmup_candles": 0,
    "max_horizon": 1,
    "truncated": false,
    "database_time_ms": 1.4,
    "pipeline_version": "1.0.0",
    "target_pipeline_version": "1.0.0",
    "builder_version": "1.0.0",
    "generated_at": "2026-01-01T21:00:05Z",
    "created_at": "2026-01-01T21:00:05Z",
  },
}
```

**Export** (`POST .../ml/dataset/export?format=csv|json`) accepts the same
body (`preview_rows` is ignored — an export is always the complete,
unsplit-into-files matrix) and returns one flat file containing every row
plus the `split` column — never three separate files. The CSV's comment
preamble additionally lists each target's resolved parameters and version,
alongside the feature provenance `/features/export` already documents.

**Error codes specific to this surface.** Four target-generation codes are
partial-success, never a hard failure during a build — mirroring the
feature-engineering contract exactly — each recorded as one entry in
`target_failures` while every other requested target still returns:
`target_not_found` (also a top-level 404 when requested directly via `GET
/ml/targets/{target}`), `invalid_target_parameter`, `insufficient_data`
(shared code with the equivalent feature/indicator case), and
`target_execution_failed`. Three codes do hard-fail the request (400):
`duplicate_target_column` (two targets, or a target and a feature,
producing the same column name — no partial result makes sense for a name
collision), `invalid_split_ratios`, and `empty_ml_dataset` (every row fell
inside some target's undefined horizon window; distinct from zero target
columns, which is a valid, fully-explained result, not an error). Every
error code from `/features/dataset` also applies here, since building
features is the first step; the four partial-success feature codes
surface identically (recorded in `quality.feature_failures`, not raised).

### Experiment management

| Method | Path                                               | Purpose                                         |
| ------ | -------------------------------------------------- | ----------------------------------------------- |
| POST   | `/api/v1/experiments`                              | Register a new experiment                       |
| GET    | `/api/v1/experiments`                              | Search, filter, sort, and paginate experiments  |
| GET    | `/api/v1/experiments/{id}`                         | Get one experiment (with metrics and artifacts) |
| PATCH  | `/api/v1/experiments/{id}`                         | Partial update                                  |
| DELETE | `/api/v1/experiments/{id}`                         | Delete an experiment and its children           |
| POST   | `/api/v1/experiments/{id}/metrics`                 | Record a metric                                 |
| DELETE | `/api/v1/experiments/{id}/metrics/{metric_id}`     | Delete a metric                                 |
| POST   | `/api/v1/experiments/{id}/artifacts`               | Record an artifact reference                    |
| DELETE | `/api/v1/experiments/{id}/artifacts/{artifact_id}` | Delete an artifact reference                    |

The platform's one registry for experiment provenance — see
`ARCHITECTURE.md` § "Experiment Management System" for the full design.
Unlike every other surface in this document, this is a genuinely
persistent CRUD resource: an experiment is a real row, not a value
recomputed on every request.

**Create** (`POST /experiments`):

```jsonc
{
  "name": "baseline sma experiment",
  "dataset_version": "9c1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90", // the ML Dataset Builder's own ml_dataset_id
  "feature_set": [{ "feature": "sma", "params": { "period": "20" } }],
  "target_config": [{ "target": "next_close", "params": { "horizon": "1" } }],
  "split_config": { "train": 0.7, "validation": 0.15, "test": 0.15 },
  "model_type": "xgboost_baseline", // a placeholder label only — no training engine exists yet
  "status": "draft", // draft | running | completed | failed | archived — defaults to draft
  "notes": "first attempt, default hyperparameters",
  "tags": ["baseline", "sma"],
}
```

Every field except `name` is optional. `dataset_version`/`feature_set`/
`target_config`/`split_config` are **not** validated against a real
dataset — the ML Dataset Builder never persists one to reference (§ "ML
dataset builder" above) — they are recorded as given, the same way a lab
notebook entry would cite them.

**Response shape** — the full record, including its metrics and artifact
references:

```jsonc
{
  "id": "6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90",
  "name": "baseline sma experiment",
  "dataset_version": "9c1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90",
  "feature_set": [{ "feature": "sma", "params": { "period": "20" } }],
  "target_config": [{ "target": "next_close", "params": { "horizon": "1" } }],
  "split_config": { "train": 0.7, "validation": 0.15, "test": 0.15 },
  "model_type": "xgboost_baseline",
  "status": "draft",
  "notes": "first attempt, default hyperparameters",
  "tags": ["baseline", "sma"],
  "metrics": [
    {
      "id": "...",
      "name": "accuracy",
      "value": 0.87,
      "unit": "ratio",
      "recorded_at": "2026-01-01T21:00:05Z",
    },
  ],
  "artifacts": [
    {
      "id": "...",
      "artifact_type": "dataset_export",
      "uri": "ETHUSD-1h-ml-dataset.csv",
      "description": null,
      "created_at": "2026-01-01T21:00:05Z",
    },
  ],
  "created_at": "2026-01-01T21:00:05Z",
  "updated_at": "2026-01-01T21:00:05Z",
}
```

**Search, filter, sort** (`GET /experiments`) — every query parameter is
optional:

| Parameter         | Meaning                                                                                  |
| ----------------- | ---------------------------------------------------------------------------------------- |
| `q`               | Case-insensitive substring match against `name` OR `notes`                               |
| `status`          | Exact status match                                                                       |
| `model_type`      | Exact model-type match                                                                   |
| `dataset_version` | Exact dataset-version match                                                              |
| `tag`             | Exact tag match (an experiment carrying that tag)                                        |
| `sort`            | One of `name`, `status`, `model_type`, `created_at`, `updated_at` (default `created_at`) |
| `dir`             | `asc` or `desc` (default `desc`)                                                         |
| `limit`/`offset`  | Pagination — same shape as `GET /markets/{symbol}/candles`                               |

The response is `{ experiments: [...summaries], total, limit, offset,
statuses, artifact_types }` — `statuses`/`artifact_types` are the full
valid value lists, published so a filter dropdown never hardcodes them.
Each summary row omits `metrics`/`artifacts` (only their counts) to keep a
list page light; fetch `GET /experiments/{id}` for the full record.

**`PATCH` semantics**: only fields present in the request body are
changed. Sending `tags` **replaces** the entire tag set (not a merge) —
omit it to leave tags untouched.

**Error codes**: `experiment_not_found` / `metric_not_found` /
`artifact_not_found` (404), `invalid_sort` (400 — unsupported `sort` or
`dir`). A malformed request body (e.g. an invalid `status` or
`artifact_type` value) is rejected with FastAPI's standard `422`.

### Machine Learning Training Framework

| Method | Path                                 | Purpose                                                   |
| ------ | ------------------------------------ | --------------------------------------------------------- |
| GET    | `/api/v1/training-jobs/models`       | List every registered model adapter (the extension point) |
| POST   | `/api/v1/training-jobs`              | Register a new training job against an experiment         |
| GET    | `/api/v1/training-jobs`              | Search, filter, sort, and paginate training jobs          |
| GET    | `/api/v1/training-jobs/{id}`         | Get one training job (with its full log trail)            |
| DELETE | `/api/v1/training-jobs/{id}`         | Delete a training job (refuses a running job)             |
| POST   | `/api/v1/training-jobs/{id}/run`     | Execute the six-stage pipeline synchronously              |
| POST   | `/api/v1/training-jobs/{id}/cancel`  | Cancel a pending job                                      |
| POST   | `/api/v1/training-jobs/{id}/predict` | Predict using a completed job's trained model             |

The orchestration layer BC4 adds on top of Experiment Management — see
`ARCHITECTURE.md` § "Machine Learning Training Framework" and § "Baseline
Model Framework" for the full design. Three model adapters are registered:
`placeholder` (fabricates deterministic metrics, trains nothing real),
`logistic_regression` and `linear_regression` (real scikit-learn baseline
models — `POST .../run` performs a real `fit` and evaluation for these
two).

**Model adapter catalogue** (`GET /training-jobs/models`):

```jsonc
{
  "adapters": [
    {
      "name": "placeholder",
      "label": "Placeholder Model",
      "description": "Fabricates deterministic metrics...",
      "framework": "placeholder",
      "model_kind": "placeholder", // "placeholder" | "classification" | "regression"
      "requires_real_data": false, // true means the job needs symbol/timeframe/target_column
      "hyperparameter_hints": ["epochs", "learning_rate"],
      "version": "1.0.0",
    },
    {
      "name": "logistic_regression",
      "label": "Logistic Regression (Baseline)",
      "model_kind": "classification",
      "requires_real_data": true,
      "hyperparameter_hints": ["max_iter", "C", "random_seed"],
      "...": "...",
    },
    {
      "name": "linear_regression",
      "label": "Linear Regression (Baseline)",
      "model_kind": "regression",
      "requires_real_data": true,
      "hyperparameter_hints": ["fit_intercept"],
      "...": "...",
    },
  ],
}
```

**Create** (`POST /training-jobs`):

```jsonc
{
  "experiment_id": "6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90",
  "model_type": "logistic_regression", // must be a name from GET /training-jobs/models
  "dataset_version": null, // optional — defaults from the experiment's own dataset_version
  "symbol": "ETHUSD", // required if the chosen adapter's requires_real_data is true
  "timeframe": "1h", // required alongside symbol
  "target_column": null, // optional — defaults to the first target column the dataset build produces
  "hyperparameters": { "max_iter": 200, "C": 1.0, "random_seed": 42 },
}
```

The job starts in `pending` status. `dataset_version` is not validated
against a real dataset (the ML Dataset Builder never persists one) — it is
a citation, exactly as `Experiment.dataset_version` already is.
`symbol`/`timeframe`/`target_column` are only meaningful for a
`requires_real_data` adapter — the placeholder ignores them entirely.

**Response shape** — the full job record (shown here for a completed
`logistic_regression` run):

```jsonc
{
  "id": "...",
  "experiment_id": "6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90",
  "dataset_version": "9c1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90",
  "symbol": "ETHUSD",
  "timeframe": "1h",
  "target_column": "next_direction_1",
  "model_type": "logistic_regression",
  "hyperparameters": { "max_iter": 200, "C": 1.0, "random_seed": 42 },
  "status": "completed", // pending | running | completed | failed | cancelled
  "current_stage": "update_experiment", // the last pipeline stage entered
  "error_message": null,
  "result_summary": {
    "metrics": { "accuracy": 0.83, "precision": 0.81, "recall": 0.8, "f1": 0.805 },
    "artifact_uri": "file:///.../var/model_artifacts/logistic_regression-....joblib",
    "target_column": "next_direction_1",
    "feature_columns": ["open", "high", "low", "close", "volume"],
    "classes": ["down", "flat", "up"],
    "confusion_matrix": [
      [12, 1, 0],
      [2, 8, 1],
      [0, 2, 14],
    ],
    "n_train": 56,
    "n_validation": 12,
    "n_test": 12,
    "test_metrics": { "accuracy": 0.83, "precision": 0.8, "recall": 0.79, "f1": 0.795 },
    "hyperparameters": { "max_iter": 200, "C": 1.0, "random_seed": 42 },
  },
  "started_at": "2026-01-01T21:00:00Z",
  "completed_at": "2026-01-01T21:00:01Z",
  "logs": [
    {
      "id": "...",
      "level": "info",
      "stage": "validate_dataset",
      "message": "Starting stage: validate_dataset",
      "logged_at": "...",
    },
  ],
  "created_at": "2026-01-01T21:00:00Z",
  "updated_at": "2026-01-01T21:00:01Z",
}
```

`linear_regression`'s `result_summary.metrics` instead carries `mae`/
`mse`/`rmse`/`r2`, and its `summary` carries `coefficients`/`intercept`
rather than `classes`/`confusion_matrix`. `placeholder`'s shape is
unchanged from before (`placeholder_loss`/`placeholder_accuracy`,
`epochs`/`learning_rate`, a fabricated `placeholder://` artifact URI).

**Lifecycle** (`app/training/state_machine.py`): `pending -> running ->
completed | failed`, and `pending | running -> cancelled`. `completed`/
`failed`/`cancelled` are terminal. `POST .../run` executes the pipeline
**synchronously** — no worker/queue service exists on this platform yet
(`AI.md` § "Current status"), so the call blocks for the run's duration
(near-instant for the placeholder; a real but small `fit`/evaluate for a
baseline model).

**The pipeline's six stages**, each logged as it starts and completes:
`validate_dataset` (dataset citation present, model adapter registered) →
`load_dataset` (for the placeholder, resolves the citation into a
`TrainingDataset` handle with no real rows read; for a `requires_real_data`
adapter, actually builds a real `MLDataset` from `symbol`/`timeframe` and
the experiment's `feature_set`/`target_config`/`split_config`, then
resolves `target_column` and numeric feature columns) → `initialize_model`
→ `execute_training` (a real `fit`+evaluate for a baseline model) →
`save_results` (writes `result_summary`) → `update_experiment` — this last
stage reuses `ExperimentService` directly: it sets the linked experiment's
`status` to `completed` (or `failed`, if any earlier stage raised), and
records the run's metrics/artifact through the _same_ `POST /experiments/
{id}/metrics` / `.../artifacts` logic the Experiment Management API itself
uses — no duplicated persistence code.

**Predict** (`POST /training-jobs/{id}/predict`) — only once a job has
`status="completed"`:

```jsonc
// Request
{ "rows": [[3050.0, 3060.0, 3040.0, 3055.0, 120.5]] } // each row matches result_summary.feature_columns

// Response
{ "predictions": ["up"], "feature_columns": ["open", "high", "low", "close", "volume"] }
```

Loads the model `train` serialized (via `app/training/serialization.py`)
and predicts with the adapter's own `predict` — decoupled from the
training run itself, so this works even in a later request or process.

**Search, filter, sort** (`GET /training-jobs`): `experiment_id`, `status`,
`model_type` filter exactly; `sort` is one of `status`, `model_type`,
`created_at`, `updated_at`, `started_at`, `completed_at` (default
`created_at`); `dir` is `asc`/`desc`; `limit`/`offset` paginate, same shape
as every other list endpoint on this platform.

**Error codes**: `training_job_not_found` / `model_adapter_not_found` (404),
`invalid_training_job_transition` / `training_job_not_cancellable` /
`prediction_not_available` (409 — no completed model to predict with yet),
`missing_dataset_version` / `missing_training_data_source` (no symbol/
timeframe) / `missing_feature_or_target_config` / `incompatible_target_dtype`
/ `no_numeric_feature_columns` / `no_target_columns` /
`unknown_target_column` / `empty_training_split` (400 — all raised
mid-pipeline, surfacing as a `failed` job rather than an HTTP error, since
`/run` always returns 200 with the job's final state), `invalid_sort` /
`invalid_prediction_input` (400 — a predict row's length doesn't match
`feature_columns`).

### Model Evaluation & Benchmarking Engine

| Method | Path                              | Purpose                                                   |
| ------ | --------------------------------- | --------------------------------------------------------- |
| GET    | `/api/v1/evaluation/metrics`      | List every registered metric (the extension point)        |
| POST   | `/api/v1/evaluation/benchmark`    | Compare completed training jobs by their recorded metrics |
| GET    | `/api/v1/evaluation/history`      | List past benchmark comparisons (Benchmark History)       |
| GET    | `/api/v1/evaluation/history/{id}` | Reopen one past comparison — its exact request/response   |
| DELETE | `/api/v1/evaluation/history/{id}` | Remove one past comparison from Benchmark History         |

Full design in `ARCHITECTURE.md` § "Model Evaluation & Benchmarking
Engine". This engine computes nothing new at request time — every metric
value it serves or compares was already produced during training
(`app/evaluation/engine.py`'s `default_engine`, called from
`logistic_regression.py`/`linear_regression.py`).

**Metric catalogue** (`GET /evaluation/metrics`):

```jsonc
{
  "metrics": [
    {
      "name": "accuracy",
      "label": "Accuracy",
      "description": "Overall fraction of predictions that match the true label.",
      "category": "classification",
      "higher_is_better": true,
      "requires_probabilities": false,
      "version": "1.0.0",
    },
    {
      "name": "roc_auc",
      "label": "ROC AUC",
      "description": "Area under the ROC curve.",
      "category": "classification",
      "higher_is_better": true,
      "requires_probabilities": true,
      "version": "1.0.0",
    },
    // ... precision, recall, f1 (classification); mae, mse, rmse, r2 (regression)
  ],
}
```

**Benchmark** (`POST /evaluation/benchmark`) — at least one of
`dataset_version`, `target_column`, or `experiment_ids` is required;
`experiment_ids`, when given, narrows an already-matching set further, not
an alternative to the other two:

```jsonc
// Request
{ "dataset_version": "abc123", "target_column": "next_direction" }

// Response
{
  "candidates": [
    {
      "training_job_id": "6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90",
      "experiment_id": "…",
      "experiment_name": "Baseline SMA",
      "model_type": "logistic_regression",
      "model_kind": "classification",
      "dataset_version": "abc123",
      "target_column": "next_direction",
      "completed_at": "2026-01-01T00:00:00Z",
      "metrics": { "accuracy": 0.82, "precision": 0.8, "recall": 0.79, "f1": 0.795, "roc_auc": 0.87 },
      "symbol": "ETHUSD",
      "timeframe": "1h",
      "feature_count": 5,
      "sample_count": 640,
      "model_artifact_url": "/api/v1/training-jobs/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90/artifacts/model_joblib",
      "report": { "confusion_matrix": ["…"], "roc_pr_curves": { "…": "…" }, "…": "…" },
    },
    // ... one entry per completed training job matched
  ],
  "best_by_metric": [
    {
      "metric": "accuracy",
      "training_job_id": "6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90",
      "model_type": "logistic_regression",
      "value": 0.82,
      "higher_is_better": true,
    },
    // ... one entry per metric name appearing on at least one candidate
  ],
}
```

Only `status="completed"` jobs are considered; a completed job that
recorded no metrics (e.g. the `placeholder` adapter) is silently excluded
rather than shown as an empty row. `model_kind` is resolved from the
current model adapter registry — a `model_type` no longer registered
reports `"unknown"` rather than failing the whole comparison.

`symbol`/`timeframe`/`feature_count`/`sample_count`/`model_artifact_url`
are all read from data the training job itself already produced — never
recomputed — and are `null`/absent when that job didn't record them
(`feature_count`/`sample_count` need `result_summary.model_metadata`;
`model_artifact_url` needs `result_summary.artifact_uri`). `report` is the
job's own `result_summary`, verbatim, letting a client render the same
confusion matrix / ROC-PR curves / feature importance / prediction samples
`GET /training-jobs/{id}` itself would show, without a second request.

**Error codes**: `no_benchmark_target` (400 — none of `dataset_version` /
`target_column` / `experiment_ids` were given, so there is nothing to
match), `empty_benchmark` (404 — the request was well-formed but matched
zero completed training jobs), `metric_not_found` (404 — reserved for a
future direct metric lookup; not raised by either endpoint above today).

**Benchmark History** — every successful `POST /evaluation/benchmark` call
is recorded (best-effort; a persistence failure never fails the comparison
itself), so a past comparison can be reopened later exactly as it was:

```jsonc
// GET /evaluation/history?dataset_version=abc123
{
  "runs": [
    {
      "id": "9c2b1a3e-...",
      "dataset_version": "abc123",
      "target_column": "next_direction",
      "candidate_count": 2,
      "created_at": "2026-01-01T00:00:00Z",
    },
  ],
  "total": 1,
  "limit": 20,
  "offset": 0,
}

// GET /evaluation/history/{id}
{
  "id": "9c2b1a3e-...",
  "created_at": "2026-01-01T00:00:00Z",
  "request": { "dataset_version": "abc123", "target_column": "next_direction", "experiment_ids": [] },
  "response": { "candidates": ["…"], "best_by_metric": ["…"] }, // the exact BenchmarkResponse shape above
}
```

`GET /evaluation/history` accepts `dataset_version`/`target_column` filters
and `sort`/`dir`/`limit`/`offset` (one of `dataset_version`,
`target_column`, `candidate_count`, `created_at`; default `created_at`
descending) — the same list-endpoint shape every other history surface on
this platform uses. `DELETE /evaluation/history/{id}` removes only the
persisted record; the underlying `TrainingJob` rows are untouched.
**Error codes**: `benchmark_run_not_found` (404 — unknown run id, on both
`GET` and `DELETE`), `invalid_benchmark_run_sort` (400 — an unsupported
`sort`/`dir` combination on the list endpoint).

### Platform health

| Method | Path                     | Purpose                                            |
| ------ | ------------------------ | -------------------------------------------------- |
| GET    | `/api/v1/system/health`  | Per-component status (always 200, states in body)  |
| GET    | `/api/v1/system/status`  | Uptime, version, WS + ingestion freshness          |
| GET    | `/api/v1/system/metrics` | Stored counts, message processing, bus/state stats |

Components reported by `/system/health`: `api`, `database`, `delta_rest`,
`delta_ws`, `event_bus`, `state_manager`. WebSocket status reflects the
**live connection state** (stopped/connecting/connected/disconnected with
subscriptions, message counts, reconnects, heartbeats, and uptime in
`/system/status`), never the configured mode. DB-derived metric fields are
`null` when no database is configured.

### WebSocket (live market stream)

| Method | Path                | Purpose                                                           |
| ------ | ------------------- | ----------------------------------------------------------------- |
| WS     | `/api/v1/ws/market` | Live trade, ticker, and order-book updates for subscribed symbols |

The platform's one server-to-browser push channel — the frontend never
connects to Delta Exchange directly. A client sends
`{"action": "subscribe", "symbols": [...]}` to receive anything (no symbol
is implicit); the server replies with an immediate `snapshot` and then
`trade`/`ticker`/`orderbook` messages as they occur, plus `pong` for a
client `ping`. Order-book messages carry an already-sorted (bids
descending, asks ascending), depth-limited (100 levels/side) _reconstructed_
book — snapshot merged with incremental diffs, not a single raw exchange
message — built by `app/marketdata/orderbook.py`'s `OrderBookAggregator`.
Full wire format is documented at the top of
`app/api/v1/endpoints/market_stream.py`; see `FRONTEND.md` § "Live Market
Dashboard" and § "Live Order Book Viewer" for how the two implemented pages
consume it.

## Authentication

None — the current surface is read-only and public. Private endpoints will
use HMAC/JWT credentials when trading/AI surfaces are added.

## Error Handling

- Domain errors return `4xx` with `{"code": "...", "detail": "..."}`.
- Liveness endpoints return `503` when the database is unreachable.
- System endpoints always return `200`; component states are carried in the
  body so dashboards can render granular states.

## Rate Limiting

Not implemented. Delta REST calls are bounded by the client's retry/backoff
policy (see `app/integrations/delta/client.py`).

## SDKs

None. The dashboard consumes these endpoints directly via axios (see
`apps/dashboard/src/lib/api/`).
