"""Market data processing pipeline.

Converts raw exchange WebSocket messages into exchange-independent
domain models and publishes them on the in-process event bus. Layered
as Parser -> Normalizer -> Validator -> Domain event -> Event Bus, with
processing metrics that can be exposed to Prometheus later.
"""

from app.marketdata.bus_events import (
    OrderBookUpdated,
    TickerUpdated,
    TradeEventReceived,
)
from app.marketdata.metrics import ProcessingMetrics
from app.marketdata.models import (
    MarketDataEvent,
    OrderBookEvent,
    OrderBookLevel,
    TickerEvent,
    TradeEvent,
)
from app.marketdata.normalizer import DeltaNormalizer, NormalizationResult, Normalizer
from app.marketdata.pipeline import MarketDataPipeline

__all__ = [
    "DeltaNormalizer",
    "MarketDataEvent",
    "MarketDataPipeline",
    "NormalizationResult",
    "Normalizer",
    "OrderBookEvent",
    "OrderBookLevel",
    "OrderBookUpdated",
    "ProcessingMetrics",
    "TickerEvent",
    "TickerUpdated",
    "TradeEvent",
    "TradeEventReceived",
]
