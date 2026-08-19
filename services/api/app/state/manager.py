"""Market state manager.

Centralized in-memory source of truth for live market data. Consumes
normalized bus events (``TradeEventReceived``, ``TickerUpdated``,
``OrderBookUpdated``, ``CandleClosed``) and maintains the latest state
per symbol, keyed independently by event type.

Thread safety: handlers mutate state synchronously with no ``await``
between the read-modify-write steps, so concurrent handler tasks on the
single asyncio event loop cannot interleave mid-update. Queries are
synchronous plain methods — atomic reads, safe from handlers and REST
endpoints alike. Updates are last-writer-wins: stream order is
authoritative (order book reconstruction from ``seq``/checksum is a
consumer concern).
"""

import logging
import time
from datetime import UTC, datetime
from typing import TypeVar

from app.events.bus import EventBus
from app.events.event import Event
from app.events.example_events import CandleClosed
from app.marketdata.bus_events import OrderBookUpdated, TickerUpdated, TradeEventReceived
from app.marketdata.models import OrderBookEvent, TickerEvent, TradeEvent
from app.state.metrics import StateMetrics
from app.state.models import MarketState

__all__ = ["MarketStateManager"]

logger = logging.getLogger("app.state")

T = TypeVar("T")


class MarketStateManager:
    """Latest per-symbol market state, fed by the event bus."""

    def __init__(self, metrics: StateMetrics | None = None) -> None:
        self._metrics = metrics if metrics is not None else StateMetrics()
        self._trades: dict[str, TradeEvent] = {}
        self._tickers: dict[str, TickerEvent] = {}
        self._candles: dict[tuple[str, str], CandleClosed] = {}
        self._books: dict[str, OrderBookEvent] = {}
        self._latest_candle: dict[str, tuple[str, str]] = {}
        self._updated: dict[str, datetime] = {}

    @property
    def metrics(self) -> StateMetrics:
        """Live metrics for this manager instance."""
        return self._metrics

    def attach(self, bus: EventBus) -> "MarketStateManager":
        """Subscribe the state handlers to the four market event types."""
        bus.subscribe("TradeEventReceived", self._on_trade_received)
        bus.subscribe("TickerUpdated", self._on_ticker_updated)
        bus.subscribe("OrderBookUpdated", self._on_order_book_updated)
        bus.subscribe("CandleClosed", self._on_candle_closed)
        return self

    def symbols(self) -> frozenset[str]:
        """Symbols with at least one recorded update."""
        return frozenset(self._updated)

    def snapshot(self) -> dict[str, object]:
        """Immutable view of live market state for the metrics endpoint.

        Prices are the latest ticker ``last_price``, falling back to the
        latest trade price; rendered as strings to preserve precision in
        JSON.
        """
        symbols = sorted(self._updated)
        prices: dict[str, str] = {}
        for symbol in symbols:
            ticker = self._tickers.get(symbol)
            if ticker is not None and ticker.last_price is not None:
                prices[symbol] = str(ticker.last_price)
            else:
                trade = self._trades.get(symbol)
                if trade is not None:
                    prices[symbol] = str(trade.price)
        return {
            "symbols": symbols,
            "symbols_tracked": len(symbols),
            "latest_update_at": max(self._updated.values()) if self._updated else None,
            "latest_prices": prices,
            "trades_cached": len(self._trades),
            "tickers_cached": len(self._tickers),
            "order_books_cached": len(self._books),
            "candles_cached": len(self._candles),
        }

    def get_latest_trade(self, symbol: str) -> TradeEvent | None:
        """Latest normalized trade for ``symbol``, or ``None``."""
        return self._count(self._trades.get(symbol))

    def get_latest_ticker(self, symbol: str) -> TickerEvent | None:
        """Latest normalized ticker for ``symbol``, or ``None``."""
        return self._count(self._tickers.get(symbol))

    def get_latest_candle(
        self, symbol: str, resolution: str | None = None
    ) -> CandleClosed | None:
        """Latest closed candle for ``symbol``.

        With ``resolution``, the latest candle of that timeframe;
        otherwise the most recently updated resolution.
        """
        if resolution is not None:
            return self._count(self._candles.get((symbol, resolution)))
        key = self._latest_candle.get(symbol)
        return self._count(self._candles.get(key) if key is not None else None)

    def get_order_book(self, symbol: str) -> OrderBookEvent | None:
        """Latest order book event for ``symbol``, or ``None``."""
        return self._count(self._books.get(symbol))

    def get_market_state(self, symbol: str) -> MarketState | None:
        """Snapshot of the latest state for ``symbol``, or ``None``.

        ``None`` means the symbol has never produced an event.
        """
        updated_at = self._updated.get(symbol)
        if updated_at is None:
            self._metrics.cache_misses += 1
            return None
        self._metrics.cache_hits += 1
        key = self._latest_candle.get(symbol)
        return MarketState(
            symbol=symbol,
            updated_at=updated_at,
            trade=self._trades.get(symbol),
            ticker=self._tickers.get(symbol),
            candle=self._candles.get(key) if key is not None else None,
            order_book=self._books.get(symbol),
        )

    async def _on_trade_received(self, event: Event) -> None:
        if not isinstance(event, TradeEventReceived):
            self._reject(event, "TradeEventReceived")
            return
        started = time.perf_counter()
        trade = event.trade
        self._trades[trade.symbol] = trade
        self._touch(trade.symbol)
        self._record(started)

    async def _on_ticker_updated(self, event: Event) -> None:
        if not isinstance(event, TickerUpdated):
            self._reject(event, "TickerUpdated")
            return
        started = time.perf_counter()
        ticker = event.ticker
        self._tickers[ticker.symbol] = ticker
        self._touch(ticker.symbol)
        self._record(started)

    async def _on_order_book_updated(self, event: Event) -> None:
        if not isinstance(event, OrderBookUpdated):
            self._reject(event, "OrderBookUpdated")
            return
        started = time.perf_counter()
        book = event.order_book
        self._books[book.symbol] = book
        self._touch(book.symbol)
        self._record(started)

    async def _on_candle_closed(self, event: Event) -> None:
        if not isinstance(event, CandleClosed):
            self._reject(event, "CandleClosed")
            return
        started = time.perf_counter()
        key = (event.symbol, event.resolution)
        self._candles[key] = event
        self._latest_candle[event.symbol] = key
        self._touch(event.symbol)
        self._record(started)

    def _touch(self, symbol: str) -> None:
        """Mark ``symbol`` as updated, tracking first-time symbols."""
        if symbol not in self._updated:
            self._metrics.symbols_tracked += 1
        self._updated[symbol] = datetime.now(UTC)

    def _record(self, started: float) -> None:
        self._metrics.state_updates += 1
        self._metrics.record_latency(time.perf_counter() - started)

    def _reject(self, event: Event, expected: str) -> None:
        self._metrics.invalid_events += 1
        logger.warning(
            "Market state rejected %s event (expected %s)",
            type(event).__name__,
            expected,
        )

    def _count(self, value: T | None) -> T | None:
        if value is None:
            self._metrics.cache_misses += 1
        else:
            self._metrics.cache_hits += 1
        return value