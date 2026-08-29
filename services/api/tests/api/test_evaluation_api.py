"""Model Evaluation & Benchmarking Engine REST endpoint tests.

Runs against the real FastAPI app over ASGI with the in-memory SQLite
database, mirroring `test_training_api.py`'s own convention exactly.
"""

import httpx

from tests.api.test_training_api import seed_real_candles
from tests.conftest import SessionFactory


async def create_experiment(client: httpx.AsyncClient, **overrides: object) -> dict:
    body: dict = {"name": "evaluation target experiment"}
    body.update(overrides)
    response = await client.post("/api/v1/experiments", json=body)
    assert response.status_code == 201
    return response.json()


async def create_experiment_with_real_config(
    client: httpx.AsyncClient, *, target: str = "next_direction", **overrides: object
) -> dict:
    body: dict = {
        "dataset_version": "ds-eval",
        "feature_set": [{"feature": "ohlcv", "params": {}}],
        "target_config": [{"target": target, "params": {"horizon": "1"}}],
        "split_config": {"train": 0.7, "validation": 0.15, "test": 0.15},
    }
    body.update(overrides)
    return await create_experiment(client, **body)


class TestListMetrics:
    async def test_returns_the_builtin_catalogue(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/evaluation/metrics")

        assert response.status_code == 200
        names = {m["name"] for m in response.json()["metrics"]}
        assert {"accuracy", "precision", "recall", "f1", "roc_auc"} <= names
        assert {"mae", "mse", "rmse", "r2"} <= names

    async def test_is_also_mounted_unversioned(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/evaluation/metrics")
        assert response.status_code == 200


class TestBenchmark:
    async def test_rejects_a_request_with_no_target(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/evaluation/benchmark", json={})

        assert response.status_code == 400
        assert response.json()["code"] == "no_benchmark_target"

    async def test_returns_404_when_nothing_matches(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/evaluation/benchmark", json={"dataset_version": "ds-does-not-exist"}
        )

        assert response.status_code == 404
        assert response.json()["code"] == "empty_benchmark"

    async def test_compares_two_completed_jobs_over_the_same_dataset(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="EVALBENCHUSD")
        experiment = await create_experiment_with_real_config(
            client, target="next_direction", dataset_version="ds-bench-shared"
        )

        for model_type in ("logistic_regression", "logistic_regression"):
            created = (
                await client.post(
                    "/api/v1/training-jobs",
                    json={
                        "experiment_id": experiment["id"],
                        "model_type": model_type,
                        "symbol": "EVALBENCHUSD",
                        "timeframe": "1h",
                        "dataset_version": "ds-bench-shared",
                    },
                )
            ).json()
            run = await client.post(f"/api/v1/training-jobs/{created['id']}/run")
            assert run.json()["status"] == "completed"

        response = await client.post(
            "/api/v1/evaluation/benchmark", json={"dataset_version": "ds-bench-shared"}
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body["candidates"]) == 2
        assert any(e["metric"] == "accuracy" for e in body["best_by_metric"])
        for candidate in body["candidates"]:
            assert candidate["model_kind"] == "classification"
            assert "accuracy" in candidate["metrics"]
            # Dataset Summary Card / deep-link fields — all reused from data the
            # training run itself already produced, nothing recomputed here.
            assert candidate["symbol"] == "EVALBENCHUSD"
            assert candidate["timeframe"] == "1h"
            assert candidate["feature_count"] is not None
            assert candidate["sample_count"] is not None
            assert candidate["model_artifact_url"] == (
                f"/api/v1/training-jobs/{candidate['training_job_id']}/artifacts/model_joblib"
            )
            assert candidate["report"]["confusion_matrix"] is not None
            assert candidate["report"]["roc_pr_curves"] is not None

    async def test_narrows_by_experiment_ids(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="EVALNARROWUSD")
        experiment_a = await create_experiment_with_real_config(
            client, target="next_direction", dataset_version="ds-bench-narrow"
        )
        experiment_b = await create_experiment_with_real_config(
            client, target="next_direction", dataset_version="ds-bench-narrow"
        )
        for experiment in (experiment_a, experiment_b):
            created = (
                await client.post(
                    "/api/v1/training-jobs",
                    json={
                        "experiment_id": experiment["id"],
                        "model_type": "logistic_regression",
                        "symbol": "EVALNARROWUSD",
                        "timeframe": "1h",
                        "dataset_version": "ds-bench-narrow",
                    },
                )
            ).json()
            await client.post(f"/api/v1/training-jobs/{created['id']}/run")

        response = await client.post(
            "/api/v1/evaluation/benchmark",
            json={
                "dataset_version": "ds-bench-narrow",
                "experiment_ids": [experiment_a["id"]],
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body["candidates"]) == 1
        assert body["candidates"][0]["experiment_id"] == experiment_a["id"]

    async def test_supports_comparing_more_than_two_experiments(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="EVALMULTIUSD")
        experiments = [
            await create_experiment_with_real_config(
                client, target="next_direction", dataset_version="ds-bench-multi"
            )
            for _ in range(3)
        ]
        for experiment in experiments:
            created = (
                await client.post(
                    "/api/v1/training-jobs",
                    json={
                        "experiment_id": experiment["id"],
                        "model_type": "logistic_regression",
                        "symbol": "EVALMULTIUSD",
                        "timeframe": "1h",
                        "dataset_version": "ds-bench-multi",
                    },
                )
            ).json()
            await client.post(f"/api/v1/training-jobs/{created['id']}/run")

        response = await client.post(
            "/api/v1/evaluation/benchmark",
            json={
                "dataset_version": "ds-bench-multi",
                "experiment_ids": [e["id"] for e in experiments],
            },
        )

        assert response.status_code == 200
        assert len(response.json()["candidates"]) == 3


class TestBenchmarkHistory:
    async def test_a_successful_benchmark_appears_in_history(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="EVALHISTUSD")
        experiment = await create_experiment_with_real_config(
            client, target="next_direction", dataset_version="ds-bench-hist"
        )
        created = (
            await client.post(
                "/api/v1/training-jobs",
                json={
                    "experiment_id": experiment["id"],
                    "model_type": "logistic_regression",
                    "symbol": "EVALHISTUSD",
                    "timeframe": "1h",
                    "dataset_version": "ds-bench-hist",
                },
            )
        ).json()
        await client.post(f"/api/v1/training-jobs/{created['id']}/run")

        await client.post("/api/v1/evaluation/benchmark", json={"dataset_version": "ds-bench-hist"})

        history = await client.get(
            "/api/v1/evaluation/history", params={"dataset_version": "ds-bench-hist"}
        )

        assert history.status_code == 200
        body = history.json()
        assert body["total"] == 1
        assert body["runs"][0]["dataset_version"] == "ds-bench-hist"
        assert body["runs"][0]["candidate_count"] == 1

    async def test_reopening_a_run_returns_its_full_request_and_response(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="EVALREOPENUSD")
        experiment = await create_experiment_with_real_config(
            client, target="next_direction", dataset_version="ds-bench-reopen"
        )
        created = (
            await client.post(
                "/api/v1/training-jobs",
                json={
                    "experiment_id": experiment["id"],
                    "model_type": "logistic_regression",
                    "symbol": "EVALREOPENUSD",
                    "timeframe": "1h",
                    "dataset_version": "ds-bench-reopen",
                },
            )
        ).json()
        await client.post(f"/api/v1/training-jobs/{created['id']}/run")
        await client.post(
            "/api/v1/evaluation/benchmark", json={"dataset_version": "ds-bench-reopen"}
        )
        run_id = (
            await client.get(
                "/api/v1/evaluation/history", params={"dataset_version": "ds-bench-reopen"}
            )
        ).json()["runs"][0]["id"]

        response = await client.get(f"/api/v1/evaluation/history/{run_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["request"]["dataset_version"] == "ds-bench-reopen"
        assert len(body["response"]["candidates"]) == 1

    async def test_reopening_an_unknown_run_returns_404(self, client: httpx.AsyncClient) -> None:
        response = await client.get(
            "/api/v1/evaluation/history/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90"
        )

        assert response.status_code == 404
        assert response.json()["code"] == "benchmark_run_not_found"

    async def test_deleting_a_run_removes_it_from_history(
        self, client: httpx.AsyncClient, session_factory: SessionFactory
    ) -> None:
        await seed_real_candles(session_factory, symbol="EVALDELETEUSD")
        experiment = await create_experiment_with_real_config(
            client, target="next_direction", dataset_version="ds-bench-delete"
        )
        created = (
            await client.post(
                "/api/v1/training-jobs",
                json={
                    "experiment_id": experiment["id"],
                    "model_type": "logistic_regression",
                    "symbol": "EVALDELETEUSD",
                    "timeframe": "1h",
                    "dataset_version": "ds-bench-delete",
                },
            )
        ).json()
        await client.post(f"/api/v1/training-jobs/{created['id']}/run")
        await client.post(
            "/api/v1/evaluation/benchmark", json={"dataset_version": "ds-bench-delete"}
        )
        run_id = (
            await client.get(
                "/api/v1/evaluation/history", params={"dataset_version": "ds-bench-delete"}
            )
        ).json()["runs"][0]["id"]

        delete_response = await client.delete(f"/api/v1/evaluation/history/{run_id}")
        assert delete_response.status_code == 204

        get_response = await client.get(f"/api/v1/evaluation/history/{run_id}")
        assert get_response.status_code == 404

    async def test_deleting_an_unknown_run_returns_404(self, client: httpx.AsyncClient) -> None:
        response = await client.delete(
            "/api/v1/evaluation/history/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90"
        )
        assert response.status_code == 404
        assert response.json()["code"] == "benchmark_run_not_found"
