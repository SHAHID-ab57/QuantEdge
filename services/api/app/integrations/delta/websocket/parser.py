"""Delta Exchange WebSocket message parsing.

Preloads the generic :class:`app.ws.parser.MessageParser` registry with
the Delta Exchange message models.
"""

from app.integrations.delta.websocket import models as events
from app.ws.parser import MessageParser


class DeltaMessageParser(MessageParser):
    """Parser preloaded with the Delta Exchange message model registry."""

    def __init__(self) -> None:
        super().__init__()
        self.register("subscriptions", events.SubscriptionsEvent)
        self.register("key-auth", events.KeyAuthEvent)
        self.register("heartbeat", events.HeartbeatEvent)
        self.register("pong", events.PongEvent)
        self.register("ticker", events.TickerEvent)
        self.register("ob_l1", events.OrderBookL1Event)
        self.register("ob_l2", events.OrderBookL2Event)
        self.register("ob_updates", events.OrderBookUpdatesEvent)
        self.register("trades", events.TradesEvent)
        self.register("mark_price", events.MarkPriceEvent)
        self.register("candlestick_*", events.CandlestickEvent)
        self.register("candlesticks", events.CandlestickEvent)
        self.register("spot_price", events.SpotPriceEvent)
        self.register("spot_30mtwap_price", events.SpotTwapPriceEvent)
        self.register("funding_rate", events.FundingRateEvent)
        self.register("product_updates", events.ProductUpdatesEvent)
        self.register("system_status", events.SystemStatusEvent)
        self.register("positions", events.PositionsEvent)
        self.register("orders", events.OrdersEvent)
        self.register("user_trades", events.UserTradesEvent)
        self.register("margins", events.MarginsEvent)
