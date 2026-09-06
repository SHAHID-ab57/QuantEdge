"""The Etherscan connector — the third concrete connector, and the second
requiring authentication, against Etherscan's V2 API
(`docs/architecture/SystemContext.md` § 3). Uses the **Gas Oracle**
endpoint (`module=gastracker&action=gasoracle`), reporting
`ProposeGasPrice` — the standard recommended gas price Etherscan's own
gas tracker UI treats as the default tier, not the safe/slow or
fast/priority alternatives it also returns.

**Investigated before building, not assumed — three things changed or
were confirmed live against the real API:**

1. **Etherscan's API moved to V2.** The old endpoint
   (`api.etherscan.io/api`) is deprecated — a real request against it now
   returns a deprecation notice instead of data (verified live). The
   current one, `api.etherscan.io/v2/api`, requires an explicit
   `chainid` parameter (`1` for Ethereum mainnet) — V2 folds every EVM
   chain Etherscan supports behind one base URL, distinguished by this
   one parameter.
2. **The free-tier rate limit has genuinely changed.** Historically cited
   as 5 calls/second; Etherscan's own current rate-limits page states
   **3 calls/second, up to 100,000 calls/day** for the free tier — used
   here, not the historical figure.
3. **Etherscan always returns HTTP 200, even for errors** — confirmed
   live for both a rate-limit response and a missing/invalid-key
   response. Real domain errors live entirely in the JSON body
   (`{"status": "0"|"1", "message": ..., "result": ...}`), so this
   client's own retry/error-typing dispatch is genuinely different from
   `FearGreedClient`/`FredClient`'s HTTP-status-code-based one: it must
   inspect the body on every response, never the status code, to decide
   what happened.

**Why `dailyavggasprice` (a real historical daily series) was not used
instead.** Etherscan's `stats` module does publish a genuine
day-by-day gas price history under that name — but it is a **Pro-tier
endpoint**, confirmed via Etherscan's own documentation, not available
on the free tier this connector targets. `ethsupply` (Ether's total
supply) was also considered and rejected: it changes by a vanishingly
small amount day to day (net issuance minus the EIP-1559 burn), making
it a nearly-flat, uninformative signal — and it additionally requires an
API key even to attempt (confirmed live: `gasoracle` still returns real
data with no key at all, just a slower degraded rate, while `ethsupply`
hard-fails without one).

**Lag — confirmed zero, not assumed, for a genuinely different reason
than Fear & Greed's same-day publication.** Gas Oracle has no historical
query capability at all, and its response carries no `date`/`timestamp`
field of its own (only `LastBlock`, a block number). There is exactly one
timestamp concept available: the wall-clock moment this connector made
the request — `RawDataPoint.timestamp` is always `datetime.now(UTC)` at
fetch time, so "when it was observed" and "when it became knowable" are
the same instant by construction, the same way a live stock-ticker quote
has no separate reference-vs-publication distinction to get wrong.

**The real, disclosed limitation this connector has that neither Fear &
Greed nor FRED does: there is no way to backfill history.** Both of
those sources let a caller fetch their entire past — this one cannot;
Gas Oracle only ever answers "what is it right now." `fetch(start, end)`
therefore makes exactly one live request regardless of the requested
range, and returns that single fresh point only if "now" actually falls
at or after `start` and no later than `end` plus a small grace period
(`_END_GRACE_PERIOD`) — otherwise an empty tuple, honestly reporting
"nothing available for that range" rather than fabricating history that
was never observed. `scripts/backfill_etherscan.py` performs exactly one
poll for the same reason; the periodic sync scheduler is what actually
builds a history over time, one point per tick, starting from whenever
ingestion first began — never earlier.

**A real bug this design caught, but only once run against the real
scheduler path with real network latency, never the mocked test suite:**
`ExternalDataSyncScheduler.run_catch_up` captures one `now` up front and
threads `end=now` through an async chain — a DB query, then whichever
other sources sync first in the same tick — before this connector's own
`fetch()` even starts its HTTP round trip. Since the returned point is
always timestamped *after* that round trip completes, a strict
`point.timestamp <= end` check can never hold: real wall-clock time has
already moved past the caller's stale `end` snapshot by the time the
point exists at all. A real manual poll (`scripts/backfill_etherscan.py`)
run immediately after this connector was first written confirmed it
live: `received=0`, not the expected single point, purely because of
this timing gap, not any real data problem. Fixed with
`_END_GRACE_PERIOD` (see its own comment for the full account); reran
the same real poll afterward and got `received=1 inserted=1`.
"""

import asyncio
import logging
import random
import time
from datetime import UTC, datetime, timedelta
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

logger = logging.getLogger("app.connectors.etherscan")

ETHERSCAN_SOURCE = "eth_gas_price"
ETHERSCAN_GAS_ORACLE_PARAMS = {"module": "gastracker", "action": "gasoracle"}
#: The gas price tier this connector reports — Etherscan's own "standard"
#: recommendation, not the safe/slow (`SafeGasPrice`) or fast/priority
#: (`FastGasPrice`) alternatives the same response also carries.
_RESULT_VALUE_FIELD = "ProposeGasPrice"

