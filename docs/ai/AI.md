# AI

## Purpose

How this platform gets from raw market data to trained models and
probabilistic predictions — what exists today, what does not, and the
contracts the missing pieces will plug into.

Written honestly about status: the platform is **AI-ready at the data
layer, and nothing more**. Feature engineering, dataset validation, and the
ML Dataset Builder (target generation, chronological splitting, versioned
export) are implemented; model training, inference, and evaluation are not.
Every section below says which it is, because a document that describes an
aspirational pipeline in the present tense is worse than no document at
all.

## Status

Draft — Feature Engineering, the Dataset Validation Gate, the ML Dataset
Builder, and Experiment Management (the registry, not model training)
implemented; Models, Training (beyond dataset preparation), Inference, and
Evaluation are design intent only.

## Overview

Machine learning models do not consume raw candles. They consume engineered
feature vectors: fixed-width, aligned, numeric rows with no missing values.
The stage that produces them is the **Feature Engineering Engine**
(`services/api/app/features/`), the platform's BC3 bounded context
(`docs/architecture/DomainModel.md`).

```text
Market Data (D1–D5) → Engineered Features (D6) → ML Datasets (D7) → Validated (gate) → ML Dataset (versioned, split) → Models (D8–D9)
   implemented            implemented                implemented       implemented         implemented                   not built
```

The first five stages exist today. A researcher can select a market,
timeframe, date range, and set of features, build a versioned dataset,
export it as CSV or JSON, and run it through the **Dataset Validation &
Quality Engine** — the platform's mandatory quality gate. On top of that,
the **ML Dataset Builder** (`services/api/app/ml_datasets/`) appends
prediction-target label columns, re-runs the same validation gate over the
combined matrix, and produces a chronologically split, versioned,
exportable training artifact — the only supported path for producing a
dataset actually used in AI training (see § "ML Dataset Builder" below).
What consumes that artifact — a model, a training loop — does not exist
yet.

## Data Pipeline

Full architecture in [`ARCHITECTURE.md`](../../ARCHITECTURE.md) § "Feature
Engineering Engine"; API surface in [`API.md`](../api/API.md) § "Feature
engineering". In short:

| Stage              | Component                      | Responsibility                                                           |
| ------------------ | ------------------------------ | ------------------------------------------------------------------------ |
| Candle load        | `services/candle_points.py`    | Market/timeframe/range validation, one ordered query, ORM → `OHLCVPoint` |
| Feature resolution | `features/registry.py`         | Name → generator; the single extension point                             |
| Feature generation | `features/pipeline.py`         | Validate params → check warmup → generate → verify alignment             |
| Dataset assembly   | `features/dataset.py`          | Column collision detection, warmup trimming, provenance                  |
| Serialization      | `features/export.py`           | CSV and JSON, both carrying provenance                                   |
| Validation gate    | `dataset_validation/engine.py` | Structural, data-quality, time-series, and feature checks, on demand     |

Eight generators ship today: `ohlcv` (5 columns), `candle_shape` (body,
upper wick, lower wick, direction), and `sma`/`ema`/`wma`.

### Training/serving consistency

The single most damaging failure mode in an ML system is _training/serving
skew_: the feature a model was trained on and the feature computed at
inference time are subtly different. BC3 exists to prevent it, and the
engine's design is shaped around that guarantee:

- **One implementation per calculation.** SMA, EMA, and WMA are not
  reimplemented as feature generators. `IndicatorFeature`
  (`features/builtin/indicator_feature.py`) wraps the _already-registered
  indicator_ and delegates to the same `IndicatorEngine` the charts use, so
  "SMA(20)" has exactly one definition on this platform. A dataset column
  and a chart overlay cannot disagree, because they are the same code.
- **One execution path.** The contract has no batch-versus-online split —
  there is one `generate` method, given plain `OHLCVPoint` values. The same
  generator can therefore serve a REST request today and a training job or
  live inference path later without modification.
- **Framework-free inputs.** Nothing in `app/features/` imports SQLAlchemy,
  FastAPI, or Pydantic, so a future training job supplying candles from a
  Parquet file or a replay session runs identical code.

### Reproducibility

An unreproducible dataset is not research (`PROJECT.md` § principles).
Every dataset records, and every export carries:

