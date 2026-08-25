"""Dataset validation REST endpoint tests.

Runs against the real FastAPI app over ASGI with the in-memory SQLite
database, so routing, JSON body parsing, and the shared ``AppError`` → JSON
envelope are all covered end to end — over both a clean dataset and
several intentionally-corrupted ones, using the same seeded-candle fixtures
``tests/conftest.py`` already provides for the market-data quality tests.
"""

import httpx


def validate_body(*features: dict, **kwargs: object) -> dict:
    """A validation request body over 1h candles."""
    body: dict = {"timeframe": "1h", "features": list(features)}
    body.update(kwargs)
    return body


class TestRuleCatalogueEndpoint:
    async def test_lists_every_builtin_rule(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/validation/rules")
        assert response.status_code == 200
        body = response.json()
        names = {entry["name"] for entry in body["rules"]}
        assert {
            "required_columns",
            "data_types",
            "missing_values",
            "duplicate_rows",
            "duplicate_timestamps",
            "nan_values",
            "infinite_values",
            "timestamp_ordering",
            "time_gaps",
            "metadata_consistency",
            "feature_failures",
        } <= names
        assert body["total"] == len(body["rules"])

    async def test_reports_every_category(self, client: httpx.AsyncClient) -> None:
        body = (await client.get("/api/v1/validation/rules")).json()
        assert {"structural", "data_quality", "time_series", "feature"} <= set(body["categories"])

    async def test_is_mounted_unversioned_too(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/validation/rules")).status_code == 200


class TestValidateEndpointOnCleanData:
    async def test_a_clean_dataset_passes(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/validate",
            json=validate_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["passed"] is True
        assert body["summary"]["errors"] == 0
        assert body["rows"] == 3
        assert body["columns"] == 5

    async def test_reports_every_category_at_zero_when_clean(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        body = (
            await client.post(
                "/api/v1/markets/ETCUSD/features/validate",
                json=validate_body({"feature": "ohlcv"}),
            )
        ).json()
        assert set(body["categories"]) == {"structural", "data_quality", "time_series", "feature"}
        assert all(cat["errors"] == 0 for cat in body["categories"].values())

    async def test_runs_every_rule_by_default(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        body = (
            await client.post(
                "/api/v1/markets/ETCUSD/features/validate",
                json=validate_body({"feature": "ohlcv"}),
            )
        ).json()
        assert len(body["rules_run"]) == 11

    async def test_is_mounted_unversioned_too(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/markets/ETCUSD/features/validate",
            json=validate_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 200


class TestValidateEndpointOnCorruptedData:
    async def test_repeated_identical_candles_are_flagged_as_duplicate_rows(
        self, client: httpx.AsyncClient, seeded: None
    ) -> None:
        # `seeded` gives ETHUSD five 1h candles with byte-for-byte identical
        # OHLCV values — a real, not synthetic, duplicate-rows scenario.
        response = await client.post(
            "/api/v1/markets/ETHUSD/features/validate",
            json=validate_body({"feature": "ohlcv"}),
        )
        body = response.json()
        codes = {issue["code"] for issue in body["issues"]}
        assert "duplicate_rows" in codes
        # Duplicate rows are a warning, not an error — the gate still passes.
        assert body["passed"] is True

    async def test_a_gap_in_the_candle_series_is_flagged_as_a_time_gap(
        self, client: httpx.AsyncClient, seeded_with_gap: None
    ) -> None:
        # `seeded_with_gap` gives BTCUSD 1h candles skipping the 03:00 bucket.
        response = await client.post(
            "/api/v1/markets/BTCUSD/features/validate",
            json=validate_body({"feature": "ohlcv"}),
        )
        body = response.json()
        gap_issues = [issue for issue in body["issues"] if issue["code"] == "time_gaps"]
        assert len(gap_issues) == 1
        assert gap_issues[0]["count"] == 1
        assert gap_issues[0]["severity"] == "warning"

    async def test_an_unknown_feature_is_recorded_as_a_failure_and_flagged(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/validate",
            json=validate_body({"feature": "ohlcv"}, {"feature": "does_not_exist"}),
        )
        assert response.status_code == 200
        body = response.json()
        codes = {issue["code"] for issue in body["issues"]}
        assert "feature_generation_failed" in codes


class TestRequiredColumnsAndRuleSubset:
    async def test_a_missing_required_column_fails_the_gate(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/validate",
            json=validate_body({"feature": "ohlcv"}, required_columns=["sma_20"]),
        )
        body = response.json()
        assert body["passed"] is False
        assert any(issue["code"] == "missing_required_column" for issue in body["issues"])

    async def test_running_a_rule_subset_only_reports_those_rules(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/validate",
            json=validate_body({"feature": "ohlcv"}, rules=["required_columns"]),
        )
        body = response.json()
        assert body["rules_run"] == ["required_columns"]

    async def test_an_unknown_rule_name_returns_404(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.post(
            "/api/v1/markets/ETCUSD/features/validate",
            json=validate_body({"feature": "ohlcv"}, rules=["made_up_rule"]),
        )
        assert response.status_code == 404
        assert response.json()["code"] == "validation_rule_not_found"


class TestErrorPropagation:
    async def test_returns_404_for_an_unknown_market(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/markets/NOPE/features/validate",
            json=validate_body({"feature": "ohlcv"}),
        )
        assert response.status_code == 404
