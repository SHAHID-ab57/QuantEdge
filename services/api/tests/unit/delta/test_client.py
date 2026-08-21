"""Unit tests for the Delta Exchange HTTP client using mocked transports."""

import logging
from collections.abc import Callable, Coroutine

import httpx
import pytest
from pydantic import BaseModel

from app.integrations.delta.client import DeltaClient
from app.integrations.delta.config import DeltaConfig
from app.integrations.delta.exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    RateLimitError,
)


class Product(BaseModel):
    """Small response model used to exercise response validation."""

    id: int
    symbol: str


Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]


def public_config() -> DeltaConfig:
    """A config without credentials for public-endpoint tests."""
    return DeltaConfig(
        base_url="https://api.india.delta.exchange",
        api_key="",
        api_secret="",
        request_timeout=5.0,
    )


def authed_config() -> DeltaConfig:
    """A config with placeholder credentials (never real secrets)."""
    return DeltaConfig(
        base_url="https://api.india.delta.exchange",
        api_key="placeholder-delta-api-key",
        api_secret="placeholder-delta-api-secret",
        request_timeout=5.0,
    )


def client_for(
    handler: Handler,
    *,
    config: DeltaConfig | None = None,
    max_retries: int = 3,
    retry_backoff: float = 0.01,
) -> DeltaClient:
    """Build a DeltaClient over a mocked transport using fast backoff."""
    transport = httpx.MockTransport(handler)
    return DeltaClient(
        config or public_config(),
        transport=transport,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
    )


@pytest.mark.asyncio
async def test_success_returns_validated_model() -> None:
    """A 200 envelope with a matching result validates into the model."""
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"success": True, "result": {"id": 27, "symbol": "BTCUSD"}},
        )

    client = client_for(handler)
    async with client:
        product = await client.request(
            "GET", "/v2/products", params={"id": 27}, response_model=Product
        )

    assert product == Product(id=27, symbol="BTCUSD")
    assert captured["url"] == "https://api.india.delta.exchange/v2/products?id=27"