- `dataset_id` — a fresh `uuid4()` per build, identifying _this specific
  build_, not a content hash. Rebuilding an identical request later — over
  data that may itself have changed — is expected to yield a different
  `dataset_id`; reproducibility is established by the fields below, not by
  `dataset_id` matching.
- `pipeline_version` — the execution pipeline's own version.
- Each feature's `version` — bumped when a change would alter previously
  computed values, so a dataset built under 1.0.0 is known not to be
  reproducible under 2.0.0.
- Each feature's **fully resolved** parameters, defaults applied — the
  values that actually ran, not the ones that were requested.
- `candles_analyzed`, `rows_dropped`, and `warmup_candles`.

### Missing values

A training matrix must not contain nulls, and imputing them is a modelling
decision the data layer has no business making silently. The dataset
builder therefore **drops any row containing a null** by default and reports
how many it dropped. Set `drop_warmup: false` to keep full alignment for
inspection or for a consumer that imputes its own.

A feature that cannot be computed at all for the requested range —
including a range shorter than its warmup — no longer aborts the whole
dataset. It is instead recorded as one entry in `quality.feature_failures`
(feature name, resolved params, error code, actionable detail), and every
other requested feature's columns are still returned. See
`ARCHITECTURE.md` § "Feature Engineering Engine — Production Hardening" for
why (mirrors the indicator engine's batch partial-success contract) and
`API.md` § "Feature engineering" for the exact response shape.

### Data quality report

Every dataset carries a `quality` object (`app/features/quality.py`'s
`DatasetQualityReport`) summarizing its own trustworthiness: rows
read/returned/removed, per-column null counts (computed **before** warmup
trimming, so a mid-series null is never hidden by the trim), duplicate
timestamps and missing candles in the source data, per-feature generation
failures, and total generation time. A model-training pipeline consuming
this API should treat a non-empty `feature_failures` or a non-zero
`duplicate_timestamps`/`missing_candles` as a signal to inspect the dataset
before training on it, not just its row count.

## Dataset Validation Gate

**Implemented, and the platform's other explicit mandatory gate** (see
`ARCHITECTURE.md` § "Dataset Validation & Quality Engine" for the full rule
architecture). Per the project's own stated Data Engineering objective
("Dataset quality must be measured and reported before any dataset is
approved for model training or backtesting use" — `PROJECT.md` § Medium-
Term Goals), a dataset's own `quality` report (above) is necessarily
partial: it can only describe what the _build_ itself observed. The
validation gate is a second, independent pass over the _delivered_ dataset
— run on demand via `POST /markets/{symbol}/features/validate` — checking
four categories a training pipeline should require pass (or at least
inspect) before consuming a dataset:

| Category     | What it catches                                                                              |
| ------------ | -------------------------------------------------------------------------------------------- |
| Structural   | A declared column that doesn't actually exist; a value that doesn't match its column's dtype |
| Data quality | Missing values, whole-row duplicates, duplicate timestamps, NaN, and infinite values         |
| Time-series  | Out-of-order timestamps; gaps in the delivered series at the timeframe's cadence             |
| Feature      | Row/column count inconsistencies; any feature that failed during generation                  |

The verdict (`passed`) is boolean and mechanical — `False` only when at
least one `error`-severity finding exists — so a training pipeline can gate
on it programmatically (`if not report["passed"]: raise`) rather than
having a human read a report every time. `warning`/`info` findings are
always included but never block, matching the platform's existing
"correctness blocks, judgment calls surface" posture (the same three-tier
severity a linter uses).

**Extensibility**: a new check is one file in
`app/dataset_validation/rules/` — a class, its metadata, and `@register` —
with no change to the engine, the API, or the frontend, the identical
guarantee `FeatureGenerator` and `Indicator` already give their own
registries. This matters specifically for AI readiness: as concrete
training/backtesting workflows are built, they will very likely need
additional checks this initial set does not anticipate (e.g. label
leakage, class imbalance, feature-target correlation) — the rule
architecture exists so those arrive as new files, not as changes to
already-shipped rules.

## ML Dataset Builder

**Implemented** (`services/api/app/ml_datasets/`; full architecture in
`ARCHITECTURE.md` § "ML Dataset Builder"). Composes the Feature Engineering
Engine, a new target-generation pipeline, and the Dataset Validation Gate
into the platform's one supported path from stored candles to a
model-trainable artifact:

```text
Features (X)  +  Targets/labels (y)  →  combined matrix  →  Validation Gate  →  Chronological split  →  Versioned export
```

**Target generation** is a fourth Strategy + Registry, deliberately kept in
its own namespace rather than folded into the feature registry — a target
generator can never be requested as a feature, which structurally rules
out training a model on its own label. Three initial targets ship, each a
`horizon`-parameterized generator: `next_close` (raw future close price),
`next_return` (fractional change to it), and `next_direction`
(`"up"`/`"down"`/`"flat"` classification).

**No look-ahead bias, enforced three ways, not merely by convention:**

1. A target is always computed by reading `candles[i + horizon]` for row
   `i` — a strictly later candle — never row `i` itself or anything
   earlier.
2. `TargetPipeline` mechanically verifies that a generator's trailing
   `horizon` positions are `None` before accepting its output, rejecting
   any generator (buggy or malicious) that fabricates an unknowable future
   value.
3. Splitting is strictly chronological and contiguous — train, then
   validation, then test, in time order, **never shuffled** — so no split
   boundary can place a future row in the training set ahead of a past row
   in validation or test.

**Versioning** layers on top of the Feature Engineering Engine's own
provenance (§ "Reproducibility" above): a fresh `ml_dataset_id` per build,
independent from the embedded `dataset_id`; `ML_BUILDER_VERSION` and
`TARGET_PIPELINE_VERSION`, each bumped independently of `PIPELINE_VERSION`
and the validation engine's own version; each target's own resolved
version and parameters; the exact `split_ratios` used; and the embedded
`ValidationReport` verdict for the combined feature+target matrix.

**Export** produces one flat CSV or JSON file — not three — containing the
full matrix plus a per-row `split` label (`"train"`/`"validation"`/
`"test"`), so the one downloaded artifact is complete and reproducible on
its own. The `/ml-datasets` workbench shows exactly this shape (rows,
columns, target, split ratios, format, an approximate size) in a
confirmation dialog before the download starts.

**Configuration is portable, not just the dataset.** Beyond the dataset
artifact's own versioning, `/ml-datasets` lets a researcher copy the
_request_ that produced it — market, timeframe, range, feature selections,
target selections, and split ratios — as one JSON object, and paste it
back in later (their own session, a teammate's, or a future one) to
restore the exact configuration before rebuilding. This is a frontend-only
convenience with no server-side counterpart: importing a configuration
only populates the build form, and the researcher still triggers the
build themselves, so it can never become an unaudited second way to
produce a dataset.

A training pipeline consuming this API should treat the embedded
`validation.passed` the same way it should treat a plain feature dataset's
quality report: a mechanical gate to check before training, not something
to eyeball. See `API.md` § "ML dataset builder" for the full request/
response shape and `TESTING.md` § "Testing the ML Dataset Builder" for how
the leakage-prevention guarantees above are independently tested.

## Experiment Management

**Implemented** (`services/api/app/models/experiment.py` +
`app/repositories/experiments.py` + `app/services/experiments.py`; full
design in `ARCHITECTURE.md` § "Experiment Management System"). Per
`PROJECT.md`'s own stated objective ("Establish experiment tracking and
model versioning... Complete experiment provenance ensures that any
prediction can be traced back to the exact model, data, and parameters
that produced it"), this is the platform's central registry for recording
an experiment's configuration and outcome:

```text
Experiment record: name, dataset_version, feature_set, target_config, split_config, model_type, status, notes, tags
                    → Metrics (evaluation results)
                    → Artifact references (files/reports/exports produced)
```

**This records the intent and result of a training run — it does not run
one.** No model training exists on this platform (see § "Models" below),
so `model_type` is explicitly documented, in both the schema and the API,
as a placeholder label a researcher fills in by hand — not a value this
system validates against a real model registry, because no such registry
exists yet.

**Reproducibility, the same principle the ML Dataset Builder already
established, applied one layer up.** An experiment references its
dataset by copying the ML Dataset Builder's own `ml_dataset_id` (and the
resolved feature/target/split configuration that produced it) as plain
data — not a foreign key, since the dataset itself is never persisted to
a table (§ "ML Dataset Builder" above). This is the same "cite it like a
lab notebook would" relationship applied consistently: neither the
dataset nor the experiment record depends on the other still existing to
remain meaningful on its own.

