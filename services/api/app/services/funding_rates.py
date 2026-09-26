"""Funding-rate history ingestion from Delta's public candles endpoint.

**The unit is converted here, once.** Delta publishes `funding_rate` in
*percent* (`0.01` means 0.01%, the documented interest-rate floor), on the
`FUNDING:<symbol>` candle series and in its ticker alike. Everything
downstream (`app.paper_trading.margin.funding_payment`, the
`funding_rates` table) works in **fractions** (`0.0001` = 0.01%), and
`funding_percent_to_fraction` is the single place the conversion happens,
pinned by `tests/paper_trading/test_funding_rates.py` against the real
figures the unit was established from (Delta's own formula, checked against
17 real funding times, see `docs/research/FUTURES_MECHANICS_AND_LEVERAGE_
DESIGN.md` section 1.4).

**Which candle is the rate for a funding time.** The `FUNDING:` series is a
step function that changes exactly at each funding time; the value at candle
time `t` *is* the rate applied at `t` (it is computed from the 8-hour premium
window ending at `t`, and holds until the next funding time). The index and
mark price at `t` are the *open* of the candle that starts at `t`, the
closest sample to the funding instant.

Funding times fall on multiples of the market's funding interval from the
Unix epoch (`28800`s for ETHUSD/BTCUSD: 00:00, 08:00, 16:00 UTC).
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.integrations.delta import DeltaClient
from app.models.market import Market
from app.repositories.funding_rates import FundingRateRepository

logger = logging.getLogger("app.services.funding_rates")

#: Funding rate candles carry one value per funding interval, so hourly is
#: ample; the index/mark series are read at 5 minutes so the *open* at the
#: funding instant is a close sample of it.
FUNDING_RESOLUTION = "1h"
PRICE_RESOLUTION = "5m"


def funding_percent_to_fraction(published_percent: Decimal) -> Decimal:
    """Delta's published funding percent (`0.01` = 0.01%) as a fraction (`0.0001`)."""
    return published_percent / Decimal(100)


def funding_times_between(start: datetime, end: datetime, interval_seconds: int) -> list[datetime]:
    """Every funding time in `[start, end]`, ascending — multiples of
    `interval_seconds` from the Unix epoch, as timezone-aware UTC datetimes."""
    if interval_seconds <= 0:
        return []
    first = -(-int(start.timestamp()) // interval_seconds) * interval_seconds
    last = int(end.timestamp()) // interval_seconds * interval_seconds
    return [datetime.fromtimestamp(ts, UTC) for ts in range(first, last + 1, interval_seconds)]


class FundingRateIngestService:
    """Fetch and persist the funding rate, index price and mark price at each
    real funding time in a window, for one market."""

    def __init__(self, client: DeltaClient, repository: FundingRateRepository) -> None:
        self._client = client
        self._repository = repository

    async def ingest(self, market: Market, *, start: datetime, end: datetime) -> int:
        """Ingest every funding time in `[start, end]` for which Delta has
        published the funding rate, the index price and the mark price.
        Returns how many rows were newly created (re-ingesting is safe)."""
        interval = market.funding_interval_seconds
        if not interval:
            return 0
        times = funding_times_between(start, end, interval)
        if not times:
            return 0

        product = await self._client.get_product(market.symbol)
        if product.spot_index is None:
            logger.warning("No spot index on product %s; cannot price funding", market.symbol)
            return 0
        window_start = int(times[0].timestamp())
        window_end = int(times[-1].timestamp()) + 3600
        funding = await self._client.get_series(
            symbol=f"FUNDING:{market.symbol}",
            resolution=FUNDING_RESOLUTION,
            start=window_start,
            end=window_end,
        )
        index = await self._client.get_series(
            symbol=product.spot_index.symbol,
            resolution=PRICE_RESOLUTION,
            start=window_start,
            end=window_end,
        )
        mark = await self._client.get_series(
            symbol=f"MARK:{market.symbol}",
            resolution=PRICE_RESOLUTION,
            start=window_start,
            end=window_end,
        )
        funding_by_time = {c.time: c for c in funding}
        index_by_time = {c.time: c for c in index}
        mark_by_time = {c.time: c for c in mark}

        created = 0
        for funding_time in times:
            key = int(funding_time.timestamp())
            funding_candle = funding_by_time.get(key)
            index_candle = index_by_time.get(key)
            if funding_candle is None or index_candle is None:
                continue  # not (yet) published: settled on a later tick
            mark_candle = mark_by_time.get(key)
            was_new = await self._repository.upsert(
                market.id,
                funding_time,
                funding_rate=funding_percent_to_fraction(funding_candle.close),
                index_price=index_candle.open,
                mark_price=mark_candle.open if mark_candle is not None else None,
            )
            created += int(was_new)
        return created


def lookback_start(now: datetime, hours: int) -> datetime:
    return now - timedelta(hours=hours)
