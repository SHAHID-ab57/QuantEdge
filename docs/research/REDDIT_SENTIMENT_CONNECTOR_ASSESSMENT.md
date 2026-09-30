# Reddit Sentiment/Volume Connector Assessment

**Task:** M4-E4-T1 (`TASKBOOK.md`), reopening Milestone 4 — Data Breadth
after it was already marked complete, to test whether retail
sentiment/volume from Reddit adds anything **`volatility_regime`** does
not already get from `realized_volatility` — deliberately not
_direction_, which Marketaux's `news_sentiment` already tested for this
exact signal category (professional, curated financial news sentiment)
and found nothing (`TARGET_REDEFINITION_ASSESSMENT.md`).

## TL;DR verdict

**Steps 1 and 2 are done: a real connector, a real dedicated table, and
two real, tested, no-look-ahead-verified features exist and are wired
in.** **Step 3 — the actual signal test against `volatility_regime` —
is deliberately not run.** A real, full-depth backfill attempt found
Arctic Shift's (the data source's) informal rate limit has a
session-cumulative component that no amount of per-request pacing or
post-failure cooldown could clear, capping one real backfill session at
roughly 56 days of history. This project's own established methodology
(`TARGET_REDEFINITION_ASSESSMENT.md`) treats only the full ~2.6-year
candle history as the **authoritative** primary comparison window, and a
42-day recent slice as **explicitly weaker, cross-check-only** evidence
— precisely because a single recent-window result has previously been
mistaken for a durable finding in this same research thread. Reddit's
real depth cannot reach the authoritative window at all, and running
only the window it can reach and reporting that as the answer would
repeat the exact mistake this project's own standard exists to prevent.
Per an explicit user decision, this document reports the constraint and
stops here rather than publish a result that would immediately need to
be caveated away.

---

## Step 1 — real investigation, not assumed

### Reddit's own API is not usable in this environment

A real, current policy change — Reddit's "Responsible Builder Policy",
effective 2026-06-05 — replaced self-service OAuth app registration with
a manual approval queue: 2-4+ weeks turnaround, real rejection risk, no
dedicated academic/research fast-track. Confirmed via third-party
sources (no assumption from stale training data), since every
Reddit-owned domain (`reddit.com`, `redditinc.com`,
`developers.reddit.com`, `web.archive.org`) was unreachable from this
environment. Reddit's own live API (`oauth.reddit.com`) is therefore not
usable here, at any tier.

### Arctic Shift — a free, keyless, third-party mirror, confirmed live

`arctic-shift.photon-reddit.com` (GitHub: `ArthurHeitmann/arctic_shift`)
is a community-run historical mirror of Reddit data. Confirmed live via
direct `curl`, not assumed from its own README:

- No authentication required.
- `limit` is capped at 100/request — confirmed via a real
  `{"data":null,"error":"'limit' must be between 1 and 100"}` response.
- `sort=asc`/`sort=desc` both work (default descending) — this connector
  always sends `sort=asc` explicitly.
- `after`/`before` accept both ISO date strings and raw Unix epoch
  seconds — confirmed by direct testing with both forms.
- Its `fields=` allowlist is **narrower** than the unfiltered response's
  own field set: `permalink` is present in a full response but is
  **not** a valid `fields=` name, discovered via a real HTTP 400 during
  the first backfill attempt (`{"data":null,"error":"'permalink' is not
a valid field"}`), confirmed by a follow-up `curl`, and fixed by
  removing it from `_FIELDS` (`RedditComment.permalink` is always
  `null` today as a result).
- Real historical depth confirmed back to at least January 2023 for
  r/ethereum.
- A post's own `score`/`num_comments` fields can read `0`/stale for up
  to ~36h before finalizing per Arctic Shift's own README — irrelevant
  here, since this connector only ever reads comment-level fields, never
  a post's own score/comment-count.
- No uptime or performance guarantees are documented; bulk automated
  extraction via the live API is explicitly discouraged in favor of
  monthly dumps. This task did not build support for those dumps — see
  "What would unblock Step 3" below.

### Real subreddit-activity investigation — post volume too thin, comment volume usable

Checked live via direct `curl` + item-count sampling across multiple
real recent days, not assumed:

| Subreddit        | Posts/day (sample) |                           Comments/day (sample) |
| ---------------- | -----------------: | ----------------------------------------------: |
| r/ethereum       |                1-3 |                                         ~69-100 |
| r/ethtrader      |                  3 |                                             ~90 |
| r/ethfinance     |                  1 |                                        not used |
| r/ethstaker      |                  1 |                                        not used |
| r/CryptoCurrency |        not sampled | 100+ (hits the API's own 100-item response cap) |

Post volume on ETH-specific subreddits is too thin for a feature — the
task's own explicitly flagged risk. Comment volume is materially higher
and consistent across 2023/2024/2025 samples. Final
`reddit_subreddits` default: `"ethereum,ethtrader,CryptoCurrency"`.

### No pre-computed sentiment — VADER chosen, per the task's own instruction

Arctic Shift's comment payload carries no sentiment score (unlike
Marketaux's own per-entity `sentiment_score`). Per this task's explicit
allowance not to build custom NLP from scratch when a simple, defensible
method suffices, `vaderSentiment`'s
`SentimentIntensityAnalyzer().polarity_scores(body)["compound"]` is used,
giving `[-1, 1]` — matching Marketaux's own scale convention exactly.
`score_comment()` returns `None` for empty/`[deleted]`/`[removed]`
bodies; they still count toward volume, excluded from sentiment.

---

## Step 2 — the build

Full architectural detail lives in `ARCHITECTURE.md` § "External Data
Connectors" → "Reddit Connector"; summarized here:

- **`app/connectors/reddit.py`** — `ArcticShiftClient` (retry/backoff,
  now including HTTP 422 as retryable) + `RedditConnector`
  (`ConnectorMetadata(auto_synced=False)`), paginating forward per
  subreddit with a real, deliberate `reddit_page_pause_seconds=1.5`
  pause between pages (added after a real backfill crash showed retries
  alone did not clear a sustained 422).
- **`app/models/reddit.py`** — `RedditComment`, mirroring `NewsArticle`'s
  dedicated-table pattern (`reddit_id` unique dedup key, `subreddit`,
  `body`, `score`, nullable `sentiment_score`, `created_utc`,
  `raw_payload`). Migration `433b86f94f10`.
- **`app/services/reddit_ingest.py`** — `ingest_reddit()`, mirroring
  `news_ingest.py`; `_mirror_daily_aggregates` computes and upserts
  **two** derived daily aggregates per touched day (`reddit_volume`,
  `reddit_sentiment`) into `external_data_points`, only when the value
  actually changed (a real bug — unconditionally re-marking a day as
  recomputed regardless of whether anything changed — was caught while
  writing the "second tick with nothing new" test and fixed before it
  shipped).
- **`app/services/reddit_sync.py`** — `RedditSyncScheduler`, mirroring
  `NewsSyncScheduler`'s shape, with a much smaller discovery-safety
  margin (30 minutes vs. Marketaux's 6 hours) since comments are
  queryable promptly, unlike articles which can be indexed well after
  `published_at`.
- **`app/features/builtin/reddit_volume.py`** /
  **`reddit_sentiment.py`** — both reuse
  `most_recent_value_at_or_before`, the same no-look-ahead mechanism
  every other feature in this platform uses.
- **`scripts/backfill_reddit.py`** — CLI backfill, walking backward in
  `--chunk-days`-sized windows (default 7), now with a per-chunk
  cooldown-and-retry (`--chunk-cooldown-seconds`, default 300;
  `--chunk-max-retries`, default 5) added after the rate-limit finding
  below.

**Testing:** `tests/connectors/test_reddit.py` (25 tests),
`tests/services/test_reddit_ingest.py`, `tests/services/test_reddit_sync.py`,
`tests/features/test_reddit_features.py` — all passing. Full backend
suite (`uv run pytest`) passes with zero failures (only the usual
opt-in/environment-gated skips). `ruff check` and `pyright` both clean
on every new/modified file.

---

## The real rate-limit finding that blocks Step 3

A first full-history backfill attempt (`--days 180`) succeeded for its
first four 7-day chunks (28 days, ~12,768 comments received) at a
steady, paced cadence (`--pause-seconds 2` between chunks,
`reddit_page_pause_seconds=1.5` between pages within a chunk), then
crashed on the fifth chunk with a sustained run of HTTP 422s that the
connector's own 5-attempt, exponential-backoff retry (capped at 8s)
could not clear.

Two escalating cooldown-and-retry strategies were then tried in
`scripts/backfill_reddit.py`, added specifically in response to this
finding:

| Attempt                                             | Cooldown | Retries | Result                                                                                                                                                                                                                                                                                                                                                                                                              |
| --------------------------------------------------- | -------: | ------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1                                                   |      90s |       3 | Failed after all 3 — each retry recovered the identical shape (a fresh ~14-16-request allowance drained in well under a minute, then sustained 422s)                                                                                                                                                                                                                                                                |
| 2                                                   |     300s |       5 | Failed after all 5 (25 minutes of cumulative cooldown) — same shape again, no improvement from the 3x longer wait                                                                                                                                                                                                                                                                                                   |
| 3 (a tiny, 3-day gap-fill, run after the two above) |     300s |       5 | Failed after all 5 retries too, on a request volume orders of magnitude smaller than the earlier attempts — confirming the limit persists across separate process invocations within the same real-world session (this is a cumulative, session-level condition, not something that resets when a process exits), and that request volume alone is not a reliable predictor of whether a given attempt will succeed |

This pattern — waiting _longer_ not changing how much capacity comes
back — is the load-bearing evidence that this is not a simple
"wait N seconds and retry" token bucket that per-request pacing or a
longer cooldown can outlast. It reads as either a longer-duration,
session-level throttle (measured in many minutes to hours, not seconds)
or genuine shared-infrastructure congestion on a free, "no uptime or
performance guarantees" community service — this task did not have
time or cause to determine which, and either way the practical
consequence for this session is the same.

**Real data actually obtained:** 27,614 comments across 56 real days
(`2026-08-02` to `2026-09-27`), confirmed via a direct query against
`reddit_comments`:

| Subreddit      | Comments |
| -------------- | -------: |
| CryptoCurrency |   16,048 |
| ethereum       |    5,920 |
| ethtrader      |    5,646 |

This window overlaps almost all of this project's own established
**cross-check** window (`2026-07-30` to `2026-09-10`) but covers **none**
of the **primary, authoritative** window (the full ~2.6-year ETHUSD/1h
history, `limit=23,000`) that every other feature in
`TARGET_REDEFINITION_ASSESSMENT.md` was measured against.

## Why Step 3 was not run anyway on the window that is available

Running the comparison methodology on the 42-day cross-check window
alone was considered and explicitly rejected. `TARGET_REDEFINITION_ASSESSMENT.md`
already documents, in its own words, why a cross-check-window-only
result cannot stand in for the primary one: "the cross-check window's
dramatic numbers... [are] carried almost entirely by [a] real, not-by-
chance but also not-necessarily-durable correlation with that window's
own price trend — not a real, durable pattern." Publishing a Reddit
result measured only on that same class of window, with no authoritative
counterpart to check it against, would produce exactly the kind of
number this project's own methodology was built to distrust. Given the
explicit choice offered — run the weaker window anyway and caveat it
heavily, spread the backfill over further sessions to eventually reach
the authoritative window, or report the constraint and hold off — the
user chose the third.

## What would unblock Step 3

- **Patient, multi-session backfilling.** Spread short backfill batches
  across hours or days, respecting whatever the real (still not fully
  characterized) recovery window turns out to be, until enough history
  accumulates to attempt the authoritative primary window. Slow, and the
  exact pacing needed is not yet known.
- **Arctic Shift's own monthly bulk dumps.** Its README recommends these
  over live-API extraction for exactly this kind of bulk historical need.
  Not built here — a materially different ingestion mechanism (file
  download/parse rather than paginated HTTP), out of this task's scope.
- Either path, once enough real history exists, the exact methodology
  every other candidate in this thread was held to (same primary window,
  chronological split, noise band, cross-check window, all three
  classifiers, permutation importance) should be applied unchanged —
  no new methodology is needed, only more real data.
