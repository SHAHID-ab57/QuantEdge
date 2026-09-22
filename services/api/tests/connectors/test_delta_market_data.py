"""Tests for the Delta funding-rate and open-interest connectors (M4-E3-T3).

Mocked transport only (`httpx.MockTransport`), with response shapes taken from
the real `GET /v2/history/candles` payloads for `FUNDING:ETHUSD` / `OI:ETHUSD`
(volume null, prices as strings/numbers, newest first). The behaviour worth
pinning is the *stamping*: the value attached to a timestamp must be knowable
at that timestamp (funding: the rate set then; OI: the candle's open, never its
close), and a constant funding stretch must not be stored once per hour.
"""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.connectors.delta_market_data import (
    FUNDING_SOURCE,
    OPEN_INTEREST_SOURCE,
    DeltaFundingRateConnector,
    DeltaOpenInterestConnector,
)
from app.connectors.errors import ConnectorAPIError, ConnectorNetworkError, ConnectorRateLimitError
from app.integrations.delta import get_delta_client

Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]

#: 2026-01-01 00:00:00 UTC, a funding time (a multiple of 28,800 s).
T0 = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
HOUR = 3600


def candle(seconds: int, *, open_: str, close: str | None = None) -> dict[str, object]:
    return {
        "time": seconds,
        "open": open_,
        "high": open_,
        "low": open_,
        "close": close if close is not None else open_,
        "volume": None,
    }


def funding_connector(handler: Handler) -> DeltaFundingRateConnector:
    client = get_delta_client(transport=httpx.MockTransport(handler), retry_backoff=0.01)
    return DeltaFundingRateConnector(client=client)


def oi_connector(handler: Handler) -> DeltaOpenInterestConnector:
    client = get_delta_client(transport=httpx.MockTransport(handler), retry_backoff=0.01)
    return DeltaOpenInterestConnector(client=client)


def utc(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


@pytest.mark.asyncio
class TestFundingRate:
    async def test_percent_is_converted_to_a_fraction_exactly_once(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": True, "result": [candle(T0, open_="0.01")]})

        async with funding_connector(handler) as connector:
            points = await connector.fetch(utc(T0), utc(T0))

        assert len(points) == 1
        assert points[0].timestamp == utc(T0)
        assert points[0].value == pytest.approx(0.0001)  # 0.01% -> 0.0001
        assert points[0].symbol is None

    async def test_requests_the_funding_prefixed_symbol(self) -> None:
        seen: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.params["symbol"])
            return httpx.Response(200, json={"success": True, "result": []})

        async with funding_connector(handler) as connector:
            await connector.fetch(utc(T0), utc(T0 + HOUR))
        assert seen == ["FUNDING:ETHUSD"]

    async def test_a_constant_stretch_is_stored_only_at_funding_times(self) -> None:
        """Hourly candles of a step series: the value is stored at the boundary
        (T0), not at every one of the seven constant hours after it."""
        candles = [candle(T0 + i * HOUR, open_="0.01") for i in range(8)]
        candles.append(candle(T0 + 8 * HOUR, open_="0.01"))  # next funding time

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": True, "result": list(reversed(candles))})

        async with funding_connector(handler) as connector:
            points = await connector.fetch(utc(T0), utc(T0 + 8 * HOUR))

        assert [p.timestamp for p in points] == [utc(T0), utc(T0 + 8 * HOUR)]

    async def test_an_off_boundary_change_is_stored_at_the_moment_it_happened(self) -> None:
        candles = [
            candle(T0, open_="0.01"),
            candle(T0 + HOUR, open_="0.01"),
            candle(T0 + 2 * HOUR, open_="0.02"),  # off-boundary change (2024-11-29 style)
            candle(T0 + 3 * HOUR, open_="0.02"),
        ]

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": True, "result": candles})

        async with funding_connector(handler) as connector:
            points = await connector.fetch(utc(T0), utc(T0 + 3 * HOUR))

        assert [(p.timestamp, p.value) for p in points] == [
            (utc(T0), pytest.approx(0.0001)),
            (utc(T0 + 2 * HOUR), pytest.approx(0.0002)),
        ]

    async def test_the_first_value_is_kept_even_when_it_is_not_on_a_boundary(self) -> None:
        """A backfill that starts mid-interval must not lose its opening value."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"success": True, "result": [candle(T0 + 3 * HOUR, open_="0.01")]}
            )

        async with funding_connector(handler) as connector:
            points = await connector.fetch(utc(T0 + 3 * HOUR), utc(T0 + 3 * HOUR))
        assert len(points) == 1

    async def test_negative_and_zero_rates_survive(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": [
                        candle(T0, open_="-0.0123"),
                        candle(T0 + 8 * HOUR, open_="0"),
                    ],
                },
            )

        async with funding_connector(handler) as connector:
            points = await connector.fetch(utc(T0), utc(T0 + 8 * HOUR))
        assert [p.value for p in points] == [pytest.approx(-0.000123), 0.0]

    async def test_a_long_range_is_split_into_bounded_requests_and_deduplicated(self) -> None:
        """Delta caps a request; a 4,000-hour range must be several calls, and a
        candle on a chunk boundary must not be emitted twice."""
        calls: list[tuple[int, int]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            start = int(request.url.params["start"])
            end = int(request.url.params["end"])
            calls.append((start, end))
            assert (end - start) / HOUR <= 2000  # inside Delta's per-request cap
            times = range(start - start % HOUR + (HOUR if start % HOUR else 0), end, HOUR)
            return httpx.Response(
                200, json={"success": True, "result": [candle(t, open_="0.01") for t in times]}
            )

        async with funding_connector(handler) as connector:
            points = await connector.fetch(utc(T0), utc(T0 + 4_000 * HOUR))

        assert len(calls) >= 3
        stamps = [p.timestamp for p in points]
        assert stamps == sorted(set(stamps))  # ascending, no duplicates
        assert stamps[0] == utc(T0)
        assert all(int(s.timestamp()) % 28_800 == 0 for s in stamps)

    async def test_naive_datetimes_and_reversed_ranges_are_rejected(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": True, "result": []})

        async with funding_connector(handler) as connector:
            with pytest.raises(ValueError, match="timezone-aware"):
                await connector.fetch(datetime(2026, 1, 1), datetime(2026, 1, 2))
            with pytest.raises(ValueError, match="before start"):
                await connector.fetch(utc(T0 + HOUR), utc(T0))

    async def test_metadata_declares_the_real_cadence(self) -> None:
        metadata = DeltaFundingRateConnector.metadata
        assert metadata.source == FUNDING_SOURCE
        assert metadata.expected_interval_seconds == 28_800
        assert metadata.requires_auth is False


@pytest.mark.asyncio
class TestOpenInterest:
    async def test_the_value_is_the_candles_open_not_its_close(self) -> None:
        """The candle for hour `t` closes at `t + 1h`; only its open is knowable at `t`."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"success": True, "result": [candle(T0, open_="15000", close="99999")]},
            )

        async with oi_connector(handler) as connector:
            points = await connector.fetch(utc(T0), utc(T0))

        assert len(points) == 1
        assert points[0].value == 15000.0
        assert points[0].timestamp == utc(T0)
        assert 99999.0 not in [p.value for p in points]

    async def test_requests_the_oi_prefixed_symbol_and_returns_every_hour_ascending(self) -> None:
        seen: list[str] = []
        times = [T0 + i * HOUR for i in range(5)]

        async def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.params["symbol"])
            payload = [candle(t, open_=str(15000 + i)) for i, t in enumerate(times)]
            return httpx.Response(200, json={"success": True, "result": list(reversed(payload))})

        async with oi_connector(handler) as connector:
            points = await connector.fetch(utc(T0), utc(T0 + 4 * HOUR))

        assert seen == ["OI:ETHUSD"]
        assert [p.timestamp for p in points] == [utc(t) for t in times]
        assert [p.value for p in points] == [15000.0, 15001.0, 15002.0, 15003.0, 15004.0]

    async def test_metadata(self) -> None:
        metadata = DeltaOpenInterestConnector.metadata
        assert metadata.source == OPEN_INTEREST_SOURCE
        assert metadata.expected_interval_seconds == 3_600


