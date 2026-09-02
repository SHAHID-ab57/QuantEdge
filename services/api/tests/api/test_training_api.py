"""Machine Learning Training Framework REST endpoint tests.

Runs against the real FastAPI app over ASGI with the in-memory SQLite
database, mirroring `test_experiments_api.py`'s own convention exactly.

`POST /training-jobs/{id}/run` no longer blocks for the run's duration — it
validates and transitions to 'running' synchronously, then executes the
pipeline in a background `asyncio.Task` (see `app/dependencies/training.py`).
That task opens its own DB session via `get_engine()`, never through
`get_db`/FastAPI's dependency overrides, so `tests/api/conftest.py`'s
autouse fixture points it at this suite's own in-memory engine — the same
convention `tests/services/test_candle_sync.py` already uses for
`CandleSyncScheduler`. `run_and_wait` is this suite's replacement for the
old "the run response IS the final state" pattern: it asserts the response
is already 'running', then deterministically awaits the background task
(never a real sleep) before fetching the job's settled state.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.dependencies.training import wait_for_in_flight_training_jobs
from app.models import Candle, Exchange, Market
from app.training.pipeline import TrainingPipeline
from tests.conftest import SessionFactory

# `_training_background_uses_the_test_engine` (autouse) lives in
# `tests/api/conftest.py` — every suite under `tests/api/` needs it, not
# just this file.


async def run_and_wait(client: httpx.AsyncClient, job_id: str) -> dict:
    """POST /run, assert it returned before the pipeline could have finished
    (status is 'running', not a terminal state), deterministically await the
    background task, then return the job's settled state.
    """
    response = await client.post(f"/api/v1/training-jobs/{job_id}/run")
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    await wait_for_in_flight_training_jobs()
    final = await client.get(f"/api/v1/training-jobs/{job_id}")
    assert final.status_code == 200
    return final.json()


async def create_experiment(client: httpx.AsyncClient, **overrides: object) -> dict:
    body: dict = {"name": "training target experiment"}
    body.update(overrides)
    response = await client.post("/api/v1/experiments", json=body)
    assert response.status_code == 201
    return response.json()


async def create_experiment_with_real_config(
    client: httpx.AsyncClient, *, target: str = "next_direction", **overrides: object
) -> dict:
    body: dict = {
        "dataset_version": "ds-real",
        "feature_set": [{"feature": "ohlcv", "params": {}}],
        "target_config": [{"target": target, "params": {"horizon": "1"}}],
        "split_config": {"train": 0.7, "validation": 0.15, "test": 0.15},
    }
    body.update(overrides)
    return await create_experiment(client, **body)


async def seed_real_candles(
    session_factory: SessionFactory, *, symbol: str, count: int = 80
) -> None:
    """A wobbling hourly price series long enough for a non-empty train/validation/test
    split, with both 'up' and 'down' next_direction labels present."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    async with session_factory() as session:
        exchange = Exchange(name="Delta Exchange", slug="delta", country="India")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol=symbol,
            base_asset=symbol[:3],
            quote_asset=symbol[3:],
            market_type="perpetual",
        )
        session.add(market)
        await session.commit()

        price = 100.0
        for i in range(count):
            price += 3.0 if i % 3 != 0 else -4.0
            open_time = base + timedelta(hours=i)
            session.add(
                Candle(
                    market_id=market.id,
                    timeframe="1h",
                    open_time=open_time,
                    close_time=open_time + timedelta(hours=1),
                    open=Decimal(str(price)),
                    high=Decimal(str(price + 2)),
                    low=Decimal(str(price - 2)),
                    close=Decimal(str(price)),
                    volume=Decimal("100"),
                    quote_volume=None,
                    trade_count=None,
                    source="delta",
                )
            )
        await session.commit()


def job_body(experiment_id: str, **overrides: object) -> dict:
    body: dict = {"experiment_id": experiment_id, "model_type": "placeholder"}
    body.update(overrides)
    return body


