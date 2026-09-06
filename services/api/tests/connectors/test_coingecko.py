"""Unit tests for the CoinGecko connector using mocked transports —
mirrors `tests/connectors/test_fear_greed.py`'s own conventions
(`httpx.MockTransport`, fast retry backoff for the failure-path tests),
adapted for CoinGecko's own real, verified shape: real HTTP status codes
for errors (like Fear & Greed/FRED/DefiLlama, unlike Etherscan), a
genuinely optional API key, and a source-provided `updated_at` timestamp
(unlike Etherscan's dateless Gas Oracle).
"""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.connectors.base import RawDataPoint
from app.connectors.coingecko import CoinGeckoClient, CoinGeckoConnector
from app.connectors.errors import (
    ConnectorAPIError,
    ConnectorAuthenticationError,
    ConnectorNetworkError,
    ConnectorRateLimitError,
)

Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]

#: This connector's own timestamp always comes from the response body's
#: own `updated_at` (never a locally-patched `datetime.now()` — unlike
#: Etherscan's dateless Gas Oracle), so tests need no clock monkeypatch;
#: fixtures just set `updated_at` to whatever instant a test needs.
FIXED_NOW = datetime(2026, 9, 6, 17, 45, 15, tzinfo=UTC)

#: A real CoinGecko `/global` response shape (trimmed), verified live
#: against the real API. `updated_at` corresponds to `FIXED_NOW` above.
_REAL_SHAPED_DATA = {
    "active_cryptocurrencies": 19648,
    "markets": 1498,
    "total_market_cap": {"usd": 2696863165042.916},
    "total_volume": {"usd": 92000000000.0},
    "market_cap_percentage": {"btc": 59.217620949379814, "eth": 11.246157428931873},
    "market_cap_change_percentage_24h_usd": -3.4548766043151167,
    "updated_at": int(FIXED_NOW.timestamp()),
}


def client_for(
    handler: Handler,
    *,
    api_key: str = "",
    max_retries: int = 3,
    retry_backoff: float = 0.01,
) -> CoinGeckoClient:
    """Build a CoinGeckoClient over a mocked transport using fast backoff."""
    transport = httpx.MockTransport(handler)
    return CoinGeckoClient(
        transport=transport, api_key=api_key, max_retries=max_retries, retry_backoff=retry_backoff
    )


@pytest.mark.asyncio
class TestCoinGeckoClient:
    async def test_successful_fetch_returns_the_raw_data_object(self) -> None:
        captured_url: dict[str, str] = {}
        captured_headers: dict[str, dict[str, str]] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured_url["url"] = str(request.url)
            captured_headers["headers"] = dict(request.headers)
            return httpx.Response(200, json={"data": _REAL_SHAPED_DATA})

        client = client_for(handler)
        async with client:
            data = await client.fetch_global()

        assert data == _REAL_SHAPED_DATA
        assert "/global" in captured_url["url"]
        assert "x-cg-demo-api-key" not in captured_headers["headers"]

    async def test_no_api_key_makes_a_real_request_anyway(self) -> None:
        """The genuine architectural difference from FRED/Etherscan: an
        unconfigured key never raises locally here — CoinGecko's own
        `/global` works fully keyless, confirmed live."""
        called = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            called["count"] += 1
            return httpx.Response(200, json={"data": _REAL_SHAPED_DATA})

        client = client_for(handler, api_key="")
        async with client:
            data = await client.fetch_global()

        assert data == _REAL_SHAPED_DATA
        assert called["count"] == 1

    async def test_configured_api_key_is_sent_as_a_header_not_a_query_param(self) -> None:
        captured: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["header_value"] = request.headers.get("x-cg-demo-api-key")
            return httpx.Response(200, json={"data": _REAL_SHAPED_DATA})

        client = client_for(handler, api_key="real-demo-key")
        async with client:
            await client.fetch_global()

        assert captured["header_value"] == "real-demo-key"
        assert "real-demo-key" not in str(captured["url"])

    async def test_bad_api_key_raises_authentication_error(self) -> None:
        """CoinGecko's own real response for a bad/invalid Demo key —
        verified live: HTTP 401 with `{"status": {"error_code": 10002,
        ...}}`, the same code documented for a *missing* key."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json={
                    "status": {
                        "error_code": 10002,
                        "error_message": "API Key Missing. Please make sure you're "
                        "using the right authentication method.",
                    }
                },
            )

        client = client_for(handler, api_key="deliberately-invalid-key", max_retries=0)
        async with client:
            with pytest.raises(ConnectorAuthenticationError):
                await client.fetch_global()

    async def test_malformed_response_non_json_body_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"this-is-not-json{{{")

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_global()

    async def test_malformed_response_non_object_envelope_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[1, 2, 3])

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_global()

    async def test_malformed_response_missing_data_field_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": True})

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_global()

    async def test_network_failure_timeout_raises_network_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("read timed out after 5s")

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorNetworkError):
                await client.fetch_global()

    async def test_network_failure_connect_error_is_retried_then_raises(self) -> None:
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            raise httpx.ConnectError("connection refused")

        client = client_for(handler, max_retries=2)
        async with client:
            with pytest.raises(ConnectorNetworkError):
                await client.fetch_global()

        assert calls["count"] == 3  # initial attempt + 2 retries

    async def test_rate_limit_with_json_body_retries_then_succeeds(self) -> None:
        """CoinGecko's own documented, authenticated-tier 429 shape."""
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] == 1:
                return httpx.Response(429, json={"status": {"error_message": "Too many requests"}})
            return httpx.Response(200, json={"data": _REAL_SHAPED_DATA})

        client = client_for(handler, max_retries=2)
        async with client:
            data = await client.fetch_global()

        assert data == _REAL_SHAPED_DATA
        assert calls["count"] == 2

    async def test_rate_limit_with_plain_text_body_retries_then_succeeds(self) -> None:
        """The real, live-confirmed keyless shape: a plain-text
        `"Throttled\\n"` body, not CoinGecko's own JSON envelope — proves
        the retry loop doesn't assume a JSON body on 429."""
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] == 1:
                return httpx.Response(429, content=b"Throttled\n")
            return httpx.Response(200, json={"data": _REAL_SHAPED_DATA})

        client = client_for(handler, max_retries=2)
        async with client:
            data = await client.fetch_global()

        assert data == _REAL_SHAPED_DATA
        assert calls["count"] == 2

    async def test_rate_limit_exhausted_raises_rate_limit_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, content=b"Throttled\n")

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorRateLimitError):
                await client.fetch_global()


