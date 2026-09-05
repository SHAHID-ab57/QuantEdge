"""Paper Trading REST endpoints.

A virtual trading account: place simulated market orders against a real,
realistic fill (modeled slippage and fee, always applied — see
`app/paper_trading/pricing.py`'s own module docstring), track positions,
and compute PnL. Long-only, market orders only. An account may also opt
into a single automated strategy (`PATCH .../strategy`, off by default)
that places orders through this exact same service — see
`ARCHITECTURE.md` § "Paper Trading" for the full design.
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
    PaperPositionDTO,
    PaperPositionListResponse,
    PaperStrategyConfigUpdateRequest,
    PaperStrategyDecisionListResponse,
    PortfolioSummaryResponse,
    PositionThresholdsUpdateRequest,
    RiskSummaryResponse,
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
                    "trading_halted": {
                        "summary": "This account's trading is halted by the drawdown limit",
                        "value": {
                            "code": "trading_halted",
                            "detail": "Trading is halted for this account: balance 7800.00 has "
                            "fallen more than 20 % below its peak of 10000.00. Resume trading "
                            "explicitly before placing another order — a halt never clears "
                            "itself on balance recovery.",
                        },
                    },
                    "max_position_size_exceeded": {
                        "summary": "This order's resulting position value exceeds the limit",
                        "value": {
                            "code": "max_position_size_exceeded",
                            "detail": "This order would bring the 'ETHUSD' position to a value "
                            "of 15000.00 — 15 % of the current balance of 100000.00 — exceeding "
                            "the 10 % max position size limit for this account",
                        },
                    },
                    "max_exposure_exceeded": {
                        "summary": "Total exposure after this order would exceed the limit",
                        "value": {
                            "code": "max_exposure_exceeded",
                            "detail": "This order would bring total exposure to 60000.00 — 60 % "
                            "of the current balance of 100000.00 — exceeding the 50 % max "
                            "exposure limit for this account",
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
                    "invalid_stop_loss_price": {
                        "summary": "A stop-loss at or above the current price would trigger "
                        "immediately",
                        "value": {
                            "code": "invalid_stop_loss_price",
                            "detail": "stop_loss_price 1050 must be below the current price "
                            "1000 for a long position — a value at or above the current price "
                            "would trigger immediately",
                        },
                    },
                    "invalid_take_profit_price": {
                        "summary": "A take-profit at or below the current price would trigger "
                        "immediately",
                        "value": {
                            "code": "invalid_take_profit_price",
                            "detail": "take_profit_price 950 must be above the current price "
                            "1000 for a long position — a value at or below the current price "
                            "would trigger immediately",
                        },
                    },
                    "stop_loss_not_below_take_profit": {
                        "summary": "The stop-loss and take-profit would overlap",
                        "value": {
                            "code": "stop_loss_not_below_take_profit",
                            "detail": "stop_loss_price 1100 must be strictly below "
                            "take_profit_price 1050 — otherwise a single price could satisfy "
                            "both trigger conditions at once",
                        },
                    },
                    "strategy_missing_training_job": {
                        "summary": "strategy_enabled=true with no training job named",
                        "value": {
                            "code": "strategy_missing_training_job",
                            "detail": "strategy_enabled cannot be set without a "
                            "strategy_training_job_id — the automated strategy needs a "
                            "completed training job to request predictions from",
                        },
                    },
                    "strategy_training_job_missing_symbol": {
                        "summary": "The named training job was never trained on real market data",
                        "value": {
                            "code": "strategy_training_job_missing_symbol",
                            "detail": "Training job 6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90 has no "
                            "recorded symbol — it was not trained on real market data, so the "
                            "automated strategy has no market to predict for",
                        },
                    },
                }
            }
        },
    },
    status.HTTP_404_NOT_FOUND: {
        "description": "Unknown account, market, position, or training job, or no price "
        "available at all",
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
                    "position_not_found": {
                        "summary": "This account holds no open position in this symbol",
                        "value": {
                            "code": "position_not_found",
                            "detail": "Account 6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90 holds no "
                            "open position in 'ETHUSD'",
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
                    "training_job_not_found": {
                        "summary": "The named strategy_training_job_id does not exist",
                        "value": {
                            "code": "training_job_not_found",
                            "detail": "Training job 6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90 not found",
                        },
                    },
                }
            }
        },
    },
}

PaperTradingServiceDep = Annotated[PaperTradingService, Depends(get_paper_trading_service)]
AccountIdPath = Annotated[uuid.UUID, Path(description="Paper trading account id")]
SymbolPath = Annotated[str, Path(description="Market symbol")]


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


@router.get(
    "/paper-trading/accounts/{account_id}/risk",
    response_model=RiskSummaryResponse,
    summary="An account's own current exposure and drawdown against its risk limits",
    responses=_ERROR_RESPONSES,
)
async def get_paper_risk_summary(
    account_id: AccountIdPath, service: PaperTradingServiceDep
) -> RiskSummaryResponse:
    """Return this account's own current exposure %, drawdown %, distance
    to each limit, and halted status."""
    return await service.risk_summary(account_id)


@router.post(
    "/paper-trading/accounts/{account_id}/resume-trading",
    response_model=PaperAccountResponse,
    summary="Explicitly clear a drawdown halt",
    description=(
        "The only way a drawdown halt ever clears — it does not self-heal on balance "
        "recovery. Also resets peak_balance to the account's current balance, so the account "
        "is measured for drawdown fresh from this point rather than immediately re-halting "
        "against its old, untouched peak on the very next order."
    ),
    responses=_ERROR_RESPONSES,
)
async def resume_paper_trading(
    account_id: AccountIdPath, service: PaperTradingServiceDep
) -> PaperAccountResponse:
    """Clear this account's trading_halted flag and reset its peak_balance."""
    return await service.resume_trading(account_id)


