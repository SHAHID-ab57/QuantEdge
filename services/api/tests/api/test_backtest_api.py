"""Backtesting Engine REST endpoint tests.

Runs against the real FastAPI app over ASGI with the in-memory SQLite
database, mirroring `test_training_api.py`/`test_prediction_api.py`'s own
convention exactly — including reusing their `seed_real_candles`/
`create_experiment_with_real_config`/`job_body`/`run_and_wait` helpers
rather than a second copy of any of them.
"""

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.config import get_settings
from app.repositories.backtest_runs import BacktestRunRepository
from app.services import background_tasks
from app.services.prediction import PredictionService
from tests.api.test_training_api import (
    create_experiment_with_real_config,
    job_body,
    run_and_wait,
    seed_real_candles,
)
from tests.conftest import SessionFactory

#: Well within `seed_real_candles`'s own 80-hour seeded series (starting
#: 2026-01-01T00:00), leaving real candles already stored past a horizon
#: of 1 for every step walked here.
_EARLY_START = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=40)


async def train_completed_job(
    client: httpx.AsyncClient,
    session_factory: SessionFactory,
    *,
    symbol: str,
    model_type: str = "logistic_regression",
    target: str = "next_direction",
) -> dict:
    await seed_real_candles(session_factory, symbol=symbol)
    experiment = await create_experiment_with_real_config(client, target=target)
    created = (
        await client.post(
            "/api/v1/training-jobs",
            json=job_body(experiment["id"], model_type=model_type, symbol=symbol, timeframe="1h"),
        )
    ).json()
    body = await run_and_wait(client, created["id"])
    assert body["status"] == "completed", body
    return body


