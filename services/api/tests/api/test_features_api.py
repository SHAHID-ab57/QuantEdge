"""Feature engineering REST endpoint tests.

Runs against the real FastAPI app over ASGI with the in-memory SQLite
database, so routing, JSON body parsing, serialization, the file-download
headers, and the shared ``AppError`` → JSON envelope are all covered end to
end.
"""

import csv
import io
import json

import httpx


def dataset_body(*features: dict, **kwargs: object) -> dict:
    """A dataset request body over 1h candles."""
    body: dict = {"timeframe": "1h", "features": list(features)}
    body.update(kwargs)
    return body


class TestCatalogueEndpoint:
    async def test_lists_registered_features(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/features")
        assert response.status_code == 200
        body = response.json()
        names = {entry["name"] for entry in body["features"]}
        assert {"ohlcv", "candle_shape", "sma", "ema", "wma"} <= names
        assert body["total"] == len(body["features"])

    async def test_reports_categories_for_grouping(self, client: httpx.AsyncClient) -> None:
        body = (await client.get("/api/v1/features")).json()
        assert "raw" in body["categories"]
        assert "price_action" in body["categories"]

    async def test_publishes_parameter_specs_for_form_building(
        self, client: httpx.AsyncClient
    ) -> None:
        body = (await client.get("/api/v1/features")).json()
        shape = next(e for e in body["features"] if e["name"] == "candle_shape")
        normalize = next(spec for spec in shape["parameters"] if spec["name"] == "normalize")
        assert normalize["type"] == "bool"
        assert normalize["default"] is False
        assert normalize["required"] is False

    async def test_publishes_output_column_templates(self, client: httpx.AsyncClient) -> None:
        body = (await client.get("/api/v1/features")).json()
        ohlcv = next(e for e in body["features"] if e["name"] == "ohlcv")
        assert ohlcv["outputs"] == ["open", "high", "low", "close", "volume"]

    async def test_describes_a_single_feature(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/features/candle_shape")
        assert response.status_code == 200
        assert response.json()["category"] == "price_action"

    async def test_a_delegating_feature_inherits_the_indicators_metadata(
        self, client: httpx.AsyncClient
    ) -> None:
        feature = (await client.get("/api/v1/features/sma")).json()
        indicator = (await client.get("/api/v1/indicators/sma")).json()
        assert feature["label"] == indicator["label"]
        assert feature["complexity"] == indicator["complexity"]
        assert feature["aliases"] == indicator["aliases"]

    async def test_returns_404_for_an_unknown_feature(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/features/nope")
        assert response.status_code == 404
        assert response.json()["code"] == "feature_not_found"

    async def test_is_mounted_unversioned_too(self, client: httpx.AsyncClient) -> None:
        # Every route on this platform is served at both prefixes.
        assert (await client.get("/features")).status_code == 200


class TestDatasetEndpoint:
    async def test_builds_a_dataset_over_stored_candles(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/dataset",
            json=dataset_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["symbol"] == "ETCUSD"
        assert [c["name"] for c in body["columns"]] == [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
        assert len(body["rows"]) == 3

    async def test_rows_align_with_timestamps(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        body = (
            await client.post(
                "/api/v1/markets/ETCUSD/features/dataset",
                json=dataset_body({"feature": "ohlcv"}),
            )
        ).json()
        assert len(body["timestamps"]) == len(body["rows"])
        for row in body["rows"]:
            assert len(row) == len(body["columns"])

    async def test_serializes_timestamps_with_a_literal_z_suffix(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        # The frontend validates with z.string().datetime(), which rejects
        # a "+00:00" offset.
        body = (
            await client.post(
                "/api/v1/markets/ETCUSD/features/dataset",
                json=dataset_body({"feature": "ohlcv"}),
            )
        ).json()
        assert body["timestamps"][0].endswith("Z")
        assert body["meta"]["generated_at"].endswith("Z")

    async def test_combines_several_features_into_one_matrix(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        body = (
            await client.post(
                "/api/v1/markets/ETCUSD/features/dataset",
                json=dataset_body(
                    {"feature": "ohlcv"},
                    {"feature": "candle_shape"},
                    {"feature": "sma", "params": {"period": "2"}},
                ),
            )
        ).json()
        names = [c["name"] for c in body["columns"]]
        assert "close" in names
        assert "candle_body" in names
        assert "sma_2" in names

    async def test_reports_column_dtypes(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        body = (
            await client.post(
                "/api/v1/markets/ETCUSD/features/dataset",
                json=dataset_body({"feature": "candle_shape"}),
            )
        ).json()
        by_name = {c["name"]: c for c in body["columns"]}
        assert by_name["candle_direction"]["dtype"] == "categorical"
        assert by_name["candle_body"]["dtype"] == "float"

    async def test_reports_provenance_metadata(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        body = (
            await client.post(
                "/api/v1/markets/ETCUSD/features/dataset",
                json=dataset_body({"feature": "sma", "params": {"period": "2"}}),
            )
        ).json()
        assert body["meta"]["pipeline_version"]
        assert body["meta"]["candles_analyzed"] == 3
        assert body["meta"]["rows_dropped"] == 1
        assert body["meta"]["warmup_candles"] == 2
        assert body["features"][0]["parameters"] == {"period": 2, "source": "close"}
        assert body["features"][0]["columns"] == ["sma_2"]

    async def test_preview_truncation_still_reports_the_true_size(
        self, client: httpx.AsyncClient, seeded: None
    ) -> None:
        body = (
            await client.post(
                "/api/v1/markets/ETHUSD/features/dataset",
                json=dataset_body({"feature": "ohlcv"}, preview_rows=2),
            )
        ).json()
        assert len(body["rows"]) == 2
        assert body["meta"]["total_rows"] == 5
        assert body["meta"]["truncated"] is True

    async def test_keeps_warmup_rows_when_asked(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        body = (
            await client.post(
                "/api/v1/markets/ETCUSD/features/dataset",
                json=dataset_body({"feature": "sma", "params": {"period": "2"}}, drop_warmup=False),
            )
        ).json()
        assert len(body["rows"]) == 3
        assert body["rows"][0][0] is None

    async def test_is_mounted_unversioned_too(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/markets/ETCUSD/features/dataset", json=dataset_body({"feature": "ohlcv"})
        )
        assert response.status_code == 200


class TestDatasetErrors:
    async def test_returns_404_for_an_unknown_market(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/markets/NOPE/features/dataset", json=dataset_body({"feature": "ohlcv"})
        )
        assert response.status_code == 404
        assert response.json()["code"] == "market_not_found"

    async def test_reports_an_unknown_feature_as_a_quality_failure_not_a_404(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        # Partial-success: one bad feature name is a fact about that
        # feature, recorded in `quality.feature_failures`, and must not
        # fail the whole request — mirroring the indicator batch endpoint.
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/dataset",
            json=dataset_body({"feature": "ohlcv"}, {"feature": "macd"}),
        )
        assert response.status_code == 200
        body = response.json()
        assert [c["name"] for c in body["columns"]] == [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
        failure = body["quality"]["feature_failures"][0]
        assert failure["feature"] == "macd"
        assert failure["error_code"] == "feature_not_found"

    async def test_reports_an_out_of_range_parameter_as_a_quality_failure(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/dataset",
            json=dataset_body({"feature": "sma", "params": {"period": "0"}}),
        )
        assert response.status_code == 200
        failure = response.json()["quality"]["feature_failures"][0]
        assert failure["error_code"] == "invalid_feature_parameter"

    async def test_reports_an_unknown_parameter_as_a_quality_failure(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/dataset",
            json=dataset_body({"feature": "sma", "params": {"perid": "2"}}),
        )
        assert response.status_code == 200
        failure = response.json()["quality"]["feature_failures"][0]
        assert "is not accepted" in failure["error_detail"]

    async def test_rejects_two_features_producing_the_same_column(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/dataset",
            json=dataset_body(
                {"feature": "sma", "params": {"period": "2"}},
                {"feature": "sma", "params": {"period": "2"}},
            ),
        )
        assert response.status_code == 400
        assert response.json()["code"] == "duplicate_feature_column"

    async def test_reports_insufficient_data_with_the_required_count(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        # Three stored candles, default SMA period of 20 — reported as a
        # quality failure, not a 400: no candles at all would still be a
        # hard error (market/timeframe/range are wrong), but "one feature's
        # period is too long for this range" is a fact about that feature.
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/dataset", json=dataset_body({"feature": "sma"})
        )
        assert response.status_code == 200
        body = response.json()
        assert body["columns"] == []
        failure = body["quality"]["feature_failures"][0]
        assert failure["error_code"] == "insufficient_data"
        assert "at least 20" in failure["error_detail"]

    async def test_rejects_an_unsupported_timeframe(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/dataset",
            json=dataset_body({"feature": "ohlcv"}, timeframe="7d"),
        )
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_timeframe"

    async def test_returns_404_when_no_candles_are_stored_for_the_timeframe(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/dataset",
            json=dataset_body({"feature": "ohlcv"}, timeframe="1d"),
        )
        assert response.status_code == 404
        assert response.json()["code"] == "candle_not_found"

    async def test_rejects_an_empty_feature_list(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post("/api/v1/markets/ETCUSD/features/dataset", json=dataset_body())
        assert response.status_code == 422

    async def test_requires_a_timeframe(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/dataset",
            json={"features": [{"feature": "ohlcv"}]},
        )
        assert response.status_code == 422


class TestExportEndpoint:
    async def test_exports_csv_as_a_file_download(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/export?format=csv",
            json=dataset_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        assert ".csv" in response.headers["content-disposition"]

    async def test_exported_csv_parses_as_a_matrix(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/export?format=csv",
            json=dataset_body({"feature": "ohlcv"}),
        )
        lines = [line for line in response.text.splitlines() if not line.startswith("#")]
        rows = list(csv.reader(io.StringIO("\n".join(lines))))
        assert rows[0] == ["timestamp", "open", "high", "low", "close", "volume"]
        assert len(rows) == 4  # header + three candles

    async def test_exports_json_as_a_file_download(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/export?format=json",
            json=dataset_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert ".json" in response.headers["content-disposition"]
        payload = json.loads(response.text)
        assert payload["symbol"] == "ETCUSD"
        assert len(payload["data"]) == 3

    async def test_defaults_to_csv(self, client: httpx.AsyncClient, seeded_varied: None) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/export",
            json=dataset_body({"feature": "ohlcv"}),
        )
        assert response.headers["content-type"].startswith("text/csv")

    async def test_rejects_an_unknown_format(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/export?format=parquet",
            json=dataset_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 422

    async def test_export_ignores_preview_truncation(
        self, client: httpx.AsyncClient, seeded: None
    ) -> None:
        # An export truncated to what a preview happened to show would
        # silently produce a partial training set.
        response = await client.post(
            "/api/v1/markets/ETHUSD/features/export?format=json",
            json=dataset_body({"feature": "ohlcv"}, preview_rows=1),
        )
        assert len(json.loads(response.text)["data"]) == 5

    async def test_export_surfaces_the_same_errors_as_a_build(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/markets/NOPE/features/export?format=csv",
            json=dataset_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 404
        assert response.json()["code"] == "market_not_found"

    async def test_is_mounted_unversioned_too(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/markets/ETCUSD/features/export?format=csv",
            json=dataset_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 200
