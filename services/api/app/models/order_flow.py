"""Order-flow / microstructure capture tables.

A **capture mechanism only**. These two tables persist the live order book
and trade stream — the same `OrderBookUpdated` / `TradeEventReceived` bus
events `app.marketdata.orderbook.OrderBookAggregator` and the Trade
Analytics dashboard already consume — so that a future microstructure
research task has real historical depth to work with instead of starting
from zero. Unlike every connector on this platform, order-flow data has
**no historical backfill**: it only accumulates in real time, one day per
calendar day, from the moment capture is switched on.

Nothing downstream reads these tables yet. There is deliberately no
feature generator, no connector abstraction integration, and no analysis —
that is a separate task, to be done once real depth has accumulated. See
`app.services.order_flow_capture.OrderFlowCapture`.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel

__all__ = ["OrderBookSnapshotRow", "TradeFlowRow"]


class OrderBookSnapshotRow(BaseModel):
    """One depth-limited order book snapshot for one symbol at one instant.

    Written on a fixed interval (`orderflow_snapshot_interval_seconds`), not
    per exchange tick — the read comes from `OrderBookAggregator`'s
    reconstructed book (snapshot + merged diffs), so each row is a coherent
    top-`depth` view, never a raw single-message diff. `bids`/`asks` are
    `[[price, size], ...]` string pairs (bids descending, asks ascending),
    kept as strings so the exact exchange-provided precision survives a JSON
    round-trip on both SQLite and PostgreSQL.
    """

    __tablename__ = "orderbook_snapshots"

    exchange: Mapped[str] = mapped_column(String(50), nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="The reconstructed book's own latest exchange event_time; falls back "
        "to the capture instant when the book carries none.",
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When this platform actually wrote the row.",
    )
    sequence: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="The book's last-applied exchange sequence number, when the feed provides one.",
    )
    depth: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Levels per side actually stored in this row."
    )
    bids: Mapped[list[list[str]]] = mapped_column(
        JSON, nullable=False, comment='Descending [["price","size"], ...] pairs.'
    )
    asks: Mapped[list[list[str]]] = mapped_column(
        JSON, nullable=False, comment='Ascending [["price","size"], ...] pairs.'
    )

    __table_args__ = (Index("ix_orderbook_snapshots_symbol_event_time", "symbol", "event_time"),)


class TradeFlowRow(BaseModel):
    """One market trade fill, captured verbatim from the live `trades` stream.

    One row per `TradeEventReceived`, buffered and flushed in batches
    (`orderflow_trade_flush_seconds` / `orderflow_trade_buffer_max`). No
    uniqueness constraint: Delta's compact `trades` channel carries no
    stable fill id, and the channel does not replay on reconnect, so
    duplicates are not expected — dedup, if ever needed, is a
    research-time concern, not a capture-time one.
    """

    __tablename__ = "trade_flow"

    exchange: Mapped[str] = mapped_column(String(50), nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="Exchange-assigned event time."
    )
    trade_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="The fill's own timestamp when distinct from event_time.",
    )
    side: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        comment="Aggressor side as normalized upstream: buy / sell / bid / ask / unknown.",
    )
    price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    size: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_trade_flow_symbol_event_time", "symbol", "event_time"),)
