"""Paper Trading service — place a market order against a real, realistic
fill, and track an account's positions and PnL.

Composes `MarketRepository`/`CandleRepository` directly (never a second
copy of them) and reads live state from the process-wide `MarketStateManager`
(`app/runtime.py`) — the same real market data every other live feature on
this platform already reads from, never a second data path invented for
this one.

**Accounting model, stated plainly** (see `PaperAccount`'s own docstring
for the schema side of this):

- `average_entry_price` (on `PaperPosition`) is the VWAP of *fill* prices
  only (post-slippage, pre-fee) — fees are never blended into cost basis.
- A **buy** immediately realizes its own fee as a certain, already-paid
  cost: `realized_pnl -= fee_applied`. It does not otherwise realize any
  gain/loss — converting cash into a position at cost is not a gain or a
  loss until that position is later sold.
- A **sell** realizes `(fill_price - average_entry_price) * quantity -
  fee_applied` — the price-move gain/loss on the quantity actually sold,
  net of this trade's own fee. `average_entry_price` itself never changes
  on a sell (it only ever moves via a buy's own VWAP average).
- **Once every position an account has ever held is fully closed, `balance`
  exactly equals `starting_balance + realized_pnl`** — every dollar has
  either been spent-then-recovered through a sell (netting into a realized
  gain/loss) or never spent at all. While a position is still open, the
  two numbers don't (and shouldn't) reconcile: the difference is exactly
  the cost-basis value of what's still held, which is neither a gain nor
  a loss yet — that's what `unrealized_pnl` is for, computed fresh on
  every read against a live price, never stored.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.paper_trading import PaperAccount, PaperOrder
from app.paper_trading.errors import (
    InsufficientBalanceError,
    InsufficientPositionError,
    InvalidPaperOrderSortError,
    PaperAccountNotFoundError,
)
from app.paper_trading.pricing import apply_fill_model, resolve_current_price
from app.repositories.candles import CandleRepository
from app.repositories.markets import MarketRepository
from app.repositories.paper_trading import (
    ORDER_SORT_COLUMNS,
    PaperAccountRepository,
    PaperOrderRepository,
    PaperPositionRepository,
)
from app.schemas.paper_trading import (
    PaperAccountCreateRequest,
    PaperAccountListResponse,
    PaperAccountResponse,
    PaperOrderListResponse,
    PaperOrderRequest,
    PaperOrderResponse,
    PaperPositionDTO,
    PaperPositionListResponse,
    PortfolioSummaryResponse,
)
from app.services.market_query import MarketNotFoundError
from app.state.manager import MarketStateManager


class PaperTradingService:
    """The one entry point routers use for every paper trading operation."""

    def __init__(
        self,
        account_repository: PaperAccountRepository,
        order_repository: PaperOrderRepository,
        position_repository: PaperPositionRepository,
        market_repository: MarketRepository,
        candle_repository: CandleRepository,
        state_manager: MarketStateManager,
        slippage_bps: int,
        fee_bps: int,
        staleness_threshold: timedelta,
    ) -> None:
        self.account_repository = account_repository
        self.order_repository = order_repository
        self.position_repository = position_repository
        self.market_repository = market_repository
        self.candle_repository = candle_repository
        self.state_manager = state_manager
        self.slippage_bps = slippage_bps
        self.fee_bps = fee_bps
        self.staleness_threshold = staleness_threshold

    async def create_account(self, request: PaperAccountCreateRequest) -> PaperAccountResponse:
        account = PaperAccount(
            name=request.name,
            starting_balance=request.starting_balance,
            balance=request.starting_balance,
            realized_pnl=Decimal(0),
        )
        created = await self.account_repository.create(account)
        return PaperAccountResponse.from_model(created)

    async def get_account(self, account_id: uuid.UUID) -> PaperAccountResponse:
        account = await self._get_account_or_404(account_id)
        return PaperAccountResponse.from_model(account)

    async def list_accounts(self, *, limit: int, offset: int) -> PaperAccountListResponse:
        accounts, total = await self.account_repository.list_all(limit=limit, offset=offset)
        return PaperAccountListResponse(
            accounts=[PaperAccountResponse.from_model(a) for a in accounts],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def place_order(
        self, account_id: uuid.UUID, request: PaperOrderRequest
    ) -> PaperOrderResponse:
        """Fill one market order immediately, completely, and realistically.

        There is no pending/partial-fill state: every order either fills
        in full right now (long-only — a buy adds to a position, a sell
        reduces one) or is rejected outright (insufficient cash for a buy,
        insufficient held quantity for a sell — never partially executed).
        """
        account = await self._get_account_or_404(account_id)
        market = await self.market_repository.get_by_symbol(request.symbol)
        if market is None:
            raise MarketNotFoundError(request.symbol)

        quote = await resolve_current_price(
            state_manager=self.state_manager,
            candle_repository=self.candle_repository,
            market_id=market.id,
            symbol=request.symbol,
            staleness_threshold=self.staleness_threshold,
        )
        fill = apply_fill_model(
            quote,
            side=request.side,
            quantity=request.quantity,
            slippage_bps=self.slippage_bps,
            fee_bps=self.fee_bps,
        )

        realized_pnl_this_order: Decimal | None = None
        if request.side == "buy":
            total_cost = fill.notional + fill.fee_applied
            available = Decimal(account.balance)
            if available < total_cost:
                raise InsufficientBalanceError(total_cost, available)
            await self.position_repository.apply_buy(
                account_id, request.symbol, request.quantity, fill.fill_price
            )
            new_balance = available - total_cost
            new_realized_pnl = Decimal(account.realized_pnl) - fill.fee_applied
            await self.account_repository.update(
                account, {"balance": new_balance, "realized_pnl": new_realized_pnl}
            )
        else:
            position = await self.position_repository.get_by_account_and_symbol(
                account_id, request.symbol
            )
            held = Decimal(position.quantity) if position is not None else Decimal(0)
            if position is None or request.quantity > held:
                raise InsufficientPositionError(request.symbol, request.quantity, held)
            upsert = await self.position_repository.apply_sell(position, request.quantity)
            realized_pnl_this_order = (
                fill.fill_price - upsert.previous_average_entry_price
            ) * request.quantity - fill.fee_applied
            net_proceeds = fill.notional - fill.fee_applied
            new_balance = Decimal(account.balance) + net_proceeds
            new_realized_pnl = Decimal(account.realized_pnl) + realized_pnl_this_order
            await self.account_repository.update(
                account, {"balance": new_balance, "realized_pnl": new_realized_pnl}
            )

        order = PaperOrder(
            account_id=account_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            raw_price=quote.price,
            fill_price=fill.fill_price,
            fill_time=datetime.now(UTC),
            price_source=quote.source,
            price_observed_at=quote.observed_at,
            is_stale_price=quote.is_stale,
            slippage_applied=fill.slippage_applied,
            fee_applied=fill.fee_applied,
            notional=fill.notional,
            realized_pnl=realized_pnl_this_order,
        )
        created = await self.order_repository.create(order)
        return PaperOrderResponse.from_model(created)

    async def list_orders(
        self,
        account_id: uuid.UUID,
        *,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> PaperOrderListResponse:
        await self._get_account_or_404(account_id)
        if sort not in ORDER_SORT_COLUMNS or direction not in {"asc", "desc"}:
            raise InvalidPaperOrderSortError(sort, direction, tuple(ORDER_SORT_COLUMNS))
        orders, total = await self.order_repository.search(
            account_id=account_id, sort=sort, direction=direction, limit=limit, offset=offset
        )
        return PaperOrderListResponse(
            orders=[PaperOrderResponse.from_model(o) for o in orders],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def list_positions(self, account_id: uuid.UUID) -> PaperPositionListResponse:
        """Every symbol this account currently holds, marked to the *same*
        live price a fill would use — never a slippage-adjusted
        hypothetical exit price (mark-to-market, not a projected trade)."""
        await self._get_account_or_404(account_id)
        positions = await self.position_repository.list_open(account_id)
        dtos = []
        for position in positions:
            market = await self.market_repository.get_by_symbol(position.symbol)
            if market is None:
                continue
            quote = await resolve_current_price(
                state_manager=self.state_manager,
                candle_repository=self.candle_repository,
                market_id=market.id,
                symbol=position.symbol,
                staleness_threshold=self.staleness_threshold,
            )
            dtos.append(
                PaperPositionDTO.from_model(
                    position, current_price=quote.price, price_source=quote.source
                )
            )
        return PaperPositionListResponse(positions=dtos)

    async def summary(self, account_id: uuid.UUID) -> PortfolioSummaryResponse:
        account = await self._get_account_or_404(account_id)
        positions = (await self.list_positions(account_id)).positions
        unrealized_pnl = sum((p.unrealized_pnl for p in positions), Decimal(0))
        position_value = sum((p.current_price * p.quantity for p in positions), Decimal(0))
        return PortfolioSummaryResponse(
            account_id=str(account.id),
            balance=account.balance,
            realized_pnl=account.realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_equity=Decimal(account.balance) + position_value,
            open_position_count=len(positions),
        )

    async def _get_account_or_404(self, account_id: uuid.UUID) -> PaperAccount:
        account = await self.account_repository.get_by_id(account_id)
        if account is None:
            raise PaperAccountNotFoundError(account_id)
        return account
