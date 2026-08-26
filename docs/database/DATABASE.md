# Database

## Purpose

The relational schema backing this platform: what tables exist today, how
they relate, and how they're migrated. This document was an empty stub
until the Experiment Management System (below) became the first feature
whose data model deserved a home here rather than only living in
docstrings — `docs/domain/MarketDataDomain.md` remains the detailed,
business-rule-level source for the market data schema (`exchanges`,
`markets`, `candles`); this document is the cross-cutting, schema-wide view.

## Status

Draft — covers every table that exists in the database today. Everything
described here has a real, applied Alembic migration; nothing below is
aspirational.

## Overview

PostgreSQL 17 in development (`infra/docker/docker-compose.yml`), accessed
through SQLAlchemy 2.x async + asyncpg. Three schema families exist:

| Family                | Tables                                                                         | Owner                                        |
| --------------------- | ------------------------------------------------------------------------------ | -------------------------------------------- |
| Market data           | `exchanges`, `markets`, `candles`                                              | Market Data bounded context                  |
| Experiment Management | `experiments`, `experiment_tags`, `experiment_metrics`, `experiment_artifacts` | AI Research & Training bounded context (BC4) |
| ML Training Framework | `training_jobs`, `training_job_logs`                                           | AI Research & Training bounded context (BC4) |

Every table uses a surrogate `UUID` primary key (`app/models/base.py`'s
`BaseModel`) and `created_at`/`updated_at` timezone-aware UTC timestamps
(`TimestampMixin`), so every row is independently identifiable and
auditable regardless of which family it belongs to.

## Schema Diagrams

```text
exchanges 1──* markets 1──* candles


experiments 1──* experiment_tags
experiments 1──* experiment_metrics
experiments 1──* experiment_artifacts
experiments 1──* training_jobs
training_jobs 1──* training_job_logs
```

Market data is described in full (entities, constraints, business rules)
in `docs/domain/MarketDataDomain.md`. The Experiment Management schema is
described in full below.

### Experiment Management schema

