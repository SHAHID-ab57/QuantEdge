# API

## Purpose

HTTP API of the AI-powered Ethereum Market Analysis Platform, served by the
FastAPI service in `services/api` (OpenAPI docs at `/docs`).

## Status

Draft — v1 surface is read-only and unauthenticated (monitoring + market data).

## Overview

The API exposes historical market data and operational monitoring:

- Liveness and metadata: `GET /health`, `GET /api/v1/health`
- Market data (read-only): `GET /api/v1/markets`, `/api/v1/markets/{symbol}/candles`, ...
- Feature engineering: `GET /api/v1/features`, `POST /api/v1/markets/{symbol}/features/dataset|export`
- Dataset validation: `POST /api/v1/markets/{symbol}/features/validate`, `GET /api/v1/validation/rules`
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

| Method | Path                                        | Purpose                                                       |
| ------ | ------------------------------------------- | ------------------------------------------------------------- |
| GET    | `/api/v1/features`                          | Catalogue of every registered generator, with parameter specs |
| GET    | `/api/v1/features/{feature}`                | One generator's metadata, parameters, and output columns      |
| POST   | `/api/v1/markets/{symbol}/features/dataset` | Build a feature dataset (optionally truncated for preview)    |
| POST   | `/api/v1/markets/{symbol}/features/export`  | Build the same dataset and stream it as a CSV or JSON file    |

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
