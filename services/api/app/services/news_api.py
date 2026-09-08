"""Business logic for the News API — read-only, mirroring
`app.services.connectors.ConnectorService`'s own "reads straight from the
repository" role. Ingestion lives entirely in `app.services.news_ingest`/
`news_sync`; this module never writes anything.
"""

from dataclasses import dataclass
from datetime import datetime

from app.repositories.news import NewsRepository
from app.schemas.news import (
    NewsArticleDTO,
    NewsArticleListResponse,
    NewsArticlePagination,
)

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass
class NewsService:
    """Business logic for `GET /news/articles`."""

    news_repository: NewsRepository

    async def list_articles(
        self,
        *,
        symbol: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> NewsArticleListResponse:
        """A page of articles, newest first, optionally filtered by
        tracked symbol and/or a `published_at` date range (inclusive
        both ends, this platform's own established external-data range
        convention)."""
        articles = await self.news_repository.list_paginated(
            symbol=symbol, start=start, end=end, limit=limit, offset=offset
        )
        total = await self.news_repository.count(symbol=symbol, start=start, end=end)
        return NewsArticleListResponse(
            items=[
                NewsArticleDTO(
                    id=str(article.id),
                    headline=article.headline,
                    snippet=article.snippet,
                    source=article.source,
                    url=article.url,
                    published_at=article.published_at,
                    sentiment_score=article.sentiment_score,
                    symbols=list(article.symbols),
                )
                for article in articles
            ],
            pagination=NewsArticlePagination(
                total=total,
                returned=len(articles),
                has_more=offset + len(articles) < total,
                limit=limit,
                offset=offset,
            ),
        )
