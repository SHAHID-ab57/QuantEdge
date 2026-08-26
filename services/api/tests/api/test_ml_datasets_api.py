"""ML Dataset Builder REST endpoint tests.

Runs against the real FastAPI app over ASGI with the in-memory SQLite
database, so routing, JSON body parsing, serialization, the file-download
headers, and the shared ``AppError`` → JSON envelope are all covered end
to end.
"""

import httpx


def dataset_body(*features: dict, targets: list[dict] | None = None, **kwargs: object) -> dict:
    """An ML dataset request body over 1h candles."""
    body: dict = {
        "timeframe": "1h",
        "features": list(features),
        "targets": targets if targets is not None else [{"target": "next_close"}],
    }
    body.update(kwargs)
    return body


class TestTargetCatalogueEndpoint:
    async def test_lists_registered_targets(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/ml/targets")
        assert response.status_code == 200
        body = response.json()
        names = {entry["name"] for entry in body["targets"]}
        assert {"next_close", "next_direction", "next_return"} <= names
        assert body["total"] == len(body["targets"])

    async def test_describes_a_single_target(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/ml/targets/next_close")
        assert response.status_code == 200
        assert response.json()["category"] == "price"

    async def test_returns_404_for_an_unknown_target(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/ml/targets/nope")
        assert response.status_code == 404
        assert response.json()["code"] == "target_not_found"

    async def test_is_mounted_unversioned_too(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/ml/targets")).status_code == 200


class TestBuildDatasetEndpoint:
    async def test_builds_a_dataset_over_stored_candles(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/ml/dataset",
            json=dataset_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["symbol"] == "ETCUSD"
        assert "next_close_1" in body["target_columns"]
        assert body["feature_columns"] == ["open", "high", "low", "close", "volume"]

    async def test_embeds_the_validation_report(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        body = (
            await client.post(
                "/api/v1/markets/ETCUSD/ml/dataset",
                json=dataset_body({"feature": "ohlcv"}),
            )
        ).json()
        assert "passed" in body["validation"]
        assert "issues" in body["validation"]

    async def test_every_row_has_a_split_label(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        body = (
            await client.post(
                "/api/v1/markets/ETCUSD/ml/dataset",
                json=dataset_body({"feature": "ohlcv"}),
            )
        ).json()
        assert len(body["split"]) == len(body["rows"])
        assert all(label in ("train", "validation", "test") for label in body["split"])

    async def test_reports_split_bounds_and_ratios(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        body = (
            await client.post(
                "/api/v1/markets/ETCUSD/ml/dataset",
                json=dataset_body(
                    {"feature": "ohlcv"}, split_train=0.5, split_validation=0.25, split_test=0.25
                ),
            )
        ).json()
        assert body["split_ratios"] == {"train": 0.5, "validation": 0.25, "test": 0.25}

    async def test_an_unknown_target_is_reported_as_a_failure_not_a_404(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/ml/dataset",
            json=dataset_body({"feature": "ohlcv"}, targets=[{"target": "nope"}]),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["target_failures"][0]["error_code"] == "target_not_found"

    async def test_rejects_split_ratios_that_do_not_sum_to_one(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/ml/dataset",
            json=dataset_body(
                {"feature": "ohlcv"}, split_train=0.5, split_validation=0.3, split_test=0.3
            ),
        )
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_split_ratios"

    async def test_rejects_a_column_collision_between_two_targets(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/ml/dataset",
            json=dataset_body(
                {"feature": "ohlcv"},
                targets=[{"target": "next_close"}, {"target": "next_close"}],
            ),
        )
        assert response.status_code == 400
        assert response.json()["code"] == "duplicate_target_column"

    async def test_requires_at_least_one_target(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/ml/dataset",
            json={"timeframe": "1h", "features": [{"feature": "ohlcv"}], "targets": []},
        )
        assert response.status_code == 422

    async def test_returns_404_for_an_unknown_market(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/markets/NOPE/ml/dataset",
            json=dataset_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 404

    async def test_is_mounted_unversioned_too(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/markets/ETCUSD/ml/dataset",
            json=dataset_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 200


class TestExportEndpoint:
    async def test_exports_a_csv_file(self, client: httpx.AsyncClient, seeded_varied: None) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/ml/dataset/export?format=csv",
            json=dataset_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        assert "next_close_1" in response.text

    async def test_exports_a_json_file(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/ml/dataset/export?format=json",
            json=dataset_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        body = response.json()
        assert "split_bounds" in body

    async def test_export_always_contains_every_row_ignoring_preview_rows(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/ml/dataset/export?format=json",
            json=dataset_body({"feature": "ohlcv"}, preview_rows=1),
        )
        body = response.json()
        assert len(body["data"]) > 1

    async def test_rejects_an_unsupported_format(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/ml/dataset/export?format=parquet",
            json=dataset_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 422