@pytest.mark.asyncio
class TestCoinGeckoConnector:
    async def test_fetch_returns_the_current_value_timestamped_by_updated_at(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": _REAL_SHAPED_DATA})

        client = client_for(handler)
        connector = CoinGeckoConnector(client=client)
        async with connector:
            points = await connector.fetch(
                FIXED_NOW - timedelta(hours=1), FIXED_NOW + timedelta(hours=1)
            )

        assert points == (
            RawDataPoint(
                timestamp=FIXED_NOW,
                value=59.217620949379814,
                symbol=None,
                raw_payload=_REAL_SHAPED_DATA,
            ),
        )

    async def test_fetch_excludes_the_point_when_updated_at_is_outside_the_requested_range(
        self,
    ) -> None:
        """The load-bearing proof of this connector's own disclosed
        limitation: there is no way to answer for a range that has
        already closed in the past — an honest empty result, never a
        fabricated point."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": _REAL_SHAPED_DATA})

        client = client_for(handler)
        connector = CoinGeckoConnector(client=client)
        async with connector:
            points = await connector.fetch(
                datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 1, 2, tzinfo=UTC)
            )

        assert points == ()

    async def test_malformed_result_missing_btc_percentage_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "market_cap_percentage": {"eth": 11.0},
                        "updated_at": int(FIXED_NOW.timestamp()),
                    }
                },
            )

        client = client_for(handler)
        connector = CoinGeckoConnector(client=client)
        async with connector:
            with pytest.raises(ConnectorAPIError):
                await connector.fetch(
                    FIXED_NOW - timedelta(hours=1), FIXED_NOW + timedelta(hours=1)
                )

    async def test_malformed_result_missing_updated_at_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {"market_cap_percentage": {"btc": 59.0}}})

        client = client_for(handler)
        connector = CoinGeckoConnector(client=client)
        async with connector:
            with pytest.raises(ConnectorAPIError):
                await connector.fetch(
                    FIXED_NOW - timedelta(hours=1), FIXED_NOW + timedelta(hours=1)
                )

    async def test_rejects_naive_datetimes(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid range")

        connector = CoinGeckoConnector(client=client_for(never_called))
        with pytest.raises(ValueError, match="timezone-aware"):
            await connector.fetch(FIXED_NOW.replace(tzinfo=None), FIXED_NOW)

    async def test_rejects_end_before_start(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid range")

        connector = CoinGeckoConnector(client=client_for(never_called))
        with pytest.raises(ValueError, match="end must not be before start"):
            await connector.fetch(FIXED_NOW, FIXED_NOW - timedelta(days=1))
