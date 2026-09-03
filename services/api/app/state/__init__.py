"""Market state manager.

Centralized in-memory source of truth for live market data. Consumes
normalized bus events (``TradeEventReceived``, ``TickerUpdated``,
``OrderBookUpdated``, ``CandleClosed``) and serves the latest per-symbol
state through a synchronous query interface. No persistence, no Redis.
"""

from app.state.manager import MarketStateManager
from app.state.metrics import StateMetrics
from app.state.models import MarketState

__all__ = ["MarketState", "MarketStateManager", "StateMetrics"]
