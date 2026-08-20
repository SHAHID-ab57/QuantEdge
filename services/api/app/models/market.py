"""Market model — a tradeable instrument (trading pair) on an exchange."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TimestampMixin

if TYPE_CHECKING:
    from app.models.candle import Candle
    from app.models.exchange import Exchange

MARKET_TYPES = ("spot", "perpetual", "expiry")


class Market(BaseModel, TimestampMixin):
    """A trading pair or derivative contract, scoped to one exchange."""

    __tablename__ = "markets"

    exchange_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exchanges.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    base_asset: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    quote_asset: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    market_type: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="spot",
        server_default="spot",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    delta_product_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
    )
    delta_contract_type: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    tick_size: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    funding_method: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    funding_interval_seconds: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    listing_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "exchange_id",
            "symbol",
            name="uq_markets_exchange_symbol",
        ),
        CheckConstraint(
            "base_asset <> quote_asset",
            name="base_not_quote",
        ),
        CheckConstraint(
            "market_type IN ('spot', 'perpetual', 'expiry')",
            name="market_type_valid",
        ),
    )

    exchange: Mapped["Exchange"] = relationship(
        back_populates="markets",
        lazy="raise",
    )
    candles: Mapped[list["Candle"]] = relationship(
        back_populates="market",
        cascade="all, delete-orphan",
        lazy="raise",
    )
