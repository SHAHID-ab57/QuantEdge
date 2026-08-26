"""Experiment Management REST endpoint tests.

Runs against the real FastAPI app over ASGI with the in-memory SQLite
database, so routing, JSON body parsing, serialization, and the shared
``AppError`` → JSON envelope are all covered end to end — the same
convention ``test_ml_datasets_api.py``/``test_dataset_validation_api.py``
already establish.
"""

import httpx


def experiment_body(**overrides: object) -> dict:
    """A minimal, valid experiment-create request body."""
    body: dict = {"name": "baseline sma experiment"}
    body.update(overrides)
    return body


class TestCreateExperiment:
    async def test_creates_an_experiment(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/experiments", json=experiment_body())
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "baseline sma experiment"
        assert body["status"] == "draft"
        assert body["tags"] == []
        assert body["metrics"] == []
        assert body["artifacts"] == []
        assert "id" in body and "created_at" in body and "updated_at" in body

    async def test_creates_an_experiment_with_full_configuration(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/experiments",
            json=experiment_body(
                dataset_version="ds-abc123",
                feature_set=[{"feature": "sma", "params": {"period": "20"}}],
                target_config=[{"target": "next_close", "params": {"horizon": "1"}}],
                split_config={"train": 0.7, "validation": 0.15, "test": 0.15},
                model_type="xgboost",
                status="running",
                notes="first real attempt",
                tags=["baseline", "sma"],
            ),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["dataset_version"] == "ds-abc123"
        assert body["feature_set"] == [{"feature": "sma", "params": {"period": "20"}}]
        assert body["split_config"] == {"train": 0.7, "validation": 0.15, "test": 0.15}
        assert body["status"] == "running"
        assert sorted(body["tags"]) == ["baseline", "sma"]

    async def test_rejects_an_empty_name(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/experiments", json=experiment_body(name=""))
        assert response.status_code == 422

    async def test_rejects_an_invalid_status(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/experiments", json=experiment_body(status="not_a_real_status")
        )
        assert response.status_code == 422

    async def test_is_mounted_unversioned_too(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/experiments", json=experiment_body())
        assert response.status_code == 201


class TestGetExperiment:
    async def test_gets_an_existing_experiment(self, client: httpx.AsyncClient) -> None:
        created = (await client.post("/api/v1/experiments", json=experiment_body())).json()
        response = await client.get(f"/api/v1/experiments/{created['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    async def test_returns_404_for_an_unknown_id(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/experiments/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90")
        assert response.status_code == 404
        assert response.json()["code"] == "experiment_not_found"

    async def test_returns_422_for_a_malformed_id(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/experiments/not-a-uuid")
        assert response.status_code == 422


class TestUpdateExperiment:
    async def test_applies_a_partial_update(self, client: httpx.AsyncClient) -> None:
        created = (await client.post("/api/v1/experiments", json=experiment_body())).json()
        response = await client.patch(
            f"/api/v1/experiments/{created['id']}", json={"status": "completed"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["name"] == created["name"]

    async def test_replaces_tags(self, client: httpx.AsyncClient) -> None:
        created = (
            await client.post("/api/v1/experiments", json=experiment_body(tags=["a", "b"]))
        ).json()
        response = await client.patch(f"/api/v1/experiments/{created['id']}", json={"tags": ["c"]})
        assert response.json()["tags"] == ["c"]

    async def test_returns_404_for_an_unknown_id(self, client: httpx.AsyncClient) -> None:
        response = await client.patch(
            "/api/v1/experiments/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90",
            json={"status": "completed"},
        )
        assert response.status_code == 404


class TestDeleteExperiment:
    async def test_deletes_an_experiment(self, client: httpx.AsyncClient) -> None:
        created = (await client.post("/api/v1/experiments", json=experiment_body())).json()
        response = await client.delete(f"/api/v1/experiments/{created['id']}")
        assert response.status_code == 204

        follow_up = await client.get(f"/api/v1/experiments/{created['id']}")
        assert follow_up.status_code == 404

    async def test_returns_404_for_an_unknown_id(self, client: httpx.AsyncClient) -> None:
        response = await client.delete("/api/v1/experiments/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90")
        assert response.status_code == 404


class TestListExperiments:
    async def test_lists_created_experiments(self, client: httpx.AsyncClient) -> None:
        await client.post("/api/v1/experiments", json=experiment_body(name="first"))
        await client.post("/api/v1/experiments", json=experiment_body(name="second"))

        response = await client.get("/api/v1/experiments")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 2
        names = {row["name"] for row in body["experiments"]}
        assert {"first", "second"} <= names

    async def test_search_narrows_by_name(self, client: httpx.AsyncClient) -> None:
        await client.post("/api/v1/experiments", json=experiment_body(name="unique-alpha-name"))
        await client.post("/api/v1/experiments", json=experiment_body(name="something else"))

        response = await client.get("/api/v1/experiments", params={"q": "unique-alpha"})
        body = response.json()
        assert body["total"] == 1
        assert body["experiments"][0]["name"] == "unique-alpha-name"

    async def test_filters_by_status(self, client: httpx.AsyncClient) -> None:
        await client.post(
            "/api/v1/experiments", json=experiment_body(name="running-one", status="running")
        )

        response = await client.get("/api/v1/experiments", params={"status": "running"})
        body = response.json()
        assert all(row["status"] == "running" for row in body["experiments"])
        assert any(row["name"] == "running-one" for row in body["experiments"])

    async def test_filters_by_tag(self, client: httpx.AsyncClient) -> None:
        await client.post(
            "/api/v1/experiments", json=experiment_body(name="tagged-one", tags=["unique-tag"])
        )

        response = await client.get("/api/v1/experiments", params={"tag": "unique-tag"})
        body = response.json()
        assert body["total"] == 1
        assert body["experiments"][0]["name"] == "tagged-one"

    async def test_sorts_by_name_ascending(self, client: httpx.AsyncClient) -> None:
        await client.post("/api/v1/experiments", json=experiment_body(name="zzz-last"))
        await client.post("/api/v1/experiments", json=experiment_body(name="aaa-first"))

        response = await client.get(
            "/api/v1/experiments", params={"sort": "name", "dir": "asc", "limit": 200}
        )
        names = [row["name"] for row in response.json()["experiments"]]
        assert names.index("aaa-first") < names.index("zzz-last")

    async def test_paginates_with_limit_and_offset(self, client: httpx.AsyncClient) -> None:
        for i in range(3):
            await client.post("/api/v1/experiments", json=experiment_body(name=f"page-test-{i}"))

        response = await client.get("/api/v1/experiments", params={"limit": 1, "offset": 0})
        body = response.json()
        assert len(body["experiments"]) == 1
        assert body["limit"] == 1
        assert body["offset"] == 0

    async def test_returns_400_for_an_invalid_sort_column(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/experiments", params={"sort": "not_a_column"})
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_sort"

    async def test_returns_422_for_an_out_of_range_limit(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/experiments", params={"limit": 100000})
        assert response.status_code == 422


class TestMetrics:
    async def test_creates_a_metric(self, client: httpx.AsyncClient) -> None:
        created = (await client.post("/api/v1/experiments", json=experiment_body())).json()
        response = await client.post(
            f"/api/v1/experiments/{created['id']}/metrics",
            json={"name": "accuracy", "value": 0.91, "unit": "ratio"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "accuracy"
        assert body["value"] == 0.91

        experiment = (await client.get(f"/api/v1/experiments/{created['id']}")).json()
        assert len(experiment["metrics"]) == 1

    async def test_returns_404_for_an_unknown_experiment(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/experiments/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90/metrics",
            json={"name": "accuracy", "value": 0.9},
        )
        assert response.status_code == 404

    async def test_deletes_a_metric(self, client: httpx.AsyncClient) -> None:
        created = (await client.post("/api/v1/experiments", json=experiment_body())).json()
        metric = (
            await client.post(
                f"/api/v1/experiments/{created['id']}/metrics",
                json={"name": "accuracy", "value": 0.9},
            )
        ).json()

        response = await client.delete(
            f"/api/v1/experiments/{created['id']}/metrics/{metric['id']}"
        )
        assert response.status_code == 204

        experiment = (await client.get(f"/api/v1/experiments/{created['id']}")).json()
        assert experiment["metrics"] == []

    async def test_returns_404_for_an_unknown_metric(self, client: httpx.AsyncClient) -> None:
        created = (await client.post("/api/v1/experiments", json=experiment_body())).json()
        response = await client.delete(
            f"/api/v1/experiments/{created['id']}/metrics/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90"
        )
        assert response.status_code == 404
        assert response.json()["code"] == "metric_not_found"


class TestArtifacts:
    async def test_creates_an_artifact(self, client: httpx.AsyncClient) -> None:
        created = (await client.post("/api/v1/experiments", json=experiment_body())).json()
        response = await client.post(
            f"/api/v1/experiments/{created['id']}/artifacts",
            json={"artifact_type": "dataset_export", "uri": "ETHUSD-1h-ml-dataset.csv"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["artifact_type"] == "dataset_export"
        assert body["uri"] == "ETHUSD-1h-ml-dataset.csv"

    async def test_rejects_an_unknown_artifact_type(self, client: httpx.AsyncClient) -> None:
        created = (await client.post("/api/v1/experiments", json=experiment_body())).json()
        response = await client.post(
            f"/api/v1/experiments/{created['id']}/artifacts",
            json={"artifact_type": "not_a_real_type", "uri": "x"},
        )
        assert response.status_code == 422

    async def test_returns_404_for_an_unknown_experiment(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/experiments/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90/artifacts",
            json={"artifact_type": "report", "uri": "x"},
        )
        assert response.status_code == 404

    async def test_deletes_an_artifact(self, client: httpx.AsyncClient) -> None:
        created = (await client.post("/api/v1/experiments", json=experiment_body())).json()
        artifact = (
            await client.post(
                f"/api/v1/experiments/{created['id']}/artifacts",
                json={"artifact_type": "report", "uri": "report.pdf"},
            )
        ).json()

        response = await client.delete(
            f"/api/v1/experiments/{created['id']}/artifacts/{artifact['id']}"
        )
        assert response.status_code == 204

        experiment = (await client.get(f"/api/v1/experiments/{created['id']}")).json()
        assert experiment["artifacts"] == []

    async def test_returns_404_for_an_unknown_artifact(self, client: httpx.AsyncClient) -> None:
        created = (await client.post("/api/v1/experiments", json=experiment_body())).json()
        response = await client.delete(
            f"/api/v1/experiments/{created['id']}/artifacts/6f1e4a2c-3b8d-4c9a-9e2f-1a7c5d6b8e90"
        )
        assert response.status_code == 404
        assert response.json()["code"] == "artifact_not_found"
