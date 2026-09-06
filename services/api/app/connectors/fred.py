"""The FRED (Federal Reserve Economic Data) connector — the first
connector on this platform that actually requires authentication
(`requires_auth=True`), against the St. Louis Fed's free
`fred/series/observations` API (`docs/architecture/SystemContext.md` § 3).

`FredClient` mirrors `app.connectors.fear_greed.FearGreedClient`'s own
error-typing and bounded-retry conventions (which themselves mirror
`app.integrations.delta.client.DeltaClient`), with an `api_key` query
parameter added to every request and a FRED-specific error envelope
(`{"error_code": ..., "error_message": ...}`, not alternative.me's
`{"metadata": {"error": ...}}` shape).

**Publication lag — the reason `timestamp` is `realtime_start`, never
`date`.** Investigated before writing any feature-lookup code (see
`ARCHITECTURE.md` § "External Data Connectors" → "FRED Connector" for the
full writeup). The chosen series, `FEDFUNDS` (the monthly effective
federal funds rate), is dated by FRED at the *first day of the calendar
month it averages* — e.g. `date: "2026-08-01"` for August's average — but
that average cannot possibly be known until August itself has ended;
FRED's own real-time tracking confirms it is actually published in the
first few days of the *following* month. Using `date` as this connector's
effective timestamp would be a genuine look-ahead bug: a feature "at or
before" a mid-August candle would see August's own average as if it were
already knowable mid-August. FRED's API itself separates this: every
observation carries its own `realtime_start` (the date that exact value
first became — or, on revision, most recently became — publicly known),
distinct from `date` (the economic reference period). This connector uses
`realtime_start` as `RawDataPoint.timestamp`, keeping both fields in
`raw_payload` for audit. FEDFUNDS is documented as rarely revised (small,
sub-basis-point corrections), so most observations carry exactly one real
vintage — but the field is used on principle, not because this specific
series happens to make it unimportant.

**A second, real bug this same investigation caught live, not in
mocked tests.** Every observation's own `realtime_start`/`realtime_end`
only reflect their *true* individual vintage history when the request
itself supplies an explicit, wide `realtime_start`/`realtime_end` range.
Omit them (as an early version of this connector did, verified only
against a *fabricated* mock response) and FRED silently defaults **both**
to today — collapsing every single observation's `realtime_start` onto
today's date, regardless of how long ago it actually became known. Caught
by running the real backfill against the real API (not a mocked test):
only one row landed where hundreds were expected, every one of the
remaining 865 real values discarded as a false in-batch "duplicate
timestamp" by `_persist_points`'s own dedup check — and, worse, every
future sync tick would have kept re-inserting the same already-stored
observations under a new, different "today" timestamp each time, forever.
Fixed by always passing FRED's own documented "as far as possible"
sentinels, `realtime_start=1776-07-04`/`realtime_end=9999-12-31`
(`_REALTIME_START_SENTINEL`/`_REALTIME_END_SENTINEL` below) — which,
combined with the default `output_type=1`, returns exactly one row per
*genuine* vintage (initial publication, plus one row per real later
revision), in the same simple `{date, value, realtime_start,
realtime_end}` shape already parsed here; no parsing changes were needed,
only the two missing parameters. One accepted, harmless edge: ALFRED's
own vintage tracking does not reach back before roughly 1991–1996
(depending on series); an observation older than that reports its
`realtime_start` as whenever ALFRED's own tracking began, not FEDFUNDS's
true 1954-era original publication date — irrelevant in practice, since
no candle on this platform predates 1954 by decades in the other
direction (the earliest real market data is from 2018 onward).

**Why FEDFUNDS, not a finer-grained alternative (e.g. the daily `DFF`
series).** `ROADMAP.md`/`docs/architecture/SystemContext.md` both
characterize FRED's own role on this platform as "macro" — a slow-moving
policy backdrop, not a high-frequency signal the way Fear & Greed's daily
sentiment index is. A monthly average is the right granularity for that
role, and its real, order-of-a-month publication lag is exactly the kind
of correctness problem worth handling properly rather than sidestepping
by picking a series where it would be small enough to ignore.

**Why a full-history fetch, not a range-scoped one.** FRED's own
`observation_start`/`observation_end` parameters filter by `date` (the
reference period), not `realtime_start` (the field this connector
actually cares about) — a date-filtered request for a recent window could
silently miss an older-dated observation that was only just published
(or revised) inside that window. Since FEDFUNDS's entire history back to
July 1954 is under a thousand small JSON objects — the same "cheap enough
to always fetch in full" situation `FearGreedConnector` is already in —
`fetch` always requests the whole history and filters locally on
`realtime_start`, sidestepping any need to estimate a worst-case lag
buffer.
"""

import asyncio
import logging
import random
import time
from datetime import UTC, date, datetime
from typing import Any, ClassVar

