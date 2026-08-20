"""Synchronization of Delta Exchange markets into the local database.

Fetches the Delta product catalog through the Delta REST client and upserts
it into the domain tables (``exchanges``, ``markets``). The sync is
idempotent: re-running it leaves already-synced records untouched unless the
upstream data changed.
"""

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import get_engine
from app.integrations.delta import DeltaClient, Product, get_delta_client
from app.models.exchange import Exchange
from app.models.market import Market

logger = logging.getLogger("app.services.market_sync")

EXCHANGE_SLUG = "delta"
EXCHANGE_NAME = "Delta Exchange"
EXCHANGE_COUNTRY = "India"

PRODUCTS_PATH = "/v2/products"
SYNC_PAGE_SIZE = 500
PRODUCT_FILTERS: Mapping[str, str] = {
    "states": "live",
    "contract_types": "perpetual_futures,spot,futures",
    "page_size": str(SYNC_PAGE_SIZE),
}

CONTRACT_TYPE_TO_MARKET_TYPE: Mapping[str, str] = {
    "perpetual_futures": "perpetual",
    "spot": "spot",
    "futures": "expiry",
}

_PRODUCTS_ADAPTER: TypeAdapter[list[Product]] = TypeAdapter(list[Product])


class MarketSyncError(RuntimeError):
    """Raised when the sync cannot proceed safely."""


@dataclass(frozen=True)
class SyncReport:
    """Outcome of a market synchronization run."""

    exchange_id: uuid.UUID
    products_fetched: int
    inserted: int
    updated: int
    skipped: int
    duration_seconds: float


async def sync_markets(
    *,
    client: DeltaClient | None = None,
    session: AsyncSession | None = None,
) -> SyncReport:
    """Synchronize Delta product listings into the local database.

    Args:
        client: Delta REST client; built from settings when omitted.
        session: Database session; built from the configured engine when
            omitted. Pass a session with no active transaction.

    Returns:
        A report with fetch/insert/update/skip counts and elapsed time.

    Raises:
        MarketSyncError: When the product list looks truncated.
        RuntimeError: When no database is configured.
    """
    started_at = perf_counter()
    logger.info("Market sync started (exchange=%s, endpoint=%s)", EXCHANGE_SLUG, PRODUCTS_PATH)

    owns_session = session is None
    if session is None:
        engine = get_engine()
        if engine is None:
            raise RuntimeError("Database is not configured")
        session = async_sessionmaker(bind=engine, expire_on_commit=False)()

    owns_client = client is None
    if client is None:
        client = get_delta_client()

    try:
        return await _run_sync(client, session, started_at)
    finally:
        if owns_client:
            await client.aclose()
        if owns_session:
            await session.close()


async def _run_sync(client: DeltaClient, session: AsyncSession, started_at: float) -> SyncReport:
    """Fetch products, then upsert them inside a single transaction."""
    raw = await client.get(PRODUCTS_PATH, params=PRODUCT_FILTERS)
    products = _PRODUCTS_ADAPTER.validate_python(raw)
    logger.info("Fetched %d products from Delta Exchange", len(products))

    if len(products) >= SYNC_PAGE_SIZE:
        raise MarketSyncError(
            f"Product list appears truncated ({len(products)} of page size {SYNC_PAGE_SIZE}); "
            "pagination is not implemented — refusing to sync a partial catalog"
        )

    async with session.begin():
        exchange = await _ensure_exchange(session)
        existing = await _load_markets(session, exchange.id)
        inserted, updated, skipped = _apply_products(session, exchange.id, existing, products)

    duration_seconds = perf_counter() - started_at
    logger.info("Market sync: inserted=%d updated=%d skipped=%d", inserted, updated, skipped)
    logger.info("Market sync completed in %.2fs", duration_seconds)

    return SyncReport(
        exchange_id=exchange.id,
        products_fetched=len(products),
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        duration_seconds=duration_seconds,
    )


