"""Async HTTP client for the Delta Exchange REST API.

Provides connection pooling, HMAC request signing, bounded retries with
exponential backoff, response validation, structured logging, and typed
error mapping. No business logic or persistence lives here.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import random
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TypeVar
from urllib.parse import urlencode

import httpx
from pydantic import ValidationError

from app.integrations.delta.config import DeltaConfig, get_delta_config
from app.integrations.delta.exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    RateLimitError,
)
from app.integrations.delta.models import DeltaResponse

logger = logging.getLogger("app.integrations.delta")

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 0.5
_MAX_RETRY_DELAY = 30.0
_USER_AGENT = "eth-ai-platform/0.1.0"

T = TypeVar("T")


class DeltaClient:
    """Async REST client for the Delta Exchange API.

    Wraps an ``httpx.AsyncClient`` configured for connection pooling and
    a configurable timeout. Retries idempotent requests on rate limits and
    server errors, and any request on transient transport errors.
    """

    def __init__(
        self,
        config: DeltaConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        limits: httpx.Limits | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = DEFAULT_RETRY_BACKOFF,
    ) -> None:
        """Initialize the client.

        Args:
            config: Validated client configuration.
            transport: Optional transport override (e.g. ``httpx.MockTransport``).
            limits: Connection pool limits; sensible defaults when omitted.
            max_retries: Maximum retries for transient failures.
            retry_backoff: Base backoff seconds (doubles per retry).
        """
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if retry_backoff <= 0:
            raise ValueError("retry_backoff must be positive")

        self._config = config
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff

        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.request_timeout),
            limits=limits or httpx.Limits(max_connections=10, max_keepalive_connections=5),
            transport=transport,
            headers={
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/json",
            },
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
        json_body: object | None = None,
        response_model: type[T] | None = None,
        auth: bool = False,
    ) -> object:
        """Perform a Delta API request and return the validated ``result``.

        Args:
            method: HTTP method (``GET``, ``POST``, ...).
            path: Full API path including the ``/v2`` prefix, e.g. ``/v2/products``.
            params: Optional query parameters (sorted before signing and sending).
            json_body: Optional JSON-serializable request body.
            response_model: Pydantic model (or ``list[...]``) to validate the
                envelope ``result`` against.
            auth: Sign the request with the configured API credentials.

        Returns:
            The envelope ``result`` field, validated by ``response_model``
            when one is given.
        """
        result = await self._execute(method, path, params=params, json_body=json_body, auth=auth)
        if response_model is None:
            return result
        model_validate = getattr(response_model, "model_validate", None)
        if model_validate is None:
            return result
        try:
            return model_validate(result)
        except ValidationError as exc:
            name = getattr(response_model, "__name__", str(response_model))
            raise APIError(
                f"Delta response does not match {name}",
                detail=exc.errors(include_url=False),
            ) from exc

    async def get(
        self,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
        response_model: type[T] | None = None,
        auth: bool = False,
    ) -> object:
        """Perform a ``GET`` request."""
        return await self.request(
            "GET",
            path,
            params=params,
            response_model=response_model,
            auth=auth,
        )

    async def post(
        self,
        path: str,
        *,
        json_body: object | None = None,
        response_model: type[T] | None = None,
        auth: bool = False,
    ) -> object:
        """Perform a ``POST`` request."""
        return await self.request(
            "POST",
            path,
            json_body=json_body,
            response_model=response_model,
            auth=auth,
        )

    async def aclose(self) -> None:
        """Close the underlying httpx client, releasing pooled connections."""
        await self._client.aclose()

    async def __aenter__(self) -> "DeltaClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        await self.aclose()

    async def _execute(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, object] | None,
        json_body: object | None,
        auth: bool,
    ) -> object:
        """Send one request with retries; return the parsed envelope result."""
        headers, url, content = self._prepare_request(method, path, params, json_body, auth)
        attempt = 0

        while True:
            started = time.perf_counter()
            try:
                response = await self._client.request(method, url, headers=headers, content=content)
            except httpx.TimeoutException as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "Delta %s %s timed out on attempt %d (%.1fms)",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                )
                if attempt >= self._max_retries:
                    raise NetworkError(
                        f"Delta request timed out: {method} {path}",
                        detail=str(exc),
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue
            except httpx.TransportError as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "Delta %s %s transport error on attempt %d (%.1fms): %s",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                    exc,
                )
                if attempt >= self._max_retries:
                    raise NetworkError(
                        f"Delta network failure for {method} {path}: {exc}",
                        detail=str(exc),
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue

            latency_ms = (time.perf_counter() - started) * 1000
            status = response.status_code
            logger.info("Delta %s %s -> %d (%.1fms)", method, path, status, latency_ms)

            if (
                status in RETRYABLE_STATUS_CODES
                and method in IDEMPOTENT_METHODS
                and attempt < self._max_retries
            ):
                delay = self._retry_delay(status, response, attempt)
                logger.warning(
                    "Delta retrying %s %s after %d in %.2fs (attempt %d/%d)",
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
        """Map an HTTP response to a result or a typed exception."""
        status = response.status_code

        if status == 429:
            raise RateLimitError(
                f"Delta rate limit exceeded for {method} {path}",
                retry_after=self._parse_retry_after(response),
                status_code=status,
            )
        if status in (401, 403):
            raise AuthenticationError(
                f"Delta authentication failed for {method} {path}",
                status_code=status,
                detail=self._error_payload(response),
            )

        payload = self._json_payload(response)
        if payload is None:
            if status >= 400:
                raise APIError(
                    f"Delta request failed with HTTP {status} for {method} {path}",
                    status_code=status,
                )
            raise APIError(
                f"Malformed Delta response for {method} {path}: body is not valid JSON",
                status_code=status,
            )
        if not isinstance(payload, dict):
            raise APIError(
                f"Malformed Delta response for {method} {path}: expected object envelope",
                status_code=status,
                detail=payload,
            )

        try:
            envelope = DeltaResponse.model_validate(payload)
        except ValidationError as exc:
            raise APIError(
                f"Malformed Delta response envelope for {method} {path}",
                status_code=status,
                detail=exc.errors(include_url=False),
            ) from exc

        if not envelope.success:
            error = envelope.error
            fallback = f"Delta API error for {method} {path}"
            message = (error.message or fallback) if error is not None else fallback
            raise APIError(
                message,
                status_code=status,
                detail=error.model_dump() if error is not None else payload,
            )

        if status >= 400:
            raise APIError(
                f"Delta request failed with HTTP {status} for {method} {path}",
                status_code=status,
                detail=payload,
            )

        return envelope.result

    def _prepare_request(
        self,
        method: str,
        path: str,
        params: Mapping[str, object] | None,
        json_body: object | None,
        auth: bool,
    ) -> tuple[dict[str, str], str, str | None]:
        """Build headers, URL, and body; the query string is deterministic."""
        query_string = self._build_query_string(params)
        url = f"{path}{query_string}"

        content: str | None = None
        if json_body is not None:
            content = json.dumps(json_body, separators=(",", ":"))

        headers: dict[str, str] = {}
        if auth:
            if not self._config.api_key or not self._config.api_secret:
                raise AuthenticationError(
                    "Delta API credentials required for authenticated requests "
                    "(set DELTA_API_KEY / DELTA_API_SECRET)"
                )
            headers.update(self._signing_headers(method, path, query_string, content))

        return headers, url, content

    def _signing_headers(
        self,
        method: str,
        path: str,
        query_string: str,
        body: str | None,
    ) -> dict[str, str]:
        """Build Delta authentication headers via HMAC-SHA256 signing.

        Signature payload: ``method + timestamp + path + query + body``.
        """
        timestamp = str(int(time.time()))
        message = f"{method}{timestamp}{path}{query_string}{body or ''}"
        digest = hmac.new(
            self._config.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {"api-key": self._config.api_key, "timestamp": timestamp, "signature": digest}

    @staticmethod
    def _build_query_string(params: Mapping[str, object] | None) -> str:
        """URL-encode query params in sorted key order so the signature matches."""
        if not params:
            return ""
        items = [(str(key), str(value)) for key, value in sorted(params.items())]
        return f"?{urlencode(items)}"

    def _retry_delay(self, status: int, response: httpx.Response, attempt: int) -> float:
        """Compute the delay before the next attempt (Retry-After aware)."""
        if status == 429:
            retry_after = self._parse_retry_after(response)
            if retry_after is not None:
                return min(max(retry_after, 0.0), _MAX_RETRY_DELAY)
        return min(self._retry_backoff * (2**attempt), _MAX_RETRY_DELAY)

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float | None:
        """Parse ``Retry-After`` as seconds or HTTP-date."""
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            pass
        try:
            when = parsedate_to_datetime(value)
            return max(0.0, (when - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _json_payload(response: httpx.Response) -> object | None:
        """Return the decoded JSON body, or None when it is not valid JSON."""
        try:
            return response.json()
        except ValueError:
            return None

    @staticmethod
    def _error_payload(response: httpx.Response) -> object | None:
        """Best-effort decoded body for errors; never raises."""
        try:
            return response.json()
        except ValueError:
            return None

    async def _backoff(self, attempt: int) -> None:
        """Sleep for the exponential backoff of the current attempt."""
        delay = min(self._retry_backoff * (2**attempt), _MAX_RETRY_DELAY)
        await self._sleep(delay)

    @staticmethod
    async def _sleep(delay: float) -> None:
        """Sleep with a small jitter to desynchronize retry waves."""
        jittered = delay * (1.0 + random.random() * 0.1)
        await asyncio.sleep(jittered)


def get_delta_client(
    config: DeltaConfig | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    limits: httpx.Limits | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
) -> DeltaClient:
    """Return a configured Delta client.

    Use it as an async context manager (``async with``) so pooled connections
    are always released, or call :meth:`DeltaClient.aclose` explicitly.
    """
    resolved = config if config is not None else get_delta_config()
    return DeltaClient(
        resolved,
        transport=transport,
        limits=limits,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
    )
