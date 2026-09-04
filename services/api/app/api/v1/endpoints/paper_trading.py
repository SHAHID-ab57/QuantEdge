"""Paper Trading REST endpoints.

A virtual trading account: place simulated market orders against a real,
realistic fill (modeled slippage and fee, always applied — see
`app/paper_trading/pricing.py`'s own module docstring), track positions,
and compute PnL. Long-only, market orders only, no automation — see
`ARCHITECTURE.md` § "Paper Trading" for the full design and what's
deliberately out of scope.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.config import get_settings
from app.dependencies.paper_trading import get_paper_trading_service
from app.schemas.paper_trading import (
    PaperAccountCreateRequest,
    PaperAccountListResponse,
    PaperAccountResponse,
    PaperOrderListResponse,
    PaperOrderRequest,
    PaperOrderResponse,
    PaperPositionListResponse,
    PortfolioSummaryResponse,
)
from app.services.paper_trading import PaperTradingService

router = APIRouter(tags=["paper-trading"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {
        "description": "The order cannot be filled as requested",
        "content": {
            "application/json": {
                "examples": {
                    "insufficient_balance": {
                        "summary": "A buy would take the account balance negative",
                        "value": {
                            "code": "insufficient_balance",
                            "detail": "Order requires 1001.00 (notional + fee) but the account "
                            "only has 500.00 available — this account has no margin, so the "
                            "order is rejected rather than partially filled or allowed to go "
                            "negative",
                        },
                    },
                    "insufficient_position": {
                        "summary": "A sell would exceed the held quantity (no shorting)",
                        "value": {
                            "code": "insufficient_position",
                            "detail": "Cannot sell 5 of 'ETHUSD': this account holds only 2 — "
                            "this platform is long-only, so a sell can never exceed the held "
                            "quantity (no shorting)",
                        },
                    },
                    "invalid_paper_order_sort": {
                        "summary": "Unsupported sort column on the order history endpoint",
                        "value": {
                            "code": "invalid_paper_order_sort",
                            "detail": "Invalid sort 'bogus'/'desc'. Available sort columns: "
                            "created_at, fill_time, side, symbol; direction must be 'asc' or "
                            "'desc'",
                        },
                    },
                }
            }
        },
    },
    status.HTTP_404_NOT_FOUND: {
        "description": "Unknown account or market, or no price available at all",
        "content": {
            "application/json": {
                "examples": {
                    "paper_account_not_found": {
                        "summary": "Unknown account id",
                        "value": {
                            "code": "paper_account_not_found",
                            "detail": "Paper trading account 6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90 "
                            "not found",
                        },
                    },
                    "market_not_found": {
                        "summary": "Unknown market symbol",
                        "value": {
                            "code": "market_not_found",
                            "detail": "Market 'DOES-NOT-EXIST' not found",
                        },
                    },
                    "no_price_available": {
                        "summary": "No live data and no candle ever stored for this symbol",
                        "value": {
                            "code": "no_price_available",
                            "detail": "No price available for 'ETHUSD' — no live ticker/trade "
                            "is flowing and no candle has ever been stored for it",
                        },
                    },
                }
            }
        },
    },
}

PaperTradingServiceDep = Annotated[PaperTradingService, Depends(get_paper_trading_service)]
AccountIdPath = Annotated[uuid.UUID, Path(description="Paper trading account id")]


@router.post(
    "/paper-trading/accounts",
    response_model=PaperAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open a new virtual trading account",
)
async def create_paper_account(
    body: PaperAccountCreateRequest, service: PaperTradingServiceDep
) -> PaperAccountResponse:
    """Open a new paper trading account with a starting cash balance."""
    return await service.create_account(body)


@router.get(
    "/paper-trading/accounts",
    response_model=PaperAccountListResponse,
    summary="List every paper trading account",
)
async def list_paper_accounts(
    service: PaperTradingServiceDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=get_settings().paper_trading_accounts_max_limit,
            description="Maximum accounts per page",
        ),
    ] = get_settings().paper_trading_accounts_default_limit,
    offset: Annotated[int, Query(ge=0, description="Number of accounts to skip")] = 0,
) -> PaperAccountListResponse:
    """Return a page of paper trading accounts, most recently created first."""
    return await service.list_accounts(limit=limit, offset=offset)


@router.get(
    "/paper-trading/accounts/{account_id}",
    response_model=PaperAccountResponse,
    summary="Get one paper trading account",
    responses=_ERROR_RESPONSES,
)
async def get_paper_account(
    account_id: AccountIdPath, service: PaperTradingServiceDep
) -> PaperAccountResponse:
    """Return one paper trading account by id."""
    return await service.get_account(account_id)


@router.post(
    "/paper-trading/accounts/{account_id}/orders",
    response_model=PaperOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Place a market order",
    description=(
        "Fills immediately and completely against a real, realistic price: the current "
        "ticker/trade if live data is flowing, otherwise the latest stored candle's own "
        "close — with a modeled slippage and fee always applied, never a perfect, "
        "cost-free fill. Long-only: a buy opens/adds to a position; a sell reduces/closes "
        "one and can never exceed the held quantity (no shorting, no margin)."
    ),
    responses=_ERROR_RESPONSES,
)
async def place_paper_order(
    account_id: AccountIdPath,
    body: PaperOrderRequest,
    service: PaperTradingServiceDep,
) -> PaperOrderResponse:
    """Place and fill one market order for this account."""
    return await service.place_order(account_id, body)


@router.get(
    "/paper-trading/accounts/{account_id}/orders",
    response_model=PaperOrderListResponse,
    summary="List an account's own order history",
    responses=_ERROR_RESPONSES,
)
async def list_paper_orders(
    account_id: AccountIdPath,
    service: PaperTradingServiceDep,
    sort: Annotated[
        str, Query(description="Sort column; one of symbol, side, fill_time, created_at")
    ] = "created_at",
    dir: Annotated[str, Query(description="Sort direction; asc or desc")] = "desc",
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=get_settings().paper_trading_orders_max_limit,
            description="Maximum orders per page",
        ),
    ] = get_settings().paper_trading_orders_default_limit,
    offset: Annotated[int, Query(ge=0, description="Number of orders to skip")] = 0,
) -> PaperOrderListResponse:
    """Return a page of this account's own filled orders."""
    return await service.list_orders(
        account_id, sort=sort, direction=dir, limit=limit, offset=offset
    )


@router.get(
    "/paper-trading/accounts/{account_id}/positions",
    response_model=PaperPositionListResponse,
    summary="List an account's currently-open positions",
    responses=_ERROR_RESPONSES,
)
async def list_paper_positions(
    account_id: AccountIdPath, service: PaperTradingServiceDep
) -> PaperPositionListResponse:
    """Return every symbol this account currently holds, marked to a live price."""
    return await service.list_positions(account_id)


@router.get(
    "/paper-trading/accounts/{account_id}/summary",
    response_model=PortfolioSummaryResponse,
    summary="An account's own balance, realized PnL, and live unrealized PnL",
    responses=_ERROR_RESPONSES,
)
async def get_paper_portfolio_summary(
    account_id: AccountIdPath, service: PaperTradingServiceDep
) -> PortfolioSummaryResponse:
    """Return this account's own portfolio summary."""
    return await service.summary(account_id)
