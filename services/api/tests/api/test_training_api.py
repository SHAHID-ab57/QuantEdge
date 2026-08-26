"""Machine Learning Training Framework REST endpoint tests.

Runs against the real FastAPI app over ASGI with the in-memory SQLite
database, mirroring `test_experiments_api.py`'s own convention exactly.
"""

import httpx


async def create_experiment(client: httpx.AsyncClient, **overrides: object) -> dict:
    body: dict = {"name": "training target experiment"}
    body.update(overrides)
    response = await client.post("/api/v1/experiments", json=body)
    assert response.status_code == 201
    return response.json()


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