#: Etherscan's own current rate limit (verified against its live
#: rate-limits documentation, not the historically-cited 5 calls/second).
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 0.5
_MAX_RETRY_DELAY = 30.0
_USER_AGENT = "eth-ai-platform/0.1.0"

#: `EtherscanConnector.fetch`'s own `end` grace period — found necessary
#: only by running the real periodic-sync path against the live API, not
#: by any mocked test. `ExternalDataSyncScheduler.run_catch_up` captures
#: one `now` up front and passes `end=now` down through an async chain
#: (a DB query in `_catch_up_window`, then whichever other sources are
#: synced first in the same tick, each with their own real HTTP call)
#: before this connector ever makes its own request. By the time this
#: connector's point is actually observed (necessarily *after* its own
#: real HTTP round trip to Etherscan), real wall-clock time has always
#: moved past that stale `end` snapshot — confirmed live: a real manual
#: poll immediately after this connector was written returned
#: `received=0`, not the expected single point, because a strict
#: `point.timestamp <= end` can structurally never hold for a source
#: whose only answerable value is "right now". This grace period accepts
#: a point observed up to this long *after* the requested `end`, telling
#: apart "the caller asked about now, but now moved on while this
#: connector was fetching" (accept) from "the caller asked about a
#: genuinely, meaningfully past window" (reject) — every real caller's
#: historical `end` (e.g. `scripts/backfill_etherscan.py --end
#: 2020-01-01`) is off by whole days at minimum, comfortably outside
#: this window, while no realistic sync tick takes anywhere near this
#: long.
_END_GRACE_PERIOD = timedelta(minutes=5)


