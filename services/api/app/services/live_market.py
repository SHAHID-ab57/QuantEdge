"""Live ticker + funding assembly for the REST layer.

Reads the in-memory :class:`~app.state.manager.MarketStateManager` (fed by
the Delta WebSocket) and, when the funding rate or open interest is not yet
in memory, fills those two fields in with a single time-boxed Delta REST
call. Funding frames are infrequent — one per funding interval plus one on
each rate change — so a freshly (re)connected server legitimately has
ticker and trade data flowing while the funding rate is still unknown; the
REST fill-in closes that window for the ``GET /markets/{symbol}/ticker``
endpoint without adding a second streaming path.

No SQL and no persistence: this is a pure read-through over live state.
"""

import logging

from app.integrations.delta.client import DeltaClient
from app.integrations.delta.exceptions import DeltaError
from app.schemas.market_data import LiveTickerResponse
from app.state.manager import MarketStateManager

logger = logging.getLogger("app.services.live_market")

__all__ = ["LiveMarketService"]


class LiveMarketService:
    """Assembles a live ticker snapshot from market state, REST as fallback."""

    def __init__(
        self,
        *,
        state_manager: MarketStateManager,
        delta_client: DeltaClient | None = None,
    ) -> None:
        """Wire the service.

        Args:
            state_manager: The process-wide live market state.
            delta_client: Delta REST client used only for the funding/OI
                fill-in. When ``None`` the fill-in is skipped and the
                snapshot reflects live state alone.
        """
        self._state = state_manager
        self._delta = delta_client

    async def get_ticker(self, symbol: str) -> LiveTickerResponse:
        """Return the latest ticker + funding snapshot for ``symbol``.

        Always returns a response: a symbol with no live data yet yields
        one with every price field ``None`` and ``source="none"``.
        """
        symbol = symbol.strip().upper()
        ticker = self._state.get_latest_ticker(symbol)
        funding = self._state.get_latest_funding_rate(symbol)
        state = self._state.get_market_state(symbol)

        response = LiveTickerResponse(
            symbol=symbol,
            as_of=state.updated_at if state is not None else None,
        )
        if ticker is not None:
            response.last_price = ticker.last_price
            response.bid = ticker.bid
            response.ask = ticker.ask
            response.mark_price = ticker.mark_price
            response.spot_price = ticker.spot_price
            response.open_interest = ticker.open_interest
            response.price_change_24h = ticker.price_change_24h
            response.turnover_24h = ticker.turnover
        if funding is not None:
            response.source = "ws"
            response.funding_rate = funding.funding_rate
            response.funding_interval_seconds = funding.funding_interval_seconds
            response.next_funding_time = funding.next_funding_time

        needs_fill = response.funding_rate is None or response.open_interest is None
        if needs_fill and self._delta is not None:
            await self._fill_from_rest(symbol, response)

        return response

    async def _fill_from_rest(self, symbol: str, response: LiveTickerResponse) -> None:
        """Best-effort REST fill-in for funding rate and open interest.

        Never raises: a Delta failure leaves the response as-is (funding
        and/or OI simply stay ``None``).
        """
        if self._delta is None:
            return
        try:
            snapshot = await self._delta.get_ticker(symbol)
        except DeltaError as exc:
            logger.warning("Delta REST ticker fill-in for %s failed: %s", symbol, exc)
            return

        # Prefer `oi_contracts` — the WebSocket ticker's `oi` is also in
        # contracts, so this keeps the field's meaning stable whichever
        # path filled it. `oi` (asset units) is the fallback's fallback.
        rest_oi = snapshot.oi_contracts if snapshot.oi_contracts is not None else snapshot.oi
        if response.open_interest is None and rest_oi is not None:
            response.open_interest = rest_oi
        if response.mark_price is None and snapshot.mark_price is not None:
            response.mark_price = snapshot.mark_price
        if response.spot_price is None and snapshot.spot_price is not None:
            response.spot_price = snapshot.spot_price
        if response.turnover_24h is None and snapshot.turnover_usd is not None:
            response.turnover_24h = snapshot.turnover_usd
        if response.funding_rate is None and snapshot.funding_rate is not None:
            response.funding_rate = snapshot.funding_rate
            response.source = "rest"