@pytest.mark.asyncio
async def test_get_helper_returns_raw_result() -> None:
    """Without a response_model the envelope result is returned as-is."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "result": [{"id": 1}, {"id": 2}]})

    client = client_for(handler)
    async with client:
        result = await client.get("/v2/products")

    assert result == [{"id": 1}, {"id": 2}]


@pytest.mark.asyncio
async def test_malformed_body_raises_api_error() -> None:
    """Non-JSON bodies raise APIError regardless of HTTP status."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"this-is-not-json{{{")

    client = client_for(handler)
    async with client:
        with pytest.raises(APIError):
            await client.get("/v2/products")


@pytest.mark.asyncio
async def test_error_envelope_in_200_raises_api_error() -> None:
    """An HTTP 200 carrying success=false maps to APIError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "error": {"code": 601, "message": "Not found"}},
        )

    client = client_for(handler)
    async with client:
        with pytest.raises(APIError) as excinfo:
            await client.get("/v2/products")

    assert excinfo.value.status_code == 200
    assert excinfo.value.detail == {"code": 601, "message": "Not found"}


@pytest.mark.asyncio
async def test_schema_mismatch_raises_api_error() -> None:
    """A result that fails model validation maps to APIError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"success": True, "result": {"id": "not-an-int", "symbol": 1}}
        )

    client = client_for(handler)
    async with client:
        with pytest.raises(APIError) as excinfo:
            await client.get("/v2/products", response_model=Product)

    assert "does not match Product" in str(excinfo.value)


@pytest.mark.asyncio
async def test_http_error_maps_to_api_error() -> None:
    """A non-retryable 4xx without a body maps to APIError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, content=b"bad request")

    client = client_for(handler)
    async with client:
        with pytest.raises(APIError) as excinfo:
            await client.get("/v2/products")

    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_rate_limit_retries_then_succeeds() -> None:
    """429 responses are retried until a success arrives."""
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(
                429,
                headers={"Retry-After": "1"},
                json={"success": False, "error": {"message": "Too Many Requests"}},
            )
        return httpx.Response(
            200,
            json={"success": True, "result": {"id": 1, "symbol": "ETHUSD"}},
        )

    client = client_for(handler, max_retries=3)
    async with client:
        product = await client.get("/v2/products", response_model=Product)

    assert calls["count"] == 3
    assert product == Product(id=1, symbol="ETHUSD")


@pytest.mark.asyncio
async def test_rate_limit_exhausted_raises_rate_limit_error() -> None:
    """When retries are exhausted, a Retry-After-aware RateLimitError is raised."""
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "2"},
            json={"success": False, "error": {"message": "Too Many Requests"}},
        )

    client = client_for(handler, max_retries=1)
    async with client:
        with pytest.raises(RateLimitError) as excinfo:
            await client.get("/v2/products")

    assert calls["count"] == 2
    assert excinfo.value.status_code == 429
    assert excinfo.value.retry_after == 2.0


@pytest.mark.asyncio
async def test_server_error_retries_then_succeeds() -> None:
    """Transient 5xx responses are retried for idempotent methods."""
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, content=b"service unavailable")
        return httpx.Response(
            200,
            json={"success": True, "result": {"id": 3, "symbol": "SOLUSD"}},
        )

    client = client_for(handler, max_retries=2)
    async with client:
        product = await client.get("/v2/products", response_model=Product)

    assert calls["count"] == 2
    assert product == Product(id=3, symbol="SOLUSD")


@pytest.mark.asyncio
async def test_timeout_raises_network_error() -> None:
    """Read timeouts surface as NetworkError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out after 5s")

    client = client_for(handler, max_retries=0)
    async with client:
        with pytest.raises(NetworkError):
            await client.get("/v2/products")


@pytest.mark.asyncio
async def test_transport_connect_error_is_retried_and_maps_to_network_error() -> None:
    """Connect failures are retried, then map to NetworkError."""
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.ConnectError("connection refused")

    client = client_for(handler, max_retries=2)
    async with client:
        with pytest.raises(NetworkError):
            await client.get("/v2/products")

    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_authenticated_request_sends_signed_headers() -> None:
    """Authenticated requests carry api-key, timestamp, and signature headers."""
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"success": True, "result": []})

    client = client_for(handler, config=authed_config())
    async with client:
        await client.get("/v2/orders", params={"state": "open"}, auth=True)

    headers = captured["headers"]

    assert isinstance(headers, dict)
    assert headers["api-key"] == "placeholder-delta-api-key"
    assert "signature" in headers
    assert "timestamp" in headers


@pytest.mark.asyncio
async def test_authenticated_request_without_keys_raises() -> None:
    """Requesting auth without configured credentials raises immediately."""
    sent = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        sent["count"] += 1
        return httpx.Response(200, json={"success": True, "result": []})

    client = client_for(handler, config=public_config())
    async with client:
        with pytest.raises(AuthenticationError):
            await client.get("/v2/orders", auth=True)

    assert sent["count"] == 0


@pytest.mark.asyncio
async def test_credentials_bad_signature_maps_to_authentication_error() -> None:
    """401 responses map to AuthenticationError."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"success": False, "error": {"message": "Invalid signature"}},
        )

    client = client_for(handler, config=authed_config())
    async with client:
        with pytest.raises(AuthenticationError) as excinfo:
            await client.get("/v2/orders", auth=True)

    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_logs_do_not_expose_secrets(caplog: pytest.LogCaptureFixture) -> None:
    """Request logs must never contain API credentials or signatures."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "result": []})

    client = client_for(handler, config=authed_config())
    with caplog.at_level(logging.INFO, logger="app.integrations.delta"):
        async with client:
            await client.get("/v2/orders", auth=True)

    caplog_text = caplog.text
    assert "placeholder-delta-api-key" not in caplog_text
    assert "placeholder-delta-api-secret" not in caplog_text
