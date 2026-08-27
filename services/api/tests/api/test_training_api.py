"""Machine Learning Training Framework REST endpoint tests.

Runs against the real FastAPI app over ASGI with the in-memory SQLite
database, mirroring `test_experiments_api.py`'s own convention exactly.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from app.models import Candle, Exchange, Market
from tests.conftest import SessionFactory


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

        response = await client.post(f"/api/v1/training-jobs/{created['id']}/run")
        assert response.status_code == 200
        body = response.json()
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

        response = await client.post(f"/api/v1/training-jobs/{created['id']}/run")
        assert response.status_code == 200
        assert response.json()["status"] == "failed"

    async def test_cannot_run_a_completed_job_again(self, client: httpx.AsyncClient) -> None:
        experiment = await create_experiment(client, dataset_version="ds-1")
        created = (
            await client.post("/api/v1/training-jobs", json=job_body(experiment["id"]))
        ).json()
        await client.post(f"/api/v1/training-jobs/{created['id']}/run")

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
        await client.post(f"/api/v1/training-jobs/{created['id']}/run")

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

        response = await client.post(f"/api/v1/training-jobs/{created['id']}/run")

        assert response.status_code == 200
        body = response.json()
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

        response = await client.post(f"/api/v1/training-jobs/{created['id']}/run")

        assert response.status_code == 200
        body = response.json()
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

        response = await client.post(f"/api/v1/training-jobs/{created['id']}/run")

        assert response.status_code == 200
        body = response.json()
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
        completed = (await client.post(f"/api/v1/training-jobs/{created['id']}/run")).json()
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
        await client.post(f"/api/v1/training-jobs/{created['id']}/run")

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
        await client.post(f"/api/v1/training-jobs/{created['id']}/run")

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
        await client.post(f"/api/v1/training-jobs/{created['id']}/run")

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