Backing the Experiment Management System (`ARCHITECTURE.md` § "Experiment
Management System"; `AI.md` § "Experiment Management"). An experiment
references a versioned ML dataset build (`ml_dataset_id`) **by value, not
by foreign key** — the ML Dataset Builder never persists a dataset to a
table (see `ARCHITECTURE.md` § "ML Dataset Builder": a dataset is a
computed-on-demand, exported artifact), so `experiments.dataset_version`
is a plain string, the same way a lab notebook would cite it.

**`experiments`**

| Column                    | Type           | Notes                                                                       |
| ------------------------- | -------------- | --------------------------------------------------------------------------- |
| `id`                      | `uuid` PK      |                                                                             |
| `name`                    | `varchar(200)` | Not null, indexed                                                           |
| `dataset_version`         | `varchar(200)` | Nullable — the `ml_dataset_id` this experiment was built over               |
| `feature_set`             | `json`         | Nullable — resolved feature requests, e.g. `[{"feature": "sma", ...}]`      |
| `target_config`           | `json`         | Nullable — resolved target requests, e.g. `[{"target": "next_close", ...}]` |
| `split_config`            | `json`         | Nullable — `{"train": 0.7, "validation": 0.15, "test": 0.15}`               |
| `model_type`              | `varchar(100)` | Nullable — a placeholder label only; no training engine exists yet          |
| `status`                  | `varchar(24)`  | Not null, default `'draft'`; `CHECK` constrained to five values (below)     |
| `notes`                   | `text`         | Nullable — free-form researcher commentary                                  |
| `created_at`/`updated_at` | `timestamptz`  |                                                                             |

`status` is `CHECK`-constrained to `'draft' | 'running' | 'completed' |
'failed' | 'archived'` at the database level (`ck_experiments_status_valid`)
— the same value set the API's Pydantic schema and the frontend's status
chip both derive from, so an invalid status can never reach storage
regardless of which layer it slips past.

**`experiment_tags`** — one row per tag, not a JSON array column: this
schema has no JSON-array-column precedent anywhere (`exchanges`/`markets`/
`candles` are all fully normalized), and a tag benefits from being a real,
indexable, joinable column — it's exactly what makes `GET /experiments?tag=...`
a real `WHERE experiment_id IN (SELECT ...)` query rather than an
in-application scan.

| Column          | Type          | Notes                                                      |
| --------------- | ------------- | ---------------------------------------------------------- |
| `id`            | `uuid` PK     |                                                            |
| `experiment_id` | `uuid` FK     | → `experiments.id`, `ON DELETE CASCADE`                    |
| `tag`           | `varchar(64)` | Not null; `UNIQUE(experiment_id, tag)` — no duplicate tags |

**`experiment_metrics`** — one row per recorded evaluation metric (the
Metrics entity):

| Column          | Type           | Notes                                         |
| --------------- | -------------- | --------------------------------------------- |
| `id`            | `uuid` PK      |                                               |
| `experiment_id` | `uuid` FK      | → `experiments.id`, `ON DELETE CASCADE`       |
| `name`          | `varchar(100)` | Not null, e.g. `"accuracy"`, `"sharpe_ratio"` |
| `value`         | `float8`       | Not null                                      |
| `unit`          | `varchar(32)`  | Nullable, e.g. `"ratio"`                      |
| `recorded_at`   | `timestamptz`  | Defaults to insert time                       |

Indexed on `(experiment_id, name)` for "every recorded value of this named
metric across an experiment" queries.

**`experiment_artifacts`** — one row per artifact _reference_ (the
Artifact Reference entity — a pointer, never the artifact's actual bytes,
since this platform has no object storage wired in yet; see
`ARCHITECTURE.md` § "Known Limitations"):

| Column                    | Type            | Notes                                                                                  |
| ------------------------- | --------------- | -------------------------------------------------------------------------------------- |
| `id`                      | `uuid` PK       |                                                                                        |
| `experiment_id`           | `uuid` FK       | → `experiments.id`, `ON DELETE CASCADE`                                                |
| `artifact_type`           | `varchar(32)`   | `CHECK` constrained to `dataset_export \| model_checkpoint \| report \| plot \| other` |
| `uri`                     | `varchar(1024)` | Not null — a file path, export filename, or URL                                        |
| `description`             | `text`          | Nullable                                                                               |
| `created_at`/`updated_at` | `timestamptz`   |                                                                                        |

### Machine Learning Training Framework schema

Backing the Training Framework (`ARCHITECTURE.md` § "Machine Learning
Training Framework"; `AI.md` § "Machine Learning Training Framework"). A
`training_jobs` row always belongs to exactly one `experiments` row — unlike
an experiment's own `dataset_version` (a citation, since the ML Dataset
Builder persists nothing), the linked experiment is a real row that already
exists by the time a job is created, so this is a genuine foreign key.

**`training_jobs`**

| Column                      | Type           | Notes                                                                     |
| --------------------------- | -------------- | ------------------------------------------------------------------------- |
| `id`                        | `uuid` PK      |                                                                           |
| `experiment_id`             | `uuid` FK      | → `experiments.id`, `ON DELETE CASCADE`, not null, indexed                |
| `dataset_version`           | `varchar(200)` | Nullable — defaults from the linked experiment's own `dataset_version`    |
| `model_type`                | `varchar(100)` | Not null — a registered model adapter name (`app/training/registry.py`)   |
| `hyperparameters`           | `json`         | Nullable — arbitrary hyperparameters passed verbatim to the adapter       |
| `status`                    | `varchar(24)`  | Not null, default `'pending'`; `CHECK` constrained to five values (below) |
| `current_stage`             | `varchar(32)`  | Nullable — the pipeline stage last entered; frozen on failure             |
| `error_message`             | `text`         | Nullable                                                                  |
| `result_summary`            | `json`         | Nullable — the adapter's fabricated metrics/summary                       |
| `started_at`/`completed_at` | `timestamptz`  | Nullable                                                                  |
| `created_at`/`updated_at`   | `timestamptz`  |                                                                           |

`status` is `CHECK`-constrained to `'pending' | 'running' | 'completed' |
'failed' | 'cancelled'` at the database level (`ck_training_jobs_status_valid`)
— the same value set `app/training/state_machine.py`'s transition rules and
the frontend's status chip both derive from.

**`training_job_logs`** — one row per log line (the pipeline logs every
stage's start and completion), the same "growing collection gets its own
table, not a JSON array" choice `experiment_metrics` already made:

| Column      | Type          | Notes                                                                        |
| ----------- | ------------- | ---------------------------------------------------------------------------- |
| `id`        | `uuid` PK     |                                                                              |
| `job_id`    | `uuid` FK     | → `training_jobs.id`, `ON DELETE CASCADE`, not null, indexed                 |
| `level`     | `varchar(16)` | `CHECK` constrained to `debug \| info \| warning \| error`, default `'info'` |
| `stage`     | `varchar(32)` | Nullable — which of the six pipeline stages logged this line                 |
| `message`   | `text`        | Not null                                                                     |
| `logged_at` | `timestamptz` | Defaults to insert time                                                      |

Indexed on `(job_id, logged_at)` for "every log line for this job, in
order" queries.

## Migrations

Alembic (`services/api/alembic/versions/`), applied in order against the
local Postgres instance:

1. `592cf2283d14` — create market data schema (`exchanges`, `markets`, `candles`)
2. `1402faec05f9` — make `candles.quote_volume` nullable
3. `0d1c3a9b5e2f` — add Delta-specific market metadata columns
4. `fa0a2a1c8181` — create Experiment Management schema (`experiments`,
   `experiment_tags`, `experiment_metrics`, `experiment_artifacts`)
5. `8cc1992f6c6f` — create Machine Learning Training Framework schema
   (`training_jobs`, `training_job_logs`)

Run via `services/api/Makefile` targets: `make db-upgrade`, `db-downgrade
REV=-1`, `db-current`, `db-history`, `make db-create-migration
MESSAGE="..."`. New migrations are generated with `alembic revision
--autogenerate` against a live database and always hand-checked (`alembic
check` reports "No new upgrade operations detected" once the models and
the migration agree) before being committed.

## Backup & Recovery

Not yet designed — no backup/restore tooling exists for the development
Postgres instance beyond the Docker volume itself
(`infra/docker/docker-compose.yml`).

## Performance

No experiment-management-specific performance work has been done — the
registry is expected to be low-volume (hundreds to low thousands of rows,
not the high-frequency insert pattern `candles` has). `experiments.name`
and every foreign key column are indexed; no further tuning has been
needed or attempted.
