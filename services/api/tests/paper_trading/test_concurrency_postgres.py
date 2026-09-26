"""Concurrency guarantees for paper trading, against a REAL PostgreSQL.

Marked ``postgres`` and auto-skipped when ``TEST_DATABASE_URL`` is unreachable
(CI runs them against its Postgres service container; locally set
``TEST_DATABASE_URL`` to any scratch database).

**Why these are not in-memory SQLite tests.** The default suite's SQLite
engine uses one shared connection (`StaticPool`), so two "concurrent"
sessions are really one transaction: there is no row lock to wait on and no
isolation between them. That cannot exercise a race between two sessions, and
worse, it can pass while the code is wrong. Running the
liquidation-versus-manual-close race against real Postgres is what exposed
that the old order of writes (commit the guarded account update, *then* write
the position) let a second actor read the committed account with a
not-yet-updated position and close a position that was already closed. The
guarded update is now the first write of ONE transaction that also writes the
position and the order (`PaperAccountRepository.try_apply_trade_effects`,
`commit=False`), so the account row lock is held until everything it gates is
written. Each test here uses genuinely separate connections.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.models  # noqa: F401 - registers every table on Base.metadata
from app.core.config import get_settings
from app.db.base import Base
from app.events.bus import EventBus
from app.marketdata.bus_events import TickerUpdated
from app.marketdata.models import TickerEvent
from app.models.market import Market
from app.models.paper_trading import PaperFundingSettlement
from app.paper_trading import monitor as monitor_module
from app.paper_trading.errors import (
    AccountUpdateConflictError,
    MaxExposureExceededError,
    ReduceOnlyViolationError,
)
from app.schemas.paper_trading import PaperAccountCreateRequest, PaperOrderRequest
from app.services.paper_funding import build_funding_service
from app.state.manager import MarketStateManager
from tests.conftest import SessionFactory
from tests.paper_trading.test_monitor import build_monitor
from tests.paper_trading.test_service import (
    GENEROUS_MAX_PCT,
    build_service,
    publish_ticker,
    seed_market,
)

pytestmark = pytest.mark.postgres

D = Decimal
DEFAULT_URL = "postgresql+asyncpg://research:research@localhost:5432/eth_platform_test"


@pytest_asyncio.fixture
async def pg_engine() -> AsyncGenerator[AsyncEngine]:
    """A Postgres engine in its own schema whose EVERY pooled connection has
    that schema on its search path (the shared `postgres_engine` fixture sets
    it on one connection only, which is fine for sequential tests but not for
    several connections racing)."""
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_URL)
    schema = f"conc_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    admin = create_async_engine(url)
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    except Exception as exc:
        await admin.dispose()
        pytest.skip(f"PostgreSQL test database unreachable at {url}: {exc}")
    engine = create_async_engine(
        url, pool_size=10, connect_args={"server_settings": {"search_path": schema}}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()
    async with admin.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    await admin.dispose()


class _TrackingSessionMaker(async_sessionmaker[AsyncSession]):
    """Remembers every session it hands out, so teardown can close them all.

    `build_service` opens a session per service and never closes it (harmless
    on in-memory SQLite). On Postgres each one keeps a connection
    idle-in-transaction holding table locks, which would block dropping the
    test schema forever."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.opened: list[AsyncSession] = []

    def __call__(self, **local_kw: object) -> AsyncSession:
        session = super().__call__(**local_kw)  # type: ignore[arg-type]
        self.opened.append(session)
        return session


