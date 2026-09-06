"""Unit tests for the Etherscan connector using mocked transports —
mirrors `tests/connectors/test_fred.py`'s own conventions
(`httpx.MockTransport`, fast retry backoff for the failure-path tests),
adapted for Etherscan's own real, verified error shape: every response is
HTTP 200, and real errors live in the JSON body (`status`/`message`
/`result`), never the status code.
"""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta

import httpx
import pytest

import app.connectors.etherscan as etherscan_module
from app.connectors.base import RawDataPoint
from app.connectors.errors import (
    ConnectorAPIError,
    ConnectorAuthenticationError,
    ConnectorNetworkError,
    ConnectorRateLimitError,
)
from app.connectors.etherscan import EtherscanClient, EtherscanConnector

Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]

FIXED_NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)


class FakeDatetime(datetime):
    """datetime with a frozen ``now()`` for deterministic connector tests."""

    @classmethod
    def now(cls, tz=None):  # noqa: D102
        return FIXED_NOW


#: A real Etherscan V2 Gas Oracle response shape, verified live against
#: the real API (see `app/connectors/etherscan.py`'s own module
#: docstring).
_REAL_SHAPED_RESULT = {
    "LastBlock": "23467872",
    "SafeGasPrice": "0.496839934",
    "ProposeGasPrice": "0.496840168",
    "FastGasPrice": "0.55411917",
    "suggestBaseFee": "0.496839934",
    "gasUsedRatio": "0.5,0.5,0.4,0.4,0.4",
}


def client_for(
    handler: Handler,
    *,
    api_key: str = "test-key",
    max_retries: int = 3,
    retry_backoff: float = 0.01,
) -> EtherscanClient:
    """Build an EtherscanClient over a mocked transport using fast backoff."""
    transport = httpx.MockTransport(handler)
    return EtherscanClient(
        transport=transport, api_key=api_key, max_retries=max_retries, retry_backoff=retry_backoff
    )