@pytest.mark.asyncio
class TestErrorMapping:
    """Delta's own exceptions surface as the connector framework's errors, so the
    sync scheduler and the health monitor treat these like every other source."""

    async def test_rate_limit(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "1"}, json={"success": False})

        client = get_delta_client(
            transport=httpx.MockTransport(handler), max_retries=0, retry_backoff=0.01
        )
        async with DeltaOpenInterestConnector(client=client) as connector:
            with pytest.raises(ConnectorRateLimitError):
                await connector.fetch(utc(T0), utc(T0 + HOUR))

    async def test_server_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"success": False, "error": {"code": "bad"}})

        async with funding_connector(handler) as connector:
            with pytest.raises(ConnectorAPIError):
                await connector.fetch(utc(T0), utc(T0 + HOUR))

    async def test_network_failure(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        client = get_delta_client(
            transport=httpx.MockTransport(handler), max_retries=0, retry_backoff=0.01
        )
        async with DeltaFundingRateConnector(client=client) as connector:
            with pytest.raises(ConnectorNetworkError):
                await connector.fetch(utc(T0), utc(T0 + HOUR))

    async def test_a_non_list_body_is_an_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"success": True, "result": {"not": "a list"}})

        async with oi_connector(handler) as connector:
            with pytest.raises(ConnectorAPIError):
                await connector.fetch(utc(T0), utc(T0 + HOUR))


class TestRegistration:
    def test_both_sources_are_discoverable_and_the_registry_builds_them(self) -> None:
        from app.connectors import load_builtin_connectors
        from app.connectors.registry import default_registry

        load_builtin_connectors()
        assert FUNDING_SOURCE in default_registry.names()
        assert OPEN_INTEREST_SOURCE in default_registry.names()
        assert default_registry.describe(FUNDING_SOURCE).label == "ETHUSD Funding Rate"
        assert default_registry.describe(OPEN_INTEREST_SOURCE).label == "ETHUSD Open Interest"


def test_chunk_size_stays_inside_deltas_request_cap() -> None:
    from app.connectors import delta_market_data

    span = delta_market_data.REQUEST_SPAN
    assert span < timedelta(hours=2_000)
