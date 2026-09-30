"""Unit tests for the Reddit/Arctic Shift connector using mocked
transports — mirrors `tests/connectors/test_marketaux.py`'s own
conventions, adapted for Arctic Shift's own real, verified shape:
`{"data": [...]}` pages (no `meta` envelope), no auth, and cursor-based
(`after`/`sort=asc`) pagination rather than page-number pagination.
"""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime

import httpx
import pytest

from app.connectors.errors import ConnectorAPIError, ConnectorNetworkError, ConnectorRateLimitError
from app.connectors.reddit import ArcticShiftClient, RedditConnector, score_comment

Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]

#: A real Arctic Shift comment shape (trimmed to the fields this
#: connector actually requests via `fields=`), verified live.
_REAL_SHAPED_COMMENT = {
    "id": "pb2aqra",
    "body": "Indeed, I forgot about Tempo lol",
    "created_utc": 1789947423,
    "author": "Flashy-Butterfly6310",
    "score": 3,
    "subreddit": "ethereum",
    "permalink": "/r/ethereum/comments/1wl7p31/x/pb2aqra/",
}


def client_for(
    handler: Handler, *, max_retries: int = 3, retry_backoff: float = 0.01
) -> ArcticShiftClient:
    """Build an ArcticShiftClient over a mocked transport using fast backoff."""
    transport = httpx.MockTransport(handler)
    return ArcticShiftClient(
        transport=transport, max_retries=max_retries, retry_backoff=retry_backoff
    )


def connector_for(client: ArcticShiftClient, **kwargs: object) -> RedditConnector:
    """Build a RedditConnector with `page_pause_seconds=0` by default — a
    real, deliberate pause between pages exists for the live connector
    (found necessary against the real API, see `app.connectors.reddit`'s
    own module docstring), but every test here uses a mocked transport
    with no real rate limit to respect, so paying that real-world delay
    here would only slow the suite down for no reason."""
    kwargs.setdefault("page_pause_seconds", 0)
    return RedditConnector(client=client, **kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
class TestArcticShiftClient:
    async def test_successful_fetch_returns_the_raw_page(self) -> None:
        captured: dict[str, str] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, json={"data": [_REAL_SHAPED_COMMENT]})

        client = client_for(handler)
        async with client:
            data = await client.fetch_comments_page(
                subreddit="ethereum",
                after=datetime(2026, 9, 1, tzinfo=UTC),
                before=datetime(2026, 9, 2, tzinfo=UTC),
                limit=100,
            )

        assert data == [_REAL_SHAPED_COMMENT]
        url = captured["url"]
        assert "subreddit=ethereum" in url
        # The load-bearing proof of bug pattern #1: sort=asc is always
        # sent, never left to Arctic Shift's own descending default.
        assert "sort=asc" in url
        assert "limit=100" in url

    async def test_limit_above_max_raises_value_error_with_no_request(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid limit")

        client = client_for(never_called)
        async with client:
            with pytest.raises(ValueError, match="between 1 and 100"):
                await client.fetch_comments_page(
                    subreddit="ethereum",
                    after=datetime(2026, 9, 1, tzinfo=UTC),
                    before=datetime(2026, 9, 2, tzinfo=UTC),
                    limit=1000,
                )

    async def test_api_reported_error_raises_api_error(self) -> None:
        """Arctic Shift's own real error shape — verified live: HTTP 200
        with `{"data": null, "error": "..."}`, not a non-2xx status."""

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"data": None, "error": "'limit' must be between 1 and 100"}
            )

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_comments_page(
                    subreddit="ethereum",
                    after=datetime(2026, 9, 1, tzinfo=UTC),
                    before=datetime(2026, 9, 2, tzinfo=UTC),
                    limit=100,
                )

    async def test_malformed_response_non_json_body_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"this-is-not-json{{{")

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_comments_page(
                    subreddit="ethereum",
                    after=datetime(2026, 9, 1, tzinfo=UTC),
                    before=datetime(2026, 9, 2, tzinfo=UTC),
                    limit=100,
                )

    async def test_malformed_response_missing_data_raises_api_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": True})

        client = client_for(handler)
        async with client:
            with pytest.raises(ConnectorAPIError):
                await client.fetch_comments_page(
                    subreddit="ethereum",
                    after=datetime(2026, 9, 1, tzinfo=UTC),
                    before=datetime(2026, 9, 2, tzinfo=UTC),
                    limit=100,
                )

    async def test_network_failure_timeout_raises_network_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("read timed out after 5s")

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorNetworkError):
                await client.fetch_comments_page(
                    subreddit="ethereum",
                    after=datetime(2026, 9, 1, tzinfo=UTC),
                    before=datetime(2026, 9, 2, tzinfo=UTC),
                    limit=100,
                )

    async def test_rate_limit_retries_then_succeeds(self) -> None:
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] == 1:
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, json={"data": [_REAL_SHAPED_COMMENT]})

        client = client_for(handler, max_retries=2)
        async with client:
            data = await client.fetch_comments_page(
                subreddit="ethereum",
                after=datetime(2026, 9, 1, tzinfo=UTC),
                before=datetime(2026, 9, 2, tzinfo=UTC),
                limit=100,
            )

        assert data == [_REAL_SHAPED_COMMENT]
        assert calls["count"] == 2

    async def test_rate_limit_exhausted_raises_rate_limit_error(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "0"})

        client = client_for(handler, max_retries=0)
        async with client:
            with pytest.raises(ConnectorRateLimitError):
                await client.fetch_comments_page(
                    subreddit="ethereum",
                    after=datetime(2026, 9, 1, tzinfo=UTC),
                    before=datetime(2026, 9, 2, tzinfo=UTC),
                    limit=100,
                )