@pytest.mark.asyncio
class TestEtherscanClient:
    async def test_successful_fetch_returns_the_raw_result_object(self) -> None:
        captured: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(
                200, json={"status": "1", "message": "OK", "result": _REAL_SHAPED_RESULT}
            )

        client = client_for(handler)
        async with client:
            result = await client.fetch_gas_oracle()

        assert result == _REAL_SHAPED_RESULT
        assert "chainid=1" in str(captured["url"])
        assert "module=gastracker" in str(captured["url"])
        assert "action=gasoracle" in str(captured["url"])
        assert "apikey=test-key" in str(captured["url"])

    async def test_no_api_key_raises_authentication_error_with_no_request(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made with no API key configured")

        client = client_for(never_called, api_key="")
        async with client:
            with pytest.raises(ConnectorAuthenticationError):
                await client.fetch_gas_oracle()

    async def test_bad_api_key_raises_authentication_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"status": "0", "message": "NOTOK", "result": "Missing/Invalid API Key"}
            )

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorAuthenticationError):
                await client.fetch_gas_oracle()

    async def test_an_unrelated_status_zero_raises_api_error_not_misreported(self) -> None:
        """A `status: "0"` failure whose `result` names neither a rate
        limit nor an API key issue is a generic API error — proven
        distinct from the other two typed errors, not lumped in with
        either by an over-eager substring match."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"status": "0", "message": "NOTOK", "result": "Error! Invalid chainid"}
            )

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorAPIError) as exc_info:
                await client.fetch_gas_oracle()
        assert not isinstance(exc_info.value, ConnectorAuthenticationError)
        assert not isinstance(exc_info.value, ConnectorRateLimitError)

    async def test_malformed_response_non_json_body_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"this-is-not-json{{{")

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_gas_oracle()

    async def test_malformed_response_non_object_envelope_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[1, 2, 3])

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_gas_oracle()

    async def test_malformed_response_non_object_result_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"status": "1", "message": "OK", "result": "not-an-object"}
            )

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_gas_oracle()

    async def test_network_failure_timeout_raises_network_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("read timed out after 5s")

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorNetworkError):
                await client.fetch_gas_oracle()

    async def test_network_failure_connect_error_is_retried_then_raises(self) -> None:
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            raise httpx.ConnectError("connection refused")

        client = client_for(handler, max_retries=2)
        async with client:
            with pytest.raises(ConnectorNetworkError):
                await client.fetch_gas_oracle()

        assert calls["count"] == 3  # initial attempt + 2 retries

    async def test_rate_limit_retries_then_succeeds(self) -> None:
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] == 1:
                return httpx.Response(
                    200,
                    json={"status": "0", "message": "NOTOK", "result": "Max rate limit reached"},
                )
            return httpx.Response(
                200, json={"status": "1", "message": "OK", "result": _REAL_SHAPED_RESULT}
            )

        client = client_for(handler, max_retries=2)
        async with client:
            result = await client.fetch_gas_oracle()

        assert result == _REAL_SHAPED_RESULT
        assert calls["count"] == 2

    async def test_rate_limit_exhausted_raises_rate_limit_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"status": "0", "message": "NOTOK", "result": "Max rate limit reached"}
            )

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorRateLimitError):
                await client.fetch_gas_oracle()


@pytest.mark.asyncio
class TestEtherscanConnector:
    async def test_fetch_returns_the_current_value_timestamped_now(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(etherscan_module, "datetime", FakeDatetime)

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"status": "1", "message": "OK", "result": _REAL_SHAPED_RESULT}
            )

        client = client_for(handler)
        connector = EtherscanConnector(client=client)
        async with connector:
            points = await connector.fetch(
                FIXED_NOW.replace(hour=0), FIXED_NOW.replace(hour=23, minute=59)
            )

        assert points == (
            RawDataPoint(
                timestamp=FIXED_NOW,
                value=0.496840168,
                symbol=None,
                raw_payload=_REAL_SHAPED_RESULT,
            ),
        )

    async def test_fetch_excludes_the_point_when_now_is_outside_the_requested_range(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The load-bearing proof of this connector's own disclosed
        limitation: there is no way to answer for a range that has
        already closed in the past — an honest empty result, never a
        fabricated point."""
        monkeypatch.setattr(etherscan_module, "datetime", FakeDatetime)

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"status": "1", "message": "OK", "result": _REAL_SHAPED_RESULT}
            )

        client = client_for(handler)
        connector = EtherscanConnector(client=client)
        async with connector:
            points = await connector.fetch(
                datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 1, 2, tzinfo=UTC)
            )

        assert points == ()

    async def test_fetch_accepts_a_point_observed_shortly_after_a_stale_end(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reproduces a real bug, only ever caught by running the real
        scheduler path against the live API: `ExternalDataSyncScheduler
        .run_catch_up` captures one `now` and threads `end=now` through an
        async chain (a DB query, other sources' own real HTTP calls in
        the same tick) before this connector's own request even starts —
        so the point (always timestamped *after* its own HTTP round trip)
        is observed strictly after that stale `end` by construction, every
        single time. A real manual poll run immediately after this
        connector was first written confirmed it live: `received=0`, not
        the expected single point. `end` here is deliberately set 30
        seconds *before* `FIXED_NOW` (the point's own timestamp) to model
        exactly that gap; `_END_GRACE_PERIOD` must absorb it."""
        monkeypatch.setattr(etherscan_module, "datetime", FakeDatetime)

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"status": "1", "message": "OK", "result": _REAL_SHAPED_RESULT}
            )

        client = client_for(handler)
        connector = EtherscanConnector(client=client)
        async with connector:
            points = await connector.fetch(
                FIXED_NOW - timedelta(hours=1), FIXED_NOW - timedelta(seconds=30)
            )

        assert points == (
            RawDataPoint(
                timestamp=FIXED_NOW,
                value=0.496840168,
                symbol=None,
                raw_payload=_REAL_SHAPED_RESULT,
            ),
        )

    async def test_fetch_still_excludes_a_point_observed_well_beyond_the_grace_period(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The grace period has a real edge, not an unbounded one: a
        genuinely historical `end` (here, 10 minutes before `FIXED_NOW`,
        comfortably beyond `_END_GRACE_PERIOD`'s 5 minutes) is still
        correctly rejected, not silently accepted by an overly generous
        fix."""
        monkeypatch.setattr(etherscan_module, "datetime", FakeDatetime)

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"status": "1", "message": "OK", "result": _REAL_SHAPED_RESULT}
            )

        client = client_for(handler)
        connector = EtherscanConnector(client=client)
        async with connector:
            points = await connector.fetch(
                FIXED_NOW - timedelta(hours=1), FIXED_NOW - timedelta(minutes=10)
            )

        assert points == ()

    async def test_malformed_result_missing_value_field_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"status": "1", "message": "OK", "result": {"LastBlock": "1"}}
            )

        client = client_for(handler)
        connector = EtherscanConnector(client=client)
        async with connector:
            with pytest.raises(ConnectorAPIError):
                await connector.fetch(
                    datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
                )

    async def test_rejects_naive_datetimes(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid range")

        connector = EtherscanConnector(client=client_for(never_called))
        with pytest.raises(ValueError, match="timezone-aware"):
            await connector.fetch(datetime(2026, 1, 1), datetime(2026, 1, 2, tzinfo=UTC))

    async def test_rejects_end_before_start(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid range")

        connector = EtherscanConnector(client=client_for(never_called))
        with pytest.raises(ValueError, match="end must not be before start"):
            await connector.fetch(
                datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)
            )