class TestListModelAdapters:
    async def test_lists_the_placeholder_adapter(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/training-jobs/models")
        assert response.status_code == 200
        names = [a["name"] for a in response.json()["adapters"]]
        assert "placeholder" in names

    async def test_lists_the_real_baseline_adapters_with_their_model_kind(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/api/v1/training-jobs/models")
        by_name = {a["name"]: a for a in response.json()["adapters"]}
        assert by_name["logistic_regression"]["model_kind"] == "classification"
        assert by_name["logistic_regression"]["requires_real_data"] is True
        assert by_name["linear_regression"]["model_kind"] == "regression"
        assert by_name["linear_regression"]["requires_real_data"] is True
        assert by_name["placeholder"]["model_kind"] == "placeholder"
        assert by_name["placeholder"]["requires_real_data"] is False


class TestCreateTrainingJob:
    async def test_creates_a_pending_job(self, client: httpx.AsyncClient) -> None:
        experiment = await create_experiment(client, dataset_version="ds-abc")
        response = await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "pending"
        assert body["model_type"] == "placeholder"
        assert body["dataset_version"] == "ds-abc"
        assert body["logs"] == []
        assert body["normalize_features"] is True

    async def test_normalize_features_can_be_disabled(self, client: httpx.AsyncClient) -> None:
        experiment = await create_experiment(client, dataset_version="ds-abc")
        response = await client.post(
            "/api/v1/training-jobs",
            json=job_body(experiment["id"], normalize_features=False),
        )
        assert response.status_code == 201
        assert response.json()["normalize_features"] is False

    async def test_returns_404_for_an_unknown_experiment(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/training-jobs",
            json=job_body("6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90"),
        )
        assert response.status_code == 404
        assert response.json()["code"] == "experiment_not_found"

    async def test_rejects_a_missing_model_type(self, client: httpx.AsyncClient) -> None:
        experiment = await create_experiment(client)
        response = await client.post(
            "/api/v1/training-jobs", json={"experiment_id": experiment["id"]}
        )
        assert response.status_code == 422

    async def test_is_mounted_unversioned_too(self, client: httpx.AsyncClient) -> None:
        experiment = await create_experiment(client)
        response = await client.post("/training-jobs", json=job_body(experiment["id"]))
        assert response.status_code == 201


class TestGetTrainingJob:
    async def test_gets_an_existing_job(self, client: httpx.AsyncClient) -> None:
        experiment = await create_experiment(client)
        created = (
            await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        ).json()
        response = await client.get(f"/api/v1/training-jobs/{created['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    async def test_returns_404_for_an_unknown_id(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/training-jobs/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90")
        assert response.status_code == 404
        assert response.json()["code"] == "training_job_not_found"


class TestListTrainingJobs:
    async def test_lists_and_filters_by_experiment(self, client: httpx.AsyncClient) -> None:
        experiment_a = await create_experiment(client, name="a")
        experiment_b = await create_experiment(client, name="b")
        await client.post("/api/v1/training-jobs", json=job_body(experiment_a["id"]))
        await client.post("/api/v1/training-jobs", json=job_body(experiment_b["id"]))

        response = await client.get(
            "/api/v1/training-jobs", params={"experiment_id": experiment_a["id"]}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["jobs"][0]["experiment_id"] == experiment_a["id"]

    async def test_rejects_an_invalid_sort_column(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/training-jobs", params={"sort": "not_a_column"})
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_sort"


class TestDeleteTrainingJob:
    async def test_deletes_a_pending_job(self, client: httpx.AsyncClient) -> None:
        experiment = await create_experiment(client)
        created = (
            await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        ).json()

        response = await client.delete(f"/api/v1/training-jobs/{created['id']}")
        assert response.status_code == 204

        follow_up = await client.get(f"/api/v1/training-jobs/{created['id']}")
        assert follow_up.status_code == 404

    async def test_returns_404_for_an_unknown_id(self, client: httpx.AsyncClient) -> None:
        response = await client.delete("/api/v1/training-jobs/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90")
        assert response.status_code == 404


class TestRunTrainingJob:
    async def test_returns_before_a_slow_background_run_would_finish(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The non-blocking behavior itself: an artificially slow pipeline run
        must not delay the response — the request returns 'running' almost
        immediately, well under the delay, and the job only reaches its
        final state once the background task is explicitly awaited."""
        delay_seconds = 0.5
        original_run = TrainingPipeline.run

        async def slow_run(self: TrainingPipeline, **kwargs: object):
            await asyncio.sleep(delay_seconds)
            return await original_run(self, **kwargs)

        monkeypatch.setattr(TrainingPipeline, "run", slow_run)

        experiment = await create_experiment(client, dataset_version="ds-slow")
        created = (
            await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        ).json()

        started = time.perf_counter()
        response = await client.post(f"/api/v1/training-jobs/{created['id']}/run")
        elapsed = time.perf_counter() - started

        assert response.status_code == 200
        assert response.json()["status"] == "running"
        assert elapsed < delay_seconds / 2, (
            f"run endpoint took {elapsed:.3f}s — it should return long before "
            f"the artificial {delay_seconds}s pipeline delay elapses"
        )

        await wait_for_in_flight_training_jobs()
        final = (await client.get(f"/api/v1/training-jobs/{created['id']}")).json()
        assert final["status"] == "completed"

    async def test_polling_after_run_eventually_shows_completed(
        self, client: httpx.AsyncClient
    ) -> None:
        """The replacement for a real sleep-based poll: the background task
        is awaited deterministically (`wait_for_in_flight_training_jobs`),
        not slept for — this is what `GET /training-jobs/{id}` would
        observe on its own 3s poll interval once the job settles."""
        experiment = await create_experiment(client, dataset_version="ds-poll")
        created = (
            await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        ).json()

        response = await client.post(f"/api/v1/training-jobs/{created['id']}/run")
        assert response.json()["status"] == "running"

        await wait_for_in_flight_training_jobs()

        final = (await client.get(f"/api/v1/training-jobs/{created['id']}")).json()
        assert final["status"] == "completed"

    async def test_a_second_run_call_while_running_is_rejected_not_double_executed(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A duplicate run call while the job is still 'running' must be
        rejected — never silently ignored, and never a second execution
        racing the first.

        `schedule_training_job` is stubbed out for this test so the first
        call's job stays deterministically 'running' (no real background
        task ever transitions it further) while the second call is made —
        real concurrency safety (two callers genuinely racing the same
        atomic transition) is proven separately and more precisely at the
        service layer, without any HTTP/background-task involved, by
        `tests/training/test_service.py::TestStartAndExecuteRun::
        test_two_genuinely_concurrent_starts_reject_exactly_one` (two
        independent `TrainingJobService` instances racing `start()` via
        `asyncio.gather`). Letting a *real* background task run here too
        was tried and is flaky in this suite's single-shared-connection
        SQLite test harness specifically — the background task's own
        commit can collide with this test's second request's commit on the
        one physical connection `StaticPool` hands out to every session
        (`sqlite3.OperationalError: cannot commit transaction - SQL
        statements in progress`), a test-harness artifact of the
        accepted-as-is engine/pool sharing (see `ARCHITECTURE.md` §
        "Machine Learning Training Framework"), not a production one —
        real Postgres gives each session its own connection.
        """
        monkeypatch.setattr(
            "app.api.v1.endpoints.training.schedule_training_job", lambda job_id: None
        )
        experiment = await create_experiment(client, dataset_version="ds-dup")
        created = (
            await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        ).json()

        first = await client.post(f"/api/v1/training-jobs/{created['id']}/run")
        assert first.status_code == 200
        assert first.json()["status"] == "running"

        second = await client.post(f"/api/v1/training-jobs/{created['id']}/run")
        assert second.status_code == 409
        assert second.json()["code"] == "invalid_training_job_transition"

    async def test_runs_to_completion_and_reflects_on_the_experiment(
        self, client: httpx.AsyncClient
    ) -> None:
        experiment = await create_experiment(client, dataset_version="ds-run")
        created = (
            await client.post(
                "/api/v1/training-jobs",
                json=job_body(experiment["id"], hyperparameters={"epochs": 2}),
            )
        ).json()

        body = await run_and_wait(client, created["id"])
        assert body["status"] == "completed"
        assert body["result_summary"]["metrics"]["placeholder_loss"] is not None
        assert len(body["logs"]) > 0

        experiment_after = (await client.get(f"/api/v1/experiments/{experiment['id']}")).json()
        assert experiment_after["status"] == "completed"
        assert any(m["name"] == "placeholder_loss" for m in experiment_after["metrics"])
        assert any(a["artifact_type"] == "model_checkpoint" for a in experiment_after["artifacts"])

    async def test_fails_without_a_dataset_version(self, client: httpx.AsyncClient) -> None:
        experiment = await create_experiment(client)  # no dataset_version
        created = (
            await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        ).json()

        body = await run_and_wait(client, created["id"])
        assert body["status"] == "failed"

    async def test_cannot_run_a_completed_job_again(self, client: httpx.AsyncClient) -> None:
        experiment = await create_experiment(client, dataset_version="ds-1")
        created = (
            await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        ).json()
        await run_and_wait(client, created["id"])

        response = await client.post(f"/api/v1/training-jobs/{created['id']}/run")
        assert response.status_code == 409
        assert response.json()["code"] == "invalid_training_job_transition"


class TestCancelTrainingJob:
    async def test_cancels_a_pending_job(self, client: httpx.AsyncClient) -> None:
        experiment = await create_experiment(client)
        created = (
            await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        ).json()

        response = await client.post(f"/api/v1/training-jobs/{created['id']}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    async def test_returns_409_for_a_completed_job(self, client: httpx.AsyncClient) -> None:
        experiment = await create_experiment(client, dataset_version="ds-1")
        created = (
            await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        ).json()
        await run_and_wait(client, created["id"])

        response = await client.post(f"/api/v1/training-jobs/{created['id']}/cancel")
        assert response.status_code == 409


class TestRealBaselineModels:
    async def test_logistic_regression_trains_on_real_candles(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="APILOGUSD")
        experiment = await create_experiment_with_real_config(client, target="next_direction")
        created = (
            await client.post(
                "/api/v1/training-jobs",
                json=job_body(
                    experiment["id"],
                    model_type="logistic_regression",
                    symbol="APILOGUSD",
                    timeframe="1h",
                ),
            )
        ).json()

        body = await run_and_wait(client, created["id"])

        assert body["status"] == "completed"
        metrics = body["result_summary"]["metrics"]
        assert {"accuracy", "precision", "recall", "f1"} <= metrics.keys()
        assert "confusion_matrix" in body["result_summary"]
        summary = body["result_summary"]
        assert "train_metrics" in summary
        assert "test_metrics" in summary
        assert "overfitting" in summary
        assert "confusion_matrix_details" in summary
        assert "roc_pr_curves" in summary
        assert "feature_importance" in summary
        assert "prediction_samples" in summary
        assert summary["model_metadata"]["sample_count"] > 0

        experiment_after = (await client.get(f"/api/v1/experiments/{experiment['id']}")).json()
        assert experiment_after["status"] == "completed"
        assert any(m["name"] == "accuracy" for m in experiment_after["metrics"])
        assert any(a["artifact_type"] == "report" for a in experiment_after["artifacts"])
        assert any(a["artifact_type"] == "plot" for a in experiment_after["artifacts"])

    async def test_linear_regression_trains_on_real_candles(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="APILINUSD")
        experiment = await create_experiment_with_real_config(client, target="next_close")
        created = (
            await client.post(
                "/api/v1/training-jobs",
                json=job_body(
                    experiment["id"],
                    model_type="linear_regression",
                    symbol="APILINUSD",
                    timeframe="1h",
                ),
            )
        ).json()

        body = await run_and_wait(client, created["id"])

        assert body["status"] == "completed"
        metrics = body["result_summary"]["metrics"]
        assert {"mae", "mse", "rmse", "r2"} <= metrics.keys()

    async def test_fails_without_a_symbol_and_timeframe(self, client: httpx.AsyncClient) -> None:
        experiment = await create_experiment_with_real_config(client)
        created = (
            await client.post(
                "/api/v1/training-jobs",
                json=job_body(experiment["id"], model_type="logistic_regression"),
            )
        ).json()

        body = await run_and_wait(client, created["id"])

        assert body["status"] == "failed"
        assert body["error_detail"] is not None
        assert body["error_detail"]["suggested_fix"]


class TestPredictTrainingJob:
    async def test_predicts_using_a_completed_jobs_model(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="APIPREDUSD")
        experiment = await create_experiment_with_real_config(client, target="next_direction")
        created = (
            await client.post(
                "/api/v1/training-jobs",
                json=job_body(
                    experiment["id"],
                    model_type="logistic_regression",
                    symbol="APIPREDUSD",
                    timeframe="1h",
                ),
            )
        ).json()
        completed = await run_and_wait(client, created["id"])
        feature_columns = completed["result_summary"]["feature_columns"]

        response = await client.post(
            f"/api/v1/training-jobs/{created['id']}/predict",
            json={"rows": [[1.0] * len(feature_columns)]},
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body["predictions"]) == 1
        assert body["feature_columns"] == feature_columns
        assert body["classes"] == completed["result_summary"]["classes"]
        assert len(body["probabilities"][0]) == len(body["classes"])
        assert body["confidence_levels"][0] in {"high", "medium", "low"}

    async def test_returns_409_before_the_job_has_completed(
        self, client: httpx.AsyncClient
    ) -> None:
        experiment = await create_experiment(client)
        created = (
            await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        ).json()

        response = await client.post(
            f"/api/v1/training-jobs/{created['id']}/predict", json={"rows": [[1.0]]}
        )

        assert response.status_code == 409
        assert response.json()["code"] == "prediction_not_available"

    async def test_returns_400_for_a_row_length_mismatch(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="APIMISMATCHUSD")
        experiment = await create_experiment_with_real_config(client, target="next_direction")
        created = (
            await client.post(
                "/api/v1/training-jobs",
                json=job_body(
                    experiment["id"],
                    model_type="logistic_regression",
                    symbol="APIMISMATCHUSD",
                    timeframe="1h",
                ),
            )
        ).json()
        await run_and_wait(client, created["id"])

        response = await client.post(
            f"/api/v1/training-jobs/{created['id']}/predict",
            json={"rows": [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]]},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_prediction_input"


class TestTrainingJobArtifacts:
    async def test_lists_and_downloads_every_artifact_for_a_completed_job(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="APIARTIFACTUSD")
        experiment = await create_experiment_with_real_config(client, target="next_direction")
        created = (
            await client.post(
                "/api/v1/training-jobs",
                json=job_body(
                    experiment["id"],
                    model_type="logistic_regression",
                    symbol="APIARTIFACTUSD",
                    timeframe="1h",
                ),
            )
        ).json()
        await run_and_wait(client, created["id"])

        listing = await client.get(f"/api/v1/training-jobs/{created['id']}/artifacts")

        assert listing.status_code == 200
        artifacts = listing.json()["artifacts"]
        types = {a["artifact_type"] for a in artifacts}
        assert types == {
            "model_joblib",
            "metrics_json",
            "training_report_json",
            "feature_importance_csv",
            "confusion_matrix_png",
            "roc_curve_png",
            "precision_recall_curve_png",
        }

        csv_entry = next(a for a in artifacts if a["artifact_type"] == "feature_importance_csv")
        download = await client.get(csv_entry["download_url"])
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("text/csv")
        assert b"feature,coefficient,abs_importance,sign" in download.content

    async def test_returns_404_for_an_unknown_artifact_type(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="APIARTIFACT404USD")
        experiment = await create_experiment_with_real_config(client, target="next_close")
        created = (
            await client.post(
                "/api/v1/training-jobs",
                json=job_body(
                    experiment["id"],
                    model_type="linear_regression",
                    symbol="APIARTIFACT404USD",
                    timeframe="1h",
                ),
            )
        ).json()
        await run_and_wait(client, created["id"])

        response = await client.get(
            f"/api/v1/training-jobs/{created['id']}/artifacts/roc_curve_png"
        )

        assert response.status_code == 404
        assert response.json()["code"] == "training_artifact_not_found"

    async def test_lists_no_artifacts_for_a_job_that_has_not_run(
        self, client: httpx.AsyncClient
    ) -> None:
        experiment = await create_experiment(client)
        created = (
            await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        ).json()

        response = await client.get(f"/api/v1/training-jobs/{created['id']}/artifacts")

        assert response.status_code == 200
        assert response.json()["artifacts"] == []
