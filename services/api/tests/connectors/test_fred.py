"""Unit tests for the FRED connector using mocked transports — mirrors
`tests/connectors/test_fear_greed.py`'s own conventions (`httpx
.MockTransport`, fast retry backoff for the failure-path tests), plus the
publication-lag-specific proof this connector exists to get right.
"""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime

import httpx
import pytest

from app.connectors.base import RawDataPoint
from app.connectors.errors import (
    ConnectorAPIError,
    ConnectorAuthenticationError,
    ConnectorNetworkError,
    ConnectorRateLimitError,
)
from app.connectors.fred import FredClient, FredConnector

Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]

#: A real FRED `series/observations` response shape (trimmed to two
#: entries): August's average isn't published until September — its own
#: `realtime_start` is a full month after its `date`.
_REAL_SHAPED_RESPONSE = {
    "realtime_start": "2026-09-05",
    "realtime_end": "2026-09-05",
    "observation_start": "1954-07-01",
    "observation_end": "2026-09-05",
    "units": "lin",
    "output_type": 1,
    "file_type": "json",
    "count": 2,
    "observations": [
        {
            "realtime_start": "2026-08-01",
            "realtime_end": "2026-08-01",
            "date": "2026-07-01",
            "value": "3.65",
        },
        {
            "realtime_start": "2026-09-01",
            "realtime_end": "2026-09-01",
            "date": "2026-08-01",
            "value": "3.63",
        },
    ],
}


def client_for(
    handler: Handler,
    *,
    api_key: str = "test-key",
    max_retries: int = 3,
    retry_backoff: float = 0.01,
) -> FredClient:
    """Build a FredClient over a mocked transport using fast backoff."""
    transport = httpx.MockTransport(handler)
    return FredClient(
        transport=transport, api_key=api_key, max_retries=max_retries, retry_backoff=retry_backoff
    )


