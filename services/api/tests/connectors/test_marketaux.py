"""Unit tests for the Marketaux connector using mocked transports —
mirrors `tests/connectors/test_fred.py`'s own conventions (a hard-required
key, real-status-code error dispatch), adapted for Marketaux's own real,
verified shape: `{"meta": ..., "data": [...]}` pages, per-entity
sentiment, and pagination.
"""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime

import httpx
import pytest

from app.connectors.errors import (
    ConnectorAPIError,
    ConnectorAuthenticationError,
    ConnectorNetworkError,
    ConnectorRateLimitError,
)
from app.connectors.marketaux import MarketauxClient, MarketauxConnector

Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]

#: A real Marketaux article shape (trimmed), verified live/via docs —
#: `entities` deliberately includes only the queried symbol, since this
#: client always sends `filter_entities=true` (see bug pattern #1 in
#: `app.connectors.marketaux`'s own module docstring).
_REAL_SHAPED_ARTICLE = {
    "uuid": "9b9fb67e-9438-4263-815e-ef6a7d36af07",
    "title": "Bitcoin (BTC/USD), Ethereum (ETH/USD) Crushed as Cryptocurrency Market is "
    "Overrun by Sellers",
    "description": "The cryptocurrency market has been experiencing wild price swings.",
    "keywords": "",
    "snippet": "The cryptocurrency market has been experiencing wild price swings over the...",
    "url": "https://www.dailyfx.com/forex/market_alert/2021/02/23/example.html",
    "image_url": "https://a.c-dn.net/example.jpg",
    "language": "en",
    "published_at": "2024-11-08T01:24:00.000000Z",
    "source": "dailyfx.com",
    "relevance_score": None,
    "entities": [
        {
            "symbol": "ETHUSD",
            "name": "Ethereum USD",
            "exchange": "CC",
            "exchange_long": "Cryptocurrency",
            "country": "global",
            "type": "cryptocurrency",
            "industry": "N/A",
            "match_score": 34.29,
            "sentiment_score": -0.4215,
            "highlights": [
                {
                    "highlight": "Bitcoin (BTC/USD), Ethereum (ETH/USD) Crushed...",
                    "sentiment": -0.4215,
                    "highlighted_in": "title",
                }
            ],
        }
    ],
}


def _page(*articles: dict, found: int | None = None, limit: int = 3) -> dict:
    return {
        "meta": {
            "found": found if found is not None else len(articles),
            "returned": len(articles),
            "limit": limit,
            "page": 1,
        },
        "data": list(articles),
    }


def client_for(
    handler: Handler,
    *,
    api_key: str = "test-key",
    max_retries: int = 3,
    retry_backoff: float = 0.01,
) -> MarketauxClient:
    """Build a MarketauxClient over a mocked transport using fast backoff."""
    transport = httpx.MockTransport(handler)
    return MarketauxClient(
        transport=transport, api_key=api_key, max_retries=max_retries, retry_backoff=retry_backoff
    )


