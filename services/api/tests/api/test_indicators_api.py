"""Indicator REST endpoint tests.

Runs against the real FastAPI app over ASGI with the in-memory SQLite
database, so routing, query-parameter collection, serialization, and the
shared ``AppError`` → JSON envelope are all covered end to end.
"""

import httpx


class TestCatalogueEndpoint:
    async def test_lists_registered_indicators(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/indicators")
        assert response.status_code == 200
        body = response.json()
        names = {entry["name"] for entry in body["indicators"]}
        assert {"sma", "ema", "rsi"} <= names
        assert body["total"] == len(body["indicators"])

    async def test_publishes_parameter_specs_for_form_building(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/api/v1/indicators")
        sma = next(e for e in response.json()["indicators"] if e["name"] == "sma")
        period = next(spec for spec in sma["parameters"] if spec["name"] == "period")
        assert period["type"] == "int"
        assert period["default"] == 20
        assert period["minimum"] == 1
        assert period["required"] is False

    async def test_publishes_choices_for_a_constrained_parameter(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/api/v1/indicators")
        sma = next(e for e in response.json()["indicators"] if e["name"] == "sma")
        source = next(spec for spec in sma["parameters"] if spec["name"] == "source")
        assert source["choices"] == ["open", "high", "low", "close"]

    async def test_describes_a_single_indicator(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/indicators/rsi")
        assert response.status_code == 200
        assert response.json()["category"] == "momentum"

    async def test_returns_404_for_an_unknown_indicator(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/indicators/nope")
        assert response.status_code == 404
        assert response.json()["code"] == "indicator_not_found"

    async def test_is_mounted_unversioned_too(self, client: httpx.AsyncClient) -> None:
        # Every route on this platform is served at both prefixes.
        assert (await client.get("/indicators")).status_code == 200


class TestCalculationEndpoint:
    async def test_calculates_an_indicator_over_stored_candles(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.get(
            "/api/v1/markets/ETCUSD/indicators/sma",
            params={"timeframe": "1h", "period": 2},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["symbol"] == "ETCUSD"
        assert body["series"][0]["values"] == [None, 17.5, 28.0]

    async def test_aligns_timestamps_with_the_series(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.get(
            "/api/v1/markets/ETCUSD/indicators/sma",
            params={"timeframe": "1h", "period": 2},
        )
        body = response.json()
        assert len(body["timestamps"]) == len(body["series"][0]["values"])

    async def test_serializes_timestamps_with_a_literal_z_suffix(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        # The frontend validates with z.string().datetime(), which rejects
        # a "+00:00" offset — the same bug the market-stream gateway hit.
        response = await client.get(
            "/api/v1/markets/ETCUSD/indicators/sma",
            params={"timeframe": "1h", "period": 2},
        )
        body = response.json()
        assert body["timestamps"][0].endswith("Z")
        assert body["meta"]["generated_at"].endswith("Z")

    async def test_applies_defaults_for_omitted_parameters(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.get(
            "/api/v1/markets/ETCUSD/indicators/sma",
            params={"timeframe": "1h", "period": 2},
        )
        assert response.json()["parameters"] == {"period": 2, "source": "close"}

    async def test_reports_execution_metadata(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.get(
            "/api/v1/markets/ETCUSD/indicators/sma",
            params={"timeframe": "1h", "period": 2},
        )
        meta = response.json()["meta"]
        assert meta["candles_analyzed"] == 3
        assert meta["warmup_candles"] == 2
        assert meta["cache_status"] in {"hit", "miss", "disabled"}

    async def test_honours_a_source_parameter(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        # seeded_varied highs are 12, 25, 33 → SMA(2) = [None, 18.5, 29].
        response = await client.get(
            "/api/v1/markets/ETCUSD/indicators/sma",
            params={"timeframe": "1h", "period": 2, "source": "high"},
        )
        assert response.json()["series"][0]["values"] == [None, 18.5, 29.0]


class TestCalculationErrors:
    async def test_rejects_an_out_of_range_parameter(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.get(
            "/api/v1/markets/ETCUSD/indicators/sma",
            params={"timeframe": "1h", "period": 0},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_indicator_parameter"

    async def test_rejects_an_unknown_parameter_rather_than_ignoring_it(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.get(
            "/api/v1/markets/ETCUSD/indicators/sma",
            params={"timeframe": "1h", "perid": 2},
        )
        assert response.status_code == 400
        assert "is not accepted" in response.json()["detail"]

    async def test_rejects_a_non_numeric_parameter(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.get(
            "/api/v1/markets/ETCUSD/indicators/sma",
            params={"timeframe": "1h", "period": "twenty"},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_indicator_parameter"

    async def test_reports_insufficient_data_with_the_required_count(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        # Three stored candles, default SMA period of 20.
        response = await client.get(
            "/api/v1/markets/ETCUSD/indicators/sma",
            params={"timeframe": "1h"},
        )
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == "insufficient_data"
        assert "at least 20" in body["detail"]

    async def test_returns_404_for_an_unknown_market(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.get(
            "/api/v1/markets/NOPE/indicators/sma",
            params={"timeframe": "1h", "period": 2},
        )
        assert response.status_code == 404
        assert response.json()["code"] == "market_not_found"

    async def test_returns_404_for_an_unknown_indicator(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.get(
            "/api/v1/markets/ETCUSD/indicators/macd",
            params={"timeframe": "1h"},
        )
        assert response.status_code == 404
        assert response.json()["code"] == "indicator_not_found"

    async def test_rejects_an_unsupported_timeframe(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.get(
            "/api/v1/markets/ETCUSD/indicators/sma",
            params={"timeframe": "7d", "period": 2},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_timeframe"

    async def test_returns_404_when_no_candles_are_stored_for_the_timeframe(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.get(
            "/api/v1/markets/ETCUSD/indicators/sma",
            params={"timeframe": "1d", "period": 2},
        )
        assert response.status_code == 404
        assert response.json()["code"] == "candle_not_found"

    async def test_requires_the_timeframe_query_parameter(
        self, client: httpx.AsyncClient, seeded_varied: None
    ) -> None:
        response = await client.get("/api/v1/markets/ETCUSD/indicators/sma")
        assert response.status_code == 422
