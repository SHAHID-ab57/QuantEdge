"""Periodic funding for open paper positions: ingest Delta's real funding
history, then settle each real funding time exactly once.

Runs as a single asyncio task like `CandleSyncScheduler`/
`PaperTradingStrategyScheduler` (database-optional: a no-op with a warning
when no database is configured). One tick does two things, only for markets
in which some account holds an open position, so an idle platform never
calls Delta for funding:

1. **Ingest** the funding rate, index price and mark price at every funding
   time in the lookback window (`app.services.funding_rates`).
2. **Settle** every open position's funding for each of those funding times
   it held the position through (`PaperTradingService.settle_funding`). The
   `(account, symbol, funding_time)` unique key makes this idempotent, so a
   tick that repeats work, a restart, or a catch-up after downtime can never
   charge the same funding time twice.

A funding time with no published rate yet is simply skipped and picked up by
a later tick. Two honest limits: funding older than the lookback window is
not caught up after a long outage, and the quantity charged is the position's
*current* size (a position resized between a funding time and its
settlement is charged on the new size). With a five-minute tick the gap is
small, and both err by at most that gap's worth of resizing.
"""

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.db.engine import get_engine
from app.integrations.delta import get_delta_client
from app.repositories.audit_log import AuditLogRepository
from app.repositories.candles import CandleRepository
from app.repositories.funding_rates import FundingRateRepository
from app.repositories.markets import MarketRepository
from app.repositories.paper_trading import (
    PaperAccountRepository,
    PaperFundingSettlementRepository,
    PaperOrderRepository,
    PaperPositionRepository,
    PaperStrategyDecisionRepository,
)
from app.repositories.training import TrainingJobRepository
from app.services.funding_rates import FundingRateIngestService, funding_times_between
from app.services.paper_trading import PaperTradingService
from app.state.manager import MarketStateManager

logger = logging.getLogger("app.services.paper_funding")


@dataclass(frozen=True)
class FundingTickSummary:
    """Outcome of one funding pass."""

    symbols: int
    rates_ingested: int
    settled: int
    duration_seconds: float


def build_funding_service(
    session: AsyncSession, state_manager: MarketStateManager, settings: Settings
) -> PaperTradingService:
    """A `PaperTradingService` wired for funding settlement."""
    return PaperTradingService(
        account_repository=PaperAccountRepository(session),
        order_repository=PaperOrderRepository(session),
        position_repository=PaperPositionRepository(session),
        market_repository=MarketRepository(session),
        candle_repository=CandleRepository(session),
        training_job_repository=TrainingJobRepository(session),
        strategy_decision_repository=PaperStrategyDecisionRepository(session),
        audit_log_repository=AuditLogRepository(session),
        state_manager=state_manager,
        slippage_bps=settings.paper_trading_slippage_bps,
        fee_bps=settings.paper_trading_fee_bps,
        triggered_slippage_bps=settings.paper_trading_triggered_slippage_bps,
        staleness_threshold=timedelta(seconds=settings.paper_trading_stale_price_threshold_seconds),
        default_max_position_size_pct=settings.paper_trading_default_max_position_size_pct,
        default_max_exposure_pct=settings.paper_trading_default_max_exposure_pct,
        default_max_drawdown_pct=settings.paper_trading_default_max_drawdown_pct,
        max_order_attempts=settings.paper_trading_max_order_attempts,
        default_strategy_confidence_threshold_pct=(
            settings.paper_trading_strategy_default_confidence_threshold_pct
        ),
        default_strategy_default_stop_loss_pct=(
            settings.paper_trading_strategy_default_stop_loss_pct
        ),
        default_max_leverage=settings.paper_trading_default_max_leverage,
        maintenance_margin_rate=settings.paper_trading_maintenance_margin_pct / Decimal(100),
        max_leverage_notional=settings.paper_trading_max_leverage_notional,
        funding_settlement_repository=PaperFundingSettlementRepository(session),
    )