**Full CRUD, not an append-only ledger** — deliberately. `docs/
architecture/DataArchitecture.md` § D9 describes experiment records as
"persistent and append-only," which this system honors in the sense that
matters for reproducibility (a re-run of an experiment gets a _new_
record, never silently overwriting a prior one's history) without
extending that to "a researcher can never fix a typo or delete a
duplicate entry" — the same distinction the dataset builder already draws
between an immutable _build_ and a mutable _view_ over it.

**Search, filter, sort** (`GET /experiments`) reuse the exact whitelisted-
sort-column and limit/offset-with-total pagination shape `GET /markets/
{symbol}/candles` already established, rather than inventing a second
pagination convention for the one other list-shaped endpoint this
platform has. Tags are their own normalized table
(`experiment_tags`), not a JSON array — the first genuinely new
structural choice in this schema, made because a tag is exactly the kind
of value that benefits from being indexed and joined on, and because
every other table in this schema is already fully normalized.

See `API.md` § "Experiment management" for the full request/response
shapes and error codes, `docs/database/DATABASE.md` § "Experiment
Management schema" for the table definitions, and `TESTING.md` § "Testing
the Experiment Management System" for how CRUD, search/filter/sort, and
validation are tested.

## Models

**Not built.** No model artifacts, no model registry, no training code
exists in this repository. `docs/architecture/DomainModel.md` § BC4 defines
the intended bounded context (AI Research & Training) and
`DataArchitecture.md` § D8–D9 the intended artifacts.

When it is built, its input is the dataset described above — which is why
the dataset carries versioned provenance: a model artifact must be able to
name the exact dataset definition it was trained on.

## Training Pipeline

**Dataset preparation is implemented; the model-facing half is not.** The
intended full shape (`PROJECT.md` § objectives) is: dataset snapshot →
experiment run → evaluation → model registry → promotion to serving. The
first arrow — turning stored candles into a reproducible, versioned,
labeled, chronologically split, exportable dataset — is now built end to
end by the ML Dataset Builder (§ above). Everything from "experiment run"
onward does not exist.

Generators remain callable directly from Python (`FeaturePipeline.run`,
`TargetPipeline.run`) without going through HTTP — the seam a training job
would use. `app/features/ai_extensions.py`'s `SplitRatios`/`DatasetSplit`/
`TrainValidationTestSplitter` Protocol now has a real implementer
(`app/ml_datasets/split.py`'s `ChronologicalSplitter`); `LabelSpec`/
`LabelGenerator` is likewise now realized in substance by the ML Dataset
Builder's target-generation pipeline, though not through that exact
Protocol type (target generators use `TargetGenerator`, described above, for
the leakage-prevention reasons documented there). `WindowSpec`/
`SequenceWindower` remains the next, still-unimplemented arrow: turning a
labeled feature matrix into fixed-size, strided sequence windows for a
sequence model.

## Inference

**Not built.** No prediction service exists (`DomainModel.md` § BC5).

The relevant design commitment already made: because feature generators are
framework-free and have a single execution path, an inference path will
compute features with the _same_ code that produced the training data,
rather than a reimplementation. That is the property that has to be
designed in from the start, and it has been.

## Evaluation

**Not built.** No backtesting engine, no evaluation harness, no metrics
store.

The platform's stated commitment (`PROJECT.md`) is that predictions are
probabilistic and that uncertainty is communicated honestly — no evaluation
code exists yet to hold to that, and none of the current UI displays any
prediction or confidence figure, precisely because there is nothing real to
display.

## AI extension points

**Documented, typed, and testable — one now has a real implementer.**
`services/api/app/features/ai_extensions.py` declares six `Protocol`/
`dataclass` pairs so that when the workstreams above are actually built,
they have a contract to implement rather than a blank page:

| Extension point                                                | Purpose                                                                                                                                                     | Status                                                                                                                                                                    |
| -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `LabelSpec` / `LabelGenerator`                                 | Deriving a training target/label from a dataset (e.g. next-candle direction)                                                                                | Realized in substance by `app/ml_datasets/` (a distinct `TargetGenerator` contract — see § "ML Dataset Builder")                                                          |
| `WindowSpec` / `SequenceWindower`                              | Slicing a feature matrix into fixed-size, strided sequence windows                                                                                          | Not implemented                                                                                                                                                           |
| `NormalizationStats` / `FeatureNormalizer`                     | Per-column scaling, with `fit`/`transform` kept as two separate methods so a normalizer fit on training data can never leak test-set statistics into itself | Not implemented                                                                                                                                                           |
| `SplitRatios` / `DatasetSplit` / `TrainValidationTestSplitter` | Chronological (never random) train/validation/test splitting — a random split of time-series data leaks future information into training                    | **Implemented** — `app/ml_datasets/split.py`'s `ChronologicalSplitter` is the first real implementer; `SplitRatios`/`DatasetSplit` are imported unchanged, not redeclared |
| `CategoricalEncoding` / `CategoricalEncoder`                   | One-hot or ordinal encoding, driven by a column's declared `dtype`, never a hardcoded column list                                                           | Not implemented                                                                                                                                                           |

These mirror the frontend's own established pattern for the same purpose:
`apps/dashboard/src/features/replay/extension-points.ts` documents replay's
own not-yet-built extension points the identical way. Implementing any one
of these workstreams means writing a concrete class that satisfies the
relevant Protocol — the pipeline, dataset builder, and export layer need no
changes to support it, since all of them already produce the versioned,
quality-reported dataset these Protocols consume as their input.

## What a new feature generator requires

Adding a generator is one file and one line:

1. Create `services/api/app/features/builtin/<name>.py`.
2. Subclass `FeatureGenerator`, declare `metadata: FeatureMetadata`, and
   implement `generate(ctx) -> FeatureOutput`.
3. Decorate the class with `@register`.

Nothing else changes — not the pipeline, the registry, the dataset builder,
the service, the API, or the frontend. The `/features` page renders the new
generator's selection row, its parameter form, and its column headers
directly from the catalogue response. An indicator-backed feature is even
cheaper: add its name to `INDICATOR_BACKED_FEATURES`.

## What a new prediction target requires

Adding a target generator is one file:

1. Create `services/api/app/ml_datasets/targets/<name>.py`.
2. Subclass `TargetGenerator`, declare `metadata: TargetMetadata` (name,
   label, description, category, `default_horizon`), and implement
   `generate(ctx) -> TargetOutput`.
3. Decorate the class with `@register`.

Nothing else changes — not the pipeline, the registry, the dataset
builder, the service, the API, or the frontend. `/ml-datasets`'s target
selector and `GET /ml/targets` both render the new generator immediately,
with no frontend change. A generator's output is mechanically checked for
look-ahead bias by `TargetPipeline` before it is ever accepted (§ "ML
Dataset Builder" above) — a new target cannot silently introduce leakage
without the pipeline itself rejecting it.

## What a new validation rule requires

Adding a rule is one file:

1. Create a module in `services/api/app/dataset_validation/rules/` (or add
   to an existing category module if the check fits one already there).
2. Subclass `ValidationRule`, declare `metadata: ValidationRuleMetadata`
   (name, category, description, default severity), and implement
   `check(ctx) -> list[ValidationIssue]`.
3. Decorate the class with `@register`.

Nothing else changes — not the engine, the registry, the service, the API,
or the frontend. `/validation`'s "Available Checks" panel and `GET
/validation/rules` both render the new rule immediately, with no frontend
change.

## References

- [`ARCHITECTURE.md`](../../ARCHITECTURE.md) § "Feature Engineering Engine",
  § "Dataset Validation & Quality Engine", § "ML Dataset Builder", and
  § "Experiment Management System"
- [`API.md`](../api/API.md) § "Feature engineering", § "Dataset validation",
  § "ML dataset builder", and § "Experiment management"
- [`FRONTEND.md`](../../FRONTEND.md) § "Feature Engineering", § "Dataset
  Validation", § "ML Dataset Builder", and § "Experiment Management"
- [`TESTING.md`](../../services/api/TESTING.md) § "Testing the ML Dataset
  Builder" and § "Testing the Experiment Management System"
- [`docs/database/DATABASE.md`](../database/DATABASE.md) § "Experiment
  Management schema"
- [`docs/architecture/DomainModel.md`](../architecture/DomainModel.md) § BC3, BC4
- [`docs/architecture/DataArchitecture.md`](../architecture/DataArchitecture.md) § D6, D7, D9