import httpx

from app.connectors.base import ConnectorMetadata, RawDataPoint
from app.connectors.errors import (
    ConnectorAPIError,
    ConnectorAuthenticationError,
    ConnectorNetworkError,
    ConnectorRateLimitError,
)
from app.connectors.registry import register_connector
from app.core.config import get_settings

logger = logging.getLogger("app.connectors.fred")

FRED_SOURCE = "fed_funds_rate"
FRED_SERIES_ID = "FEDFUNDS"
FRED_OBSERVATIONS_PATH = "/fred/series/observations"

#: FEDFUNDS's own real start (per its FRED series page: "since July 1954") —
#: used as a fixed, generous `observation_start` so a full-history fetch
#: never has to guess at how far back to look.
_SERIES_START_DATE = date(1954, 7, 1)

#: FRED's own documented "no value yet" sentinel for a period that hasn't
#: closed, or a gap — never `null`, always the literal string ".".
_MISSING_VALUE_SENTINEL = "."

#: FRED's own documented sentinels for "the earliest/latest possible
#: real-time date" (`realtime_start`/`realtime_end` docs). Passed on
#: *every* request — see `fetch_observations`'s own docstring for why
#: this is load-bearing, not cosmetic: omitting them collapses every
#: observation's own `realtime_start` to today's date.
_REALTIME_START_SENTINEL = "1776-07-04"
_REALTIME_END_SENTINEL = "9999-12-31"

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 0.5
_MAX_RETRY_DELAY = 30.0
_USER_AGENT = "eth-ai-platform/0.1.0"