async def settle_open_positions(
    session: AsyncSession,
    state_manager: MarketStateManager,
    settings: Settings,
    *,
    symbols: list[str],
    now: datetime,
    lookback: timedelta,
) -> int:
    """Settle every open position in `symbols` for every funding time in the
    lookback window that has a stored rate. Returns how many payments were
    newly settled. Safe to call repeatedly."""
    service = build_funding_service(session, state_manager, settings)
    market_repository = MarketRepository(session)
    rate_repository = FundingRateRepository(session)
    position_repository = PaperPositionRepository(session)
    settled = 0
    for symbol in symbols:
        market = await market_repository.get_by_symbol(symbol)
        if market is None or not market.funding_interval_seconds:
            continue
        times = funding_times_between(now - lookback, now, market.funding_interval_seconds)
        positions = await position_repository.list_open_for_symbols([symbol])
        for funding_time in times:
            rate = await rate_repository.get(market.id, funding_time)
            if rate is None:
                continue
            for position in positions:
                try:
                    result = await service.settle_funding(
                        position.account_id,
                        symbol,
                        funding_time=funding_time,
                        funding_rate=Decimal(rate.funding_rate),
                        index_price=Decimal(rate.index_price),
                    )
                except Exception:
                    # Isolated per position — one account's failure must never
                    # stop the rest of this funding time's settlements.
                    logger.exception(
                        "Funding settlement failed: account=%s symbol=%s funding_time=%s",
                        position.account_id,
                        symbol,
                        funding_time.isoformat(),
                    )
                    continue
                settled += int(result is not None)
    return settled


class PaperFundingScheduler:
    """Periodic ingestion and settlement of funding for open paper positions."""

    def __init__(
        self,
        *,
        state_manager: MarketStateManager,
        interval_seconds: int = 300,
        lookback_hours: int = 48,
    ) -> None:
        self._state_manager = state_manager
        self._interval_seconds = max(interval_seconds, 1)
        self._lookback = timedelta(hours=max(lookback_hours, 1))
        self._stopped = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Begin the periodic loop, running the first tick immediately."""
        if self.running:
            return
        if get_engine() is None:
            logger.warning("Paper funding scheduler not started: database not configured")
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._loop(), name="paper-funding-loop")
        logger.info("Paper funding scheduler started (interval=%ss)", self._interval_seconds)

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        self._stopped.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._task = None
        logger.info("Paper funding scheduler stopped")

    async def _loop(self) -> None:
        while not self._stopped.is_set():
            try:
                summary = await self.run_tick()
                if summary.settled or summary.rates_ingested:
                    logger.info(
                        "Paper funding tick: symbols=%d rates_ingested=%d settled=%d in %.2fs",
                        summary.symbols,
                        summary.rates_ingested,
                        summary.settled,
                        summary.duration_seconds,
                    )
            except Exception:
                logger.exception("Paper funding tick crashed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval_seconds)

    async def run_tick(self) -> FundingTickSummary:
        """One pass: ingest funding history for every market with an open
        position, then settle. Opens its own session (the same
        `get_engine()`-gated pattern every scheduler here uses)."""
        started = perf_counter()
        engine = get_engine()
        if engine is None:
            logger.warning("Paper funding skipped: database is not configured")
            return FundingTickSummary(0, 0, 0, 0.0)

        settings = get_settings()
        now = datetime.now(UTC)
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with session_factory() as session:
            symbols = await PaperPositionRepository(session).list_open_symbols()
            ingested = 0
            if symbols:
                ingested = await self._ingest(session, symbols, now)
            settled = await settle_open_positions(
                session,
                self._state_manager,
                settings,
                symbols=symbols,
                now=now,
                lookback=self._lookback,
            )
        return FundingTickSummary(
            symbols=len(symbols),
            rates_ingested=ingested,
            settled=settled,
            duration_seconds=perf_counter() - started,
        )

    async def _ingest(self, session: AsyncSession, symbols: list[str], now: datetime) -> int:
        market_repository = MarketRepository(session)
        created = 0
        async with get_delta_client() as client:
            service = FundingRateIngestService(client, FundingRateRepository(session))
            for symbol in symbols:
                market = await market_repository.get_by_symbol(symbol)
                if market is None:
                    continue
                try:
                    created += await service.ingest(market, start=now - self._lookback, end=now)
                except Exception:
                    # Isolated per symbol: an upstream hiccup for one market
                    # must not stop settlement of rates already stored.
                    logger.exception("Funding rate ingest failed for %s", symbol)
        return created
