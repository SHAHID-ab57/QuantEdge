"""Response schemas (DTOs) for the News API.

Backs the `/news` page (`ARCHITECTURE.md` § "External Data Connectors" →
"Marketaux Connector"): a paginated, filterable article feed, mirroring
`app.schemas.connectors.ConnectorHistoryResponse`'s own limit/offset
pagination shape — kept as its own smaller pair of models rather than
reused, since an article carries genuinely richer fields than a bare
`{timestamp, value}` point.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


def _ensure_utc(value: datetime) -> datetime:
    """Normalize a timestamp to aware UTC — the same SQLite round-trip
    workaround `app.schemas.connectors._ensure_utc` already applies."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class NewsArticleDTO(BaseModel):
    """One real news article, everything `/news` needs to render a card:
    headline, source, a link to the original, published time, and
    sentiment as an actual score — never just a color dot."""

    id: str
    headline: str
    snippet: str | None = None
    source: str
    url: str
    published_at: datetime
    sentiment_score: float | None = Field(
        default=None,
        description="Mean sentiment across this article's own tracked-symbol entities; "
        "null when none carried a score",
    )
    symbols: list[str] = Field(default_factory=list)

    @field_validator("published_at", mode="before")
    @classmethod
    def _validate_published_at(cls, value: datetime) -> datetime:
        return _ensure_utc(value)


class NewsArticlePagination(BaseModel):
    """Pagination metadata — the same total/returned/has_more/limit/offset
    shape `ConnectorHistoryPagination` uses."""

    total: int = Field(..., description="Total articles matching the query")
    returned: int = Field(..., description="Articles returned in this page")
    has_more: bool = Field(..., description="Whether further pages exist")
    limit: int
    offset: int


class NewsArticleListResponse(BaseModel):
    """A page of articles, newest first."""

    items: list[NewsArticleDTO]
    pagination: NewsArticlePagination
