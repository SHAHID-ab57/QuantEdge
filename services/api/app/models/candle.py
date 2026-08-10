"""Candle model — an immutable OHLCV market fact for one market/timeframe."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TimestampMixin

if TYPE_CHECKING:
    from app.models.market import Market

TIMEFRAMES = (
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "1w",
)

PRECISION = 38
SCALE = 18


class Candle(BaseModel, TimestampMixin):
    """Aggregated open/high/low/close prices and volume for one bucket."""

    __tablename__ = "candles"

    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timeframe: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    open_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    close_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    open: Mapped[Decimal] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
    )
    high: Mapped[Decimal] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
    )
    low: Mapped[Decimal] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
    )
    close: Mapped[Decimal] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
    )
    volume: Mapped[Decimal] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
    )
    quote_volume: Mapped[Decimal] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
    )

    trade_count: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "market_id",
            "timeframe",
            "open_time",
            name="uq_candles_market_timeframe_open_time",
        ),
        CheckConstraint("high >= open AND high >= close", name="high_dominant"),
        CheckConstraint("low <= open AND low <= close", name="low_dominant"),
        CheckConstraint("low >= 0", name="prices_nonnegative"),
        CheckConstraint("volume >= 0 AND quote_volume >= 0", name="volume_nonnegative"),
        CheckConstraint("close_time > open_time", name="time_ordered"),
        CheckConstraint(
            "timeframe IN ('1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', "
            "'6h', '8h', '12h', '1d', '1w')",
            name="timeframe_valid",
        ),
        CheckConstraint("trade_count >= 0", name="trade_count_nonnegative"),
        Index(
            "ix_candles_market_timeframe_time_desc",
            "market_id",
            "timeframe",
            text("open_time DESC"),
        ),
    )

    market: Mapped["Market"] = relationship(
        back_populates="candles",
        lazy="raise",
    )
