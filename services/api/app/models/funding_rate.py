"""Funding-rate history: Delta's real, published funding rate at each real
funding time, with the index and mark price alongside it.

Ingested from Delta's public candles endpoint (`FUNDING:<symbol>`,
`MARK:<symbol>`, and the product's spot-index symbol) by
`app.services.funding_rates`. **`funding_rate` here is a fraction** (0.0001
= 0.01%): Delta publishes the value in percent, and that conversion is done
exactly once, at ingestion, so nothing downstream ever has to remember it.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TimestampMixin

PRECISION = 38
SCALE = 18


class FundingRate(BaseModel, TimestampMixin):
    """The funding rate Delta applied at one funding time for one market."""

    __tablename__ = "funding_rates"

    market_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    funding_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    funding_rate: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        comment="Fraction per funding interval (0.0001 = 0.01%), converted from Delta's percent.",
    )
    index_price: Mapped[Any] = mapped_column(
        Numeric(PRECISION, SCALE),
        nullable=False,
        comment="The underlying index price at the funding time; the funding payment is "
        "position value at this price times the rate.",
    )
    mark_price: Mapped[Any] = mapped_column(Numeric(PRECISION, SCALE), nullable=True)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="delta_candles", server_default="delta_candles"
    )

    __table_args__ = (UniqueConstraint("market_id", "funding_time", name="uq_funding_rates_time"),)