@pytest.mark.asyncio
class TestRedditConnectorFetchItems:
    async def test_maps_comment_fields(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [_REAL_SHAPED_COMMENT]})

        client = client_for(handler)
        connector = connector_for(client, subreddits="ethereum")
        async with connector:
            items = await connector.fetch_items(
                datetime(2026, 9, 20, tzinfo=UTC), datetime(2026, 9, 21, tzinfo=UTC)
            )

        assert len(items) == 1
        item = items[0]
        assert item.reddit_id == "pb2aqra"
        assert item.subreddit == "ethereum"
        assert item.author == "Flashy-Butterfly6310"
        assert item.body == "Indeed, I forgot about Tempo lol"
        assert item.score == 3
        assert item.created_utc == datetime(2026, 9, 20, 23, 37, 3, tzinfo=UTC)

    async def test_queries_every_configured_subreddit(self) -> None:
        requested_subreddits: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requested_subreddits.append(request.url.params["subreddit"])
            return httpx.Response(200, json={"data": []})

        client = client_for(handler)
        connector = connector_for(client, subreddits="ethereum,CryptoCurrency")
        async with connector:
            await connector.fetch_items(
                datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 2, tzinfo=UTC)
            )

        assert requested_subreddits == ["ethereum", "CryptoCurrency"]

    async def test_pauses_between_subreddits_the_same_as_between_pages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The last page of one subreddit and the first page of the next
        used to be back-to-back with zero pause — the exact same
        sustained-request pattern that was found, for real, to trip
        Arctic Shift's rate limit between pages. `max_pages=1` here rules
        out a page-level pause being what's actually observed: with only
        one page per subreddit, any sleep recorded can only be the new
        between-subreddit one."""
        sleep_calls: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        monkeypatch.setattr("app.connectors.reddit.asyncio.sleep", fake_sleep)

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": []})

        client = client_for(handler)
        connector = RedditConnector(
            client=client,
            subreddits="ethereum,ethtrader,CryptoCurrency",
            page_limit=100,
            max_pages=1,
            page_pause_seconds=1.5,
        )
        async with connector:
            await connector.fetch_items(
                datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 2, tzinfo=UTC)
            )

        # 3 subreddits -> 2 transitions (before the 2nd and 3rd), none
        # before the 1st (no pointless upfront delay).
        assert sleep_calls == [1.5, 1.5]

    async def test_paginates_forward_past_the_last_seen_cursor(self) -> None:
        """A full page implies more results might exist within the
        window — the connector must advance its own cursor past the
        last-seen comment's `created_utc`, not repeat the same page."""
        calls: list[dict[str, str]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append(dict(request.url.params))
            page_num = len(calls)
            if page_num == 1:
                comment = {**_REAL_SHAPED_COMMENT, "id": "first", "created_utc": 1000}
                return httpx.Response(200, json={"data": [comment]})
            if page_num == 2:
                comment = {**_REAL_SHAPED_COMMENT, "id": "second", "created_utc": 2000}
                return httpx.Response(200, json={"data": [comment]})
            return httpx.Response(200, json={"data": []})

        client = client_for(handler)
        connector = connector_for(client, subreddits="ethereum", page_limit=1, max_pages=5)
        async with connector:
            items = await connector.fetch_items(
                datetime(1970, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)
            )

        assert [item.reddit_id for item in items] == ["first", "second"]
        # Second request's own cursor must have advanced past the first
        # comment's created_utc (1000), never repeating it.
        assert int(calls[1]["after"]) > 1000

    async def test_stops_at_max_pages_per_fetch_even_if_more_results_exist(self) -> None:
        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            comment = {
                **_REAL_SHAPED_COMMENT,
                "id": f"comment-{calls['count']}",
                "created_utc": 1000 * calls["count"],
            }
            return httpx.Response(200, json={"data": [comment]})

        client = client_for(handler)
        connector = connector_for(client, subreddits="ethereum", page_limit=1, max_pages=4)
        async with connector:
            items = await connector.fetch_items(
                datetime(1970, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)
            )

        assert calls["count"] == 4
        assert len(items) == 4

    async def test_logs_a_warning_when_max_pages_is_exhausted(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Real evidence a window may hold more comments than were
        gathered must be visible, not silently swallowed — a real
        interaction found while sizing `scripts/backfill_reddit.py`'s own
        `--chunk-days` default against `reddit_max_pages_per_fetch`."""
        import logging

        calls = {"count": 0}

        async def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            comment = {**_REAL_SHAPED_COMMENT, "created_utc": 1000 * calls["count"]}
            return httpx.Response(200, json={"data": [comment]})

        client = client_for(handler)
        connector = connector_for(client, subreddits="ethereum", page_limit=1, max_pages=2)
        with caplog.at_level(logging.WARNING, logger="app.connectors.reddit"):
            async with connector:
                await connector.fetch_items(
                    datetime(1970, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)
                )

        assert any("exhausted max_pages" in record.message for record in caplog.records)

    async def test_no_warning_when_a_partial_page_ends_pagination_naturally(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [_REAL_SHAPED_COMMENT]})

        client = client_for(handler)
        connector = connector_for(client, subreddits="ethereum", page_limit=100, max_pages=5)
        with caplog.at_level(logging.WARNING, logger="app.connectors.reddit"):
            async with connector:
                await connector.fetch_items(
                    datetime(2026, 9, 20, tzinfo=UTC), datetime(2026, 9, 21, tzinfo=UTC)
                )

        assert not any("exhausted max_pages" in record.message for record in caplog.records)

    async def test_excludes_comments_outside_the_requested_range(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [_REAL_SHAPED_COMMENT]})

        client = client_for(handler)
        connector = connector_for(client, subreddits="ethereum")
        async with connector:
            items = await connector.fetch_items(
                datetime(2030, 1, 1, tzinfo=UTC), datetime(2030, 1, 2, tzinfo=UTC)
            )

        assert items == ()

    async def test_malformed_comment_missing_required_field_raises_api_error(self) -> None:
        malformed = {k: v for k, v in _REAL_SHAPED_COMMENT.items() if k != "id"}

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [malformed]})

        client = client_for(handler)
        connector = connector_for(client, subreddits="ethereum")
        async with connector:
            with pytest.raises(ConnectorAPIError):
                await connector.fetch_items(
                    datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 2, tzinfo=UTC)
                )

    async def test_rejects_naive_datetimes(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid range")

        connector = connector_for(client_for(never_called), subreddits="ethereum")
        with pytest.raises(ValueError, match="timezone-aware"):
            await connector.fetch_items(datetime(2026, 9, 1), datetime(2026, 9, 2, tzinfo=UTC))

    async def test_rejects_end_before_start(self) -> None:
        async def never_called(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for an invalid range")

        connector = connector_for(client_for(never_called), subreddits="ethereum")
        with pytest.raises(ValueError, match="end must not be before start"):
            await connector.fetch_items(
                datetime(2026, 9, 2, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC)
            )


@pytest.mark.asyncio
class TestRedditConnectorFetchProtocol:
    async def test_fetch_returns_one_point_per_scoreable_comment(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [_REAL_SHAPED_COMMENT]})

        client = client_for(handler)
        connector = connector_for(client, subreddits="ethereum")
        async with connector:
            points = await connector.fetch(
                datetime(2026, 9, 20, tzinfo=UTC), datetime(2026, 9, 21, tzinfo=UTC)
            )

        assert len(points) == 1
        assert points[0].symbol is None
        assert points[0].timestamp == datetime(2026, 9, 20, 23, 37, 3, tzinfo=UTC)

    async def test_fetch_excludes_deleted_comments(self) -> None:
        deleted = {**_REAL_SHAPED_COMMENT, "body": "[deleted]"}

        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [deleted]})

        client = client_for(handler)
        connector = connector_for(client, subreddits="ethereum")
        async with connector:
            points = await connector.fetch(
                datetime(2026, 9, 20, tzinfo=UTC), datetime(2026, 9, 21, tzinfo=UTC)
            )

        assert points == ()


class TestScoreComment:
    def test_positive_text_scores_positive(self) -> None:
        score = score_comment("ETH is going to the moon, love this!")
        assert score is not None
        assert score > 0

    def test_negative_text_scores_negative(self) -> None:
        score = score_comment("This is terrible, I am dumping everything now")
        assert score is not None
        assert score < 0

    def test_deleted_body_returns_none(self) -> None:
        assert score_comment("[deleted]") is None

    def test_removed_body_returns_none(self) -> None:
        assert score_comment("[removed]") is None

    def test_empty_body_returns_none(self) -> None:
        assert score_comment("   ") is None
