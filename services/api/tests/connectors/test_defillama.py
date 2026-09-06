"""Unit tests for the DefiLlama connector using mocked transports —
mirrors `tests/connectors/test_fear_greed.py`'s own conventions
(`httpx.MockTransport`, fast retry backoff for the failure-path tests),
adapted for DefiLlama's own real, verified shape: a bare JSON array (no
envelope), no authentication, and real HTTP status codes for errors
(unlike Etherscan's always-200 body-content dispatch).
"""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime

import httpx
import pytest

from app.connectors.base import RawDataPoint
from app.connectors.defillama import DefiLlamaClient, DefiLlamaConnector
from app.connectors.errors import ConnectorAPIError, ConnectorNetworkError, ConnectorRateLimitError

Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]

#: A real DefiLlama `v2/historicalChainTvl/Ethereum` response shape
#: (trimmed to two entries), verified live against the real API — oldest
#: first, per the API's own documented order.
_REAL_SHAPED_RESPONSE = [
    {"date": 1735603200, "tvl": 45000000000.0},  # 2024-12-31T00:00:00Z
    {"date": 1735689600, "tvl": 49531283486.0},  # 2025-01-01T00:00:00Z
]


def client_for(
    handler: Handler,
    *,
    max_retries: int = 3,
    retry_backoff: float = 0.01,
) -> DefiLlamaClient:
    """Build a DefiLlamaClient over a mocked transport using fast backoff."""
    transport = httpx.MockTransport(handler)
    return DefiLlamaClient(
        chain="Ethereum", transport=transport, max_retries=max_retries, retry_backoff=retry_backoff
    )


@pytest.mark.asyncio
class TestDefiLlamaClient:
    async def test_successful_fetch_returns_the_raw_array(self) -> None:
        captured: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, json=_REAL_SHAPED_RESPONSE)

        client = client_for(handler)
        async with client:
            data = await client.fetch_history()

        assert data == _REAL_SHAPED_RESPONSE
        assert "/v2/historicalChainTvl/Ethereum" in str(captured["url"])
        # No API key, no auth header, no query string of any kind — this
        # endpoint takes no parameters at all (verified live).
        assert "?" not in str(captured["url"])
        assert "apikey" not in str(captured["url"]).lower()

    async def test_malformed_response_non_json_body_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"this-is-not-json{{{")

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_history()

    async def test_malformed_response_non_list_body_raises_api_error(self) -> None:
        """DefiLlama's own response is a bare array, never an object
        envelope — an object body is malformed for this endpoint."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"date": 1, "tvl": 2})

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_history()

    async def test_unknown_chain_404_raises_api_error(self) -> None:
        """A real, live-confirmed behavior: an unknown chain slug returns
        a genuine HTTP 404 with a plain nginx HTML body, not even
        DefiLlama's own JSON — this client must not choke trying to parse
        it as JSON before recognizing the status code."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, content=b"<html><body>404 Not Found</body></html>")

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_history()

    async def test_http_error_status_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "internal"})

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_history()

    async def test_network_failure_timeout_raises_network_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("read timed out after 5s")

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorNetworkError):
                await client.fetch_history()

    async def test_network_failure_connect_error_is_retried_then_raises(self) -> None:
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            raise httpx.ConnectError("connection refused")

        client = client_for(handler, max_retries=2)
        async with client:
            with pytest.raises(ConnectorNetworkError):
                await client.fetch_history()

        assert calls["count"] == 3  # initial attempt + 2 retries

    async def test_rate_limit_retries_then_succeeds(self) -> None:
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] == 1:
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, json=_REAL_SHAPED_RESPONSE)

        client = client_for(handler, max_retries=2)
        async with client:
            data = await client.fetch_history()

        assert data == _REAL_SHAPED_RESPONSE
        assert calls["count"] == 2

    async def test_rate_limit_exhausted_raises_rate_limit_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "0"})

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorRateLimitError):
                await client.fetch_history()


@pytest.mark.asyncio
class TestDefiLlamaConnector:
    async def test_fetch_maps_and_filters_to_the_requested_range(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_REAL_SHAPED_RESPONSE)

        client = client_for(handler)
        connector = DefiLlamaConnector(client=client)
        async with connector:
            points = await connector.fetch(
                datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC)
            )

        assert points == (
            RawDataPoint(
                timestamp=datetime(2025, 1, 1, tzinfo=UTC),
                value=49531283486.0,
                symbol=None,
                raw_payload=_REAL_SHAPED_RESPONSE[1],
            ),
        )

    async def test_fetch_excludes_points_outside_the_requested_range(self) -> None:
        """The 2024-12-31 entry in the fixture is outside a
        2025-01-01-only request — proves local filtering actually
        happens, not just a pass-through of the whole history DefiLlama
        always returns."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_REAL_SHAPED_RESPONSE)

        client = client_for(handler)
        connector = DefiLlamaConnector(client=client)
        async with connector:
            points = await connector.fetch(
                datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC)
            )

        assert len(points) == 1
        assert points[0].timestamp == datetime(2025, 1, 1, tzinfo=UTC)

    async def test_malformed_entry_value_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[{"date": 1735689600, "tvl": "not-a-number"}])

        client = client_for(handler)
        connector = DefiLlamaConnector(client=client)
        async with connector:
            with pytest.raises(ConnectorAPIError):
                await connector.fetch(
                    datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC)
                )

    async def test_malformed_entry_missing_key_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[{"tvl": 123.0}])

        client = client_for(handler)
        connector = DefiLlamaConnector(client=client)
        async with connector:
            with pytest.raises(ConnectorAPIError):
                await connector.fetch(
                    datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC)
                )

    async def test_rejects_naive_datetimes(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid range")

        connector = DefiLlamaConnector(client=client_for(never_called))
        with pytest.raises(ValueError, match="timezone-aware"):
            await connector.fetch(datetime(2025, 1, 1), datetime(2025, 1, 2, tzinfo=UTC))

    async def test_rejects_end_before_start(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid range")

        connector = DefiLlamaConnector(client=client_for(never_called))
        with pytest.raises(ValueError, match="end must not be before start"):
            await connector.fetch(
                datetime(2025, 1, 2, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC)
            )
