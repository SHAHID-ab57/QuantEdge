"""The DefiLlama connector — the fourth concrete connector, and the first
requiring no authentication at all (confirmed live, not assumed from
history — DefiLlama's own current docs describe a completely separate,
optional Pro tier for extra endpoints and higher rate limits; the TVL
endpoint used here needs neither).

**Investigated before building, not assumed — checked directly against
DefiLlama's own current API documentation and the real live API:**

1. **No API key required.** DefiLlama's own docs (`api-docs.defillama.com`)
   describe two entirely separate services: the free API
   (`api.llama.fi`, no auth) and a $300/month Pro API
   (`pro-api.llama.fi/{KEY}`, a different base URL and 38 extra
   endpoints). `v2/historicalChainTvl/{chain}` — the endpoint this
   connector uses — is explicitly listed under the free API; confirmed
   live with a plain, unauthenticated request.
2. **No documented numeric rate limit.** DefiLlama's own docs describe the
   free tier's limit only as "Standard" (vs. Pro's "Higher"), unlike
   Etherscan's explicit "3/sec, 100k/day." Checked empirically rather than
   left unverified: 15 concurrent real requests all succeeded (HTTP 200),
   in contrast to Etherscan's own real rate-limit responses at just 10
   concurrent requests. This client still retries on 429/5xx defensively,
   the same shape as every other connector, in case a real limit exists
   under heavier load than tested here.
3. **Real HTTP status codes carry real errors.** Unlike Etherscan (always
   HTTP 200, errors only in the JSON body), an unknown chain slug returns
   a genuine HTTP 404 (plain nginx HTML, not even DefiLlama's own JSON),
   confirmed live. This client's error handling is status-code-based, the
   same shape as `FearGreedClient`/`FredClient`, not Etherscan's
   body-content dispatch.

**The three known bug patterns from this milestone's prior connectors,
checked explicitly against this API before writing any client code:**

- *Omitted parameter defaulting to something surprising* (FRED's
  `realtime_start`/`realtime_end`): does not apply here —
  `v2/historicalChainTvl/{chain}` takes no query parameters at all beyond
  the chain itself; there is nothing to omit.
- *A timestamp computed at the wrong moment relative to the network call*
  (Etherscan's `end`-before-round-trip bug): does not apply here either —
  every entry carries its own `date` field from the response body itself;
  this connector never calls `datetime.now()` to invent a timestamp.
- *A response field silently not captured* (Fear & Greed's own
  `external_sources` DTO gap): guarded the same way every connector since
  has been — this connector's feature
  (`app.features.builtin.defillama_eth_tvl`) and its own test coverage
  follow the now three-times-proven registration pattern exactly.

**A real, live-confirmed revision risk, genuinely new to this connector —
see `ConnectorMetadata.revisable`'s own docstring for the mechanical
fix.** DefiLlama's docs make no explicit promise that a historical TVL
figure, once published, never changes — and a direct live comparison
found concrete evidence that it does, at least for an in-progress day: at
2026-09-06T13:58Z, `v2/chains`'s own *current* Ethereum TVL read
~49.62B, while `v2/historicalChainTvl/Ethereum`'s own *most recent* entry
for that same calendar day (`date` at 2026-09-06T00:00Z) read ~49.53B —
a ~0.18% difference between "current" and "today's own historical
entry," for the same day, at the same moment. Today's entry is still
settling; there is no documented guarantee any other date could not, in
principle, be corrected later too.

Decision: this source is registered `revisable=True` — an already-stored
point is overwritten, not silently skipped, when a later fetch reports a
genuinely different value for the same date (see
`app.services.external_data_ingest`'s own `updated` handling). This is
deliberately *not* narrowed to "only revise the last N days": no such
window is documented or evidenced, and inventing an unverified number
would repeat the exact mistake this investigation was meant to avoid. In
practice, only whatever window a given sync tick actually requests is
ever re-checked — `ExternalDataSyncScheduler`'s own "resume from the last
stored timestamp" convention means a routine tick only re-examines the
single most recent stored date (see
`app.services.external_data_sync._catch_up_window`); a deep historical
revision, if one is ever suspected, needs an explicit wide manual
backfill to actually re-verify.

**Why the Ethereum chain TVL, not a protocol-level or all-chains
metric.** `v2/chains` gives only *current* TVL for every chain — no
history, unusable as a time-series feature. `/protocol/{protocol}` needs
picking one specific protocol, a far more arbitrary choice than "the
chain itself" for a platform whose own focus is Ethereum broadly, not any
one DeFi application. `v2/historicalChainTvl/Ethereum` is DefiLlama's own
directly-relevant, free, unauthenticated, full-history answer to "how
much value is locked in DeFi on Ethereum, over time" — the metric the
task itself named as the default candidate.

**Why a full-history fetch every time, not a narrower request.** There is
no parameter to narrow it by even if this connector wanted to — the
endpoint always returns its entire history (currently ~3,267 daily
entries, ~120KB) regardless of any query string. `fetch` always requests
the whole array and filters locally to `[start, end]`, the same
trade-off `FearGreedConnector.fetch` already makes, with even less to
compute (no `limit` translation needed at all).
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

logger = logging.getLogger("app.connectors.defillama")

DEFILLAMA_SOURCE = "eth_tvl"

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 0.5
_MAX_RETRY_DELAY = 30.0
_USER_AGENT = "eth-ai-platform/0.1.0"


class DefiLlamaClient:
    """Async HTTP client for DefiLlama's free v2 historical chain TVL API.

    Same shape as `FearGreedClient`: connection pooling, bounded retries
    with exponential backoff, structured logging, status-code-based error
    mapping (confirmed live — see this module's own docstring for why,
    unlike Etherscan). No authentication at all: no key, no header, no
    query parameter.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        chain: str | None = None,
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
        self._chain = chain if chain is not None else settings.defillama_chain
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.defillama_base_url,
            timeout=httpx.Timeout(
                request_timeout
                if request_timeout is not None
                else settings.defillama_request_timeout
            ),
            transport=transport,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )

    async def fetch_history(self) -> list[dict[str, Any]]:
        """Return the raw `[{date, tvl}, ...]` array — DefiLlama's entire
        recorded history for the configured chain, oldest first (its own
        documented order, confirmed live)."""
        payload = await self._execute("GET", f"/v2/historicalChainTvl/{self._chain}")
        if not isinstance(payload, list):
            raise ConnectorAPIError("Malformed DefiLlama response: expected a list", detail=payload)
        return payload

    async def aclose(self) -> None:
        """Close the underlying httpx client, releasing pooled connections."""
        await self._client.aclose()

    async def __aenter__(self) -> "DefiLlamaClient":
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
                    "DefiLlama %s %s timed out on attempt %d (%.1fms)",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                )
                if attempt >= self._max_retries:
                    raise ConnectorNetworkError(
                        f"DefiLlama request timed out: {method} {path}", detail=str(exc)
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue
            except httpx.TransportError as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "DefiLlama %s %s transport error on attempt %d (%.1fms): %s",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                    exc,
                )
                if attempt >= self._max_retries:
                    raise ConnectorNetworkError(
                        f"DefiLlama network failure for {method} {path}: {exc}", detail=str(exc)
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue

            latency_ms = (time.perf_counter() - started) * 1000
            status = response.status_code
            logger.info("DefiLlama %s %s -> %d (%.1fms)", method, path, status, latency_ms)

            if status in RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                delay = self._retry_delay(status, response, attempt)
                logger.warning(
                    "DefiLlama retrying %s %s after %d in %.2fs (attempt %d/%d)",
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
                f"DefiLlama rate limit exceeded for {method} {path}",
                retry_after=self._parse_retry_after(response),
                status_code=status,
            )
        if status == 404:
            raise ConnectorAPIError(
                f"DefiLlama request failed with HTTP 404 for {method} {path} (unknown chain?)",
                status_code=status,
            )
        payload = self._json_payload(response)
        if payload is None:
            raise ConnectorAPIError(
                f"Malformed DefiLlama response for {method} {path}: body is not valid JSON",
                status_code=status,
            )
        if status >= 400:
            raise ConnectorAPIError(
                f"DefiLlama request failed with HTTP {status} for {method} {path}",
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


def get_defillama_client(
    *,
    base_url: str | None = None,
    chain: str | None = None,
    request_timeout: float | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
) -> DefiLlamaClient:
    """Return a configured DefiLlama client, defaulting from settings."""
    return DefiLlamaClient(
        base_url=base_url,
        chain=chain,
        request_timeout=request_timeout,
        transport=transport,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
    )


@register_connector
class DefiLlamaConnector:
    """Adapts `DefiLlamaClient` to the `Connector` protocol.

    Holds its own client (built fresh per instance, same reasoning as
    every other connector); `aclose()` releases it, and the class supports
    `async with` for the "use once, then close" case ingestion/backfill
    both need.
    """

    metadata: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        source=DEFILLAMA_SOURCE,
        label="Ethereum Chain TVL",
        description=(
            "Total value locked in DeFi on the Ethereum mainnet (DefiLlama's "
            "v2/historicalChainTvl, excludes liquid staking and double-counted "
            "TVL), in USD. Free and unauthenticated. DefiLlama does not "
            "guarantee a published figure is final — see this connector's own "
            "module docstring — so an already-stored value may later be "
            "overwritten if a re-fetch reports a genuine revision."
        ),
        frequency="daily (most recent day may still be settling)",
        requires_auth=False,
        version="1.0.0",
        aliases=("tvl", "defillama", "chain_tvl"),
        revisable=True,
    )

    def __init__(self, *, client: DefiLlamaClient | None = None) -> None:
        self._client = client or get_defillama_client()

    async def fetch(self, start: datetime, end: datetime) -> tuple[RawDataPoint, ...]:
        """Fetch every recorded value in `[start, end]` (inclusive both ends).

        DefiLlama's own endpoint takes no query parameters at all — every
        call returns the *entire* history, always; there is no `limit` or
        date filter to compute (unlike `FearGreedConnector.fetch`). This
        method always requests everything and filters locally, the same
        trade-off applied with even less to get wrong.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware datetimes")
        if end < start:
            raise ValueError("end must not be before start")

        entries = await self._client.fetch_history()
        points = [_to_point(entry) for entry in entries]
        return tuple(point for point in points if start <= point.timestamp <= end)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "DefiLlamaConnector":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


def _to_point(entry: object) -> RawDataPoint:
    """Map one raw `{date, tvl}` record to a `RawDataPoint`.

    `date` is a Unix timestamp in seconds (verified live — not
    milliseconds, and not an ISO string); `tvl` is already a JSON number,
    not a string (unlike Fear & Greed's own `value`/`timestamp`, verified
    live rather than assumed identical). Any missing key or unparseable
    value is a malformed response, not a data point to silently skip.
    """
    if not isinstance(entry, dict):
        raise ConnectorAPIError("Malformed DefiLlama entry: expected an object", detail=entry)
    try:
        value = float(entry["tvl"])
        timestamp = datetime.fromtimestamp(int(entry["date"]), tz=UTC)
    except (KeyError, TypeError, ValueError) as exc:
        raise ConnectorAPIError(f"Malformed DefiLlama entry: {exc}", detail=entry) from exc
    return RawDataPoint(timestamp=timestamp, value=value, symbol=None, raw_payload=entry)
