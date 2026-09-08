"""News API tests — mirrors `tests/api/test_connectors_api.py`'s own
shape: a real FastAPI app over ASGI with the in-memory SQLite database,
so routing, JSON serialization, and pagination are all covered end to
end.
"""

from datetime import UTC, datetime

import httpx

from app.models.news import NewsArticle
from tests.conftest import SessionFactory


async def seed_article(
    session_factory: SessionFactory,
    *,
    uuid: str,
    published_at: datetime,
    sentiment_score: float | None = 0.1,
    primary_symbol: str | None = "ETHUSD",
) -> None:
    """Insert one real article directly."""
    async with session_factory() as session:
        session.add(
            NewsArticle(
                marketaux_uuid=uuid,
                headline=f"Headline {uuid}",
                snippet="A snippet.",
                source="example.com",
                url=f"https://example.com/{uuid}",
                published_at=published_at,
                sentiment_score=sentiment_score,
                primary_symbol=primary_symbol,
                symbols=[primary_symbol] if primary_symbol else [],
                raw_payload={"uuid": uuid},
            )
        )
        await session.commit()


class TestListArticlesEndpoint:
    async def test_lists_articles_newest_first(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_article(
            session_factory, uuid="a1", published_at=datetime(2026, 1, 1, tzinfo=UTC)
        )
        await seed_article(
            session_factory, uuid="a2", published_at=datetime(2026, 1, 2, tzinfo=UTC)
        )

        response = await client.get("/api/v1/news/articles")
        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body["items"]] == [
            next(i["id"] for i in body["items"] if i["headline"] == "Headline a2"),
            next(i["id"] for i in body["items"] if i["headline"] == "Headline a1"),
        ]
        assert body["pagination"] == {
            "total": 2,
            "returned": 2,
            "has_more": False,
            "limit": 20,
            "offset": 0,
        }

    async def test_reports_full_article_detail(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_article(
            session_factory,
            uuid="a1",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            sentiment_score=0.42,
        )

        body = (await client.get("/api/v1/news/articles")).json()
        item = body["items"][0]
        assert item["headline"] == "Headline a1"
        assert item["source"] == "example.com"
        assert item["url"] == "https://example.com/a1"
        assert item["sentiment_score"] == 0.42
        assert item["symbols"] == ["ETHUSD"]
        assert item["published_at"] == "2026-01-01T00:00:00Z"

    async def test_a_null_sentiment_article_reports_null_not_a_fabricated_value(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_article(
            session_factory,
            uuid="a1",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            sentiment_score=None,
        )

        body = (await client.get("/api/v1/news/articles")).json()
        assert body["items"][0]["sentiment_score"] is None

    async def test_filters_by_symbol(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_article(
            session_factory,
            uuid="eth",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            primary_symbol="ETHUSD",
        )
        await seed_article(
            session_factory,
            uuid="btc",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            primary_symbol="BTCUSD",
        )

        body = (await client.get("/api/v1/news/articles", params={"symbol": "ETHUSD"})).json()
        assert len(body["items"]) == 1
        assert body["items"][0]["headline"] == "Headline eth"

    async def test_filters_by_published_at_range_inclusive(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_article(
            session_factory, uuid="early", published_at=datetime(2025, 12, 31, tzinfo=UTC)
        )
        await seed_article(
            session_factory, uuid="in_range", published_at=datetime(2026, 1, 1, tzinfo=UTC)
        )
        await seed_article(
            session_factory, uuid="late", published_at=datetime(2026, 1, 3, tzinfo=UTC)
        )

        body = (
            await client.get(
                "/api/v1/news/articles",
                params={"start": "2026-01-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
            )
        ).json()
        assert len(body["items"]) == 1
        assert body["items"][0]["headline"] == "Headline in_range"

    async def test_paginates_with_limit_and_offset(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        for day in (1, 2, 3):
            await seed_article(
                session_factory, uuid=f"a{day}", published_at=datetime(2026, 1, day, tzinfo=UTC)
            )

        first = await client.get("/api/v1/news/articles", params={"limit": 2, "offset": 0})
        first_body = first.json()
        assert len(first_body["items"]) == 2
        assert first_body["pagination"]["has_more"] is True

        second = await client.get("/api/v1/news/articles", params={"limit": 2, "offset": 2})
        second_body = second.json()
        assert len(second_body["items"]) == 1
        assert second_body["pagination"]["has_more"] is False

    async def test_empty_result_is_a_clean_response_not_an_error(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/api/v1/news/articles")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["pagination"]["total"] == 0

    async def test_is_mounted_unversioned_too(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        assert (await client.get("/news/articles")).status_code == 200
