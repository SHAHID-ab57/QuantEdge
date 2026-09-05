"""Unit tests for the Fear & Greed connector using mocked transports —
mirrors `tests/unit/delta/test_client.py`'s own conventions exactly
(`httpx.MockTransport`, fast retry backoff for the failure-path tests).
"""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime

import httpx
import pytest

from app.connectors.base import RawDataPoint
from app.connectors.errors import ConnectorAPIError, ConnectorNetworkError, ConnectorRateLimitError
from app.connectors.fear_greed import FearGreedClient, FearGreedConnector

Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]

#: A real alternative.me response shape (trimmed to two entries) — most
#: recent first, per the API's own documented order.
_REAL_SHAPED_RESPONSE = {
    "name": "Fear and Greed Index",
    "data": [
        {
            "value": "73",
            "value_classification": "Greed",
            "timestamp": "1735689600",  # 2025-01-01T00:00:00Z
            "time_until_update": "3600",
        },
        {
            "value": "45",
            "value_classification": "Fear",
            "timestamp": "1735603200",  # 2024-12-31T00:00:00Z
            "time_until_update": "3600",
        },
    ],
    "metadata": {"error": None},
}


def client_for(
    handler: Handler,
    *,
    max_retries: int = 3,
    retry_backoff: float = 0.01,
) -> FearGreedClient:
    """Build a FearGreedClient over a mocked transport using fast backoff."""
    transport = httpx.MockTransport(handler)
    return FearGreedClient(
        transport=transport, max_retries=max_retries, retry_backoff=retry_backoff
    )


@pytest.mark.asyncio
class TestFearGreedClient:
    async def test_successful_fetch_returns_the_raw_data_array(self) -> None:
        captured: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, json=_REAL_SHAPED_RESPONSE)

        client = client_for(handler)
        async with client:
            data = await client.fetch_history(limit=2)

        assert data == _REAL_SHAPED_RESPONSE["data"]
        assert "limit=2" in str(captured["url"])
        assert "format=json" in str(captured["url"])

    async def test_a_full_history_request_uses_the_zero_limit_sentinel(self) -> None:
        captured: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, json={"name": "x", "data": [], "metadata": {"error": None}})

        client = client_for(handler)
        async with client:
            await client.fetch_history(limit=0)

        assert "limit=0" in str(captured["url"])

    async def test_malformed_response_non_json_body_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"this-is-not-json{{{")

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_history(limit=10)

    async def test_malformed_response_missing_data_field_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"name": "Fear and Greed Index", "metadata": {}})

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_history(limit=10)

    async def test_malformed_response_non_object_envelope_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[1, 2, 3])

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_history(limit=10)

    async def test_api_reported_error_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"name": "x", "data": [], "metadata": {"error": "something broke"}}
            )

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_history(limit=10)

    async def test_http_error_status_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "internal"})

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_history(limit=10)

    async def test_network_failure_timeout_raises_network_error(self) -> None:
        """A network failure (read timeout, connection refused, DNS
        failure, ...) surfaces as `ConnectorNetworkError` — never an
        unhandled `httpx` exception leaking past this client."""

        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("read timed out after 5s")

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorNetworkError):
                await client.fetch_history(limit=10)

    async def test_network_failure_connect_error_is_retried_then_raises(self) -> None:
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            raise httpx.ConnectError("connection refused")

        client = client_for(handler, max_retries=2)
        async with client:
            with pytest.raises(ConnectorNetworkError):
                await client.fetch_history(limit=10)

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
            data = await client.fetch_history(limit=2)

        assert data == _REAL_SHAPED_RESPONSE["data"]
        assert calls["count"] == 2

    async def test_rate_limit_exhausted_raises_rate_limit_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "0"})

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorRateLimitError):
                await client.fetch_history(limit=10)


@pytest.mark.asyncio
class TestFearGreedConnector:
    async def test_fetch_maps_and_filters_to_the_requested_range(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_REAL_SHAPED_RESPONSE)

        client = client_for(handler)
        connector = FearGreedConnector(client=client)
        async with connector:
            points = await connector.fetch(
                datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC)
            )

        assert points == (
            RawDataPoint(
                timestamp=datetime(2025, 1, 1, tzinfo=UTC),
                value=73.0,
                symbol=None,
                raw_payload=_REAL_SHAPED_RESPONSE["data"][0],
            ),
        )

    async def test_fetch_excludes_points_outside_the_requested_range(self) -> None:
        """The 2024-12-31 entry in the fixture is outside a 2025-01-01-only
        request — proves local filtering actually happens, not just a
        pass-through of whatever the source returned."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_REAL_SHAPED_RESPONSE)

        client = client_for(handler)
        connector = FearGreedConnector(client=client)
        async with connector:
            points = await connector.fetch(
                datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC)
            )

        assert len(points) == 1
        assert points[0].timestamp == datetime(2025, 1, 1, tzinfo=UTC)

    async def test_malformed_entry_value_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "name": "x",
                    "data": [{"value": "not-a-number", "timestamp": "1735689600"}],
                    "metadata": {"error": None},
                },
            )

        client = client_for(handler)
        connector = FearGreedConnector(client=client)
        async with connector:
            with pytest.raises(ConnectorAPIError):
                await connector.fetch(
                    datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC)
                )

    async def test_malformed_entry_missing_key_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"name": "x", "data": [{"value": "50"}], "metadata": {"error": None}},
            )

        client = client_for(handler)
        connector = FearGreedConnector(client=client)
        async with connector:
            with pytest.raises(ConnectorAPIError):
                await connector.fetch(
                    datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC)
                )

    async def test_rejects_naive_datetimes(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid range")

        connector = FearGreedConnector(client=client_for(never_called))
        with pytest.raises(ValueError, match="timezone-aware"):
            await connector.fetch(datetime(2025, 1, 1), datetime(2025, 1, 2, tzinfo=UTC))

    async def test_rejects_end_before_start(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid range")

        connector = FearGreedConnector(client=client_for(never_called))
        with pytest.raises(ValueError, match="end must not be before start"):
            await connector.fetch(
                datetime(2025, 1, 2, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC)
            )
