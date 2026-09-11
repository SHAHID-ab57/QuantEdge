"""Order-flow / microstructure capture — a **capture mechanism only**.

Persists the live order book and trade stream into `trade_flow` /
`orderbook_snapshots` so a future microstructure research task has real
historical depth to work with. Unlike every connector on this platform,
order-flow data has no historical backfill — it only accumulates in real
time — which is why this is worth switching on now even though nothing
reads it yet.

What it does **not** do: no feature engineering, no order-flow-imbalance
computation, no connector abstraction integration, no analysis. Those are
a separate task, once real depth has accumulated. See
`app.models.order_flow`.

Shape mirrors the rest of this platform's live components:

- **Trades** — subscribes to the same `TradeEventReceived` bus event
  `MarketStateManager` and the Trade Analytics dashboard already consume,
  buffers each fill, and flushes the buffer in batches
  (`orderflow_trade_flush_seconds` / `orderflow_trade_buffer_max`).
- **Order book** — reads `OrderBookAggregator`'s already-reconstructed
  top-`depth` book on a fixed interval (`orderflow_snapshot_interval_seconds`)
  rather than per exchange tick, so each stored row is a coherent snapshot,
  never a raw single-message diff.
- **Retention** — this capture has no cap otherwise (unbounded growth is a
  real operational risk, not a hypothetical one — see `ARCHITECTURE.md` §
  "Funding Rate, Open Interest & Order-Flow Capture" for the measured
  growth rate), so the same background loop also runs a periodic sweep
  (`orderflow_retention_days` / `orderflow_prune_interval_seconds`)
  deleting rows older than the retention window, keyed on each row's own
  `captured_at`.

Execution path, concretely (see `app.events.bus.EventBus.publish`): a bus
event schedules one independent `asyncio.Task` per subscribed handler, so
`OrderFlowCapture._on_trade` runs as its own task, never inline with
`MarketStateManager`, `OrderBookAggregator`, or `MarketStreamGateway`'s own
handlers for the same event — a slow database write here cannot block
their delivery to the running platform's own live consumers. Snapshotting
and pruning run on a fully separate background task
(`asyncio.create_task` in `start()`) outside the bus entirely. All three
paths share only the process's single-threaded event loop and the app's
one database connection pool; every write here awaits real (non-blocking)
asyncpg I/O, so it yields the loop rather than stalling it, and each write
holds a pool connection only for the duration of one insert/delete.

Database-optional and gated on live mode: if the WebSocket pipeline is not
running there are no events to capture, and if no database is configured
the loop simply does not start (`Runtime.start`).
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from time import perf_counter

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.engine import get_engine
from app.events.bus import EventBus
from app.events.event import Event
from app.marketdata.bus_events import TradeEventReceived
from app.marketdata.orderbook import OrderBookAggregator
from app.models.order_flow import OrderBookSnapshotRow, TradeFlowRow
from app.repositories.order_flow import OrderFlowRepository

logger = logging.getLogger("app.services.order_flow_capture")

_EXCHANGE = "delta"


class OrderFlowCapture:
    """Buffers live trades and periodically snapshots the reconstructed book."""

    def __init__(
        self,
        *,
        aggregator: OrderBookAggregator,
        symbols: tuple[str, ...],
        snapshot_interval_seconds: int = 15,
        snapshot_depth: int = 25,
        trade_flush_seconds: int = 5,
        trade_buffer_max: int = 500,
        retention_days: int = 60,
        prune_interval_seconds: int = 3600,
    ) -> None:
        self._aggregator = aggregator
        self._symbols = symbols
        self._snapshot_interval_seconds = max(snapshot_interval_seconds, 1)
        self._snapshot_depth = max(snapshot_depth, 1)
        self._trade_flush_seconds = max(trade_flush_seconds, 1)
        self._trade_buffer_max = max(trade_buffer_max, 1)
        self._retention = timedelta(days=max(retention_days, 1))
        self._prune_interval_seconds = max(prune_interval_seconds, 1)
        self._trade_buffer: list[TradeFlowRow] = []
        self._stopped = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        #: Cheap in-process counters so `Runtime`/tests can confirm capture is
        #: actually happening without querying the database.
        self.trades_captured = 0
        self.snapshots_captured = 0
        self.trades_pruned = 0
        self.snapshots_pruned = 0

    @property
    def running(self) -> bool:
        """True while the background flush/snapshot loop is alive."""
        return self._task is not None and not self._task.done()

    def attach(self, bus: EventBus) -> "OrderFlowCapture":
        """Subscribe the trade-buffering handler to the live event bus."""
        bus.subscribe("TradeEventReceived", self._on_trade)
        return self

    async def start(self) -> None:
        """Begin the periodic flush + snapshot loop."""
        if self.running:
            return
        if get_engine() is None:
            logger.warning("Order-flow capture not started: database not configured")
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._loop(), name="order-flow-capture-loop")
        logger.info(
            "Order-flow capture started (symbols=%s, snapshot=%ss/%d levels, flush=%ss, "
            "retention=%dd/prune every %ss)",
            ",".join(self._symbols) or "*",
            self._snapshot_interval_seconds,
            self._snapshot_depth,
            self._trade_flush_seconds,
            self._retention.days,
            self._prune_interval_seconds,
        )

    async def stop(self) -> None:
        """Stop the loop and flush whatever trades remain buffered."""
        task = self._task
        if task is None:
            return
        self._stopped.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._task = None
        await self._flush_trades()
        logger.info("Order-flow capture stopped")

    async def _on_trade(self, event: Event) -> None:
        if not isinstance(event, TradeEventReceived):
            return
        trade = event.trade
        self._trade_buffer.append(
            TradeFlowRow(
                exchange=trade.exchange or _EXCHANGE,
                symbol=trade.symbol,
                event_time=trade.event_time,
                trade_time=trade.trade_time,
                side=trade.side,
                price=trade.price,
                size=trade.size,
            )
        )
        if len(self._trade_buffer) >= self._trade_buffer_max:
            await self._flush_trades()

    async def _loop(self) -> None:
        last_snapshot = 0.0
        last_prune = 0.0
        try:
            while not self._stopped.is_set():
                await asyncio.sleep(self._trade_flush_seconds)
                await self._flush_trades()
                now = perf_counter()
                if now - last_snapshot >= self._snapshot_interval_seconds:
                    await self._capture_snapshots()
                    last_snapshot = now
                if now - last_prune >= self._prune_interval_seconds:
                    await self._prune()
                    last_prune = now
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a capture loop must never crash the runtime
            logger.exception("Order-flow capture loop errored; continuing")

    async def _flush_trades(self) -> None:
        if not self._trade_buffer:
            return
        batch = self._trade_buffer
        self._trade_buffer = []
        try:
            async with self._session_factory()() as session:
                written = await OrderFlowRepository(session).add_trades(batch)
            self.trades_captured += written
            logger.debug("Order-flow capture flushed %d trade(s)", written)
        except Exception:  # noqa: BLE001 - drop the batch, never re-raise into the loop
            logger.exception("Order-flow capture failed to persist %d trade(s)", len(batch))

    async def _capture_snapshots(self) -> None:
        targets = self._symbols or self._aggregator.symbols()
        for symbol in targets:
            book = self._aggregator.get_book(symbol, depth=self._snapshot_depth)
            if book is None:
                continue
            row = OrderBookSnapshotRow(
                exchange=_EXCHANGE,
                symbol=symbol,
                event_time=book.event_time or datetime.now(UTC),
                sequence=book.sequence,
                depth=self._snapshot_depth,
                bids=[[str(level.price), str(level.size)] for level in book.bids],
                asks=[[str(level.price), str(level.size)] for level in book.asks],
            )
            try:
                async with self._session_factory()() as session:
                    await OrderFlowRepository(session).add_snapshot(row)
                self.snapshots_captured += 1
                logger.debug(
                    "Order-flow capture stored a %s book snapshot (%d/%d levels)",
                    symbol,
                    len(row.bids),
                    len(row.asks),
                )
            except Exception:  # noqa: BLE001 - drop this snapshot, never re-raise
                logger.exception("Order-flow capture failed to persist a %s snapshot", symbol)

    async def _prune(self) -> None:
        """Delete rows older than the retention window from both tables.

        Runs on its own, much coarser cadence (`orderflow_prune_interval_seconds`)
        than the snapshot/flush loop — a `DELETE ... WHERE captured_at <
        cutoff` is cheap regardless of how often it runs, so there is no
        reason to couple it to the 5-15s capture cadence.
        """
        cutoff = datetime.now(UTC) - self._retention
        try:
            async with self._session_factory()() as session:
                repository = OrderFlowRepository(session)
                trades_deleted = await repository.prune_trades_older_than(cutoff)
                snapshots_deleted = await repository.prune_snapshots_older_than(cutoff)
            self.trades_pruned += trades_deleted
            self.snapshots_pruned += snapshots_deleted
            if trades_deleted or snapshots_deleted:
                logger.info(
                    "Order-flow capture pruned %d trade(s) and %d snapshot(s) older than %s",
                    trades_deleted,
                    snapshots_deleted,
                    cutoff.isoformat(),
                )
        except Exception:  # noqa: BLE001 - a failed prune must never crash the loop
            logger.exception("Order-flow capture retention sweep failed")

    @staticmethod
    def _session_factory() -> async_sessionmaker:
        engine = get_engine()
        if engine is None:  # pragma: no cover - guarded by start()
            raise RuntimeError("Database is not configured")
        return async_sessionmaker(bind=engine, expire_on_commit=False)
