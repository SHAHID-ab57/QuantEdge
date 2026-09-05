"""The Fear & Greed Index connector — the first concrete connector built on
top of `app.connectors.base`'s `Connector` protocol, and deliberately the
lowest-risk possible first case: no authentication, one value per day,
against alternative.me's free, public API
(`docs/architecture/SystemContext.md` § 3).

`FearGreedClient` mirrors `app.integrations.delta.client.DeltaClient`'s own
error-typing and bounded-retry conventions (`ConnectorNetworkError`/
`ConnectorAPIError`/`ConnectorRateLimitError`, exponential backoff on
transient failures) with everything Delta-specific removed: no HMAC
request signing, no `api-key`/`api-secret`, no request envelope with a
`success` flag — alternative.me's own response shape is a plain
`{"name": ..., "data": [...], "metadata": {"error": ...}}` object.

**Why a full-history fetch, not a paginated one.** alternative.me's API
has no `start`/`end` query parameters at all — only `limit` (the most
recent N entries) and `format`. `FearGreedConnector.fetch` translates the
requested `[start, end]` range into a bounded `limit` (proportional to
the range's own span in days, capped generously) and filters the
response to that window locally. The whole index's history to date is a
few thousand small JSON objects — cheap enough to fetch in one request
even for a full backfill; a periodic daily sync tick naturally computes
a small `limit` instead, since its own requested range is only a day or
two wide.
"""

import asyncio
import logging
import random
import time
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from app.connectors.base import ConnectorMetadata, RawDataPoint
from app.connectors.errors import (
    ConnectorAPIError,
    ConnectorNetworkError,
    ConnectorRateLimitError,
)
from app.connectors.registry import register_connector
from app.core.config import get_settings

logger = logging.getLogger("app.connectors.fear_greed")

FEAR_GREED_SOURCE = "fear_greed"
FEAR_GREED_PATH = "/fng/"

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 0.5
_MAX_RETRY_DELAY = 30.0
_USER_AGENT = "eth-ai-platform/0.1.0"

#: alternative.me's own sentinel for "every data point it has" — used
#: whenever a requested range would otherwise need a larger limit than
#: the index's entire history could ever contain.
_FULL_HISTORY_LIMIT = 0
#: A generous ceiling on how many days a single request will ever ask
#: for by *count* rather than the full-history sentinel above — covers
#: several years without the request growing unbounded for a pathological
#: `start` far in the future of `end` (rejected before this matters) or a
#: `start` far in the past (correctly reads as "give me everything").
_MAX_LOOKBACK_DAYS = 4000