async def _ensure_exchange(session: AsyncSession) -> Exchange:
    """Return the Delta exchange record, creating it on first sync."""
    exchange = (
        await session.execute(select(Exchange).where(Exchange.slug == EXCHANGE_SLUG))
    ).scalar_one_or_none()
    if exchange is not None:
        return exchange

    exchange = Exchange(
        name=EXCHANGE_NAME,
        slug=EXCHANGE_SLUG,
        country=EXCHANGE_COUNTRY,
    )
    session.add(exchange)
    await session.flush()
    logger.info("Created exchange record (slug=%s)", EXCHANGE_SLUG)
    return exchange


async def _load_markets(session: AsyncSession, exchange_id: uuid.UUID) -> dict[str, Market]:
    """Load markets of an exchange keyed by symbol."""
    rows = await session.execute(select(Market).where(Market.exchange_id == exchange_id))
    return {market.symbol: market for market in rows.scalars()}


def _apply_products(
    session: AsyncSession,
    exchange_id: uuid.UUID,
    existing: Mapping[str, Market],
    products: Sequence[Product],
) -> tuple[int, int, int]:
    """Diff fetched products against stored markets; return (inserted, updated, skipped)."""
    inserted = 0
    updated = 0
    skipped = 0
    seen: set[str] = set()

    for product in products:
        if product.symbol in seen:
            logger.warning(
                "Duplicate symbol %r in Delta payload; ignoring duplicate entry", product.symbol
            )
            skipped += 1
            continue
        seen.add(product.symbol)

        market_type = CONTRACT_TYPE_TO_MARKET_TYPE.get(product.contract_type)
        if market_type is None:
            logger.warning(
                "Skipping product %s: unsupported contract_type %r",
                product.symbol,
                product.contract_type,
            )
            skipped += 1
            continue

        base = product.underlying_asset.symbol if product.underlying_asset is not None else None
        quote = product.quoting_asset.symbol if product.quoting_asset is not None else None
        if base is None or quote is None:
            logger.warning("Skipping product %s: underlying/quoting asset missing", product.symbol)
            skipped += 1
            continue

        current = existing.get(product.symbol)
        metadata = _market_metadata(product)
        if current is None:
            session.add(
                Market(
                    exchange_id=exchange_id,
                    symbol=product.symbol,
                    base_asset=base,
                    quote_asset=quote,
                    market_type=market_type,
                    **metadata,
                )
            )
            inserted += 1
            continue

        if (
            current.base_asset == base
            and current.quote_asset == quote
            and current.market_type == market_type
            and _metadata_matches(current, metadata)
        ):
            skipped += 1
            continue

        current.base_asset = base
        current.quote_asset = quote
        current.market_type = market_type
        _apply_metadata(current, metadata)
        updated += 1

    return inserted, updated, skipped


def _market_metadata(product: Product) -> dict[str, object]:
    """Extract persistable metadata from a Delta product listing."""
    funding_interval = None
    if product.product_specs is not None:
        funding_interval = product.product_specs.rate_exchange_interval
    return {
        "delta_product_id": product.id,
        "delta_contract_type": product.contract_type,
        "tick_size": product.tick_size,
        "funding_method": product.funding_method,
        "funding_interval_seconds": funding_interval,
        "listing_date": product.launch_time,
    }


def _metadata_matches(market: Market, metadata: Mapping[str, object]) -> bool:
    """Return whether stored metadata already equals the upstream values."""
    for field, value in metadata.items():
        stored = getattr(market, field)
        if isinstance(stored, datetime) and isinstance(value, datetime):
            if _as_aware_utc(stored) != _as_aware_utc(value):
                return False
        elif stored != value:
            return False
    return True


def _as_aware_utc(value: datetime) -> datetime:
    """Treat naive datetimes as UTC for comparisons against aware values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _apply_metadata(market: Market, metadata: Mapping[str, object]) -> None:
    """Write upstream metadata onto an existing market record."""
    for field, value in metadata.items():
        setattr(market, field, value)