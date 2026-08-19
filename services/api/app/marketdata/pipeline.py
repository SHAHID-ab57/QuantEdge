"""The market data processing pipeline.

Stages, each independently testable:

.. code-block:: text

    Raw message
        |
        v
    Parser (registered WS models -> typed WSEvent)
        |
        v
    Normalizer (exchange-specific -> domain models)
        |
        v
    Validator (pydantic constraints on domain models)
        |
        v
    Domain event
        |
        v
    Event Bus (wrapped as TradeEventReceived / TickerUpdated / OrderBookUpdated)

Use :meth:`MarketDataPipeline.process_raw` for raw JSON frames (e.g. in
tests) or :meth:`MarketDataPipeline.handle` to wire the pipeline as a
listener of an already-parsing client:

.. code-block:: python

    pipeline = MarketDataPipeline(normalizer=DeltaNormalizer(), bus=bus)
    for message_type in ("trades", "ticker", "ob_l1", "ob_l2", "ob_updates"):
        client.add_listener(message_type, pipeline.handle)

Malformed or invalid messages never raise: they are logged, counted in
:class:`~app.marketdata.metrics.ProcessingMetrics`, and dropped.
"""

import logging
import time

from pydantic import ValidationError

from app.events.bus import EventBus
from app.events.event import Event
from app.integrations.delta.websocket.parser import DeltaMessageParser
from app.marketdata.bus_events import OrderBookUpdated, TickerUpdated, TradeEventReceived
from app.marketdata.metrics import ProcessingMetrics
from app.marketdata.models import (
    MarketDataEvent,
    OrderBookEvent,
    TickerEvent,
    TradeEvent,
)
from app.marketdata.normalizer import Normalizer
from app.ws.models import WSEvent
from app.ws.parser import MessageParser

__all__ = ["MarketDataPipeline"]

logger = logging.getLogger("app.marketdata")


class MarketDataPipeline:
    """Parses, normalizes, validates, and publishes market data."""

    def __init__(
        self,
        normalizer: Normalizer,
        bus: EventBus,
        parser: MessageParser | None = None,
        metrics: ProcessingMetrics | None = None,
        source: str = "delta.ws",
    ) -> None:
        self._normalizer = normalizer
        self._bus = bus
        self._parser = parser if parser is not None else DeltaMessageParser()
        self._metrics = metrics if metrics is not None else ProcessingMetrics()
        self._source = source

    @property
    def metrics(self) -> ProcessingMetrics:
        """Live metrics for this pipeline instance."""
        return self._metrics

    async def process_raw(self, raw: str) -> None:
        """Process one raw JSON frame through the full pipeline."""
        started = time.perf_counter()
        parsed = self._parser.parse(raw)
        if parsed.error is not None:
            self._metrics.messages_received += 1
            self._metrics.validation_failures += 1
            logger.warning("Market data message rejected: %s", parsed.error)
            return
        if parsed.event is None:
            return
        await self.handle(parsed.event, _started=started)

    async def handle(self, message: WSEvent, *, _started: float | None = None) -> None:
        """Process one already-parsed message (client listener wiring)."""
        self._metrics.messages_received += 1
        started = _started if _started is not None else time.perf_counter()
        try:
            result = self._normalizer.normalize(message)
        except ValidationError as exc:
            self._metrics.validation_failures += 1
            logger.warning(
                "Market data validation failed for %s: %s",
                message.type,
                _validation_summary(exc),
            )
            return
        if result.status == "unsupported":
            self._metrics.unsupported_messages += 1
            logger.debug("Unsupported market data message type: %s", message.type)
            return
        if result.status == "ignored":
            logger.debug("Ignored market data message: %s", message.type)
            return
        for event in result.events:
            await self._bus.publish(self._to_bus_event(event))
            self._metrics.events_published += 1
        self._metrics.messages_normalized += len(result.events)
        self._metrics.record_latency(time.perf_counter() - started)

    def _to_bus_event(self, event: MarketDataEvent) -> Event:
        if isinstance(event, TradeEvent):
            return TradeEventReceived(source=self._source, trade=event)
        if isinstance(event, TickerEvent):
            return TickerUpdated(source=self._source, ticker=event)
        if isinstance(event, OrderBookEvent):
            return OrderBookUpdated(source=self._source, order_book=event)
        raise TypeError(f"Unsupported domain event: {type(event).__name__}")


def _validation_summary(error: ValidationError) -> str:
    """Condense a ValidationError into ``field: reason`` entries."""
    return "; ".join(f"{entry['loc'][-1]}: {entry['msg']}" for entry in error.errors())