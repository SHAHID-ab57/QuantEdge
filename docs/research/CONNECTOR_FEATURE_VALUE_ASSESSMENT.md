# Connector Feature Value Assessment (M4-E3-T1)

## Purpose

Milestone 4's six external data connectors (Fear & Greed, FRED, Etherscan,
DefiLlama, CoinGecko, Marketaux) were confirmed, in a prior verification
pass, to be **REGISTERED-ONLY**: real, tested, live-verified integrations
that compute and store real data, but never used in any real experiment
or training job — the model currently driving the one live, automated
paper-trading strategy is trained purely on OHLCV + SMA(20), the same
feature set that predates Milestone 4 entirely.

This task set out to answer the actual question that leaves open: **if
these six features were used, would they help?** Build one experiment
per feature, plus one with all six together, train a model on each using
the exact same target/split/symbol/timeframe/model/hyperparameters as the
existing baseline, and benchmark all of them for real.

## TL;DR verdict

**Not measurable through the existing platform as it stands today — and
that finding is itself the substantive result of this task.** Attempting
this exactly as specified surfaced two real, compounding platform
limitations (detailed below) that make every real training run land on
the same degenerate, near-two-and-a-half-year-old slice of candle
history, regardless of which features are requested. Every job that
completed training scored a trivial, tied 100% accuracy — not because any
feature helped, but because the training data itself never contained more
than one outcome class. Four of the eight real jobs failed outright with
an explicit, honest platform error rather than a wrong number. No feature
can be honestly verdicted "helped," "hurt," or "no difference" from these
runs — the correct, honest verdict for all six is **UNDETERMINED, blocked
by a real platform limitation**, not "no measurable difference."

This is not a failure to complete the task; it is what the task's own
Definition of Done explicitly asked for when something genuinely can't be
done through existing capability: disclose it, with real evidence, rather
than silently routing around it with new code.

---

## Step 1 — The baseline, confirmed exactly

The experiment currently driving the live, automated paper-trading
strategy was identified via `paper_accounts.strategy_training_job_id`
(confirmed directly against the real database, not assumed):

