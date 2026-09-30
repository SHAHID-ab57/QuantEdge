"""The Reddit sentiment/volume connector — the seventh concrete connector,
and, like Marketaux, one whose real shape doesn't fit "one connector, one
numeric value per timestamp" at all. A real comment carries genuinely
richer detail (body text, author, subreddit, score) than `RawDataPoint`
can hold, and a calendar day holds a variable, often-large number of
them — see `app.models.reddit.RedditComment`'s own module docstring for
why that detail lives in a dedicated table, with only *derived* daily
aggregates (volume count, mean VADER sentiment) ever mirrored into
`external_data_points` (`app.services.reddit_ingest`).

**Investigated before building, not assumed — checked live against real
current terms and real live API behavior (REDDIT-SENTIMENT-CONNECTOR):**

1. **Reddit's own live Data API is not usable in this session, for a real,
   current reason.** The free, non-commercial tier genuinely exists (100
   QPM per OAuth client, confirmed via current third-party documentation
   of Reddit's own terms) — but as of a June 2026 "Responsible Builder
   Policy" change, self-service OAuth app registration was replaced with
   a manual approval queue (reported 2-4+ weeks, real rejection risk, no
   dedicated research/academic fast lane). This connector therefore does
   **not** talk to `oauth.reddit.com` at all — building against it would
   require an application this session cannot submit or wait out.
2. **Arctic Shift (`arctic-shift.photon-reddit.com`) is the real, live,
   currently-usable path instead** — a third-party, community-run mirror
   of Reddit's own historical data, confirmed live with real requests
   during this investigation: no auth, no registration, real historical
   depth (comments retrieved from 2023, 2024, and 2025 alike), `limit`
   capped at 100 per request (confirmed via a real `400`-shaped error
   body, not assumed from docs), `sort=asc`/`after`/`before` (accepting
   raw Unix epoch seconds, confirmed live) usable for cursor pagination.
   Its own README asks that *bulk* extraction use the monthly dumps
   instead of the live API — this connector's own periodic sync tick and
   backfill script both stay within "a couple requests per second," never
   parallel/bulk hammering, matching that guidance's spirit even though
   this platform's own scheduled-catch-up shape is not the dump-processing
   use case the README is steering away from.
3. **Post volume is too thin to be a usable signal on its own — checked
   live, not assumed.** ETH-specific subreddits (r/ethereum, r/ethtrader,
   r/ethfinance) showed only 1-3 *posts*/day on a real recent sample day.
   **Comments are the real, usable volume signal instead**: the same
   subreddits showed 69-100+ comments on the same day, consistently
   present across 2023/2024/2025 samples. This connector ingests comments,
   not posts.
4. **No pre-computed sentiment score exists in this data** (unlike
   Marketaux, which supplies one) — VADER (`vaderSentiment`, a small,
   well-established, rule-based lexicon scorer built for short, informal
   social-media-style text, no training/corpus download required) computes
   a `compound` score in `[-1, 1]` per comment, the same scale convention
   Marketaux's own `sentiment_score` already uses on this platform. This is
   a simple, already-available, defensible method — not custom NLP built
   from scratch for this task.
5. **Data freshness**: Arctic Shift's own docs note a post's `score`/
   `num_comments` fields can read `0`/stale for up to ~36h after
   publication before finalizing; this connector never reads those two
   fields at all (only `body`/`created_utc`/`id`/`author`/`score` on the
   *comment* itself, whose own existence and body text are available
   promptly) — the safety margin this finding requires lives in
   `RedditSyncScheduler` instead (mirroring `NewsSyncScheduler`'s own
   `DISCOVERY_SAFETY_MARGIN`, sized from this same real finding).

**The three known bug patterns, checked explicitly, mirroring every
connector since Fear & Greed:**

- **An omitted parameter defaulting to something surprising**: default
  sort order is *descending* (newest first) — confirmed live. This
  connector always sends `sort=asc` explicitly for pagination; relying on
  the default would have silently paginated backward.
- **A timestamp computed at the wrong moment relative to a network
  call**: does not apply — every comment carries its own `created_utc`.
- **A response field silently not captured**: `id`/`body`/`created_utc`/
  `author`/`score`/`subreddit` are all explicitly requested via `fields=`
  and captured into `RedditComment` (`permalink` is stored but always
  `None` — confirmed live it is not a valid `fields=` name on this API
  despite appearing in the unfiltered response, a real, found-not-assumed
  instance of *this exact* bug pattern, not merely guarded against); a
  comment with a deleted/removed body (`"[deleted]"`/`"[removed]"`) still
  counts toward volume but is excluded from sentiment scoring
  (empty/placeholder text has no real sentiment to score) — recorded, not
  silently dropped.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.connectors.base import ConnectorMetadata, RawDataPoint
from app.connectors.errors import ConnectorAPIError, ConnectorNetworkError, ConnectorRateLimitError
from app.connectors.registry import register_connector
from app.core.config import get_settings

logger = logging.getLogger("app.connectors.reddit")

#: Two derived aggregates are mirrored into `external_data_points` from
#: this one connector's raw comments — see `app.services.reddit_ingest`.
REDDIT_VOLUME_SOURCE = "reddit_volume"
REDDIT_SENTIMENT_SOURCE = "reddit_sentiment"

_COMMENTS_PATH = "/api/comments/search"
#: Confirmed live: "permalink" (present in the *unfiltered* response) is
#: not a valid name for this specific `fields=` allowlist — a real
#: `{"data": null, "error": "'permalink' is not a valid field"}` on the
#: very first live backfill run, not assumed from the API's own docs.
#: `permalink` stays `None` on every `RedditItem` as a result — acceptable
#: since it is non-essential metadata, never read by sentiment/volume
#: aggregation.
_FIELDS = "id,body,created_utc,author,score,subreddit"
#: Confirmed live: a `limit` above 100 returns `{"data": null, "error":
#: "'limit' must be between 1 and 100"}`.
_MAX_LIMIT = 100

#: 422 confirmed live to be Arctic Shift's own real, non-standard
#: rate-limit/overload signal — a real backfill run hit HTTP 422 with
#: body `{"data": null, "error": "Timeout. Maybe slow down a bit"}`, not
#: 429. Not assumed from docs: this API's own README only mentions 429
#: for rate limiting, but real behavior under sustained load differs.
RETRYABLE_STATUS_CODES = frozenset({422, 429, 500, 502, 503, 504})
#: Higher than Marketaux's own default (3) — Arctic Shift's own README
#: states "no uptime or performance guarantees," and a real backfill run
#: showed genuine, recoverable overload responses under sustained
#: sequential use, not just transient network blips.
DEFAULT_MAX_RETRIES = 5
DEFAULT_RETRY_BACKOFF = 0.5
_MAX_RETRY_DELAY = 30.0
_USER_AGENT = "eth-ai-platform/0.1.0"

#: `[deleted]`/`[removed]` bodies carry no real sentiment — the comment
#: still counts toward volume (a real interaction happened), but is
#: excluded from the sentiment aggregate, mirroring how an entity-less
#: Marketaux article is stored but excluded from that mean.
_EMPTY_BODIES = frozenset({"[deleted]", "[removed]"})

#: One shared analyzer instance — VADER's own lexicon/model is loaded
#: once at import time and is stateless/thread-safe across calls, the
#: same "build once, reuse" reasoning an httpx client gets, just for a
#: pure in-process scorer with nothing to close.
_SENTIMENT_ANALYZER = SentimentIntensityAnalyzer()


def score_comment(body: str) -> float | None:
    """VADER's own `compound` score for `body`, in `[-1, 1]` (matching
    Marketaux's own `sentiment_score` scale convention) — `None` for a
    deleted/removed/empty body, which has no real sentiment to score.
    Shared by `RedditConnector.fetch`'s own protocol-conformance shim and
    `app.services.reddit_ingest`'s daily aggregate computation, so both
    ever compute a comment's sentiment exactly one way.
    """
    text = body.strip()
    if not text or text in _EMPTY_BODIES:
        return None
    return _SENTIMENT_ANALYZER.polarity_scores(text)["compound"]


@dataclass(frozen=True, slots=True)
class RedditItem:
    """One real Reddit comment, richer than `RawDataPoint` can hold —
    mirrors `app.connectors.marketaux.MarketauxArticle`'s own reasoning.
    Used by `app.services.reddit_ingest` to build a `RedditComment` row
    directly; `RedditConnector.fetch()` (the `Connector` protocol method)
    is a thinner, lossy adapter over the same underlying page fetch."""

    reddit_id: str
    subreddit: str
    author: str | None
    body: str
    score: int
    created_utc: datetime
    permalink: str | None
    raw_payload: dict[str, Any]


class ArcticShiftClient:
    """Async HTTP client for Arctic Shift's `/api/comments/search` endpoint.

    Same retry/backoff/logging shape as every other connector's client
    (`FearGreedClient`/`MarketauxClient`); no authentication at all —
    confirmed live (see this module's own docstring, point 2).
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        request_timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = DEFAULT_RETRY_BACKOFF,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if retry_backoff <= 0:
            raise ValueError("retry_backoff must be positive")

        settings = get_settings()
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.reddit_base_url,
            timeout=httpx.Timeout(
                request_timeout if request_timeout is not None else settings.reddit_request_timeout
            ),
            transport=transport,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )

    async def fetch_comments_page(
        self,
        *,
        subreddit: str,
        after: datetime,
        before: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return one raw page of comment objects, oldest first
        (`sort=asc`, sent explicitly — see this module's own docstring on
        why relying on the default would be a real bug, not a style
        choice). `after`/`before` are sent as raw Unix epoch seconds —
        confirmed live to be accepted this way, giving cursor pagination
        the second-level precision an ISO date string can't."""
        if limit < 1 or limit > _MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_LIMIT}")
        payload = await self._execute(
            "GET",
            _COMMENTS_PATH,
            params={
                "subreddit": subreddit,
                "after": int(after.timestamp()),
                "before": int(before.timestamp()),
                "limit": limit,
                "sort": "asc",
                "fields": _FIELDS,
            },
        )
        if not isinstance(payload, dict):
            raise ConnectorAPIError(
                "Malformed Arctic Shift response: expected an object envelope", detail=payload
            )
        if payload.get("error") is not None:
            raise ConnectorAPIError(
                f"Arctic Shift reported an error: {payload['error']}", detail=payload
            )
        data = payload.get("data")
        if not isinstance(data, list):
            raise ConnectorAPIError(
                "Malformed Arctic Shift response: missing or malformed 'data'", detail=payload
            )
        return data

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "ArcticShiftClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()

    async def _execute(self, method: str, path: str, *, params: dict[str, Any]) -> object:
        """Send one request with retries; return the decoded JSON body."""
        attempt = 0
        while True:
            started = time.perf_counter()
            try:
                response = await self._client.request(method, path, params=params)
            except httpx.TimeoutException as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "Arctic Shift %s %s timed out on attempt %d (%.1fms)",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                )
                if attempt >= self._max_retries:
                    raise ConnectorNetworkError(
                        f"Arctic Shift request timed out: {method} {path}", detail=str(exc)
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue
            except httpx.TransportError as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "Arctic Shift %s %s transport error on attempt %d (%.1fms): %s",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                    exc,
                )
                if attempt >= self._max_retries:
                    raise ConnectorNetworkError(
                        f"Arctic Shift network failure for {method} {path}: {exc}", detail=str(exc)
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue

            latency_ms = (time.perf_counter() - started) * 1000
            status = response.status_code
            logger.info("Arctic Shift %s %s -> %d (%.1fms)", method, path, status, latency_ms)

            if status in RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                delay = self._retry_delay(status, response, attempt)
                logger.warning(
                    "Arctic Shift retrying %s %s after %d in %.2fs (attempt %d/%d)",
                    method,
                    path,
                    status,
                    delay,
                    attempt + 1,
                    self._max_retries,
                )
                await self._sleep(delay)
                attempt += 1
                continue

            return self._handle_response(method, path, response)

    def _handle_response(self, method: str, path: str, response: httpx.Response) -> object:
        status = response.status_code
        if status == 429:
            raise ConnectorRateLimitError(
                f"Arctic Shift rate limit exceeded for {method} {path}",
                retry_after=self._parse_retry_after(response),
                status_code=status,
            )
        payload = self._json_payload(response)
        if payload is None:
            raise ConnectorAPIError(
                f"Malformed Arctic Shift response for {method} {path}: body is not valid JSON",
                status_code=status,
            )
        if status >= 400:
            raise ConnectorAPIError(
                f"Arctic Shift request failed with HTTP {status} for {method} {path}",
                status_code=status,
                detail=payload,
            )
        return payload

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After") or response.headers.get("X-RateLimit-Reset")
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    @staticmethod
    def _json_payload(response: httpx.Response) -> object | None:
        try:
            return response.json()
        except ValueError:
            return None

    def _retry_delay(self, status: int, response: httpx.Response, attempt: int) -> float:
        if status == 429:
            retry_after = self._parse_retry_after(response)
            if retry_after is not None:
                return min(max(retry_after, 0.0), _MAX_RETRY_DELAY)
        return min(self._retry_backoff * (2**attempt), _MAX_RETRY_DELAY)

    async def _backoff(self, attempt: int) -> None:
        delay = min(self._retry_backoff * (2**attempt), _MAX_RETRY_DELAY)
        await self._sleep(delay)

    @staticmethod
    async def _sleep(delay: float) -> None:
        jittered = delay * (1.0 + random.random() * 0.1)
        await asyncio.sleep(jittered)


def get_arctic_shift_client(
    *,
    base_url: str | None = None,
    request_timeout: float | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
) -> ArcticShiftClient:
    """Return a configured Arctic Shift client, defaulting from settings."""
    return ArcticShiftClient(
        base_url=base_url,
        request_timeout=request_timeout,
        transport=transport,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
    )


@register_connector
class RedditConnector:
    """Adapts `ArcticShiftClient` to the `Connector` protocol.

    Holds its own client (built fresh per instance, same reasoning as
    every other connector); `aclose()` releases it, and the class
    supports `async with` for the "use once, then close" case
    ingestion/backfill both need.
    """

    metadata: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        source=REDDIT_VOLUME_SOURCE,
        label="Reddit Comment Volume & Sentiment",
        description=(
            "Daily comment volume and mean VADER sentiment across configured "
            "cryptocurrency subreddits (via Arctic Shift, a free, keyless "
            "third-party mirror of Reddit's own data — Reddit's own live API "
            "requires a manual OAuth approval this platform has not obtained, "
            "see this module's own docstring). Raw comments live in their own "
            "table; this and reddit_sentiment are only the daily aggregates "
            "the ML pipeline consumes."
        ),
        frequency="hourly catch-up ticks (see RedditSyncScheduler)",
        expected_interval_seconds=86_400,
        requires_auth=False,
        version="1.0.0",
        aliases=("reddit", "arctic_shift"),
        auto_synced=False,
    )

    def __init__(
        self,
        *,
        client: ArcticShiftClient | None = None,
        subreddits: str | None = None,
        page_limit: int | None = None,
        max_pages: int | None = None,
        page_pause_seconds: float | None = None,
    ) -> None:
        self._client = client or get_arctic_shift_client()
        settings = get_settings()
        configured_subreddits = subreddits if subreddits is not None else settings.reddit_subreddits
        self._subreddits = [
            part.strip() for part in configured_subreddits.split(",") if part.strip()
        ]
        self._page_limit = page_limit if page_limit is not None else settings.reddit_page_limit
        self._max_pages = (
            max_pages if max_pages is not None else settings.reddit_max_pages_per_fetch
        )
        self._page_pause_seconds = (
            page_pause_seconds
            if page_pause_seconds is not None
            else settings.reddit_page_pause_seconds
        )

    async def fetch_items(self, start: datetime, end: datetime) -> tuple[RedditItem, ...]:
        """Return every real comment in `[start, end]` (inclusive both
        ends) across every configured subreddit, paginating forward in
        time (`sort=asc`, cursor advanced past the last-seen comment's own
        `created_utc`) up to `reddit_max_pages_per_fetch` pages *per
        subreddit*, to bound one call's own real request cost.

        A real, deliberate pause (`reddit_page_pause_seconds`) between
        pages — not just retries after a failure — because a real backfill
        run confirmed sustained back-to-back pagination alone (no
        concurrency, already sequential) triggers Arctic Shift's own
        informal overload response (HTTP 422, `"error": "Timeout. Maybe
        slow down a bit"`) badly enough that even 5 retries with
        exponential backoff up to 8s did not clear it. Retries alone treat
        the symptom; this addresses what was actually found to trigger it.
        The same pause applies between subreddits, not only between pages
        of the same one — the last page of one subreddit and the first
        page of the next were otherwise back-to-back with no gap at all,
        the exact same request-volume risk this pause exists to avoid.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware datetimes")
        if end < start:
            raise ValueError("end must not be before start")

        items: list[RedditItem] = []
        for subreddit_index, subreddit in enumerate(self._subreddits):
            if subreddit_index > 0:
                await asyncio.sleep(self._page_pause_seconds)
            cursor = start
            for page_index in range(self._max_pages):
                if page_index > 0:
                    await asyncio.sleep(self._page_pause_seconds)
                raw_items = await self._client.fetch_comments_page(
                    subreddit=subreddit, after=cursor, before=end, limit=self._page_limit
                )
                if not raw_items:
                    break
                for entry in raw_items:
                    item = _to_item(entry, subreddit)
                    if item is not None and start <= item.created_utc <= end:
                        items.append(item)
                last_created_utc = raw_items[-1].get("created_utc")
                if not isinstance(last_created_utc, (int, float)):
                    break
                next_cursor = datetime.fromtimestamp(last_created_utc + 1, tz=UTC)
                if next_cursor <= cursor or len(raw_items) < self._page_limit:
                    break
                cursor = next_cursor
            else:
                # The loop ran out of pages (`reddit_max_pages_per_fetch`)
                # without ever seeing a partial page — real evidence this
                # window may hold more comments than were actually
                # gathered for this subreddit. Never silently under-report
                # without a trace: a backfill's own caller (`scripts
                # /backfill_reddit.py`) sizes its own `--chunk-days` to
                # avoid this in the normal case, but a real, unusually
                # busy window should still be visible if it happens.
                logger.warning(
                    "Reddit fetch_items exhausted max_pages=%d for r/%s in [%s, %s] — "
                    "this window may hold more comments than were gathered; use a "
                    "narrower window or raise reddit_max_pages_per_fetch",
                    self._max_pages,
                    subreddit,
                    start.isoformat(),
                    end.isoformat(),
                )
        return tuple(items)

    async def fetch(self, start: datetime, end: datetime) -> tuple[RawDataPoint, ...]:
        """`Connector` protocol conformance only — one point per comment
        (using VADER's own compound score), for whichever caller only
        needs the bare protocol. `app.services.reddit_ingest` calls
        `fetch_items` directly instead, to keep a deleted/removed
        comment's own null sentiment intact (mirrors
        `MarketauxConnector.fetch`'s identical reasoning)."""
        items = await self.fetch_items(start, end)
        points: list[RawDataPoint] = []
        for item in items:
            score = score_comment(item.body)
            if score is None:
                continue
            points.append(
                RawDataPoint(
                    timestamp=item.created_utc,
                    value=score,
                    symbol=None,
                    raw_payload=item.raw_payload,
                )
            )
        return tuple(points)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "RedditConnector":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


def _to_item(entry: object, subreddit: str) -> RedditItem | None:
    """Map one raw Arctic Shift comment object to a `RedditItem`.

    Any missing key or unparseable required field is a malformed response,
    not a data point to silently skip — the same posture every connector
    since Fear & Greed takes.
    """
    if not isinstance(entry, dict):
        raise ConnectorAPIError("Malformed Arctic Shift entry: expected an object", detail=entry)
    try:
        reddit_id = str(entry["id"])
        created_utc = datetime.fromtimestamp(float(entry["created_utc"]), tz=UTC)
        body = str(entry.get("body") or "")
        score = int(entry.get("score") or 0)
    except (KeyError, TypeError, ValueError) as exc:
        raise ConnectorAPIError(f"Malformed Arctic Shift entry: {exc}", detail=entry) from exc

    author = entry.get("author")
    permalink = entry.get("permalink")
    return RedditItem(
        reddit_id=reddit_id,
        subreddit=subreddit,
        author=str(author) if isinstance(author, str) else None,
        body=body,
        score=score,
        created_utc=created_utc,
        permalink=str(permalink) if isinstance(permalink, str) else None,
        raw_payload=entry,
    )