async def run_backtest_and_wait(client: httpx.AsyncClient, body: dict) -> dict:
    """POST /backtests/run, assert it returned before the walk could have
    finished (status is 'running'), deterministically await the background
    task, then return the run's settled state."""
    response = await client.post("/api/v1/backtests/run", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "running"
    await background_tasks.wait_for_all()
    final = await client.get(f"/api/v1/backtests/{response.json()['id']}")
    assert final.status_code == 200
    return final.json()


class TestRunBacktest:
    async def test_runs_and_returns_a_completed_backtest_with_aggregate_metrics(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        job = await train_completed_job(client, session_factory, symbol="APIBTUSD")

        result = await run_backtest_and_wait(
            client,
            {
                "training_job_id": job["id"],
                "symbol": "APIBTUSD",
                "start": _EARLY_START.isoformat(),
                "end": (_EARLY_START + timedelta(hours=5)).isoformat(),
            },
        )

        assert result["status"] == "completed"
        assert result["total_steps"] == 5
        assert result["completed_steps"] == 5
        assert result["graded_count"] == 5
        assert result["truncated"] is False
        assert result["aggregate_metrics"] is not None
        assert "accuracy" in result["aggregate_metrics"]

    async def test_is_also_mounted_unversioned(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        job = await train_completed_job(client, session_factory, symbol="APIBTUNVERSUSD")

        response = await client.post(
            "/backtests/run",
            json={
                "training_job_id": job["id"],
                "symbol": "APIBTUNVERSUSD",
                "start": _EARLY_START.isoformat(),
                "end": (_EARLY_START + timedelta(hours=1)).isoformat(),
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "running"

    async def test_returns_before_a_slow_background_walk_would_finish(
        self,
        client: httpx.AsyncClient,
        session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The non-blocking behavior itself: an artificially slow prediction
        step must not delay the response — the request returns 'running'
        almost immediately, well under the delay."""
        job = await train_completed_job(client, session_factory, symbol="APIBTSLOWUSD")

        delay_seconds = 0.5
        original_run = PredictionService.run

        async def slow_run(self: PredictionService, request: object):
            await asyncio.sleep(delay_seconds)
            return await original_run(self, request)  # type: ignore[arg-type]

        monkeypatch.setattr(PredictionService, "run", slow_run)

        started = time.perf_counter()
        response = await client.post(
            "/api/v1/backtests/run",
            json={
                "training_job_id": job["id"],
                "symbol": "APIBTSLOWUSD",
                "start": _EARLY_START.isoformat(),
                "end": (_EARLY_START + timedelta(hours=1)).isoformat(),
            },
        )
        elapsed = time.perf_counter() - started

        assert response.status_code == 200
        assert response.json()["status"] == "running"
        assert elapsed < delay_seconds / 2, (
            f"run endpoint took {elapsed:.3f}s — it should return long before "
            f"the artificial {delay_seconds}s per-step delay elapses"
        )

        await background_tasks.wait_for_all()
        final = await client.get(f"/api/v1/backtests/{response.json()['id']}")
        assert final.json()["status"] == "completed"

    async def test_reports_truncation_honestly_when_the_range_needs_more_steps_than_allowed(
        self,
        client: httpx.AsyncClient,
        session_factory: SessionFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(get_settings(), "max_backtest_steps", 3)
        job = await train_completed_job(client, session_factory, symbol="APIBTCAPUSD")

        response = await client.post(
            "/api/v1/backtests/run",
            json={
                "training_job_id": job["id"],
                "symbol": "APIBTCAPUSD",
                "start": _EARLY_START.isoformat(),
                "end": (_EARLY_START + timedelta(hours=10)).isoformat(),
            },
        )

        body = response.json()
        assert body["truncated"] is True
        assert body["total_steps"] == 3

    async def test_returns_404_for_an_unknown_training_job(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/backtests/run",
            json={
                "training_job_id": "6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90",
                "symbol": "ETHUSD",
                "start": _EARLY_START.isoformat(),
                "end": (_EARLY_START + timedelta(hours=1)).isoformat(),
            },
        )
        assert response.status_code == 404
        assert response.json()["code"] == "training_job_not_found"

    async def test_returns_400_for_an_empty_range(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        job = await train_completed_job(client, session_factory, symbol="APIBTBADRANGEUSD")

        response = await client.post(
            "/api/v1/backtests/run",
            json={
                "training_job_id": job["id"],
                "symbol": "APIBTBADRANGEUSD",
                "start": _EARLY_START.isoformat(),
                "end": _EARLY_START.isoformat(),
            },
        )
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_backtest_range"

    async def test_returns_400_for_a_range_reaching_past_the_latest_stored_candle(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        """`seed_real_candles` stores exactly 80 hourly candles (hours
        0..79); requesting a range that needs data past hour 80 is
        rejected rather than silently degenerating into repeated,
        identical snapshot predictions once the walk runs out of real
        candles to advance through."""
        job = await train_completed_job(client, session_factory, symbol="APIBTPASTDATAUSD")

        response = await client.post(
            "/api/v1/backtests/run",
            json={
                "training_job_id": job["id"],
                "symbol": "APIBTPASTDATAUSD",
                "start": (_EARLY_START + timedelta(hours=35)).isoformat(),
                "end": (_EARLY_START + timedelta(hours=45)).isoformat(),  # past hour 80
            },
        )
        assert response.status_code == 400
        assert response.json()["code"] == "backtest_range_exceeds_available_data"


class TestGetAndListBacktests:
    async def test_returns_404_for_an_unknown_id(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/backtests/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90")
        assert response.status_code == 404
        assert response.json()["code"] == "backtest_run_not_found"

    async def test_lists_past_runs_most_recent_first_and_filters_by_symbol(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        job = await train_completed_job(client, session_factory, symbol="APIBTLISTUSD")

        first = await run_backtest_and_wait(
            client,
            {
                "training_job_id": job["id"],
                "symbol": "APIBTLISTUSD",
                "start": _EARLY_START.isoformat(),
                "end": (_EARLY_START + timedelta(hours=1)).isoformat(),
            },
        )
        second = await run_backtest_and_wait(
            client,
            {
                "training_job_id": job["id"],
                "symbol": "APIBTLISTUSD",
                "start": (_EARLY_START + timedelta(hours=1)).isoformat(),
                "end": (_EARLY_START + timedelta(hours=2)).isoformat(),
            },
        )

        # `created_at` is server-generated via SQLite's second-resolution
        # `CURRENT_TIMESTAMP` (see `TimestampMixin`) — two runs created
        # back-to-back within the same wall-clock second can genuinely tie,
        # which would leave "most recent first" to an arbitrary id tiebreak
        # rather than proving anything. Nudge the first one's own timestamp
        # back so there's a real, deterministic difference to assert.
        async with session_factory() as session:
            repository = BacktestRunRepository(session)
            first_run = await repository.get_by_id(uuid.UUID(first["id"]))
            assert first_run is not None
            await repository.update(
                first_run, {"created_at": datetime.now(UTC) - timedelta(minutes=1)}
            )

        listed = (await client.get("/api/v1/backtests", params={"symbol": "APIBTLISTUSD"})).json()

        assert listed["total"] == 2
        assert [r["id"] for r in listed["runs"]] == [second["id"], first["id"]]

    async def test_returns_400_for_an_unsupported_sort_column(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/api/v1/backtests", params={"sort": "bogus"})
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_backtest_sort"


class TestPredictionHistoryDrillDown:
    async def test_backtest_predictions_are_excluded_by_default_and_shown_when_filtered(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        job = await train_completed_job(client, session_factory, symbol="APIBTDRILLUSD")
        live = (
            await client.post(
                "/api/v1/predictions/run",
                json={"training_job_id": job["id"], "symbol": "APIBTDRILLUSD"},
            )
        ).json()

        run = await run_backtest_and_wait(
            client,
            {
                "training_job_id": job["id"],
                "symbol": "APIBTDRILLUSD",
                "start": _EARLY_START.isoformat(),
                "end": (_EARLY_START + timedelta(hours=3)).isoformat(),
            },
        )
        assert run["completed_steps"] == 3

        default_view = (
            await client.get("/api/v1/predictions", params={"training_job_id": job["id"]})
        ).json()
        assert default_view["total"] == 1
        assert default_view["predictions"][0]["id"] == live["id"]

        drill_down = (
            await client.get("/api/v1/predictions", params={"backtest_run_id": run["id"]})
        ).json()
        assert drill_down["total"] == 3