- **Experiment**: `565ca966-1437-4f28-b7d9-1d58002e38af` ("ETHUSD 1h
  config editor test")
- **Training job**: `8a948fba-8416-4ccb-a020-41628581cd38`
- **`feature_set`**: `[{"feature": "ohlcv", "params": {}}, {"feature":
"sma", "params": {"period": "20", "source": "close"}}]`
- **`target_config`**: `[{"target": "next_direction", "params":
{"horizon": "1"}}]`
- **`split_config`**: `{"train": 0.7, "validation": 0.15, "test": 0.15}`
- **`model_type`**: `logistic_regression`
- **`hyperparameters`**: `{"epochs": 10, "learning_rate": 0.001,
"batch_size": 32, "random_seed": 42, "validation_frequency": 1,
"max_iter": 200}`
- **`symbol`/`timeframe`**: `ETHUSD` / `1h`

Every new experiment below was built to match every one of these fields
exactly, varying only the feature set.

### A real problem found before any comparison could even begin

The baseline's own recorded `result_summary.normalization` stats showed
`open`, `high`, `low`, and `close` sharing **identical** mean, std, min,
and max (`2399.64` / `31.57` / `2340.15` / `2424.0`) across its 100
training rows — only possible if every candle in the window is perfectly
flat. Direct SQL against the real `candles` table confirmed it: a genuine
100-hour run of real, ingested ETHUSD candles, **`2024-02-08 06:00` →
`2024-02-12 09:00`, close price literally `2423.25` for all 100
candles**. Since `next_direction` (`app/ml_datasets/targets
/next_direction.py`) defines "flat" as exact equality between the current
and next close, this window's target is 100% "flat" by construction. The
baseline's own reported "100% accuracy" is a trivial artifact of training
on a dead-flat, non-representative historical stretch — not a real
model, and not something Milestone 4's connector work broke; it predates
all of it.

---

## Step 2 — Building the seven variants

### 2a. Proof that a genuinely controlled comparison is possible, at the dataset level

Real connector coverage in this dev environment, checked directly against
`external_data_points`/`news_articles`:

| Source                       | Real coverage (first → last)                          |
| ---------------------------- | ----------------------------------------------------- |
| `eth_tvl` (DefiLlama)        | 2017-09-27 → 2026-09-08                               |
| `fear_greed`                 | 2018-02-01 → 2026-09-08                               |
| `fed_funds_rate` (FRED)      | 1996-12-03 → 2026-09-01 (monthly, forward-fills fine) |
| `news_sentiment` (Marketaux) | 2026-08-06 → 2026-09-08                               |
| `eth_gas_price` (Etherscan)  | 2026-09-06 13:22 → 2026-09-08 16:07                   |
| `btc_dominance` (CoinGecko)  | 2026-09-06 17:45 → 2026-09-08 15:59                   |

The tightest constraint is `btc_dominance`, whose real data in this
environment only goes back about two days. Using the Dataset Builder's
own `/markets/ETHUSD/ml/dataset` endpoint directly (which **does** accept
an explicit `start`/`end`), a window was hand-tuned so every one of the
eight variants (baseline + six single-feature + all-six) converges on the
exact same final row set — verified **byte-identical**, not just equal
counts, by diffing each variant's own returned `timestamps` array:

- Request window: `2026-09-05T23:00:00Z` → `2026-09-08T15:00:00Z`
  (extra lookback before the connector-safe zone so `SMA(20)` warms up
  exactly in time)
- Final aligned window used by all eight: `2026-09-06T18:00:00Z` →
  `2026-09-08T13:00:00Z`, **44 rows**, real price movement (`2458.40` →
  `2513.45`), real near-balanced target distribution (**19 up / 24 down /
  0 flat** — genuinely non-degenerate)

This proves the platform's Dataset Builder itself is capable of a real,
controlled, non-degenerate comparison. **The blocker is one layer up, in
the Training Framework.**

### 2b. What happens when the seven variants are actually trained

`TrainingJobCreateRequest` (and the `Experiment` it's linked to) exposes
**no field at all** for `start`/`end`/`limit`. Confirmed directly in code
(`app/services/training.py::_make_load_dataset_hook`) and by a real probe
job: a training job always independently re-derives its own dataset from
the experiment's `feature_set`/`target_config`/`split_config` alone, with
none of the pinned-window fields above ever set — landing on whatever
`MLDatasetService`'s own default resolves to.

That default is **not** "the most recent N candles," which would at
least have been current, if narrow. It is the **earliest** N:
`app/services/candle_points.py` calls `candle_repository.get_candles(...,
sort="open_time", direction="asc")` explicitly, and when `start`/`end`
are both omitted, `normalize_range` returns `(None, None)` unchanged — so
the query is a bare `ORDER BY open_time ASC LIMIT 100`, with no lower
bound at all. **Every training job that omits an explicit date range —
which is every job the existing UI/API lets a caller create — trains on
the oldest 100 candles a market has, not the newest.** For `ETHUSD`/`1h`,
that is the exact same February 2024 dead-flat stretch the baseline used.
This is a real, previously-undisclosed platform bug, not a data-freshness
inconvenience — and it is almost certainly not the intended behavior for
a system meant to train a model to predict what happens next.

Eight real experiments and training jobs were created and run through the
existing API exactly as a real user would (`POST /experiments`, `POST
/training-jobs`, `POST /training-jobs/{id}/run`), each matching the
baseline's target/split/model/hyperparameters exactly, varying only the
feature set:

| Variant                    | Experiment id                          | Job id                                 | Result                             |
| -------------------------- | -------------------------------------- | -------------------------------------- | ---------------------------------- |
| Baseline (fresh re-run)    | `955251c8-3f0c-4e18-8227-064ec5148364` | `2fa5be0f-00ed-4cff-adbf-7fa80fd64b5f` | Completed — degenerate (see below) |
| + Fear & Greed             | `f9299c59-1d37-44d0-af83-0907f233e21c` | `c611f679-5e30-4e5d-a45d-115bf4aa471e` | Completed — degenerate             |
| + FRED                     | `0ed3ff1d-6e6f-4dab-b5ad-d51abafce130` | `a9ef2bf7-b2ae-4f97-ab79-b9f2f8c2082b` | Completed — degenerate             |
| + DefiLlama TVL            | `0f3090b8-8ef0-4f85-bc94-4d5d5f1e5468` | `717957ef-9b80-4c7b-8f5c-22b427308664` | Completed — degenerate             |
| + Etherscan gas price      | `272bb078-3449-40ba-80bc-a71ea9a810c0` | `e808f873-cc6b-4118-836a-3bbec9322b26` | **Failed**                         |
| + CoinGecko BTC dominance  | `903004eb-90b5-40a5-a49e-6eaac6c0c1ba` | `c4e6de6c-b3b9-4420-b43c-f0315a728d9f` | **Failed**                         |
| + Marketaux news sentiment | `18d0c9c9-ed80-493d-bd18-4a953c6cf971` | `f8beebeb-2631-483e-8110-6a24a4e48e71` | **Failed**                         |
| + all six                  | `9fef6f33-4da4-433c-914a-624a3a4ca27e` | `d0f89395-adc3-4149-9828-84f4e18b5c5d` | **Failed**                         |

The four failures all returned the identical, honest platform error:

```text
Every row was dropped: 121 candles were loaded but the requested
features need 20 candles of warmup. Widen the date range or reduce
the largest period parameter
```

This is the direct, mechanical consequence of the bug above: the
"earliest 100 (121 with warmup)" candles are from February 2024 — 2.5
years before `eth_gas_price`/`btc_dominance`/`news_sentiment` have any
real data at all in this environment, so every row is null for that
feature and gets dropped. `all_six` fails for the same reason, dragged
down by whichever of its six inputs has the narrowest coverage.

---

## Step 3 — The benchmark, run for real

`POST /evaluation/benchmark` was run comparing all four completed new
jobs plus the original live baseline job(s), filtered by
`experiment_ids` (the request's own `target_column` filter turned out to
require a DB column, `training_jobs.target_column`, that stays blank
unless explicitly set at job-creation time — a second, minor, real API
surprise worth a one-line disclosure of its own, unrelated to the main
finding above).

| Job        | Experiment                      | accuracy | f1  | precision | recall | Samples | Features |
| ---------- | ------------------------------- | -------- | --- | --------- | ------ | ------- | -------- |
| `2fa5be0f` | Baseline (fresh re-run)         | 1.0      | 1.0 | 1.0       | 1.0    | 100     | 6        |
| `c611f679` | + Fear & Greed                  | 1.0      | 1.0 | 1.0       | 1.0    | 100     | 7        |
| `a9ef2bf7` | + FRED                          | 1.0      | 1.0 | 1.0       | 1.0    | 100     | 7        |
| `717957ef` | + DefiLlama TVL                 | 1.0      | 1.0 | 1.0       | 1.0    | 100     | 7        |
| `8a948fba` | Original live baseline          | 1.0      | 1.0 | 1.0       | 1.0    | 100     | 6        |
| `c406b242` | Original baseline (earlier run) | 1.0      | 1.0 | 1.0       | 1.0    | 100     | 6        |

`best_by_metric` named `717957ef` (DefiLlama TVL) as "best" on every
metric. **This is a meaningless tie-break, not a real result** — every
single candidate above is tied at the exact same trivial ceiling (1.0
across all four metrics), because every one of them was trained on the
identical dead-flat window and trivially always predicts "flat." A
benchmark's own best-by-metric pick has to break ties somehow; here it
picked whichever job happened to sort first, which carries no
information about whether DefiLlama TVL is actually better than anything.

The one place a real, non-zero difference did appear: `train_metrics
.roc_auc` was `0.9509` for baseline/FRED, but `0.9014` for Fear &
Greed/DefiLlama TVL. This is a genuine, measurable numeric difference —
but it lives inside a training-set metric on a degenerate, 100-row,
single-outcome-class dataset, and says nothing trustworthy about real
predictive value. It is reported here for completeness, not as a finding
to act on.

---

## Per-feature verdict

| Feature                    | Verdict                                                                                                                                                                      |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Fear & Greed               | **UNDETERMINED** — trained, but on the same degenerate window as baseline; tied at trivial 100% accuracy                                                                     |
| FRED (Federal Funds Rate)  | **UNDETERMINED** — same as above; numerically inert even inside the degenerate run (identical to baseline on every recorded metric)                                          |
| Etherscan (gas price)      | **UNDETERMINED — blocked**: training failed outright (`every row was dropped`), this connector's own real data does not reach back to the platform's default training window |
| DefiLlama (TVL)            | **UNDETERMINED** — same as Fear & Greed/FRED                                                                                                                                 |
| CoinGecko (BTC dominance)  | **UNDETERMINED — blocked**: same failure as Etherscan                                                                                                                        |
| Marketaux (news sentiment) | **UNDETERMINED — blocked**: same failure as Etherscan                                                                                                                        |
| All six together           | **UNDETERMINED — blocked**: same failure, inherited from whichever of the six has the narrowest coverage                                                                     |

No feature above is reported as "helped," "hurt," or "no measurable
difference" — every one of those would overstate what these runs
actually show. The honest verdict, for all six, is that the platform as
it exists today cannot yet produce a trustworthy answer.

---

## Real platform limitations disclosed (not routed around)

1. **The Training Framework's own dataset-rebuild step has no way to
   specify a date range or row limit.** `TrainingJobCreateRequest` and
   `Experiment.feature_set`/`target_config`/`split_config` carry no such
   field; `_make_load_dataset_hook` (`app/services/training.py`)
   constructs its own `MLDatasetRequest` with `start`/`end`/`limit` left
   at their defaults, always. This is the direct reason the careful,
   byte-identical 44-row window proven possible at the Dataset Builder
   level (Step 2a) could not be carried through to an actual trained
   model.
2. **The default candle window (no explicit `start`/`end`) loads the
   _earliest_ candles in a market's history, not the most recent.**
   `app/services/candle_points.py` passes `direction="asc"` explicitly,
   and `normalize_range` leaves both bounds `None` when neither is
   given — so an un-dated query is a bare `ORDER BY open_time ASC LIMIT
N`. For any market with more than `N` candles of history (every real
   market on this platform), this means training on the _oldest_
   available data, not the newest — the opposite of what a system meant
   to predict "what happens next" should default to. This is very likely
   an unintended design flaw, not a deliberate choice, and it directly
   explains why the currently-live paper-trading strategy's own model is
   trained on a dead, 2.5-year-old, single-outcome-class window.
3. A minor, second API surprise: `BenchmarkRequest.target_column`
   filters on `training_jobs.target_column`, a column that stays blank
   unless a caller explicitly passes `target_column` at job-creation time
   (it is not back-filled from `result_summary.target_column`, which
   _is_ always populated). Filtering by `experiment_ids` instead worked
   as expected.

Neither limitation was worked around with new code, per this task's own
explicit instruction — both are reported here as real findings.

## What would actually need to change (not implemented here — out of scope)

- Let `TrainingJobCreateRequest` (or the linked `Experiment`) optionally
  carry an explicit `start`/`end`/`limit`, forwarded into the
  `MLDatasetRequest` `_make_load_dataset_hook` builds.
- Change the _default_ (when neither is given) to the most recent window
  — `direction="desc"` then re-sorted ascending for use, or an implicit
  `end=now()`/`start=end - limit*timeframe` — for any training-oriented
  dataset build. `direction="asc"` may still be the right default
  elsewhere (e.g. a `/candles` browse starting from a market's listing
  date); this recommendation is scoped to the training/dataset-building
  path specifically.
- Once both are fixed, re-run this exact assessment — the methodology
  (control everything except the feature set; verify row-count parity by
  diffing actual timestamps, not just counts; run one baseline + six
  single-feature + one all-six experiment; benchmark all of them
  together) is sound and reusable as-is.

---

## Real evidence trail

- All 8 new experiments/training jobs listed above are real, persisted
  database rows — not deleted, kept as the record of this investigation
  (alongside the 3 experiments that already existed).
- Real benchmark response saved during this investigation; the exact
  request/response shapes and error strings quoted above are verbatim
  from the running dev server, not paraphrased.
- The February 2024 dead-flat window was independently confirmed via
  direct SQL against `candles` (a window-function scan for the longest
  unchanging-close run in the table), not inferred from the model's
  output alone.
- The Dataset Builder's own byte-identical 44-row parity across all 8
  variants was verified by diffing full `timestamps` arrays returned by
  `POST /markets/ETHUSD/ml/dataset`, not just comparing row counts.
