"""The Marketaux news connector — the sixth concrete connector, and the
first whose real shape doesn't fit "one connector, one numeric value per
timestamp" at all. A real article carries genuinely richer detail
(headline, source, a link, per-entity sentiment) than `RawDataPoint` can
hold — see `app.models.news.NewsArticle`'s own module docstring for why
that detail lives in a dedicated table, with only a *derived* daily
aggregate ever mirrored into `external_data_points` (source
`news_sentiment`, `app.services.news_ingest`).

**Investigated before building, not assumed — checked directly against
Marketaux's current API documentation and the real live API:**

1. **An API key is hard-required** — confirmed live: a real,
   unauthenticated request to `/v1/news/all` returned a real HTTP 401,
   `{"error": {"code": "invalid_api_token", "message": "An invalid API "
   "token was supplied."}}`. Same "fail fast locally, no network call"
   contract as FRED/Etherscan when unconfigured.
2. **The free tier's real constraints, from Marketaux's own current
   pricing page, not memory of what a typical news API charges**: $0/mo,
   **100 requests/day**, **3 articles per request** (`limit` is capped at
   3 on this plan — `marketaux_articles_per_page` defaults to exactly
   this). Full entity/sentiment metadata access either way — the free
   tier is not sentiment-gated, only volume-gated.
3. **Crypto (including ETH specifically) is genuinely covered, confirmed
   via Marketaux's own real documented examples** — an entity shape
   `{"symbol": "ETHUSD", "name": "Ethereum USD", "exchange": "CC",
   "exchange_long": "Cryptocurrency", "type": "cryptocurrency"}` and a
   real example article ("Bitcoin (BTC/USD), Ethereum (ETH/USD) Crushed
   as Cryptocurrency Market is Overrun by Sellers") carrying a real
   `sentiment_score` of `-0.4215` on its own highlighted text — this is
   not a stock-only news API pressed into crypto use, and its own
   `symbol` convention already matches this platform's own `ETHUSD`, no
   translation needed.
4. **Sentiment scoring: confirmed present, real scale, per-*entity* not
   per-article** — `data > entities > sentiment_score`: "Average
   sentiment of all highlighted text found for the identified entity...
   above 0 = positive, below 0 = negative." This is genuinely per-entity:
   one article can mention several entities, each with its own score.
   `_to_article` computes the article-level score as the mean across
   whichever tracked-symbol entities the article actually matched (with
   `filter_entities=true` in force — see point 5 below), never diluted
   by an unrelated entity's own sentiment.

**The three known bug patterns, checked explicitly against Marketaux's
documented behavior before writing any code:**

- **An omitted parameter defaulting to something surprising — found for
  real, not hypothetical.** `filter_entities` defaults to `false`: "By
  default all entities for each article are returned" — meaning a query
  for `symbols=ETHUSD` on an article that *also* mentions, say, Tesla
  would return *both* entities, and naively averaging "the entities"
  would silently blend ETH-relevant sentiment with completely unrelated
  sentiment. This connector always sends `filter_entities=true`
  explicitly — the same shape of omission FRED's own
  `realtime_start`/`realtime_end` was, caught here by reading the docs
  first rather than by a live surprise.
- **A timestamp computed at the wrong moment relative to a network
  call** (Etherscan's `end`-before-round-trip bug): does not apply —
  every article carries its own `published_at`, confirmed live in real
  documented examples; this connector never calls `datetime.now()` to
  invent one.
- **A response field silently not captured**: guarded the same way every
  connector since Fear & Greed has been — `headline`/`snippet`/`source`/
  `url`/`published_at`/`sentiment_score`/`symbols` are all captured into
  `NewsArticle`, with the full real article object kept in `raw_payload`
  for audit regardless.

**A genuinely new risk this connector's own investigation surfaced,
distinct from every prior connector's own bug: discovery latency, not
value revision.** Marketaux's docs describe `published_at` as simply
"the datetime the article was published," with no companion field (or
documented guarantee) for when an article actually becomes queryable via
this API — unlike FRED's own explicit `realtime_start`/`realtime_end`
distinction. It is entirely possible for an article to be *discovered* by
Marketaux's own indexing sometime after its own `published_at`. A
periodic sync tick that resumed strictly from "the newest stored
article's own `published_at`" could permanently miss a late-discovered
article for a day already partly covered. `NewsSyncScheduler`
(`app.services.news_sync`) does not narrow its own window that tightly —
see that module's own docstring for the deliberate safety margin this
finding requires, mirroring (for a different underlying reason) why
DefiLlama's own revision-check window is not narrowed to "recent days
only" either.

**Why the daily aggregate, not a raw per-article mirror, is what reaches
`external_data_points`.** A single day can carry zero, one, or several
articles; the ML pipeline's own existing feature-lookup pattern
(`most_recent_value_at_or_before`) expects one connector-backed time
series per source, not a variable-cardinality one. The mean of a day's
own article-level sentiment scores is `app.services.news_ingest`'s own
computation, stored under `MARKETAUX_SOURCE` — registered
`auto_synced=False` (see `ConnectorMetadata.auto_synced`'s own
docstring) since this shape does not fit the generic scheduler's own
"fetch one point, persist it" tick at all.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

import httpx

from app.connectors.base import ConnectorMetadata, RawDataPoint
from app.connectors.errors import (
    ConnectorAPIError,
    ConnectorAuthenticationError,
    ConnectorNetworkError,
    ConnectorRateLimitError,
)
from app.connectors.registry import register_connector
from app.core.config import get_settings

logger = logging.getLogger("app.connectors.marketaux")

MARKETAUX_SOURCE = "news_sentiment"
_NEWS_PATH = "/news/all"
#: Marketaux's own real, documented cap for the free tier — see this
#: module's own docstring point 2.
_FILTER_ENTITIES = "true"
#: English only, deliberately: Marketaux covers 30+ languages, but a
#: single-language feed keeps sentiment scoring comparable across
#: articles for this platform's first pass at News — not a limitation
#: discovered by surprise, a scope decision stated plainly.
_LANGUAGE = "en"

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 0.5
_MAX_RETRY_DELAY = 30.0
_USER_AGENT = "eth-ai-platform/0.1.0"


@dataclass(frozen=True, slots=True)
class MarketauxArticle:
    """One real news article, richer than `RawDataPoint` can hold —
    `sentiment_score` is genuinely nullable (an article can match a
    tracked symbol with no entity carrying a computed score at all),
    which `RawDataPoint.value: float` cannot represent. Used by
    `app.services.news_ingest` to build a `NewsArticle` row directly;
    `MarketauxConnector.fetch()` (the `Connector` protocol method) is a
    thinner adapter over the same underlying page fetch — see this
    module's own docstring for why both exist.
    """

    marketaux_uuid: str
    headline: str
    snippet: str | None
    source: str
    url: str
    published_at: datetime
    sentiment_score: float | None
    symbols: tuple[str, ...]
    raw_payload: dict[str, Any]


class MarketauxClient:
    """Async HTTP client for Marketaux's `/news/all` endpoint.

    Same shape as `FearGreedClient`/`FredClient`: connection pooling,
    bounded retries with exponential backoff, structured logging,
    status-code-based error mapping (confirmed live — a real 401 for a
    bad key; 429 is Marketaux's own separately documented rate-limit
    status, never conflated with auth failures the way Etherscan's own
    always-200 body-content shape needed).
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        request_timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = DEFAULT_RETRY_BACKOFF,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if retry_backoff <= 0:
            raise ValueError("retry_backoff must be positive")

        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.marketaux_api_key
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._client = httpx.AsyncClient(
            base_url=base_url or settings.marketaux_base_url,
            timeout=httpx.Timeout(
                request_timeout
                if request_timeout is not None
                else settings.marketaux_request_timeout
            ),
            transport=transport,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )

    async def fetch_page(
        self,
        *,
        symbols: str,
        published_after: datetime,
        published_before: datetime,
        limit: int,
        page: int,
    ) -> dict[str, Any]:
        """Return one raw `{"meta": ..., "data": [...]}` page.

        Raises `ConnectorAuthenticationError` immediately, with no
        network call, when no API key is configured — Marketaux hard-
        requires one (confirmed live), unlike DefiLlama/CoinGecko.
        """
        if not self._api_key:
            raise ConnectorAuthenticationError(
                "Marketaux API key is not configured (MARKETAUX_API_KEY) — register a "
                "free key at https://www.marketaux.com/account/dashboard"
            )
        payload = await self._execute(
            "GET",
            _NEWS_PATH,
            params={
                "symbols": symbols,
                "filter_entities": _FILTER_ENTITIES,
                "language": _LANGUAGE,
                "published_after": published_after.strftime("%Y-%m-%dT%H:%M:%S"),
                "published_before": published_before.strftime("%Y-%m-%dT%H:%M:%S"),
                "limit": limit,
                "page": page,
                "api_token": self._api_key,
            },
        )
        if not isinstance(payload, dict):
            raise ConnectorAPIError(
                "Malformed Marketaux response: expected an object envelope", detail=payload
            )
        meta = payload.get("meta")
        data = payload.get("data")
        if not isinstance(meta, dict) or not isinstance(data, list):
            raise ConnectorAPIError(
                "Malformed Marketaux response: missing or malformed 'meta'/'data'",
                detail=payload,
            )
        return payload

    async def aclose(self) -> None:
        """Close the underlying httpx client, releasing pooled connections."""
        await self._client.aclose()

    async def __aenter__(self) -> "MarketauxClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()

    async def _execute(self, method: str, path: str, *, params: dict[str, Any]) -> object:
        """Send one request with retries; return the decoded JSON body."""
        attempt = 0
        while True:
            started = time.perf_counter()
            try:
                response = await self._client.request(method, path, params=params)
            except httpx.TimeoutException as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "Marketaux %s %s timed out on attempt %d (%.1fms)",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                )
                if attempt >= self._max_retries:
                    raise ConnectorNetworkError(
                        f"Marketaux request timed out: {method} {path}", detail=str(exc)
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue
            except httpx.TransportError as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "Marketaux %s %s transport error on attempt %d (%.1fms): %s",
                    method,
                    path,
                    attempt + 1,
                    latency_ms,
                    exc,
                )
                if attempt >= self._max_retries:
                    raise ConnectorNetworkError(
                        f"Marketaux network failure for {method} {path}: {exc}", detail=str(exc)
                    ) from exc
                await self._backoff(attempt)
                attempt += 1
                continue

            latency_ms = (time.perf_counter() - started) * 1000
            status = response.status_code
            logger.info("Marketaux %s %s -> %d (%.1fms)", method, path, status, latency_ms)

            if status in RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                delay = self._retry_delay(status, response, attempt)
                logger.warning(
                    "Marketaux retrying %s %s after %d in %.2fs (attempt %d/%d)",
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
        """Map an HTTP response to a decoded body or a typed exception."""
        status = response.status_code
        if status == 429:
            raise ConnectorRateLimitError(
                f"Marketaux rate limit exceeded for {method} {path}",
                retry_after=self._parse_retry_after(response),
                status_code=status,
            )
        if status == 401:
            raise ConnectorAuthenticationError(
                f"Marketaux authentication failed for {method} {path} "
                "(missing or invalid API token)",
                status_code=status,
            )
        payload = self._json_payload(response)
        if payload is None:
            raise ConnectorAPIError(
                f"Malformed Marketaux response for {method} {path}: body is not valid JSON",
                status_code=status,
            )
        if status >= 400:
            raise ConnectorAPIError(
                f"Marketaux request failed with HTTP {status} for {method} {path}",
                status_code=status,
                detail=payload,
            )
        return payload

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    @staticmethod
    def _json_payload(response: httpx.Response) -> object | None:
        try:
            return response.json()
        except ValueError:
            return None

    def _retry_delay(self, status: int, response: httpx.Response, attempt: int) -> float:
        if status == 429:
            retry_after = self._parse_retry_after(response)
            if retry_after is not None:
                return min(max(retry_after, 0.0), _MAX_RETRY_DELAY)
        return min(self._retry_backoff * (2**attempt), _MAX_RETRY_DELAY)

    async def _backoff(self, attempt: int) -> None:
        delay = min(self._retry_backoff * (2**attempt), _MAX_RETRY_DELAY)
        await self._sleep(delay)

    @staticmethod
    async def _sleep(delay: float) -> None:
        jittered = delay * (1.0 + random.random() * 0.1)
        await asyncio.sleep(jittered)


def get_marketaux_client(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    request_timeout: float | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
) -> MarketauxClient:
    """Return a configured Marketaux client, defaulting from settings."""
    return MarketauxClient(
        base_url=base_url,
        api_key=api_key,
        request_timeout=request_timeout,
        transport=transport,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
    )


@register_connector
class MarketauxConnector:
    """Adapts `MarketauxClient` to the `Connector` protocol.

    Holds its own client (built fresh per instance, same reasoning as
    every other connector); `aclose()` releases it, and the class
    supports `async with` for the "use once, then close" case
    ingestion/backfill both need.
    """

    metadata: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        source=MARKETAUX_SOURCE,
        label="Marketaux News Sentiment",
        description=(
            "Daily mean sentiment across real, tracked-symbol news articles "
            "(Marketaux, filter_entities=true — never diluted by an unrelated "
            "entity's own sentiment). Requires a free Marketaux API key. Full "
            "article detail (headline, source, link, per-article sentiment) "
            "lives in its own table and is browsable at /news; this is only "
            "the daily aggregate the ML pipeline consumes."
        ),
        frequency="several times daily (see NewsSyncScheduler)",
        requires_auth=True,
        version="1.0.0",
        aliases=("news", "marketaux", "sentiment"),
        auto_synced=False,
    )

    def __init__(
        self,
        *,
        client: MarketauxClient | None = None,
        symbols: str | None = None,
        articles_per_page: int | None = None,
        max_pages: int | None = None,
    ) -> None:
        self._client = client or get_marketaux_client()
        settings = get_settings()
        self._symbols = symbols if symbols is not None else settings.marketaux_symbols
        self._articles_per_page = (
            articles_per_page
            if articles_per_page is not None
            else settings.marketaux_articles_per_page
        )
        self._max_pages = (
            max_pages if max_pages is not None else settings.marketaux_max_pages_per_fetch
        )

    async def fetch_articles(self, start: datetime, end: datetime) -> tuple[MarketauxArticle, ...]:
        """Return every real article published in `[start, end]` (inclusive
        both ends — this table's own convention, mirroring every other
        connector), paginating up to `marketaux_max_pages_per_fetch` pages
        to respect the free tier's own real daily request budget (see this
        module's own docstring, point 2).
        """
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware datetimes")
        if end < start:
            raise ValueError("end must not be before start")

        articles: list[MarketauxArticle] = []
        for page in range(1, self._max_pages + 1):
            payload = await self._client.fetch_page(
                symbols=self._symbols,
                published_after=start,
                published_before=end,
                limit=self._articles_per_page,
                page=page,
            )
            data = payload["data"]
            meta = payload["meta"]
            for entry in data:
                article = _to_article(entry)
                if article is not None and start <= article.published_at <= end:
                    articles.append(article)
            returned = meta.get("returned")
            if not isinstance(returned, int) or returned < self._articles_per_page:
                break
        return tuple(articles)

    async def fetch(self, start: datetime, end: datetime) -> tuple[RawDataPoint, ...]:
        """`Connector` protocol conformance: one point per article with a
        computable sentiment score (never `None` — `RawDataPoint.value`
        can't represent that; see this module's own docstring for why
        `app.services.news_ingest` uses `fetch_articles` directly instead,
        to keep a genuinely scoreless article's own null intact).
        """
        articles = await self.fetch_articles(start, end)
        return tuple(
            RawDataPoint(
                timestamp=article.published_at,
                value=article.sentiment_score,
                symbol=article.symbols[0] if article.symbols else None,
                raw_payload=article.raw_payload,
            )
            for article in articles
            if article.sentiment_score is not None
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "MarketauxConnector":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


def _to_article(entry: object) -> MarketauxArticle | None:
    """Map one raw Marketaux article object to a `MarketauxArticle`.

    Any missing key or unparseable required field is a malformed
    response, not a data point to silently skip. `sentiment_score` is the
    mean across whatever tracked-symbol entities the article actually
    carries (with `filter_entities=true` in force, this is only ever the
    queried symbols, never an unrelated one) — `None` when none of them
    carry a score, a real, expected outcome, not an error.
    """
    if not isinstance(entry, dict):
        raise ConnectorAPIError("Malformed Marketaux entry: expected an object", detail=entry)
    try:
        marketaux_uuid = str(entry["uuid"])
        headline = str(entry["title"])
        source = str(entry["source"])
        url = str(entry["url"])
        published_at = _parse_published_at(entry["published_at"])
        snippet = entry.get("snippet")
        entities = entry.get("entities")
    except (KeyError, TypeError, ValueError) as exc:
        raise ConnectorAPIError(f"Malformed Marketaux entry: {exc}", detail=entry) from exc

    symbols: list[str] = []
    scores: list[float] = []
    if isinstance(entities, list):
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            symbol = entity.get("symbol")
            if isinstance(symbol, str):
                symbols.append(symbol)
            score = entity.get("sentiment_score")
            if isinstance(score, (int, float)):
                scores.append(float(score))

    sentiment_score = sum(scores) / len(scores) if scores else None
    return MarketauxArticle(
        marketaux_uuid=marketaux_uuid,
        headline=headline,
        snippet=str(snippet) if snippet else None,
        source=source,
        url=url,
        published_at=published_at,
        sentiment_score=sentiment_score,
        symbols=tuple(symbols),
        raw_payload=entry,
    )


def _parse_published_at(value: object) -> datetime:
    """Parse Marketaux's own `published_at` format, e.g.
    `"2024-11-08T01:24:00.000000Z"` — confirmed live/via docs, always UTC.
    """
    if not isinstance(value, str):
        raise ValueError(f"published_at must be a string, got {type(value).__name__}")
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
