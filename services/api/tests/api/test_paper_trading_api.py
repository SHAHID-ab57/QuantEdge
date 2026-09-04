"""Paper Trading REST endpoint tests.

Runs against the real FastAPI app over ASGI with the in-memory SQLite
database, mirroring `test_system_health.py`'s own convention for a live
`MarketStateManager`: build a real `Runtime`, publish a ticker event
straight onto its bus, and override `get_runtime` for the test.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from app.marketdata.bus_events import TickerUpdated
from app.marketdata.models import TickerEvent
from app.models.exchange import Exchange
from app.models.market import Market
from app.repositories.paper_trading import PaperAccountRepository
from app.runtime import Runtime, get_runtime
from tests.conftest import SessionFactory


async def seed_market(session_factory: SessionFactory, *, symbol: str) -> None:
    async with session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug=f"delta-{symbol.lower()}", country="India")
        session.add(exchange)
        await session.flush()
        session.add(
            Market(
                exchange_id=exchange.id,
                symbol=symbol,
                base_asset=symbol[:3],
                quote_asset=symbol[3:],
                market_type="perpetual",
            )
        )
        await session.commit()


async def override_runtime_with_ticker(app: FastAPI, *, symbol: str, price: str) -> Runtime:
    """A real `Runtime` (real `EventBus` + `MarketStateManager`), with one
    live ticker published onto it — mirrors `test_system_health.py`'s own
    convention for exercising a live `MarketStateManager` without a real
    WebSocket connection to Delta."""
    runtime = Runtime(market_data_live=False, symbols=(), started_at=datetime.now(UTC))
    app.dependency_overrides[get_runtime] = lambda: runtime
    await runtime.bus.publish(
        TickerUpdated(
            source="test",
            ticker=TickerEvent(
                exchange="delta",
                symbol=symbol,
                event_time=datetime.now(UTC),
                last_price=Decimal(price),
            ),
        )
    )
    await runtime.bus.drain()
    return runtime


class TestCreateAndGetAccount:
    async def test_creates_and_reopens_an_account(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/paper-trading/accounts",
            json={"name": "My Paper Account", "starting_balance": "100000"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "My Paper Account"
        assert float(body["balance"]) == 100000.0
        assert float(body["realized_pnl"]) == 0.0

        reopened = await client.get(f"/api/v1/paper-trading/accounts/{body['id']}")
        assert reopened.status_code == 200
        assert reopened.json()["id"] == body["id"]

    async def test_returns_404_for_an_unknown_account(self, client: httpx.AsyncClient) -> None:
        response = await client.get(
            "/api/v1/paper-trading/accounts/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90"
        )
        assert response.status_code == 404
        assert response.json()["code"] == "paper_account_not_found"

    async def test_lists_accounts_most_recently_created_first(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        first = (
            await client.post("/api/v1/paper-trading/accounts", json={"starting_balance": "1000"})
        ).json()
        second = (
            await client.post("/api/v1/paper-trading/accounts", json={"starting_balance": "2000"})
        ).json()

        # `created_at` is server-generated via SQLite's second-resolution
        # `CURRENT_TIMESTAMP` (see `TimestampMixin`) — two accounts created
        # back-to-back within the same wall-clock second can genuinely tie,
        # leaving "most recent first" to an arbitrary id tiebreak. Nudge
        # the first one's own timestamp back so there's a real,
        # deterministic difference to assert.
        async with session_factory() as session:
            repository = PaperAccountRepository(session)
            first_account = await repository.get_by_id(uuid.UUID(first["id"]))
            assert first_account is not None
            await repository.update(
                first_account, {"created_at": datetime.now(UTC) - timedelta(minutes=1)}
            )

        listed = (await client.get("/api/v1/paper-trading/accounts")).json()
        ids = [a["id"] for a in listed["accounts"]]
        assert ids.index(second["id"]) < ids.index(first["id"])


class TestPlaceOrder:
    async def test_places_a_buy_order_with_realistic_slippage_and_fee(
        self, client: httpx.AsyncClient, session_factory: SessionFactory, app: FastAPI
    ) -> None:
        await seed_market(session_factory, symbol="APIPTUSD")
        await override_runtime_with_ticker(app, symbol="APIPTUSD", price="1000")

        # 10 units at a ~$1000.5 fill is ~10.005% of a $100,000 balance —
        # a hair over this platform's real default 10% position-size
        # limit, which isn't what this test is about (see
        # `TestPositionSizeLimit` in tests/paper_trading/test_service.py
        # for that check itself) — widened here so this test exercises
        # only the slippage/fee arithmetic it's named for.
        account = (
            await client.post(
                "/api/v1/paper-trading/accounts",
                json={
                    "starting_balance": "100000",
                    "max_position_size_pct": "100",
                    "max_exposure_pct": "100",
                },
            )
        ).json()

        response = await client.post(
            f"/api/v1/paper-trading/accounts/{account['id']}/orders",
            json={"symbol": "APIPTUSD", "side": "buy", "quantity": "10"},
        )

        assert response.status_code == 201
        body = response.json()
        assert float(body["raw_price"]) == 1000.0
        assert float(body["fill_price"]) == 1000.5
        assert float(body["slippage_applied"]) == 0.5
        assert float(body["fee_applied"]) == 10.005
        assert body["price_source"] == "ticker"
        assert body["is_stale_price"] is False

    async def test_is_also_mounted_unversioned(
        self, client: httpx.AsyncClient, session_factory: SessionFactory, app: FastAPI
    ) -> None:
        await seed_market(session_factory, symbol="APIPTUNVERSUSD")
        await override_runtime_with_ticker(app, symbol="APIPTUNVERSUSD", price="500")
        account = (
            await client.post("/paper-trading/accounts", json={"starting_balance": "100000"})
        ).json()

        response = await client.post(
            f"/paper-trading/accounts/{account['id']}/orders",
            json={"symbol": "APIPTUNVERSUSD", "side": "buy", "quantity": "1"},
        )
        assert response.status_code == 201

    async def test_returns_400_when_the_order_would_take_the_balance_negative(
        self, client: httpx.AsyncClient, session_factory: SessionFactory, app: FastAPI
    ) -> None:
        await seed_market(session_factory, symbol="APIPTPOORUSD")
        await override_runtime_with_ticker(app, symbol="APIPTPOORUSD", price="1000")
        account = (
            await client.post("/api/v1/paper-trading/accounts", json={"starting_balance": "500"})
        ).json()

        response = await client.post(
            f"/api/v1/paper-trading/accounts/{account['id']}/orders",
            json={"symbol": "APIPTPOORUSD", "side": "buy", "quantity": "1"},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "insufficient_balance"

    async def test_returns_400_for_a_sell_exceeding_the_held_quantity(
        self, client: httpx.AsyncClient, session_factory: SessionFactory, app: FastAPI
    ) -> None:
        await seed_market(session_factory, symbol="APIPTSHORTUSD")
        await override_runtime_with_ticker(app, symbol="APIPTSHORTUSD", price="1000")
        account = (
            await client.post("/api/v1/paper-trading/accounts", json={"starting_balance": "100000"})
        ).json()
        await client.post(
            f"/api/v1/paper-trading/accounts/{account['id']}/orders",
            json={"symbol": "APIPTSHORTUSD", "side": "buy", "quantity": "1"},
        )

        response = await client.post(
            f"/api/v1/paper-trading/accounts/{account['id']}/orders",
            json={"symbol": "APIPTSHORTUSD", "side": "sell", "quantity": "2"},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "insufficient_position"

    async def test_returns_404_for_an_unknown_market(self, client: httpx.AsyncClient) -> None:
        account = (
            await client.post("/api/v1/paper-trading/accounts", json={"starting_balance": "1000"})
        ).json()

        response = await client.post(
            f"/api/v1/paper-trading/accounts/{account['id']}/orders",
            json={"symbol": "DOES-NOT-EXIST", "side": "buy", "quantity": "1"},
        )

        assert response.status_code == 404
        assert response.json()["code"] == "market_not_found"


class TestOrdersPositionsAndSummary:
    async def test_lists_orders_positions_and_summary_after_a_fill(
        self, client: httpx.AsyncClient, session_factory: SessionFactory, app: FastAPI
    ) -> None:
        await seed_market(session_factory, symbol="APIPTFULLUSD")
        await override_runtime_with_ticker(app, symbol="APIPTFULLUSD", price="1000")
        # See the identical note in `test_places_a_buy_order_with_realistic_slippage_and_fee`
        # above — widened so this test exercises order/position/summary
        # listing, not the (unrelated) position-size limit.
        account = (
            await client.post(
                "/api/v1/paper-trading/accounts",
                json={
                    "starting_balance": "100000",
                    "max_position_size_pct": "100",
                    "max_exposure_pct": "100",
                },
            )
        ).json()
        await client.post(
            f"/api/v1/paper-trading/accounts/{account['id']}/orders",
            json={"symbol": "APIPTFULLUSD", "side": "buy", "quantity": "10"},
        )

        orders = (await client.get(f"/api/v1/paper-trading/accounts/{account['id']}/orders")).json()
        assert orders["total"] == 1
        assert orders["orders"][0]["symbol"] == "APIPTFULLUSD"

        positions = (
            await client.get(f"/api/v1/paper-trading/accounts/{account['id']}/positions")
        ).json()
        assert len(positions["positions"]) == 1
        assert positions["positions"][0]["symbol"] == "APIPTFULLUSD"
        assert float(positions["positions"][0]["quantity"]) == 10.0

        summary = (
            await client.get(f"/api/v1/paper-trading/accounts/{account['id']}/summary")
        ).json()
        assert summary["open_position_count"] == 1
        assert float(summary["balance"]) == 100000.0 - 10015.005

    async def test_returns_400_for_an_unsupported_order_sort_column(
        self, client: httpx.AsyncClient
    ) -> None:
        account = (
            await client.post("/api/v1/paper-trading/accounts", json={"starting_balance": "1000"})
        ).json()

        response = await client.get(
            f"/api/v1/paper-trading/accounts/{account['id']}/orders", params={"sort": "bogus"}
        )
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_paper_order_sort"


class TestRiskLimits:
    async def test_creates_an_account_with_the_real_platform_default_risk_limits(
        self, client: httpx.AsyncClient
    ) -> None:
        account = (
            await client.post("/api/v1/paper-trading/accounts", json={"starting_balance": "100000"})
        ).json()

        assert float(account["max_position_size_pct"]) == pytest.approx(10.0)
        assert float(account["max_exposure_pct"]) == pytest.approx(50.0)
        assert float(account["max_drawdown_pct"]) == pytest.approx(20.0)
        assert float(account["peak_balance"]) == pytest.approx(100000.0)
        assert account["trading_halted"] is False

    async def test_returns_400_when_an_order_exceeds_the_position_size_limit(
        self, client: httpx.AsyncClient, session_factory: SessionFactory, app: FastAPI
    ) -> None:
        await seed_market(session_factory, symbol="APIPTPOSLIMITUSD")
        await override_runtime_with_ticker(app, symbol="APIPTPOSLIMITUSD", price="1000")
        # Real platform defaults (10% position size) — 11 units at a
        # ~$1000.5 fill is ~11.0055% of the $100,000 balance.
        account = (
            await client.post("/api/v1/paper-trading/accounts", json={"starting_balance": "100000"})
        ).json()

        response = await client.post(
            f"/api/v1/paper-trading/accounts/{account['id']}/orders",
            json={"symbol": "APIPTPOSLIMITUSD", "side": "buy", "quantity": "11"},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "max_position_size_exceeded"

    async def test_gets_a_risk_summary_and_resumes_a_halted_account(
        self, client: httpx.AsyncClient, session_factory: SessionFactory, app: FastAPI
    ) -> None:
        await seed_market(session_factory, symbol="APIPTRISKUSD")
        await override_runtime_with_ticker(app, symbol="APIPTRISKUSD", price="1000")
        account = (
            await client.post(
                "/api/v1/paper-trading/accounts",
                json={
                    "starting_balance": "10000",
                    "max_position_size_pct": "100",
                    "max_exposure_pct": "100",
                    "max_drawdown_pct": "20",
                },
            )
        ).json()

        risk_before = (
            await client.get(f"/api/v1/paper-trading/accounts/{account['id']}/risk")
        ).json()
        assert float(risk_before["current_exposure_pct"]) == pytest.approx(0.0)
        assert float(risk_before["current_drawdown_pct"]) == pytest.approx(0.0)
        assert risk_before["trading_halted"] is False

        # 2 units at a ~$1000.5 fill: total cost ~$2003.001 — a >20%
        # drop from the $10,000 peak, breaching the drawdown limit.
        await client.post(
            f"/api/v1/paper-trading/accounts/{account['id']}/orders",
            json={"symbol": "APIPTRISKUSD", "side": "buy", "quantity": "2"},
        )

        risk_after = (
            await client.get(f"/api/v1/paper-trading/accounts/{account['id']}/risk")
        ).json()
        assert risk_after["trading_halted"] is True
        assert float(risk_after["current_drawdown_pct"]) > 20.0

        halted_response = await client.post(
            f"/api/v1/paper-trading/accounts/{account['id']}/orders",
            json={"symbol": "APIPTRISKUSD", "side": "buy", "quantity": "0.001"},
        )
        assert halted_response.status_code == 400
        assert halted_response.json()["code"] == "trading_halted"

        resumed = (
            await client.post(f"/api/v1/paper-trading/accounts/{account['id']}/resume-trading")
        ).json()
        assert resumed["trading_halted"] is False

        resumed_order = await client.post(
            f"/api/v1/paper-trading/accounts/{account['id']}/orders",
            json={"symbol": "APIPTRISKUSD", "side": "buy", "quantity": "0.001"},
        )
        assert resumed_order.status_code == 201
