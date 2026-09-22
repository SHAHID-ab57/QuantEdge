"""Delta Exchange's own funding-rate and open-interest history as connectors
(M4-E3-T3): two sources, one shared fetch path, both for ETHUSD.

**Investigated before building, not assumed (2026-09-21, against the real
public API):** the same `GET /v2/history/candles` endpoint the platform
already uses for OHLCV also serves derived series under prefixed symbols.

- `FUNDING:ETHUSD`: hourly candles from **2024-02-05 12:00 UTC**, 22,997 of
  them (24 missing, in eight 4-hour holes, all harmless for a step series).
  The series is a **step function**, not a list of settlements: `open ==
  close` in every candle, and the value changes only at funding times
  (multiples of 28,800 seconds), with one off-boundary change on
  2024-11-29 09:00. **The value at candle time `t` is the rate settled at
  `t`**, computed from the premium over the 8 hours *ending* at `t` (checked
  against Delta's own documented formula at 17 real funding times, see
  `docs/research/FUTURES_MECHANICS_AND_LEVERAGE_DESIGN.md` section 1.4), so it is
  knowable from `t` onward, never revised afterward, and safe to attach to any
  candle at or after `t`. Published **in percent** (`0.01` = 0.01%) and
  converted to a fraction exactly once, here, by the platform's single
  `funding_percent_to_fraction`.
- `OI:ETHUSD`: hourly OHLC candles from **2024-02-06 08:00 UTC**, 23,001 of
  them, no gaps, starting exactly where the price candles start. Denominated
  in ETH (15,247 in the latest stored candle on 2026-09-21, against the live
  ticker's 1,541,534 contracts times the 0.01 ETH contract value = 15,415).
  It is a **non-stationary level**: 0.09 ETH in February 2024, a monthly
  median of about 250 in May 2024 and 2,100 in November 2024, and 15,000 to
  26,000 through 2026, so its scale is dominated by the market's growth.

**What a point's `timestamp` means (the no-look-ahead rule).** Features
attach "the most recent value at or before the candle's `open_time`"
(`app.features.base.most_recent_value_at_or_before`), so a stored point must be
stamped with the moment its value was *observable*:

- funding: the candle time `t` at which the rate was set (a step, so a
  point is stored at every funding time, and wherever the value changed off
  the boundary, never once per constant hour);
- open interest: the candle's **`open`** stamped at the candle's open time
  `t`, i.e. OI *at the start of the hour*, knowable at `t`. The candle's
  `close` is not known until `t + 1h` and is deliberately not used.
  (Delta's OI candles are not contiguous: `open[t]` equals `close[t-1]` only
  37% of the time, so this is a genuine choice of sample, not an alias.)

**Why `external_data_points`, not a dedicated table.** The feature engine's
whole plumbing (as-of lookup, the sync scheduler, backfill, the health and
alerting monitor, the Data Sources page) works on `external_data_points`, and
both fit its shape: one number per `(source, timestamp)`. Funding *also* lives
in `funding_rates` (M3-E5-T2), which paper-trading settlement uses; that one
carries the index and mark price a payment needs and is keyed per market, so
the duplication is deliberate: two consumers, two shapes.

**ETHUSD only.** Feature lookups here are global (`symbol=None`), like
`eth_tvl`, so these two sources describe ETHUSD and must not be used to build
a dataset for another market; the feature descriptions say so.
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from app.connectors.base import ConnectorMetadata, RawDataPoint
from app.connectors.errors import (
    ConnectorAPIError,
    ConnectorNetworkError,
    ConnectorRateLimitError,
)
from app.connectors.registry import register_connector
from app.integrations.delta import (
    APIError,
    DeltaClient,
    NetworkError,
    RateLimitError,
    SeriesCandle,
    get_delta_client,
)
from app.services.funding_rates import funding_percent_to_fraction

logger = logging.getLogger("app.connectors.delta_market_data")

FUNDING_SOURCE = "delta_ethusd_funding_rate"
OPEN_INTEREST_SOURCE = "delta_ethusd_open_interest"
MARKET_SYMBOL = "ETHUSD"

#: Delta's candles endpoint returns at most 2,000 candles per request; stay
#: well inside it.
REQUEST_SPAN = timedelta(hours=1_500)
_RESOLUTION = "1h"
#: A funding time: every 8 hours from the Unix epoch (00:00, 08:00, 16:00 UTC).
FUNDING_INTERVAL_SECONDS = 28_800


async def fetch_series(
    client: DeltaClient, symbol: str, start: datetime, end: datetime
) -> list[SeriesCandle]:
    """Every hourly candle of `symbol` in `[start, end]`, oldest first, in
    request-sized chunks, with Delta's own errors mapped to connector errors."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware datetimes")
    if end < start:
        raise ValueError("end must not be before start")
    candles: dict[int, SeriesCandle] = {}
    cursor = start
    try:
        while cursor <= end:
            window_end = min(cursor + REQUEST_SPAN, end)
            for candle in await client.get_series(
                symbol=symbol,
                resolution=_RESOLUTION,
                start=int(cursor.timestamp()),
                # `end` is exclusive on the wire; +1 makes the range inclusive.
                end=int(window_end.timestamp()) + 1,
            ):
                candles[candle.time] = candle
            cursor = window_end + timedelta(seconds=1)
    except RateLimitError as exc:
        raise ConnectorRateLimitError(
            exc.message, retry_after=exc.retry_after, status_code=exc.status_code, detail=exc.detail
        ) from exc
    except NetworkError as exc:
        raise ConnectorNetworkError(exc.message, detail=exc.detail) from exc
    except APIError as exc:
        raise ConnectorAPIError(
            exc.message, status_code=exc.status_code, detail=exc.detail
        ) from exc
    return [candles[key] for key in sorted(candles)]