@router.patch(
    "/paper-trading/accounts/{account_id}/positions/{symbol}",
    response_model=PaperPositionDTO,
    summary="Set, update, or clear a position's stop-loss/take-profit",
    description=(
        "Only fields present in the request body are changed — send an explicit null to "
        "clear stop_loss_price/take_profit_price, omit a field to leave it unchanged. A long "
        "position's stop-loss must sit below the current price and its take-profit above it "
        "(and, when both are set, the stop-loss must be strictly below the take-profit) — a "
        "value that would trigger immediately is rejected."
    ),
    responses=_ERROR_RESPONSES,
)
async def update_paper_position_thresholds(
    account_id: AccountIdPath,
    symbol: SymbolPath,
    body: PositionThresholdsUpdateRequest,
    service: PaperTradingServiceDep,
) -> PaperPositionDTO:
    """Set/update/clear one position's stop-loss and take-profit."""
    return await service.update_position_thresholds(account_id, symbol, body)


@router.patch(
    "/paper-trading/accounts/{account_id}/strategy",
    response_model=PaperAccountResponse,
    summary="Enable/disable the automated strategy and tune its threshold/stop-loss",
    description=(
        "Off by default — paper trading only, and this never changes anything about live "
        "trading (Milestone 6 remains gated on extensive validation regardless). Only fields "
        "present in the request body are changed; send an explicit null for training_job_id "
        "to clear it, omit a field to leave it unchanged. Enabling requires a "
        "training_job_id that names a completed job trained on real market data (a recorded "
        "symbol) — the strategy always predicts for that job's own market, never a "
        "separately-configured one."
    ),
    responses=_ERROR_RESPONSES,
)
async def update_paper_strategy_config(
    account_id: AccountIdPath,
    body: PaperStrategyConfigUpdateRequest,
    service: PaperTradingServiceDep,
) -> PaperAccountResponse:
    """Enable/disable this account's automated strategy and tune its config."""
    return await service.update_strategy_config(account_id, body)


@router.get(
    "/paper-trading/accounts/{account_id}/strategy/decisions",
    response_model=PaperStrategyDecisionListResponse,
    summary="An account's own automated-strategy decision log",
    description=(
        "Every cycle the strategy scheduler ever ran for this account, acted on or not — "
        "what it acted on (a fresh prediction's own confidence/predicted value) and why, "
        "including a plain no_action reason for a cycle that changed nothing."
    ),
    responses=_ERROR_RESPONSES,
)
async def list_paper_strategy_decisions(
    account_id: AccountIdPath,
    service: PaperTradingServiceDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=get_settings().paper_trading_strategy_decisions_max_limit,
            description="Maximum decisions per page",
        ),
    ] = get_settings().paper_trading_strategy_decisions_default_limit,
    offset: Annotated[int, Query(ge=0, description="Number of decisions to skip")] = 0,
) -> PaperStrategyDecisionListResponse:
    """Return a page of this account's own strategy decision log, most recent first."""
    return await service.list_strategy_decisions(account_id, limit=limit, offset=offset)
