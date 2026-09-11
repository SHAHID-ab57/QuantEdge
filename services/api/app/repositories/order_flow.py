"""Write/read access to the order-flow capture tables.

Deliberately thin: `app.services.order_flow_capture.OrderFlowCapture`
writes through `add_trades` / `add_snapshot`, and the count/latest helpers
exist only so the capture can be verified against real persisted data (no
consumer reads these tables for anything else yet). `prune_trades_older_than`
/ `prune_snapshots_older_than` back the same capture's own retention sweep —
see its module docstring for why an unbounded capture table needs one.
"""

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_flow import OrderBookSnapshotRow, TradeFlowRow


class OrderFlowRepository:
    """Create/read access to `trade_flow` and `orderbook_snapshots`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_trades(self, rows: list[TradeFlowRow]) -> int:
        """Insert a batch of captured trades; returns how many were written."""
        if not rows:
            return 0
        self.session.add_all(rows)
        await self.session.commit()
        return len(rows)

    async def add_snapshot(self, row: OrderBookSnapshotRow) -> OrderBookSnapshotRow:
        """Insert one order book snapshot."""
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def count_trades(self, symbol: str | None = None) -> int:
        stmt = select(func.count()).select_from(TradeFlowRow)
        if symbol is not None:
            stmt = stmt.where(TradeFlowRow.symbol == symbol)
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_snapshots(self, symbol: str | None = None) -> int:
        stmt = select(func.count()).select_from(OrderBookSnapshotRow)
        if symbol is not None:
            stmt = stmt.where(OrderBookSnapshotRow.symbol == symbol)
        return int((await self.session.execute(stmt)).scalar_one())

    async def latest_snapshot(self, symbol: str) -> OrderBookSnapshotRow | None:
        stmt = (
            select(OrderBookSnapshotRow)
            .where(OrderBookSnapshotRow.symbol == symbol)
            .order_by(OrderBookSnapshotRow.event_time.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def prune_trades_older_than(self, cutoff: datetime) -> int:
        """Delete captured trades with ``captured_at`` before ``cutoff``.

        Keyed on capture time, not the exchange's own ``event_time`` — the
        retention window is about how long *this platform* has held the
        row, independent of any backfill or replay that might one day
        write an old ``event_time`` deliberately.
        """
        result = await self.session.execute(
            delete(TradeFlowRow).where(TradeFlowRow.captured_at < cutoff)
        )
        await self.session.commit()
        # A Core DML `delete()` always yields a `CursorResult` at runtime,
        # narrowed here rather than assumed via `cast`/`# type: ignore` — see
        # `TrainingJobRepository.try_transition_to_running`'s own comment.
        assert isinstance(result, CursorResult)
        return result.rowcount or 0

    async def prune_snapshots_older_than(self, cutoff: datetime) -> int:
        """Delete order book snapshots with ``captured_at`` before ``cutoff``."""
        result = await self.session.execute(
            delete(OrderBookSnapshotRow).where(OrderBookSnapshotRow.captured_at < cutoff)
        )
        await self.session.commit()
        assert isinstance(result, CursorResult)
        return result.rowcount or 0