@pytest.mark.asyncio
class TestFredClient:
    async def test_successful_fetch_returns_the_raw_observations_array(self) -> None:
        captured: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, json=_REAL_SHAPED_RESPONSE)

        client = client_for(handler)
        async with client:
            data = await client.fetch_observations(
                "FEDFUNDS",
                observation_start=datetime(1954, 7, 1, tzinfo=UTC).date(),
                observation_end=datetime(2026, 9, 5, tzinfo=UTC).date(),
            )

        assert data == _REAL_SHAPED_RESPONSE["observations"]
        assert "series_id=FEDFUNDS" in str(captured["url"])
        assert "api_key=test-key" in str(captured["url"])
        assert "observation_start=1954-07-01" in str(captured["url"])
        assert "observation_end=2026-09-05" in str(captured["url"])
        # Load-bearing, not incidental — see fred.py's own module docstring
        # for the real bug omitting these caused (verified live).
        assert "realtime_start=1776-07-04" in str(captured["url"])
        assert "realtime_end=9999-12-31" in str(captured["url"])

    async def test_no_api_key_raises_authentication_error_with_no_request(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made with no API key configured")

        client = client_for(never_called, api_key="")
        async with client:
            with pytest.raises(ConnectorAuthenticationError):
                await client.fetch_observations(
                    "FEDFUNDS",
                    observation_start=datetime(1954, 7, 1, tzinfo=UTC).date(),
                    observation_end=datetime(2026, 1, 1, tzinfo=UTC).date(),
                )

    async def test_bad_api_key_raises_authentication_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={
                    "error_code": 400,
                    "error_message": (
                        "Bad Request. The value for variable api_key is not registered. "
                        "Read https://fred.stlouisfed.org/docs/api/api_key.html for more "
                        "information."
                    ),
                },
            )

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorAuthenticationError):
                await client.fetch_observations(
                    "FEDFUNDS",
                    observation_start=datetime(1954, 7, 1, tzinfo=UTC).date(),
                    observation_end=datetime(2026, 1, 1, tzinfo=UTC).date(),
                )

    async def test_unknown_series_raises_api_error_not_authentication_error(self) -> None:
        """A 400 whose message does not mention `api_key` is a generic API
        error, not misreported as an authentication failure."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={
                    "error_code": 400,
                    "error_message": "Bad Request. Variable series_id is not a valid series ID.",
                },
            )

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorAPIError) as exc_info:
                await client.fetch_observations(
                    "NOPE",
                    observation_start=datetime(1954, 7, 1, tzinfo=UTC).date(),
                    observation_end=datetime(2026, 1, 1, tzinfo=UTC).date(),
                )
        assert not isinstance(exc_info.value, ConnectorAuthenticationError)

    async def test_malformed_response_non_json_body_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"this-is-not-json{{{")

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_observations(
                    "FEDFUNDS",
                    observation_start=datetime(1954, 7, 1, tzinfo=UTC).date(),
                    observation_end=datetime(2026, 1, 1, tzinfo=UTC).date(),
                )

    async def test_malformed_response_missing_observations_field_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"count": 0})

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_observations(
                    "FEDFUNDS",
                    observation_start=datetime(1954, 7, 1, tzinfo=UTC).date(),
                    observation_end=datetime(2026, 1, 1, tzinfo=UTC).date(),
                )

    async def test_malformed_response_non_object_envelope_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[1, 2, 3])

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_observations(
                    "FEDFUNDS",
                    observation_start=datetime(1954, 7, 1, tzinfo=UTC).date(),
                    observation_end=datetime(2026, 1, 1, tzinfo=UTC).date(),
                )

    async def test_http_error_status_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error_code": 500, "error_message": "internal"})

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_observations(
                    "FEDFUNDS",
                    observation_start=datetime(1954, 7, 1, tzinfo=UTC).date(),
                    observation_end=datetime(2026, 1, 1, tzinfo=UTC).date(),
                )

    async def test_network_failure_timeout_raises_network_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("read timed out after 5s")

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorNetworkError):
                await client.fetch_observations(
                    "FEDFUNDS",
                    observation_start=datetime(1954, 7, 1, tzinfo=UTC).date(),
                    observation_end=datetime(2026, 1, 1, tzinfo=UTC).date(),
                )

    async def test_network_failure_connect_error_is_retried_then_raises(self) -> None:
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            raise httpx.ConnectError("connection refused")

        client = client_for(handler, max_retries=2)
        async with client:
            with pytest.raises(ConnectorNetworkError):
                await client.fetch_observations(
                    "FEDFUNDS",
                    observation_start=datetime(1954, 7, 1, tzinfo=UTC).date(),
                    observation_end=datetime(2026, 1, 1, tzinfo=UTC).date(),
                )

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
            data = await client.fetch_observations(
                "FEDFUNDS",
                observation_start=datetime(1954, 7, 1, tzinfo=UTC).date(),
                observation_end=datetime(2026, 1, 1, tzinfo=UTC).date(),
            )

        assert data == _REAL_SHAPED_RESPONSE["observations"]
        assert calls["count"] == 2

    async def test_rate_limit_exhausted_raises_rate_limit_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "0"})

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorRateLimitError):
                await client.fetch_observations(
                    "FEDFUNDS",
                    observation_start=datetime(1954, 7, 1, tzinfo=UTC).date(),
                    observation_end=datetime(2026, 1, 1, tzinfo=UTC).date(),
                )


@pytest.mark.asyncio
class TestFredConnector:
    async def test_fetch_uses_realtime_start_never_the_reference_date(self) -> None:
        """The load-bearing proof: August's own value is dated `2026-08-01`
        but not published until `2026-09-01` — `fetch` must timestamp it
        by the *publication* date, not the reference month."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_REAL_SHAPED_RESPONSE)

        client = client_for(handler)
        connector = FredConnector(client=client)
        async with connector:
            points = await connector.fetch(
                datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC)
            )

        assert points == (
            RawDataPoint(
                timestamp=datetime(2026, 9, 1, tzinfo=UTC),
                value=3.63,
                symbol=None,
                raw_payload=_REAL_SHAPED_RESPONSE["observations"][1],
            ),
        )

    async def test_fetch_excludes_points_outside_the_requested_publication_range(self) -> None:
        """The July entry (published 2026-08-01) is outside a
        2026-09-01-only request, even though nothing filters it by `date`
        — proves the exclusion is genuinely realtime_start-based."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_REAL_SHAPED_RESPONSE)

        client = client_for(handler)
        connector = FredConnector(client=client)
        async with connector:
            points = await connector.fetch(
                datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC)
            )

        assert len(points) == 1
        assert points[0].timestamp == datetime(2026, 9, 1, tzinfo=UTC)

    async def test_a_missing_value_sentinel_is_skipped_not_fabricated(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "observations": [
                        {"realtime_start": "2026-09-01", "date": "2026-08-01", "value": "."},
                        {"realtime_start": "2026-09-01", "date": "2026-08-01", "value": "3.63"},
                    ]
                },
            )

        client = client_for(handler)
        connector = FredConnector(client=client)
        async with connector:
            points = await connector.fetch(
                datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC)
            )

        assert len(points) == 1
        assert points[0].value == 3.63

    async def test_malformed_entry_value_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "observations": [
                        {
                            "realtime_start": "2026-09-01",
                            "date": "2026-08-01",
                            "value": "not-a-number",
                        }
                    ]
                },
            )

        client = client_for(handler)
        connector = FredConnector(client=client)
        async with connector:
            with pytest.raises(ConnectorAPIError):
                await connector.fetch(
                    datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC)
                )

    async def test_malformed_entry_missing_key_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"observations": [{"value": "3.63"}]})

        client = client_for(handler)
        connector = FredConnector(client=client)
        async with connector:
            with pytest.raises(ConnectorAPIError):
                await connector.fetch(
                    datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC)
                )

    async def test_rejects_naive_datetimes(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid range")

        connector = FredConnector(client=client_for(never_called))
        with pytest.raises(ValueError, match="timezone-aware"):
            await connector.fetch(datetime(2026, 1, 1), datetime(2026, 1, 2, tzinfo=UTC))

    async def test_rejects_end_before_start(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid range")

        connector = FredConnector(client=client_for(never_called))
        with pytest.raises(ValueError, match="end must not be before start"):
            await connector.fetch(
                datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)
            )