@pytest_asyncio.fixture
async def pg(
    pg_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[SessionFactory]:
    monkeypatch.setattr(monitor_module, "get_engine", lambda: pg_engine)
    factory = _TrackingSessionMaker(bind=pg_engine, expire_on_commit=False)
    yield factory
    for session in factory.opened:
        await session.close()


async def tick(bus: EventBus, symbol: str, last: str, mark: str | None = None) -> None:
    await bus.publish(
        TickerUpdated(
            source="test",
            ticker=TickerEvent(
                exchange="delta",
                symbol=symbol,
                event_time=datetime.now(UTC),
                last_price=D(last),
                mark_price=D(mark) if mark else None,
            ),
        )
    )


@pytest.mark.asyncio
class TestConcurrentOrders:
    async def test_two_concurrent_orders_that_would_jointly_breach_exposure_reject_exactly_one(
        self, pg: SessionFactory
    ) -> None:
        await seed_market(pg, symbol="PGRACEAUSD")
        await seed_market(pg, symbol="PGRACEBUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, "PGRACEAUSD", "1000")
        await publish_ticker(bus, "PGRACEBUSD", "1000")

        creator = await build_service(pg, state_manager)
        account = await creator.create_account(
            PaperAccountCreateRequest(
                starting_balance=D("100000"),
                max_position_size_pct=GENEROUS_MAX_PCT,
                max_exposure_pct=D("50"),
                max_drawdown_pct=GENEROUS_MAX_PCT,
            )
        )
        account_id = uuid.UUID(account.id)

        # Each order alone (~$30,015, ~30% of equity) is under the 50% limit;
        # together (~60%) they are not. Separate sessions, separate connections.
        service_a = await build_service(pg, state_manager)
        service_b = await build_service(pg, state_manager)
        results = await asyncio.gather(
            service_a.place_order(
                account_id, PaperOrderRequest(symbol="PGRACEAUSD", side="buy", quantity=D("30"))
            ),
            service_b.place_order(
                account_id, PaperOrderRequest(symbol="PGRACEBUSD", side="buy", quantity=D("30"))
            ),
            return_exceptions=True,
        )

        successes = [r for r in results if not isinstance(r, BaseException)]
        failures = [r for r in results if isinstance(r, BaseException)]
        assert len(successes) == 1, f"expected exactly one winner, got: {results}"
        assert len(failures) == 1, f"expected exactly one rejection, got: {results}"
        assert not isinstance(failures[0], AccountUpdateConflictError), repr(failures[0])
        assert isinstance(failures[0], MaxExposureExceededError), repr(failures[0])
        creator.account_repository.session.expire_all()
        positions = await creator.list_positions(account_id)
        assert len(positions.positions) == 1
        assert float(positions.positions[0].quantity) == pytest.approx(30.0)


@pytest.mark.asyncio
class TestConcurrentCloses:
    async def test_a_triggered_stop_loss_and_a_concurrent_manual_close_close_exactly_once(
        self, pg: SessionFactory
    ) -> None:
        await seed_market(pg, symbol="PGRACECLOSEUSD")
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        build_monitor(state_manager).attach(bus)
        creator = await build_service(pg, state_manager)
        await publish_ticker(bus, "PGRACECLOSEUSD", "1000")
        account = await creator.create_account(
            PaperAccountCreateRequest(starting_balance=D("100000"))
        )
        account_id = uuid.UUID(account.id)
        await creator.place_order(
            account_id,
            PaperOrderRequest(
                symbol="PGRACECLOSEUSD", side="buy", quantity=D("10"), stop_loss_price=D("900")
            ),
        )

        manual_service = await build_service(pg, state_manager)
        manual_task = asyncio.create_task(
            manual_service.place_order(
                account_id,
                PaperOrderRequest(
                    symbol="PGRACECLOSEUSD", side="sell", quantity=D("10"), reduce_only=True
                ),
                user_id=manual_service._default_user_id,  # noqa: SLF001
            )
        )
        await tick(bus, "PGRACECLOSEUSD", "900")
        drain, manual = await asyncio.gather(bus.drain(), manual_task, return_exceptions=True)
        assert not isinstance(drain, BaseException), drain

        creator.account_repository.session.expire_all()
        orders = await creator.list_orders(
            account_id, sort="created_at", direction="asc", limit=10, offset=0
        )
        sells = [o for o in orders.orders if o.side == "sell"]
        assert len(sells) == 1, f"expected exactly one closing sell, got {sells}"
        assert (await creator.list_positions(account_id)).positions == []
        if isinstance(manual, BaseException):
            assert isinstance(manual, ReduceOnlyViolationError), repr(manual)

    @pytest.mark.parametrize("round_", range(8))
    async def test_a_liquidation_and_a_concurrent_manual_close_close_exactly_once(
        self, pg: SessionFactory, round_: int
    ) -> None:
        """A liquidation returns no cash, so `balance` alone would not change
        under it. Repeated because a race either shows up or it doesn't, and one
        lucky ordering proves nothing."""
        symbol = f"PGLIQRACE{round_}USD"
        await seed_market(pg, symbol=symbol)
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        build_monitor(state_manager).attach(bus)
        creator = await build_service(pg, state_manager)
        await publish_ticker(bus, symbol, "2000")
        account = await creator.create_account(
            PaperAccountCreateRequest(
                starting_balance=D("100000"),
                max_position_size_pct=GENEROUS_MAX_PCT,
                max_exposure_pct=GENEROUS_MAX_PCT,
                max_drawdown_pct=GENEROUS_MAX_PCT,
                max_leverage=D("5"),
            )
        )
        account_id = uuid.UUID(account.id)
        user_id = creator._default_user_id  # noqa: SLF001
        await creator.place_order(
            account_id,
            PaperOrderRequest(symbol=symbol, side="buy", quantity=D("5"), leverage=D("5")),
            user_id=user_id,
        )

        manual_service = await build_service(pg, state_manager)
        manual_task = asyncio.create_task(
            manual_service.place_order(
                account_id,
                PaperOrderRequest(symbol=symbol, side="sell", quantity=D("5"), reduce_only=True),
                user_id=user_id,
            )
        )
        await tick(bus, symbol, "1600", mark="1600")  # below the ~$1604.81 liquidation price
        drain, manual = await asyncio.gather(bus.drain(), manual_task, return_exceptions=True)
        assert not isinstance(drain, BaseException), drain

        creator.account_repository.session.expire_all()
        orders = await creator.list_orders(
            account_id, sort="created_at", direction="asc", limit=20, offset=0
        )
        closes = [o for o in orders.orders if o.side == "sell"]
        assert len(closes) == 1, f"expected exactly one close, got {closes}"
        assert (await creator.list_positions(account_id)).positions == []
        if isinstance(manual, BaseException):
            assert isinstance(manual, ReduceOnlyViolationError), repr(manual)
        final = await creator.get_account(account_id)
        # Flat: every dollar is accounted for by starting balance + realized PnL.
        assert float(final.balance) == pytest.approx(100000 + float(final.realized_pnl))


@pytest.mark.asyncio
class TestConcurrentFundingSettlement:
    async def test_two_concurrent_settlements_of_the_same_key_charge_exactly_once(
        self, pg: SessionFactory
    ) -> None:
        symbol = "PGFUNDRACEUSD"
        await seed_market(pg, symbol=symbol)
        bus = EventBus()
        state_manager = MarketStateManager().attach(bus)
        await publish_ticker(bus, symbol, "2500")
        creator = await build_service(pg, state_manager)
        account = await creator.create_account(
            PaperAccountCreateRequest(starting_balance=D("100000"))
        )
        account_id = uuid.UUID(account.id)
        await creator.place_order(
            account_id,
            PaperOrderRequest(symbol=symbol, side="buy", quantity=D("10")),
            user_id=creator._default_user_id,  # noqa: SLF001
        )
        cash_before = float((await creator.get_account(account_id)).balance)
        when = datetime.now(UTC) + timedelta(hours=1)

        sessions = [pg() for _ in range(3)]
        services = [build_funding_service(s, state_manager, get_settings()) for s in sessions]
        results = await asyncio.gather(
            *[
                s.settle_funding(
                    account_id,
                    symbol,
                    funding_time=when,
                    funding_rate=D("0.0001"),
                    index_price=D("2500"),
                )
                for s in services
            ],
            return_exceptions=True,
        )

        assert not any(isinstance(r, BaseException) for r in results), results
        assert sum(r is not None for r in results) == 1
        async with pg() as session:
            rows = (await session.execute(select(PaperFundingSettlement))).scalars().all()
            balance = float(
                (await session.execute(text("select balance from paper_accounts"))).scalar_one()
            )
            market_rows = (await session.execute(select(Market))).scalars().all()
        assert len(rows) == 1
        assert balance == pytest.approx(cash_before - 2.5)  # 10 * 2500 * 0.0001, once
        assert market_rows
