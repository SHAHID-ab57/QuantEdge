"""Funding settlement for open positions: correct amount, correct direction,
idempotency under repeated and catch-up runs, and the cash-then-margin rule.

Amounts are worked out by hand. A position of 10 units against an index price
of $2,500 has a position value of $25,000, so at a funding rate of 0.01%
(`0.0001` as a fraction) it owes `25000 * 0.0001 = $2.50`.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.models.funding_rate import FundingRate
from app.models.market import Market
from app.models.paper_trading import PaperFundingSettlement
from app.repositories.paper_trading import PaperFundingSettlementRepository
from app.services import paper_funding as paper_funding_module
from app.services.paper_funding import (
    PaperFundingScheduler,
    build_funding_service,
    settle_open_positions,
)
from app.services.paper_trading import PaperTradingService
from tests.conftest import SessionFactory
from tests.paper_trading.test_funding_rates import FakeDeltaClient
from tests.paper_trading.test_service import build_service
from tests.paper_trading.test_short_and_leverage import Env, make_env, num

D = Decimal
SETTLEMENT_INTERVAL = 28800


async def funded_env(session_factory: SessionFactory, symbol: str, **kwargs: object) -> Env:
    env = await make_env(session_factory, symbol, **kwargs)  # type: ignore[arg-type]
    async with session_factory() as session:
        await session.execute(
            update(Market).where(Market.symbol == symbol).values(funding_interval_seconds=28800)
        )
        await session.commit()
    return env


async def funding_service(env: Env, session_factory: SessionFactory) -> PaperTradingService:
    """A service with a funding-settlement repository, on its own session."""
    service = await build_service(session_factory, env.service.state_manager)
    service.funding_settlement_repository = PaperFundingSettlementRepository(
        service.account_repository.session
    )
    return service


async def opened_at(env: Env) -> datetime:
    position = await env.service.position_repository.get_by_account_and_symbol(
        env.account_id, env.symbol
    )
    assert position is not None and position.opened_at is not None
    stamp = position.opened_at
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


async def settle(
    service: PaperTradingService,
    env: Env,
    when: datetime,
    *,
    rate: str = "0.0001",
    index: str = "2500",
):  # noqa: ANN201
    return await service.settle_funding(
        env.account_id,
        env.symbol,
        funding_time=when,
        funding_rate=D(rate),
        index_price=D(index),
    )


async def settlements(session_factory: SessionFactory) -> list[PaperFundingSettlement]:
    async with session_factory() as session:
        return list((await session.execute(select(PaperFundingSettlement))).scalars().all())


@pytest.mark.asyncio
class TestSettlementAmountAndDirection:
    async def test_a_long_pays_when_the_rate_is_positive(
        self, session_factory: SessionFactory
    ) -> None:
        env = await funded_env(session_factory, "PTFUNDLONGUSD", price="2500")
        await env.order("buy", "10")
        cash_before = num((await env.account()).balance)
        realized_before = num((await env.account()).realized_pnl)
        service = await funding_service(env, session_factory)

        result = await settle(service, env, await opened_at(env) + timedelta(hours=1))

        assert result is not None
        assert num(result.payment) == pytest.approx(2.5)  # 10 * 2500 * 0.0001
        assert result.position_side == "long"
        assert num(result.funding_rate) == pytest.approx(0.0001)  # a fraction
        assert num(result.index_price) == 2500
        assert num(result.charged_to_margin) == 0  # cash covered it
        account = await env.account()
        assert num(account.balance) == pytest.approx(cash_before - 2.5)
        assert num(account.realized_pnl) == pytest.approx(realized_before - 2.5)

    async def test_a_short_receives_when_the_rate_is_positive(
        self, session_factory: SessionFactory
    ) -> None:
        env = await funded_env(session_factory, "PTFUNDSHORTUSD", price="2500")
        await env.order("sell", "10")
        cash_before = num((await env.account()).balance)
        service = await funding_service(env, session_factory)

        result = await settle(service, env, await opened_at(env) + timedelta(hours=1))

        assert result is not None
        assert num(result.payment) == pytest.approx(-2.5)  # negative: it received
        assert num((await env.account()).balance) == pytest.approx(cash_before + 2.5)

    async def test_the_directions_reverse_when_the_rate_is_negative(
        self, session_factory: SessionFactory
    ) -> None:
        long_env = await funded_env(session_factory, "PTFUNDNEGLUSD", price="2500")
        short_env = await funded_env(session_factory, "PTFUNDNEGSUSD", price="2500")
        await long_env.order("buy", "10")
        await short_env.order("sell", "10")
        long_cash = num((await long_env.account()).balance)
        short_cash = num((await short_env.account()).balance)

        for env in (long_env, short_env):
            service = await funding_service(env, session_factory)
            await settle(service, env, await opened_at(env) + timedelta(hours=1), rate="-0.0001")

        assert num((await long_env.account()).balance) == pytest.approx(long_cash + 2.5)
        assert num((await short_env.account()).balance) == pytest.approx(short_cash - 2.5)

    async def test_the_payment_is_priced_on_the_index_price_not_the_entry_or_last_price(
        self, session_factory: SessionFactory
    ) -> None:
        env = await funded_env(session_factory, "PTFUNDINDEXUSD", price="2500")
        await env.order("buy", "10")
        await env.price("2600")  # last price has moved; the index price given is what counts
        service = await funding_service(env, session_factory)
        result = await settle(service, env, await opened_at(env) + timedelta(hours=1), index="2400")
        assert result is not None
        assert num(result.payment) == pytest.approx(10 * 2400 * 0.0001)

    async def test_funding_is_part_of_realized_pnl_so_cash_still_reconciles(
        self, session_factory: SessionFactory
    ) -> None:
        env = await funded_env(session_factory, "PTFUNDRECONUSD", price="2500")
        await env.order("sell", "10")
        service = await funding_service(env, session_factory)
        base = await opened_at(env)
        for hours in (1, 9, 17):
            await settle(service, env, base + timedelta(hours=hours))
        await env.order("buy", "10", reduce_only=True)
        assert await env.position() is None
        account = await env.account()
        # Flat: every dollar is accounted for by starting balance + realized PnL.
        assert num(account.balance) == pytest.approx(100000 + num(account.realized_pnl))


@pytest.mark.asyncio
class TestSettlementIdempotency:
    async def test_settling_the_same_funding_time_twice_charges_once(
        self, session_factory: SessionFactory
    ) -> None:
        env = await funded_env(session_factory, "PTFUNDTWICEUSD", price="2500")
        await env.order("buy", "10")
        cash_before = num((await env.account()).balance)
        service = await funding_service(env, session_factory)
        when = await opened_at(env) + timedelta(hours=1)

        first = await settle(service, env, when)
        second = await settle(service, env, when)

        assert first is not None
        assert second is None  # already settled
        assert num((await env.account()).balance) == pytest.approx(cash_before - 2.5)
        assert len(await settlements(session_factory)) == 1

    async def test_a_funding_time_before_the_position_was_opened_owes_nothing(
        self, session_factory: SessionFactory
    ) -> None:
        env = await funded_env(session_factory, "PTFUNDEARLYUSD", price="2500")
        await env.order("buy", "10")
        cash_before = num((await env.account()).balance)
        service = await funding_service(env, session_factory)

        result = await settle(service, env, await opened_at(env) - timedelta(minutes=1))

        assert result is None
        assert num((await env.account()).balance) == pytest.approx(cash_before)
        assert await settlements(session_factory) == []

    async def test_a_flat_account_owes_nothing(self, session_factory: SessionFactory) -> None:
        env = await funded_env(session_factory, "PTFUNDFLATUSD", price="2500")
        service = await funding_service(env, session_factory)
        assert await settle(service, env, datetime.now(UTC)) is None


@pytest.mark.asyncio
class TestCatchUp:
    async def test_a_catch_up_run_settles_every_missed_funding_time_once(
        self, session_factory: SessionFactory
    ) -> None:
        """Simulates downtime: three funding times have passed with rates on
        record, then two identical catch-up runs. All three are charged, once."""
        env = await funded_env(session_factory, "PTFUNDCATCHUSD", price="2500")
        await env.order("buy", "10")
        cash_before = num((await env.account()).balance)
        opened = await opened_at(env)
        first = (int(opened.timestamp()) // SETTLEMENT_INTERVAL + 1) * SETTLEMENT_INTERVAL
        times = [datetime.fromtimestamp(first + i * SETTLEMENT_INTERVAL, UTC) for i in range(3)]
        before_open = times[0] - timedelta(seconds=SETTLEMENT_INTERVAL)

        async with session_factory() as session:
            market = (
                await session.execute(select(Market).where(Market.symbol == env.symbol))
            ).scalar_one()
            for when in [before_open, *times]:
                session.add(
                    FundingRate(
                        market_id=market.id,
                        funding_time=when,
                        funding_rate=D("0.0001"),
                        index_price=D("2500"),
                    )
                )
            await session.commit()

        async def run() -> int:
            async with session_factory() as session:
                return await settle_open_positions(
                    session,
                    env.service.state_manager,
                    get_settings(),
                    symbols=[env.symbol],
                    now=times[-1] + timedelta(minutes=1),
                    lookback=timedelta(hours=48),
                )

        assert await run() == 3  # the funding time before it opened is not among them
        assert await run() == 0  # a repeat run is a no-op
        assert num((await env.account()).balance) == pytest.approx(cash_before - 3 * 2.5)
        assert len(await settlements(session_factory)) == 3


@pytest.mark.asyncio
class TestCashThenMargin:
    async def test_the_part_cash_cannot_cover_is_taken_from_the_positions_margin(
        self, session_factory: SessionFactory
    ) -> None:
        env = await funded_env(session_factory, "PTFUNDMARGINUSD", price="2500", max_leverage="5")
        await env.order("sell", "4", leverage="5")  # notional ~$10,000, margin ~$2,000
        before = await env.position()
        assert before is not None and before.liquidation_price is not None
        account = await env.service.account_repository.get_by_id(env.account_id)
        assert account is not None
        await env.service.account_repository.update(account, {"balance": D("1")})
        realized_before = num(account.realized_pnl)
        service = await funding_service(env, session_factory)

        # A short PAYS at a negative rate: 4 * 2500 * 0.01 = $100 owed, $1 of cash.
        result = await settle(service, env, await opened_at(env) + timedelta(hours=1), rate="-0.01")

        assert result is not None
        assert num(result.payment) == pytest.approx(100.0)
        assert num(result.charged_to_margin) == pytest.approx(99.0)
        after = await env.position()
        assert after is not None
        assert num(after.margin) == pytest.approx(num(before.margin) - 99.0)
        # Less margin: the liquidation price moved closer to the market.
        assert after.liquidation_price is not None
        assert num(after.liquidation_price) < num(before.liquidation_price)
        settled_account = await env.account()
        assert num(settled_account.balance) == pytest.approx(0.0)
        assert num(settled_account.realized_pnl) == pytest.approx(realized_before - 100.0)

    async def test_a_credit_never_touches_margin(self, session_factory: SessionFactory) -> None:
        env = await funded_env(session_factory, "PTFUNDCREDITUSD", price="2500", max_leverage="5")
        await env.order("sell", "4", leverage="5")
        before = await env.position()
        assert before is not None
        service = await funding_service(env, session_factory)
        result = await settle(service, env, await opened_at(env) + timedelta(hours=1))
        assert result is not None and num(result.payment) < 0
        after = await env.position()
        assert after is not None
        assert num(after.margin) == pytest.approx(num(before.margin))


@pytest.mark.asyncio
class TestFundingList:
    async def test_the_accounts_settlements_are_listed_most_recent_first(
        self, session_factory: SessionFactory
    ) -> None:
        env = await funded_env(session_factory, "PTFUNDLISTUSD", price="2500")
        await env.order("buy", "10")
        service = await funding_service(env, session_factory)
        base = await opened_at(env)
        await settle(service, env, base + timedelta(hours=1))
        await settle(service, env, base + timedelta(hours=9), rate="0.0002")

        page = await service.list_funding_settlements(env.account_id, limit=10, offset=0)

        assert page.total == 2
        assert [num(s.funding_rate) for s in page.settlements] == pytest.approx([0.0002, 0.0001])
        assert page.settlements[0].funding_time > page.settlements[1].funding_time


@pytest.mark.asyncio
class TestFundingScheduler:
    async def test_a_tick_ingests_rates_but_owes_nothing_for_times_before_the_position_existed(
        self,
        session_factory: SessionFactory,
        engine,
        monkeypatch: pytest.MonkeyPatch,  # noqa: ANN001
    ) -> None:
        env = await funded_env(session_factory, "PTFUNDTICKUSD", price="2500")
        await env.order("sell", "10")
        cash_before = num((await env.account()).balance)

        now = datetime.now(UTC)
        recent = (int(now.timestamp()) // SETTLEMENT_INTERVAL) * SETTLEMENT_INTERVAL
        times = [datetime.fromtimestamp(recent - i * SETTLEMENT_INTERVAL, UTC) for i in range(3)]
        client = FakeDeltaClient(
            funding_pct={t: "0.01" for t in times},
            index={t: "2500" for t in times},
            mark={t: "2500" for t in times},
        )
        monkeypatch.setattr(paper_funding_module, "get_engine", lambda: engine)
        monkeypatch.setattr(paper_funding_module, "get_delta_client", lambda: client)

        scheduler = PaperFundingScheduler(
            state_manager=env.service.state_manager, lookback_hours=48
        )
        summary = await scheduler.run_tick()

        assert summary.symbols == 1
        assert summary.rates_ingested == 3
        assert summary.settled == 0  # every one of those funding times predates the position
        assert num((await env.account()).balance) == pytest.approx(cash_before)

    async def test_a_tick_with_no_open_positions_never_calls_delta(
        self,
        session_factory: SessionFactory,
        engine,
        monkeypatch: pytest.MonkeyPatch,  # noqa: ANN001
    ) -> None:
        def explode() -> None:
            raise AssertionError("Delta must not be called when nothing is open")

        monkeypatch.setattr(paper_funding_module, "get_engine", lambda: engine)
        monkeypatch.setattr(paper_funding_module, "get_delta_client", explode)
        summary = await PaperFundingScheduler(
            state_manager=__import__("app.state.manager", fromlist=["x"]).MarketStateManager()
        ).run_tick()
        assert summary.symbols == 0 and summary.rates_ingested == 0

    async def test_the_service_builder_wires_a_settlement_repository(
        self, session_factory: SessionFactory
    ) -> None:
        from app.state.manager import MarketStateManager

        async with session_factory() as session:
            service = build_funding_service(session, MarketStateManager(), get_settings())
            assert service.funding_settlement_repository is not None
            assert service.maintenance_margin_rate == D("0.0025")
