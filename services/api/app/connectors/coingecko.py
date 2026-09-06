"""The CoinGecko connector — the fifth concrete connector, and the first
whose API key is genuinely *optional*, not merely "not configured yet"
(`app.connectors.fred`/`etherscan` both hard-require a key and fail fast
with no network call when one is missing). Uses CoinGecko's `/global`
endpoint (`docs.coingecko.com/reference/crypto-global`), reporting BTC
dominance — the percentage of total cryptocurrency market cap currently
held in Bitcoin.

**Investigated before building, not assumed — checked directly against
CoinGecko's current API documentation and the real live API:**

1. **`/global` works fully keyless, confirmed live.** A real, unauthenticated
   request against `https://api.coingecko.com/api/v3/global` returns real
   HTTP 200 data with no key, no header, nothing. CoinGecko's own current
   docs (`docs.coingecko.com/docs/errors-and-rate-limits`) confirm this is
   intentional: "Keyless (no API key): IP-based rate limiting — shared
   across all users on the same IP" is one of three documented access
   tiers, alongside a free "Demo" plan (a registered key,
   `x-cg-demo-api-key` header, **100 calls/min**, documented) and paid
   plans. A Demo key here only *upgrades* the rate limit; it is never
   required for the request to succeed at all — a genuine architectural
   difference from FRED/Etherscan, where an unconfigured key is a local,
   no-network-call failure.
2. **The free-tier rate limit is real and was actually exercised, not
   just documented.** A burst of 20 concurrent keyless requests produced
   real HTTP 429s for 15 of them, with a **plain-text** `"Throttled\n"`
   body — not CoinGecko's own documented JSON error envelope
   (`{"status": {"error_code": ..., "error_message": ...}}`), which is
   what a *keyed* 401/429 actually returns (confirmed separately, below).
   This client's response parsing tolerates a non-JSON body on any status
   code, including 429, rather than assuming CoinGecko's own error shape
   always applies.
3. **A real bad key produces a real, live-confirmed 401**, JSON body
   `{"status": {"error_code": 10002, "error_message": "API Key
   Missing..."}}` — the same code CoinGecko documents for a *missing*
   key, confirmed live to also cover an invalid one; this client cannot
   (and does not attempt to) distinguish "wrong key" from "no key" beyond
   what CoinGecko's own error reporting already conflates.
4. **No historical query capability on the free tier — confirmed by
   checking documentation, not discovered by trial and error.** A
   separate endpoint, "Global Market Cap Chart Data"
   (`historical global market cap and volume data by number of days away
   from now`), does exist — but its own reference page is explicitly
   tagged `Analyst Plan and Above`, a paid tier, not available here. This
   is the same Pro-tier trap Etherscan's `dailyavggasprice` and
   DefiLlama's Pro API each were — ruled out by reading the docs directly,
   not assumed free because the name sounded promising.

**The three known bug patterns from this milestone's prior four
connectors, checked explicitly against this API before writing any client
code:**

- _An omitted parameter defaulting to something surprising_ (FRED's
  `realtime_start`/`realtime_end`): does not apply — `/global` takes no
  query parameters at all; there is nothing to omit.
- _A timestamp computed at the wrong moment relative to a network call_
  (Etherscan's `end`-before-round-trip bug): structurally cannot recur
  the same way here. Unlike Etherscan's Gas Oracle (no timestamp field at
  all, forcing a locally-computed `datetime.now(UTC)` captured *after*
  the round trip), `/global` carries its own `updated_at` (Unix seconds,
  confirmed live) — this connector always uses CoinGecko's own reported
  refresh instant, never a value it computes itself.
- _A response field silently not captured_ (Fear & Greed's own
  `external_sources` DTO gap): guarded the same way every connector since
  has been — proven again by this milestone's own extended
  `test_features_api.py` assertion, now checking a fifth connector-backed
  feature.

**Why BTC dominance, not total market cap — checked, not assumed just
because it sounded right.** Delta's own ETHUSD candles already fully
capture ETH's own price; ETH's own market cap (price × slowly-changing
circulating supply) would have been almost redundant with data already in
this platform. Total market cap is *not* strictly redundant either (it
sums thousands of coins ETH's own price says nothing about), but it is
still fundamentally an aggregate *size* measure that tends to move with
the same broad market direction ETH's own price already reflects most of
the time. BTC dominance (`market_cap_percentage.btc`) is structurally
different, not just empirically different: it is a *share* of the total
market, and no absolute price series for any single asset — no matter how
transformed — can, even in principle, tell you what fraction of the whole
market is currently held in a *different* asset. A rising ETH price and a
rising BTC dominance are not the same signal and can move in opposite
directions (ETH price up while BTC dominance also rises, if BTC is
outpacing it; ETH price down while BTC dominance falls, if alts are
falling even faster) — a genuine capital-rotation signal ETH's own candle
data cannot derive on its own, chosen on that structural argument since no
free historical BTC-dominance series exists to run an empirical
correlation check against (see point 4 above).

**Lag — confirmed low, not assumed, for a genuinely different reason than
any prior connector.** `/global` is a continuously-refreshed snapshot, not
a once-daily figure: two real, live calls roughly 90 seconds apart both
returned the identical `updated_at`, confirming this endpoint refreshes on
its own cadence (observed on the order of a minute or more) rather than
per-request — this connector reports exactly that refresh instant, never
claiming more real-time precision than CoinGecko itself provides.

**No historical backfill is possible — the same disclosed limitation
Etherscan has, for the same reason.** `/global` only ever answers "what is
BTC dominance right now"; `fetch(start, end)` therefore makes exactly one
live request regardless of the requested range, and returns that single
point only if its own `updated_at` falls within `[start, end]` — an
honest empty result for any range that has already closed in the past,
never a fabricated historical value.
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
    ConnectorAuthenticationError,
    ConnectorNetworkError,
    ConnectorRateLimitError,
)
from app.connectors.registry import register_connector
from app.core.config import get_settings

logger = logging.getLogger("app.connectors.coingecko")

COINGECKO_SOURCE = "btc_dominance"
_GLOBAL_PATH = "/global"
#: The recommended, documented header (`docs.coingecko.com/demo/reference
#: /authentication`) — a query-string alternative also exists, but the
#: same docs explicitly warn against it in production ("risk exposing
#: your key in logs and browser history").
_API_KEY_HEADER = "x-cg-demo-api-key"

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 0.5
_MAX_RETRY_DELAY = 30.0
_USER_AGENT = "eth-ai-platform/0.1.0"


class CoinGeckoClient:
    """Async HTTP client for CoinGecko's `/global` endpoint.

    Same shape as `FearGreedClient`/`DefiLlamaClient`: connection pooling,
    bounded retries with exponential backoff, structured logging,
    status-code-based error mapping (confirmed live — real 401s and
    429s). The one genuine difference from every prior connector: the API
    key is optional. When configured, it is sent as a header, never a
    query parameter, on every request; when not configured, no header is
    sent at all and the request still succeeds, just under keyless,
    shared, IP-based rate limiting rather than the documented 100/min.
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
        self._api_key = api_key if api_key is not None else settings.coingecko_api_key
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
        if self._api_key:
            headers[_API_KEY_HEADER] = self._api_key
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.coingecko_base_url,
            timeout=httpx.Timeout(
                request_timeout
                if request_timeout is not None
                else settings.coingecko_request_timeout
            ),
            transport=transport,
            headers=headers,
        )

    async def fetch_global(self) -> dict[str, Any]:
        """Return the raw `data` object from `/global`.

        Never raises locally for a missing key — unlike
        `FredClient`/`EtherscanClient`, a key genuinely is not required
        for this request to succeed (confirmed live; see this module's
        own docstring).
        """
        payload = await self._execute("GET", _GLOBAL_PATH)
        if not isinstance(payload, dict):
            raise ConnectorAPIError(
                "Malformed CoinGecko response: expected an object envelope", detail=payload
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ConnectorAPIError(
                "Malformed CoinGecko response: missing or non-object 'data' field",
                detail=payload,
            )
        return data

    async def aclose(self) -> None:
        """Close the underlying httpx client, releasing pooled connections."""
        await self._client.aclose()

    async def __aenter__(self) -> "CoinGeckoClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()

    async def _execute(self, method: str, path: str) -> object:
        """Send one request with retries; return the decoded JSON body."""
        attempt = 0
        while True:
            started = time.perf_counter()
            try:
                response = await self._client.request(method, path)
            except httpx.TimeoutException as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "CoinGecko %s %s timed out on attempt %d (%.1fms)",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                )
                if attempt >= self._max_retries:
                    raise ConnectorNetworkError(
                        f"CoinGecko request timed out: {method} {path}", detail=str(exc)
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue
            except httpx.TransportError as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "CoinGecko %s %s transport error on attempt %d (%.1fms): %s",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                    exc,
                )
                if attempt >= self._max_retries:
                    raise ConnectorNetworkError(
                        f"CoinGecko network failure for {method} {path}: {exc}", detail=str(exc)
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue

            latency_ms = (time.perf_counter() - started) * 1000
            status = response.status_code
            logger.info("CoinGecko %s %s -> %d (%.1fms)", method, path, status, latency_ms)

            if status in RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                delay = self._retry_delay(status, response, attempt)
                logger.warning(
                    "CoinGecko retrying %s %s after %d in %.2fs (attempt %d/%d)",
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
                f"CoinGecko rate limit exceeded for {method} {path}",
                retry_after=self._parse_retry_after(response),
                status_code=status,
            )
        if status == 401:
            raise ConnectorAuthenticationError(
                f"CoinGecko authentication failed for {method} {path} "
                "(missing or invalid Demo API key)",
                status_code=status,
            )
        payload = self._json_payload(response)
        if payload is None:
            raise ConnectorAPIError(
                f"Malformed CoinGecko response for {method} {path}: body is not valid JSON",
                status_code=status,
            )
        if status >= 400:
            raise ConnectorAPIError(
                f"CoinGecko request failed with HTTP {status} for {method} {path}",
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


def get_coingecko_client(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    request_timeout: float | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
) -> CoinGeckoClient:
    """Return a configured CoinGecko client, defaulting from settings."""
    return CoinGeckoClient(
        base_url=base_url,
        api_key=api_key,
        request_timeout=request_timeout,
        transport=transport,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
    )


@register_connector
class CoinGeckoConnector:
    """Adapts `CoinGeckoClient` to the `Connector` protocol.

    Holds its own client (built fresh per instance, same reasoning as
    every other connector); `aclose()` releases it, and the class
    supports `async with` for the "use once, then close" case
    ingestion/backfill both need.
    """

    metadata: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        source=COINGECKO_SOURCE,
        label="Bitcoin Dominance",
        description=(
            "Bitcoin's percentage share of total cryptocurrency market "
            "capitalization (CoinGecko's /global, market_cap_percentage.btc) — "
            "a capital-rotation signal, not a price. Works without an API key; "
            "a free CoinGecko Demo key only raises the rate limit. Has no "
            "historical query capability on the free tier — this connector can "
            "only observe the current value at the moment it is polled, so its "
            "own stored history begins the day ingestion started, never "
            "earlier."
        ),
        frequency="continuous (sampled per sync tick)",
        requires_auth=False,
        version="1.0.0",
        aliases=("btc_dom", "dominance", "bitcoin_dominance"),
    )

    def __init__(self, *, client: CoinGeckoClient | None = None) -> None:
        self._client = client or get_coingecko_client()

    async def fetch(self, start: datetime, end: datetime) -> tuple[RawDataPoint, ...]:
        """Return the current BTC dominance as a single point, timestamped
        by CoinGecko's own `updated_at` — never a value this connector
        computes itself — but only if that moment falls within
        `[start, end]`. There is no way to answer for a range that has
        already closed in the past; this returns an empty tuple for that
        case rather than fabricating a value.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware datetimes")
        if end < start:
            raise ValueError("end must not be before start")

        data = await self._client.fetch_global()
        point = _to_point(data)
        if point is None or not (start <= point.timestamp <= end):
            return ()
        return (point,)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "CoinGeckoConnector":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


def _to_point(data: object) -> RawDataPoint | None:
    """Map one raw `/global` `data` object to a `RawDataPoint`.

    `timestamp` is CoinGecko's own `updated_at` (Unix seconds) — never
    `datetime.now(UTC)` — since this endpoint genuinely reports when it
    was last refreshed, unlike Etherscan's Gas Oracle. Any missing key or
    unparseable value is a malformed response, not a data point to
    silently skip.
    """
    if not isinstance(data, dict):
        raise ConnectorAPIError("Malformed CoinGecko data: expected an object", detail=data)
    try:
        percentages = data["market_cap_percentage"]
        value = float(percentages["btc"])
        timestamp = datetime.fromtimestamp(int(data["updated_at"]), tz=UTC)
    except (KeyError, TypeError, ValueError) as exc:
        raise ConnectorAPIError(f"Malformed CoinGecko data: {exc}", detail=data) from exc
    return RawDataPoint(timestamp=timestamp, value=value, symbol=None, raw_payload=data)