class FredClient:
    """Async HTTP client for the FRED `series/observations` API.

    Same shape as `FearGreedClient`: connection pooling, bounded retries
    with exponential backoff on transient failures, structured logging,
    typed error mapping — with an `api_key` query parameter on every
    request, the one genuinely new thing this client needs.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
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
        self._api_key = api_key if api_key is not None else settings.fred_api_key
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.fred_base_url,
            timeout=httpx.Timeout(
                request_timeout if request_timeout is not None else settings.fred_request_timeout
            ),
            transport=transport,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )

    async def fetch_observations(
        self, series_id: str, *, observation_start: date, observation_end: date
    ) -> list[dict[str, Any]]:
        """Return the raw `observations` array for `series_id`.

        Raises `ConnectorAuthenticationError` immediately, with no network
        call, when no API key is configured — a predictable local failure,
        not one worth a wasted round-trip to learn from the server.

        Always passes explicit `realtime_start`/`realtime_end` spanning
        FRED's own documented "as far as possible" sentinels
        (`1776-07-04`/`9999-12-31`) — **not optional**. Omitting them lets
        both silently default to today, which collapses every observation
        onto a single fake `realtime_start` (today's date) instead of each
        one's own real vintage history; verified live against the real API
        and caught before shipping — see this module's own docstring for
        the full account.
        """
        if not self._api_key:
            raise ConnectorAuthenticationError(
                "FRED API key is not configured (FRED_API_KEY) — register a free key at "
                "https://fred.stlouisfed.org/docs/api/api_key.html"
            )

        payload = await self._execute(
            "GET",
            FRED_OBSERVATIONS_PATH,
            params={
                "series_id": series_id,
                "api_key": self._api_key,
                "file_type": "json",
                "observation_start": observation_start.isoformat(),
                "observation_end": observation_end.isoformat(),
                "realtime_start": _REALTIME_START_SENTINEL,
                "realtime_end": _REALTIME_END_SENTINEL,
            },
        )
        if not isinstance(payload, dict):
            raise ConnectorAPIError(
                "Malformed FRED response: expected an object envelope", detail=payload
            )
        observations = payload.get("observations")
        if not isinstance(observations, list):
            raise ConnectorAPIError(
                "Malformed FRED response: missing or non-list 'observations' field",
                detail=payload,
            )
        return observations

    async def aclose(self) -> None:
        """Close the underlying httpx client, releasing pooled connections."""
        await self._client.aclose()

    async def __aenter__(self) -> "FredClient":
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
                    "FRED %s %s timed out on attempt %d (%.1fms)",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                )
                if attempt >= self._max_retries:
                    raise ConnectorNetworkError(
                        f"FRED request timed out: {method} {path}", detail=str(exc)
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue
            except httpx.TransportError as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "FRED %s %s transport error on attempt %d (%.1fms): %s",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                    exc,
                )
                if attempt >= self._max_retries:
                    raise ConnectorNetworkError(
                        f"FRED network failure for {method} {path}: {exc}", detail=str(exc)
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue

            latency_ms = (time.perf_counter() - started) * 1000
            status = response.status_code
            logger.info("FRED %s %s -> %d (%.1fms)", method, path, status, latency_ms)

            if status in RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                delay = self._retry_delay(status, response, attempt)
                logger.warning(
                    "FRED retrying %s %s after %d in %.2fs (attempt %d/%d)",
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
        """Map an HTTP response to a decoded body or a typed exception."""
        status = response.status_code
        if status == 429:
            raise ConnectorRateLimitError(
                f"FRED rate limit exceeded for {method} {path}",
                retry_after=self._parse_retry_after(response),
                status_code=status,
            )
        payload = self._json_payload(response)
        if payload is None:
            raise ConnectorAPIError(
                f"Malformed FRED response for {method} {path}: body is not valid JSON",
                status_code=status,
            )
        if status >= 400:
            error_message = ""
            if isinstance(payload, dict):
                error_message = str(payload.get("error_message", ""))
            # FRED reports a bad/missing/unregistered api_key as a plain
            # HTTP 400 sharing the same status as every other bad-request
            # case — the descriptive `error_message` text is the only way
            # to tell the two apart (verified against FRED's own API docs).
            if status == 400 and "api_key" in error_message.lower():
                raise ConnectorAuthenticationError(
                    f"FRED authentication failed for {method} {path}: {error_message}",
                    status_code=status,
                    detail=payload,
                )
            raise ConnectorAPIError(
                f"FRED request failed with HTTP {status} for {method} {path}: {error_message}",
                status_code=status,
                detail=payload,
            )
        return payload

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")
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


def get_fred_client(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    request_timeout: float | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
) -> FredClient:
    """Return a configured FRED client, defaulting from settings."""
    return FredClient(
        base_url=base_url,
        api_key=api_key,
        request_timeout=request_timeout,
        transport=transport,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
    )


@register_connector
class FredConnector:
    """Adapts `FredClient` to the `Connector` protocol.

    Holds its own client (built fresh per instance, same reasoning as
    `FearGreedConnector`); `aclose()` releases it, and the class supports
    `async with` for the same "use once, then close" case
    ingestion/backfill both need.
    """

    metadata: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        source=FRED_SOURCE,
        label="Federal Funds Rate",
        description=(
            "The monthly effective federal funds rate (FRED series FEDFUNDS), "
            "published by the Federal Reserve Bank of St. Louis — a macro policy "
            "backdrop, not a high-frequency signal. Requires a free FRED API key. "
            "Each value is timestamped by its own real-world publication date "
            "(FRED's own realtime_start), not the calendar month it describes: "
            "August's own average, for instance, is not actually known until "
            "early September."
        ),
        frequency="monthly",
        requires_auth=True,
        version="1.0.0",
        aliases=("fedfunds", "fed_funds", "interest_rate", "federal_funds_rate"),
    )

    def __init__(self, *, client: FredClient | None = None) -> None:
        self._client = client or get_fred_client()

    async def fetch(self, start: datetime, end: datetime) -> tuple[RawDataPoint, ...]:
        """Fetch every recorded value whose own publication date
        (`realtime_start`) falls in `[start, end]` (inclusive both ends).

        Always requests FEDFUNDS's entire history (see this module's own
        docstring for why) and filters to the actual requested window
        locally, on `realtime_start` — never on FRED's own `date` field,
        which would silently reintroduce the look-ahead bug this
        connector exists to avoid.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware datetimes")
        if end < start:
            raise ValueError("end must not be before start")

        entries = await self._client.fetch_observations(
            FRED_SERIES_ID,
            observation_start=_SERIES_START_DATE,
            observation_end=end.date(),
        )
        points = [point for point in (_to_point(entry) for entry in entries) if point is not None]
        return tuple(point for point in points if start <= point.timestamp <= end)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "FredConnector":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


def _to_point(entry: object) -> RawDataPoint | None:
    """Map one raw FRED observation to a `RawDataPoint`, or `None` to skip
    a documented "not available" observation (FRED's own literal `"."`
    value sentinel — never a data point to fabricate as zero).

    `timestamp` is the observation's own `realtime_start` (this module's
    own docstring explains why, never `date`). Any other missing key or
    unparseable value is a malformed response, not a point to silently
    skip.
    """
    if not isinstance(entry, dict):
        raise ConnectorAPIError("Malformed FRED entry: expected an object", detail=entry)
    try:
        raw_value = entry["value"]
        if raw_value == _MISSING_VALUE_SENTINEL:
            return None
        value = float(raw_value)
        timestamp = datetime.strptime(entry["realtime_start"], "%Y-%m-%d").replace(tzinfo=UTC)
    except (KeyError, TypeError, ValueError) as exc:
        raise ConnectorAPIError(f"Malformed FRED entry: {exc}", detail=entry) from exc
    return RawDataPoint(timestamp=timestamp, value=value, symbol=None, raw_payload=entry)