class EtherscanClient:
    """Async HTTP client for Etherscan's V2 API.

    Same connection-pooling/bounded-retry/structured-logging shape as
    `FearGreedClient`/`FredClient`, but error detection is entirely
    body-based (see this module's own docstring for why): Etherscan
    reports every failure — transient or not — as HTTP 200 with
    `status: "0"` in the JSON body, so there is no status-code fast path
    to check before parsing.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        chain_id: int | None = None,
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
        self._api_key = api_key if api_key is not None else settings.etherscan_api_key
        self._chain_id = chain_id if chain_id is not None else settings.etherscan_chain_id
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.etherscan_base_url,
            timeout=httpx.Timeout(
                request_timeout
                if request_timeout is not None
                else settings.etherscan_request_timeout
            ),
            transport=transport,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )

    async def fetch_gas_oracle(self) -> dict[str, Any]:
        """Return the raw Gas Oracle `result` object.

        Raises `ConnectorAuthenticationError` immediately, with no
        network call, when no API key is configured — the same
        predictable local failure `FredClient` raises, even though
        Etherscan itself would still answer (at a much slower degraded
        rate) with no key at all; this platform always uses a real key
        for reliable throughput rather than depending on that fallback.
        """
        if not self._api_key:
            raise ConnectorAuthenticationError(
                "Etherscan API key is not configured (ETHERSCAN_API_KEY) — register a "
                "free key at https://etherscan.io/apidashboard"
            )

        result = await self._execute(
            "GET",
            "",
            params={
                **ETHERSCAN_GAS_ORACLE_PARAMS,
                "chainid": self._chain_id,
                "apikey": self._api_key,
            },
        )
        if not isinstance(result, dict):
            raise ConnectorAPIError(
                "Malformed Etherscan Gas Oracle response: expected an object 'result'",
                detail=result,
            )
        return result

    async def aclose(self) -> None:
        """Close the underlying httpx client, releasing pooled connections."""
        await self._client.aclose()

    async def __aenter__(self) -> "EtherscanClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()

    async def _execute(self, method: str, path: str, *, params: dict[str, Any]) -> object:
        """Send one request with retries; return the decoded `result` value.

        Unlike `FearGreedClient`/`FredClient`, retry eligibility is
        decided entirely from the parsed body (Etherscan never signals a
        transient failure via the HTTP status line) — see this module's
        own docstring.
        """
        attempt = 0
        while True:
            started = time.perf_counter()
            try:
                response = await self._client.request(method, path, params=params)
            except httpx.TimeoutException as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "Etherscan %s %s timed out on attempt %d (%.1fms)",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                )
                if attempt >= self._max_retries:
                    raise ConnectorNetworkError(
                        f"Etherscan request timed out: {method} {path}", detail=str(exc)
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue
            except httpx.TransportError as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "Etherscan %s %s transport error on attempt %d (%.1fms): %s",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                    exc,
                )
                if attempt >= self._max_retries:
                    raise ConnectorNetworkError(
                        f"Etherscan network failure for {method} {path}: {exc}", detail=str(exc)
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue

            latency_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "Etherscan %s %s -> HTTP %d (%.1fms)",
                method,
                path,
                response.status_code,
                latency_ms,
            )

            payload = self._json_payload(response)
            if payload is None:
                raise ConnectorAPIError(
                    f"Malformed Etherscan response for {method} {path}: body is not valid JSON",
                    status_code=response.status_code,
                )
            if not isinstance(payload, dict):
                raise ConnectorAPIError(
                    f"Malformed Etherscan response for {method} {path}: expected an object "
                    "envelope",
                    status_code=response.status_code,
                    detail=payload,
                )

            status = str(payload.get("status", ""))
            message = str(payload.get("message", ""))
            result = payload.get("result")

            if status == "1":
                return result

            # status == "0" (or missing): a real domain error, described
            # by `result` — dispatched on its own text, since Etherscan
            # gives no other structured signal for which kind occurred.
            detail_text = str(result).lower()
            if "rate limit" in detail_text:
                if attempt < self._max_retries:
                    delay = min(self._retry_backoff * (2**attempt), _MAX_RETRY_DELAY)
                    logger.warning(
                        "Etherscan retrying %s %s after rate limit in %.2fs (attempt %d/%d)",
                        method,
                        path,
                        delay,
                        attempt + 1,
                        self._max_retries,
                    )
                    await self._sleep(delay)
                    attempt += 1
                    continue
                raise ConnectorRateLimitError(
                    f"Etherscan rate limit exceeded for {method} {path}: {result}",
                    status_code=response.status_code,
                )
            if "api key" in detail_text:
                raise ConnectorAuthenticationError(
                    f"Etherscan authentication failed for {method} {path}: {result}",
                    status_code=response.status_code,
                    detail=payload,
                )
            raise ConnectorAPIError(
                f"Etherscan request failed for {method} {path}: {message} ({result})",
                status_code=response.status_code,
                detail=payload,
            )

    @staticmethod
    def _json_payload(response: httpx.Response) -> object | None:
        try:
            return response.json()
        except ValueError:
            return None

    async def _backoff(self, attempt: int) -> None:
        delay = min(self._retry_backoff * (2**attempt), _MAX_RETRY_DELAY)
        await self._sleep(delay)

    @staticmethod
    async def _sleep(delay: float) -> None:
        jittered = delay * (1.0 + random.random() * 0.1)
        await asyncio.sleep(jittered)


def get_etherscan_client(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    chain_id: int | None = None,
    request_timeout: float | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
) -> EtherscanClient:
    """Return a configured Etherscan client, defaulting from settings."""
    return EtherscanClient(
        base_url=base_url,
        api_key=api_key,
        chain_id=chain_id,
        request_timeout=request_timeout,
        transport=transport,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
    )


@register_connector
class EtherscanConnector:
    """Adapts `EtherscanClient` to the `Connector` protocol.

    Holds its own client (built fresh per instance, same reasoning as
    `FearGreedConnector`/`FredConnector`); `aclose()` releases it, and the
    class supports `async with` for the same "use once, then close" case
    ingestion/backfill both need.
    """

    metadata: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        source=ETHERSCAN_SOURCE,
        label="Ethereum Gas Price",
        description=(
            "The current recommended standard gas price (Etherscan's Gas Oracle, "
            "ProposeGasPrice, in Gwei) for the Ethereum mainnet. Requires a free "
            "Etherscan API key. Has no historical query capability — this "
            "connector can only observe the price at the moment it is polled, so "
            "its own stored history begins the day ingestion started, never "
            "earlier."
        ),
        frequency="continuous (sampled per sync tick)",
        requires_auth=True,
        version="1.0.0",
        aliases=("gas_price", "gwei", "gas_oracle"),
    )

    def __init__(self, *, client: EtherscanClient | None = None) -> None:
        self._client = client or get_etherscan_client()

    async def fetch(self, start: datetime, end: datetime) -> tuple[RawDataPoint, ...]:
        """Return the current gas price as a single point, timestamped
        `datetime.now(UTC)` — the only timestamp concept this source has
        (see this module's own docstring) — but only if that moment
        actually falls at or after `start` and no later than
        `end + _END_GRACE_PERIOD`. There is no way to answer for a range
        that has already closed in the genuine past; this returns an
        empty tuple for that case rather than fabricating a value. The
        grace period on the upper bound is load-bearing, not cosmetic —
        see `_END_GRACE_PERIOD`'s own comment for the real bug that made
        it necessary.
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware datetimes")
        if end < start:
            raise ValueError("end must not be before start")

        result = await self._client.fetch_gas_oracle()
        point = _to_point(result)
        if point is None or not (start <= point.timestamp <= end + _END_GRACE_PERIOD):
            return ()
        return (point,)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "EtherscanConnector":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


def _to_point(result: object) -> RawDataPoint | None:
    """Map one raw Gas Oracle `result` object to a `RawDataPoint`.

    `timestamp` is `datetime.now(UTC)` at the moment this mapping runs —
    the request itself already happened immediately before, so this is
    the moment the value was actually observed, never an approximation.
    """
    if not isinstance(result, dict):
        raise ConnectorAPIError(
            "Malformed Etherscan Gas Oracle result: expected an object", detail=result
        )
    try:
        value = float(result[_RESULT_VALUE_FIELD])
    except (KeyError, TypeError, ValueError) as exc:
        raise ConnectorAPIError(
            f"Malformed Etherscan Gas Oracle result: {exc}", detail=result
        ) from exc
    return RawDataPoint(timestamp=datetime.now(UTC), value=value, symbol=None, raw_payload=result)
