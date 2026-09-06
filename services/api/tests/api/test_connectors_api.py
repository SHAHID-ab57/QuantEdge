"""External Data Connectors read API tests (M4-E1-T3's own backend) —
mirrors ``tests/api/test_features_api.py``'s own shape: a real FastAPI
app over ASGI with the in-memory SQLite database, so routing, JSON
serialization, and the shared ``AppError`` -> JSON envelope are all
covered end to end.
"""

from datetime import UTC, datetime

import httpx
import pytest

import app.services.connectors as connectors_service_module
from app.connectors.registry import ConnectorRegistry
from app.models.external_data import ExternalDataPoint
from tests.conftest import SessionFactory


async def seed_point(
    session_factory: SessionFactory,
    *,
    source: str = "fear_greed",
    value: float,
    timestamp: datetime,
) -> None:
    """Insert one real external data point directly."""
    async with session_factory() as session:
        session.add(ExternalDataPoint(source=source, symbol=None, timestamp=timestamp, value=value))
        await session.commit()


class TestConnectorCatalogueEndpoint:
    async def test_lists_the_registered_connector(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/connectors")
        assert response.status_code == 200
        body = response.json()
        sources = {entry["source"] for entry in body["connectors"]}
        assert "fear_greed" in sources
        assert body["total"] == len(body["connectors"])

    async def test_a_newly_registered_connector_appears_with_zero_code_change(
        self, client: httpx.AsyncClient
    ) -> None:
        """The Data Sources page's own registry-driven guarantee: `fed_funds_rate`
        (`app/connectors/fred.py`) was added well after this endpoint/page was
        first built, and appears here with no change to either — the same
        proof `test_features_api.py` already gives `/features`."""
        body = (await client.get("/api/v1/connectors")).json()
        sources = {entry["source"] for entry in body["connectors"]}
        assert "fed_funds_rate" in sources
        fed_funds = next(e for e in body["connectors"] if e["source"] == "fed_funds_rate")
        assert fed_funds["label"] == "Federal Funds Rate"
        assert fed_funds["requires_auth"] is True

    async def test_reports_null_latest_value_before_anything_is_ingested(
        self, client: httpx.AsyncClient
    ) -> None:
        """A registered connector with zero stored points reports nulls,
        never a crash or a fabricated value."""
        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["latest_value"] is None
        assert entry["latest_timestamp"] is None
        assert entry["label"] == "Fear & Greed Index"
        assert entry["requires_auth"] is False

    async def test_reports_the_real_latest_value_once_ingested(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_point(session_factory, value=30.0, timestamp=datetime(2026, 1, 1, tzinfo=UTC))
        await seed_point(session_factory, value=70.0, timestamp=datetime(2026, 1, 2, tzinfo=UTC))

        body = (await client.get("/api/v1/connectors")).json()
        entry = next(e for e in body["connectors"] if e["source"] == "fear_greed")
        assert entry["latest_value"] == 70.0
        assert entry["latest_timestamp"] == "2026-01-02T00:00:00Z"

    async def test_zero_registered_connectors_is_handled_not_crashed_on(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Shouldn't happen post-M4-E1-T1, but the endpoint must still
        return a clean, empty catalogue rather than an error."""
        monkeypatch.setattr(
            connectors_service_module, "default_connector_registry", ConnectorRegistry()
        )
        monkeypatch.setattr(connectors_service_module, "load_builtin_connectors", lambda: None)

        response = await client.get("/api/v1/connectors")
        assert response.status_code == 200
        body = response.json()
        assert body["connectors"] == []
        assert body["total"] == 0

    async def test_is_mounted_unversioned_too(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/connectors")).status_code == 200


class TestConnectorHistoryEndpoint:
    async def test_returns_points_in_the_requested_inclusive_range(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_point(session_factory, value=30.0, timestamp=datetime(2026, 1, 1, tzinfo=UTC))
        await seed_point(session_factory, value=50.0, timestamp=datetime(2026, 1, 2, tzinfo=UTC))
        await seed_point(session_factory, value=70.0, timestamp=datetime(2026, 1, 3, tzinfo=UTC))

        response = await client.get(
            "/api/v1/connectors/fear_greed/history",
            params={"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "fear_greed"
        assert [item["value"] for item in body["items"]] == [30.0, 50.0]
        assert [item["timestamp"] for item in body["items"]] == [
            "2026-01-01T00:00:00Z",
            "2026-01-02T00:00:00Z",
        ]
        assert body["pagination"] == {
            "total": 2,
            "returned": 2,
            "has_more": False,
            "limit": 100,
            "offset": 0,
        }

    async def test_omitting_start_and_end_queries_all_history(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_point(session_factory, value=42.0, timestamp=datetime(2018, 6, 1, tzinfo=UTC))
        await seed_point(session_factory, value=55.0, timestamp=datetime(2026, 1, 1, tzinfo=UTC))

        body = (await client.get("/api/v1/connectors/fear_greed/history")).json()
        assert body["pagination"]["total"] == 2
        assert [item["value"] for item in body["items"]] == [42.0, 55.0]

    async def test_paginates_with_limit_and_offset(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        for day, value in ((1, 10.0), (2, 20.0), (3, 30.0)):
            await seed_point(
                session_factory, value=value, timestamp=datetime(2026, 1, day, tzinfo=UTC)
            )

        first = await client.get(
            "/api/v1/connectors/fear_greed/history", params={"limit": 2, "offset": 0}
        )
        first_body = first.json()
        assert [item["value"] for item in first_body["items"]] == [10.0, 20.0]
        assert first_body["pagination"]["has_more"] is True

        second = await client.get(
            "/api/v1/connectors/fear_greed/history", params={"limit": 2, "offset": 2}
        )
        second_body = second.json()
        assert [item["value"] for item in second_body["items"]] == [30.0]
        assert second_body["pagination"]["has_more"] is False

    async def test_returns_404_for_an_unknown_source(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/connectors/nope/history")
        assert response.status_code == 404
        body = response.json()
        assert body["code"] == "connector_not_found"
        assert "fear_greed" in body["detail"]

    async def test_is_mounted_unversioned_too(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        assert (await client.get("/connectors/fear_greed/history")).status_code == 200