@pytest.mark.asyncio
class TestMarketauxClient:
    async def test_successful_fetch_returns_the_raw_page(self) -> None:
        captured: dict[str, str] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, json=_page(_REAL_SHAPED_ARTICLE))

        client = client_for(handler)
        async with client:
            payload = await client.fetch_page(
                symbols="ETHUSD",
                published_after=datetime(2024, 11, 1, tzinfo=UTC),
                published_before=datetime(2024, 11, 30, tzinfo=UTC),
                limit=3,
                page=1,
            )

        assert payload["data"] == [_REAL_SHAPED_ARTICLE]
        url = captured["url"]
        assert "symbols=ETHUSD" in url
        # The load-bearing proof of bug pattern #1: filter_entities=true is
        # always sent, never left to Marketaux's own false default.
        assert "filter_entities=true" in url
        assert "language=en" in url
        assert "api_token=test-key" in url

    async def test_no_api_key_raises_authentication_error_with_no_request(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made with no API key configured")

        client = client_for(never_called, api_key="")
        async with client:
            with pytest.raises(ConnectorAuthenticationError):
                await client.fetch_page(
                    symbols="ETHUSD",
                    published_after=datetime(2024, 11, 1, tzinfo=UTC),
                    published_before=datetime(2024, 11, 30, tzinfo=UTC),
                    limit=3,
                    page=1,
                )

    async def test_bad_api_key_raises_authentication_error(self) -> None:
        """Marketaux's own real response for a bad/missing key — verified
        live: HTTP 401, `{"error": {"code": "invalid_api_token", ...}}`."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json={
                    "error": {
                        "code": "invalid_api_token",
                        "message": "An invalid API token was supplied.",
                    }
                },
            )

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorAuthenticationError):
                await client.fetch_page(
                    symbols="ETHUSD",
                    published_after=datetime(2024, 11, 1, tzinfo=UTC),
                    published_before=datetime(2024, 11, 30, tzinfo=UTC),
                    limit=3,
                    page=1,
                )

    async def test_malformed_response_non_json_body_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"this-is-not-json{{{")

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_page(
                    symbols="ETHUSD",
                    published_after=datetime(2024, 11, 1, tzinfo=UTC),
                    published_before=datetime(2024, 11, 30, tzinfo=UTC),
                    limit=3,
                    page=1,
                )

    async def test_malformed_response_non_object_envelope_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[1, 2, 3])

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_page(
                    symbols="ETHUSD",
                    published_after=datetime(2024, 11, 1, tzinfo=UTC),
                    published_before=datetime(2024, 11, 30, tzinfo=UTC),
                    limit=3,
                    page=1,
                )

    async def test_malformed_response_missing_meta_or_data_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": True})

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_page(
                    symbols="ETHUSD",
                    published_after=datetime(2024, 11, 1, tzinfo=UTC),
                    published_before=datetime(2024, 11, 30, tzinfo=UTC),
                    limit=3,
                    page=1,
                )

    async def test_network_failure_timeout_raises_network_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("read timed out after 5s")

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorNetworkError):
                await client.fetch_page(
                    symbols="ETHUSD",
                    published_after=datetime(2024, 11, 1, tzinfo=UTC),
                    published_before=datetime(2024, 11, 30, tzinfo=UTC),
                    limit=3,
                    page=1,
                )

    async def test_network_failure_connect_error_is_retried_then_raises(self) -> None:
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            raise httpx.ConnectError("connection refused")

        client = client_for(handler, max_retries=2)
        async with client:
            with pytest.raises(ConnectorNetworkError):
                await client.fetch_page(
                    symbols="ETHUSD",
                    published_after=datetime(2024, 11, 1, tzinfo=UTC),
                    published_before=datetime(2024, 11, 30, tzinfo=UTC),
                    limit=3,
                    page=1,
                )

        assert calls["count"] == 3  # initial attempt + 2 retries

    async def test_rate_limit_retries_then_succeeds(self) -> None:
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] == 1:
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, json=_page(_REAL_SHAPED_ARTICLE))

        client = client_for(handler, max_retries=2)
        async with client:
            payload = await client.fetch_page(
                symbols="ETHUSD",
                published_after=datetime(2024, 11, 1, tzinfo=UTC),
                published_before=datetime(2024, 11, 30, tzinfo=UTC),
                limit=3,
                page=1,
            )

        assert payload["data"] == [_REAL_SHAPED_ARTICLE]
        assert calls["count"] == 2

    async def test_rate_limit_exhausted_raises_rate_limit_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "0"})

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorRateLimitError):
                await client.fetch_page(
                    symbols="ETHUSD",
                    published_after=datetime(2024, 11, 1, tzinfo=UTC),
                    published_before=datetime(2024, 11, 30, tzinfo=UTC),
                    limit=3,
                    page=1,
                )


@pytest.mark.asyncio
class TestMarketauxConnectorFetchArticles:
    async def test_maps_article_computing_mean_sentiment_across_entities(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_page(_REAL_SHAPED_ARTICLE))

        client = client_for(handler)
        connector = MarketauxConnector(client=client, symbols="ETHUSD")
        async with connector:
            articles = await connector.fetch_articles(
                datetime(2024, 11, 1, tzinfo=UTC), datetime(2024, 11, 30, tzinfo=UTC)
            )

        assert len(articles) == 1
        article = articles[0]
        assert article.marketaux_uuid == "9b9fb67e-9438-4263-815e-ef6a7d36af07"
        assert article.headline.startswith("Bitcoin (BTC/USD)")
        assert article.source == "dailyfx.com"
        assert article.sentiment_score == pytest.approx(-0.4215)
        assert article.symbols == ("ETHUSD",)
        assert article.published_at == datetime(2024, 11, 8, 1, 24, 0, tzinfo=UTC)

    async def test_mean_sentiment_across_multiple_entities_is_averaged(self) -> None:
        article = {
            **_REAL_SHAPED_ARTICLE,
            "uuid": "second-article",
            "entities": [
                {**_REAL_SHAPED_ARTICLE["entities"][0], "symbol": "ETHUSD", "sentiment_score": 0.5},
                {
                    **_REAL_SHAPED_ARTICLE["entities"][0],
                    "symbol": "BTCUSD",
                    "sentiment_score": -0.3,
                },
            ],
        }

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_page(article))

        client = client_for(handler)
        connector = MarketauxConnector(client=client, symbols="ETHUSD,BTCUSD")
        async with connector:
            articles = await connector.fetch_articles(
                datetime(2024, 11, 1, tzinfo=UTC), datetime(2024, 11, 30, tzinfo=UTC)
            )

        assert articles[0].sentiment_score == pytest.approx(0.1)
        assert set(articles[0].symbols) == {"ETHUSD", "BTCUSD"}

    async def test_article_with_no_scored_entity_has_null_sentiment(self) -> None:
        article = {
            **_REAL_SHAPED_ARTICLE,
            "uuid": "no-score-article",
            "entities": [{**_REAL_SHAPED_ARTICLE["entities"][0], "sentiment_score": None}],
        }

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_page(article))

        client = client_for(handler)
        connector = MarketauxConnector(client=client, symbols="ETHUSD")
        async with connector:
            articles = await connector.fetch_articles(
                datetime(2024, 11, 1, tzinfo=UTC), datetime(2024, 11, 30, tzinfo=UTC)
            )

        assert articles[0].sentiment_score is None

    async def test_paginates_until_a_page_returns_fewer_than_the_limit(self) -> None:
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            page_num = calls["count"]
            if page_num < 3:
                article = {**_REAL_SHAPED_ARTICLE, "uuid": f"article-{page_num}"}
                return httpx.Response(200, json=_page(article, found=7, limit=1))
            # Final, partial page — signals no more results.
            return httpx.Response(
                200, json={"meta": {"found": 7, "returned": 0, "limit": 1, "page": 3}, "data": []}
            )

        client = client_for(handler)
        connector = MarketauxConnector(client=client, symbols="ETHUSD", articles_per_page=1)
        async with connector:
            articles = await connector.fetch_articles(
                datetime(2024, 11, 1, tzinfo=UTC), datetime(2024, 11, 30, tzinfo=UTC)
            )

        assert len(articles) == 2
        assert calls["count"] == 3

    async def test_stops_at_max_pages_per_fetch_even_if_more_results_exist(self) -> None:
        """The real, free-tier-driven safety cap — never spend an
        unbounded number of the day's own 100 requests chasing an
        unusually newsy window."""
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            article = {**_REAL_SHAPED_ARTICLE, "uuid": f"article-{calls['count']}"}
            # Always a full page — implies more results might exist.
            return httpx.Response(200, json=_page(article, found=1000, limit=1))

        client = client_for(handler)
        connector = MarketauxConnector(
            client=client, symbols="ETHUSD", articles_per_page=1, max_pages=4
        )
        async with connector:
            articles = await connector.fetch_articles(
                datetime(2024, 11, 1, tzinfo=UTC), datetime(2024, 11, 30, tzinfo=UTC)
            )

        assert calls["count"] == 4
        assert len(articles) == 4

    async def test_excludes_articles_outside_the_requested_range(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_page(_REAL_SHAPED_ARTICLE))

        client = client_for(handler)
        connector = MarketauxConnector(client=client, symbols="ETHUSD")
        async with connector:
            articles = await connector.fetch_articles(
                datetime(2024, 12, 1, tzinfo=UTC), datetime(2024, 12, 31, tzinfo=UTC)
            )

        assert articles == ()

    async def test_malformed_article_missing_required_field_raises_api_error(self) -> None:
        malformed = {k: v for k, v in _REAL_SHAPED_ARTICLE.items() if k != "title"}

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_page(malformed))

        client = client_for(handler)
        connector = MarketauxConnector(client=client, symbols="ETHUSD")
        async with connector:
            with pytest.raises(ConnectorAPIError):
                await connector.fetch_articles(
                    datetime(2024, 11, 1, tzinfo=UTC), datetime(2024, 11, 30, tzinfo=UTC)
                )

    async def test_rejects_naive_datetimes(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid range")

        connector = MarketauxConnector(client=client_for(never_called), symbols="ETHUSD")
        with pytest.raises(ValueError, match="timezone-aware"):
            await connector.fetch_articles(datetime(2024, 11, 1), datetime(2024, 11, 2, tzinfo=UTC))

    async def test_rejects_end_before_start(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid range")

        connector = MarketauxConnector(client=client_for(never_called), symbols="ETHUSD")
        with pytest.raises(ValueError, match="end must not be before start"):
            await connector.fetch_articles(
                datetime(2024, 11, 2, tzinfo=UTC), datetime(2024, 11, 1, tzinfo=UTC)
            )


@pytest.mark.asyncio
class TestMarketauxConnectorFetchProtocol:
    async def test_fetch_returns_one_point_per_scored_article(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_page(_REAL_SHAPED_ARTICLE))

        client = client_for(handler)
        connector = MarketauxConnector(client=client, symbols="ETHUSD")
        async with connector:
            points = await connector.fetch(
                datetime(2024, 11, 1, tzinfo=UTC), datetime(2024, 11, 30, tzinfo=UTC)
            )

        assert len(points) == 1
        assert points[0].value == pytest.approx(-0.4215)
        assert points[0].symbol == "ETHUSD"
        assert points[0].timestamp == datetime(2024, 11, 8, 1, 24, 0, tzinfo=UTC)

    async def test_fetch_excludes_articles_with_no_computable_sentiment(self) -> None:
        """`RawDataPoint.value: float` can't represent a null sentiment —
        `fetch()` (the `Connector` protocol method) skips those articles
        entirely rather than fabricating a value; `fetch_articles` (used
        by the real ingestion pipeline) keeps them with a real null."""
        article = {
            **_REAL_SHAPED_ARTICLE,
            "entities": [{**_REAL_SHAPED_ARTICLE["entities"][0], "sentiment_score": None}],
        }

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_page(article))

        client = client_for(handler)
        connector = MarketauxConnector(client=client, symbols="ETHUSD")
        async with connector:
            points = await connector.fetch(
                datetime(2024, 11, 1, tzinfo=UTC), datetime(2024, 11, 30, tzinfo=UTC)
            )

        assert points == ()