def _to_utc(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


class _DeltaSeriesConnector:
    """Shared plumbing: own a Delta client, close it, support `async with`."""

    def __init__(self, *, client: DeltaClient | None = None) -> None:
        self._client = client or get_delta_client()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):  # noqa: ANN204
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()


@register_connector
class DeltaFundingRateConnector(_DeltaSeriesConnector):
    """ETHUSD's perpetual funding rate, as a fraction per 8-hour interval."""

    metadata: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        source=FUNDING_SOURCE,
        label="ETHUSD Funding Rate",
        description=(
            "Delta Exchange's ETHUSD perpetual funding rate as a fraction per 8-hour "
            "interval (0.0001 = 0.01%; Delta publishes percent, converted once at "
            "ingestion). One point per funding time (00:00, 08:00, 16:00 UTC), stamped "
            "with the moment the rate was set: the rate is known from then on and never "
            "revised. Free and unauthenticated; history from 2024-02-05. ETHUSD only."
        ),
        frequency="every 8 hours (funding times)",
        # A point is stored at every funding time, so the real cadence is 8h.
        expected_interval_seconds=FUNDING_INTERVAL_SECONDS,
        requires_auth=False,
        version="1.0.0",
        aliases=("funding", "ethusd_funding"),
    )

    async def fetch(self, start: datetime, end: datetime) -> Sequence[RawDataPoint]:
        """Points at every funding time in `[start, end]`, plus any candle where the
        rate changed off the boundary. A constant stretch does not emit a point per
        hour: as-of lookup carries the last value forward, which is exactly what a
        step series means."""
        candles = await fetch_series(self._client, f"FUNDING:{MARKET_SYMBOL}", start, end)
        points: list[RawDataPoint] = []
        previous: float | None = None
        for candle in candles:
            value = float(candle.close)
            on_boundary = candle.time % FUNDING_INTERVAL_SECONDS == 0
            if on_boundary or previous is None or value != previous:
                points.append(
                    RawDataPoint(
                        timestamp=_to_utc(candle.time),
                        value=float(funding_percent_to_fraction(candle.close)),
                        symbol=None,
                        raw_payload={"candle": candle.model_dump(mode="json"), "unit": "percent"},
                    )
                )
            previous = value
        return tuple(points)


@register_connector
class DeltaOpenInterestConnector(_DeltaSeriesConnector):
    """ETHUSD's open interest in ETH, sampled at the start of each hour."""

    metadata: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        source=OPEN_INTEREST_SOURCE,
        label="ETHUSD Open Interest",
        description=(
            "Delta Exchange's ETHUSD perpetual open interest, in ETH, sampled at the "
            "START of each hour (the OI candle's open, stamped at the candle's open time, "
            "so it is knowable at that moment; its close is not used). Free and "
            "unauthenticated; history from 2024-02-06. ETHUSD only."
        ),
        frequency="hourly",
        expected_interval_seconds=3_600,
        requires_auth=False,
        version="1.0.0",
        aliases=("oi", "ethusd_oi"),
    )

    async def fetch(self, start: datetime, end: datetime) -> Sequence[RawDataPoint]:
        candles = await fetch_series(self._client, f"OI:{MARKET_SYMBOL}", start, end)
        return tuple(
            RawDataPoint(
                timestamp=_to_utc(candle.time),
                value=float(candle.open),
                symbol=None,
                raw_payload={"candle": candle.model_dump(mode="json"), "unit": "ETH"},
            )
            for candle in candles
        )