class FearGreedClient:
    """Async HTTP client for alternative.me's Fear & Greed Index API.

    Unauthenticated, single-endpoint, but otherwise the same shape as
    `DeltaClient`: connection pooling, bounded retries with exponential
    backoff on transient failures, structured logging, typed error
    mapping. No business logic or persistence lives here.
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
            base_url=base_url or settings.fear_greed_base_url,
            timeout=httpx.Timeout(
                request_timeout
                if request_timeout is not None
                else settings.fear_greed_request_timeout
            ),
            transport=transport,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )

    async def fetch_history(self, *, limit: int) -> list[dict[str, Any]]:
        """Return the raw `data` array — most recent entry first, per the
        API's own documented order. `limit=0` means "every entry the
        index has ever recorded" (alternative.me's own sentinel)."""
        payload = await self._execute(
            "GET", FEAR_GREED_PATH, params={"limit": limit, "format": "json"}
        )
        if not isinstance(payload, dict):
            raise ConnectorAPIError(
                "Malformed Fear & Greed response: expected an object envelope", detail=payload
            )
        metadata = payload.get("metadata")
        if isinstance(metadata, dict) and metadata.get("error"):
            raise ConnectorAPIError(f"Fear & Greed API error: {metadata['error']}", detail=payload)
        data = payload.get("data")
        if not isinstance(data, list):
            raise ConnectorAPIError(
                "Malformed Fear & Greed response: missing or non-list 'data' field",
                detail=payload,
            )
        return data

    async def aclose(self) -> None:
        """Close the underlying httpx client, releasing pooled connections."""
        await self._client.aclose()

    async def __aenter__(self) -> "FearGreedClient":
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
                    "Fear & Greed %s %s timed out on attempt %d (%.1fms)",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                )
                if attempt >= self._max_retries:
                    raise ConnectorNetworkError(
                        f"Fear & Greed request timed out: {method} {path}", detail=str(exc)
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue
            except httpx.TransportError as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "Fear & Greed %s %s transport error on attempt %d (%.1fms): %s",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                    exc,
                )
                if attempt >= self._max_retries:
                    raise ConnectorNetworkError(
                        f"Fear & Greed network failure for {method} {path}: {exc}", detail=str(exc)
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue

            latency_ms = (time.perf_counter() - started) * 1000
            status = response.status_code
            logger.info("Fear & Greed %s %s -> %d (%.1fms)", method, path, status, latency_ms)

            if status in RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                delay = self._retry_delay(status, response, attempt)
                logger.warning(
                    "Fear & Greed retrying %s %s after %d in %.2fs (attempt %d/%d)",
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
                f"Fear & Greed rate limit exceeded for {method} {path}",
                retry_after=self._parse_retry_after(response),
                status_code=status,
            )
        payload = self._json_payload(response)
        if payload is None:
            raise ConnectorAPIError(
                f"Malformed Fear & Greed response for {method} {path}: body is not valid JSON",
                status_code=status,
            )
        if status >= 400:
            raise ConnectorAPIError(
                f"Fear & Greed request failed with HTTP {status} for {method} {path}",
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


def get_fear_greed_client(
    *,
    base_url: str | None = None,
    request_timeout: float | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
) -> FearGreedClient:
    """Return a configured Fear & Greed client, defaulting from settings."""
    return FearGreedClient(
        base_url=base_url,
        request_timeout=request_timeout,
        transport=transport,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
    )


@register_connector
class FearGreedConnector:
    """Adapts `FearGreedClient` to the `Connector` protocol.

    Holds its own client (built fresh per instance — see
    `ConnectorRegistry`'s own docstring for why the registry never shares
    one instance across callers); `aclose()` releases it, and the class
    also supports `async with` for the common "use once, then close" case
    ingestion/backfill both need.
    """

    metadata: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        source=FEAR_GREED_SOURCE,
        label="Fear & Greed Index",
        description=(
            "A daily sentiment index (0-100: 'Extreme Fear' to 'Extreme Greed') "
            "aggregating market volatility, momentum, social media, dominance, and "
            "trends, published by alternative.me. Free and unauthenticated."
        ),
        frequency="daily",
        requires_auth=False,
        version="1.0.0",
        aliases=("fng", "fear-and-greed"),
    )

    def __init__(self, *, client: FearGreedClient | None = None) -> None:
        self._client = client or get_fear_greed_client()

    async def fetch(self, start: datetime, end: datetime) -> tuple[RawDataPoint, ...]:
        """Fetch every recorded value in `[start, end]` (inclusive both ends).

        Translates the requested range into a bounded `limit` (alternative.me
        has no `start`/`end` query parameters of its own) and filters the
        response to the actual requested window — see this module's own
        docstring for why fetching more than requested and filtering
        locally is the right trade-off here.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware datetimes")
        if end < start:
            raise ValueError("end must not be before start")

        span_days = (end.date() - start.date()).days + 2
        limit = _FULL_HISTORY_LIMIT if span_days >= _MAX_LOOKBACK_DAYS else span_days

        entries = await self._client.fetch_history(limit=limit)
        points = [_to_point(entry) for entry in entries]
        return tuple(point for point in points if start <= point.timestamp <= end)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "FearGreedConnector":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


def _to_point(entry: object) -> RawDataPoint:
    """Map one raw alternative.me record to a `RawDataPoint`.

    Both `value` and `timestamp` arrive as JSON *strings* (not numbers) —
    verified against the real API — so both are explicitly parsed here,
    never assumed to already be numeric. Any missing key or unparseable
    value is a malformed response, not a data point to silently skip.
    """
    if not isinstance(entry, dict):
        raise ConnectorAPIError("Malformed Fear & Greed entry: expected an object", detail=entry)
    try:
        value = float(entry["value"])
        timestamp = datetime.fromtimestamp(int(entry["timestamp"]), tz=UTC)
    except (KeyError, TypeError, ValueError) as exc:
        raise ConnectorAPIError(f"Malformed Fear & Greed entry: {exc}", detail=entry) from exc
    return RawDataPoint(timestamp=timestamp, value=value, symbol=None, raw_payload=entry)
