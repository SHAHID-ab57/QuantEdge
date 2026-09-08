"""News API — backs the `/news` page (M4-E1-T7,
`ARCHITECTURE.md` § "External Data Connectors" → "Marketaux Connector").

Read-only, mirroring `app.api.v1.endpoints.connectors`'s own shape:
ingestion (a periodic scheduler, a manual backfill script) stays
internal, never triggered over HTTP. Full article detail lives here;
the daily aggregate the ML pipeline consumes is still read through the
existing, unchanged `GET /connectors`/`GET /features` surface — this
module adds nothing to either.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies.news import get_news_service
from app.schemas.news import NewsArticleListResponse
from app.services.news_api import DEFAULT_LIMIT, MAX_LIMIT, NewsService

router = APIRouter(tags=["news"])

NewsServiceDep = Annotated[NewsService, Depends(get_news_service)]


@router.get(
    "/news/articles",
    response_model=NewsArticleListResponse,
    summary="List real, tracked-symbol news articles",
    description=(
        "Return a page of ingested news articles, newest first. "
        "start/end filter on published_at, each independently inclusive "
        "when given (this platform's own established external-data range "
        "convention); omit either to leave that side open. symbol filters "
        "to articles that matched that tracked symbol. Pages use "
        "limit/offset with total/returned/has_more metadata, mirroring "
        "/connectors/{source}/history."
    ),
)
async def list_articles(
    service: NewsServiceDep,
    symbol: Annotated[
        str | None,
        Query(examples=["ETHUSD"], description="Filter to articles matching this tracked symbol"),
    ] = None,
    start: Annotated[
        datetime | None,
        Query(
            examples=["2026-01-01T00:00:00Z"],
            description="Range start (inclusive), ISO-8601 UTC, filters on published_at",
        ),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(
            examples=["2026-02-01T00:00:00Z"],
            description="Range end (inclusive), ISO-8601 UTC, filters on published_at",
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_LIMIT, description="Maximum articles per page"),
    ] = DEFAULT_LIMIT,
    offset: Annotated[
        int,
        Query(ge=0, description="Number of articles to skip"),
    ] = 0,
) -> NewsArticleListResponse:
    """Return a page of news articles."""
    return await service.list_articles(
        symbol=symbol, start=start, end=end, limit=limit, offset=offset
    )
