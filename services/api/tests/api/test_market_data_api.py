"""API tests for the market data endpoints.

Runs the full FastAPI stack against an in-memory SQLite database via a
dependency override for the database session. Uses the shared async
``client`` fixture (httpx over ASGI with lifespan).
"""

import httpx


async def test_list_markets(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get("/api/v1/markets")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["markets"][0]["symbol"] == "ETHUSD"
    assert body["markets"][0]["market_type"] == "perpetual"
    assert body["markets"][0]["exchange"] == "Delta Exchange"


async def test_list_markets_includes_product_metadata(
    client: httpx.AsyncClient, seeded_with_metadata: None
) -> None:
    response = await client.get("/api/v1/markets")

    assert response.status_code == 200
    market = response.json()["markets"][0]
    assert market["exchange_id"] == market["id"] or market["exchange_id"] is not None
    assert market["delta_product_id"] == 27
    assert market["delta_contract_type"] == "perpetual_futures"
    assert market["tick_size"] == "0.5"
    assert market["funding_method"] == "mark_price"
    assert market["funding_interval_seconds"] == 28800
    assert market["listing_date"] == "2023-12-18T13:10:39Z"


async def test_list_timeframes(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get("/api/v1/markets/ETHUSD/timeframes")

    assert response.status_code == 200
    assert response.json() == {"symbol": "ETHUSD", "timeframes": ["1h"]}


async def test_list_timeframes_unknown_symbol(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get("/api/v1/markets/NOPE/timeframes")

    assert response.status_code == 404
    assert response.json()["code"] == "market_not_found"


async def test_get_candles_ascending_with_pagination(
    client: httpx.AsyncClient, seeded: None
) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles",
        params={"timeframe": "1h", "limit": 2, "offset": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["open_time"] for item in body["items"]] == [
        "2026-01-01T01:00:00Z",
        "2026-01-01T02:00:00Z",
    ]
    assert body["pagination"] == {
        "total": 5,
        "returned": 2,
        "has_more": True,
        "limit": 2,
        "offset": 1,
    }
    assert body["items"][0]["open"] == "3050.5"
    assert body["items"][0]["quote_volume"] is None


async def test_get_candles_range_filter(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles",
        params={
            "timeframe": "1h",
            "start": "2026-01-01T01:00:00Z",
            "end": "2026-01-01T04:00:00Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 3
    assert body["pagination"]["has_more"] is False


async def test_get_candles_unknown_symbol(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get("/api/v1/markets/NOPE/candles", params={"timeframe": "1h"})

    assert response.status_code == 404
    assert response.json()["code"] == "market_not_found"


async def test_get_candles_invalid_timeframe(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get("/api/v1/markets/ETHUSD/candles", params={"timeframe": "7d"})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_timeframe"


async def test_get_candles_reversed_range(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles",
        params={
            "timeframe": "1h",
            "start": "2026-01-01T04:00:00Z",
            "end": "2026-01-01T01:00:00Z",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_range"


async def test_get_candles_one_sided_range(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles",
        params={"timeframe": "1h", "start": "2026-01-01T01:00:00Z"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_range"


async def test_get_candles_negative_limit_rejected(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles", params={"timeframe": "1h", "limit": -1}
    )

    assert response.status_code == 422


async def test_get_candles_limit_over_max_rejected(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles", params={"timeframe": "1h", "limit": 1001}
    )

    assert response.status_code == 422


async def test_get_candles_negative_offset_rejected(
    client: httpx.AsyncClient, seeded: None
) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles", params={"timeframe": "1h", "offset": -1}
    )

    assert response.status_code == 422


async def test_get_candles_invalid_sort(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles", params={"timeframe": "1h", "sort": "pepe"}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_sort"


async def test_get_candles_invalid_direction(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles", params={"timeframe": "1h", "dir": "sideways"}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_sort"


async def test_get_candles_sorted_by_column(client: httpx.AsyncClient, seeded_varied: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETCUSD/candles",
        params={"timeframe": "1h", "sort": "volume", "dir": "desc"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["open_time"] for item in items] == [
        "2026-01-01T02:00:00Z",
        "2026-01-01T01:00:00Z",
        "2026-01-01T00:00:00Z",
    ]
    assert [item["volume"] for item in items] == ["300", "200", "100"]


async def test_get_candles_sorted_open_time_desc(
    client: httpx.AsyncClient, seeded_varied: None
) -> None:
    response = await client.get(
        "/api/v1/markets/ETCUSD/candles",
        params={"timeframe": "1h", "sort": "open_time", "dir": "desc"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["open_time"] for item in items] == [
        "2026-01-01T02:00:00Z",
        "2026-01-01T01:00:00Z",
        "2026-01-01T00:00:00Z",
    ]


async def test_get_candles_includes_statistics(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get("/api/v1/markets/ETHUSD/candles", params={"timeframe": "1h"})

    assert response.status_code == 200
    assert response.json()["statistics"] == {
        "highest_price": "3060",
        "lowest_price": "3040",
        "highest_volume": "120.5",
        "lowest_volume": "120.5",
        "average_open": "3050.5",
        "average_close": "3055.25",
        "average_high": "3060",
        "average_low": "3040",
        "average_volume": "120.5",
        "total_candles": 5,
        "first_candle_at": "2026-01-01T00:00:00Z",
        "last_candle_at": "2026-01-01T04:00:00Z",
        "expected_candles": 5,
        "missing_candles": 0,
        "completeness": 100.0,
    }


async def test_get_candles_statistics_respect_range(
    client: httpx.AsyncClient, seeded: None
) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles",
        params={
            "timeframe": "1h",
            "start": "2026-01-01T01:00:00Z",
            "end": "2026-01-01T04:00:00Z",
        },
    )

    assert response.status_code == 200
    statistics = response.json()["statistics"]
    assert statistics["total_candles"] == 3
    assert statistics["first_candle_at"] == "2026-01-01T01:00:00Z"
    assert statistics["last_candle_at"] == "2026-01-01T03:00:00Z"
    assert statistics["expected_candles"] == 3
    assert statistics["missing_candles"] == 0
    assert statistics["completeness"] == 100.0


async def test_get_candles_quality_clean(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get("/api/v1/markets/ETHUSD/candles", params={"timeframe": "1h"})

    assert response.status_code == 200
    quality = response.json()["quality"]
    assert quality["completeness_score"] == 100.0
    assert quality["freshness_score"] == 0.0  # 2026 fixture data is older than 30 days
    assert quality["missing_interval_count"] == 0
    assert quality["missing_intervals"] == []
    assert quality["duplicate_candles"] == 0
    assert quality["out_of_order_candles"] == 0
    assert quality["invalid_ohlc_candles"] == 0
    assert quality["gaps_detected"] is False
    assert quality["overall_quality_score"] == 100.0


async def test_get_candles_quality_reports_gaps(
    client: httpx.AsyncClient, seeded_with_gap: None
) -> None:
    response = await client.get("/api/v1/markets/BTCUSD/candles", params={"timeframe": "1h"})

    assert response.status_code == 200
    quality = response.json()["quality"]
    assert quality["missing_interval_count"] == 1
    assert quality["missing_intervals"] == ["2026-01-01T03:00:00Z"]
    assert quality["gaps_detected"] is True
    assert quality["completeness_score"] == round(100.0 * 5 / 6, 1)
    assert quality["overall_quality_score"] == round(100.0 * 5 / 6, 2)


async def test_get_candles_quality_detects_issues(
    client: httpx.AsyncClient, seeded_with_issues: None
) -> None:
    response = await client.get("/api/v1/markets/SOLUSD/candles", params={"timeframe": "1h"})

    assert response.status_code == 200
    quality = response.json()["quality"]
    assert quality["invalid_ohlc_candles"] == 1
    assert quality["out_of_order_candles"] == 1
    assert quality["duplicate_candles"] == 0
    assert quality["overall_quality_score"] == 75.0
    assert response.json()["statistics"]["total_candles"] == 4


async def test_get_candles_empty_range_zeroed_analytics(
    client: httpx.AsyncClient, seeded: None
) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles",
        params={
            "timeframe": "1h",
            "start": "2026-01-02T00:00:00Z",
            "end": "2026-01-03T00:00:00Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["pagination"]["total"] == 0
    statistics = body["statistics"]
    assert statistics["total_candles"] == 0
    assert statistics["expected_candles"] == 0
    assert statistics["completeness"] is None
    assert statistics["highest_price"] is None
    quality = body["quality"]
    assert quality["completeness_score"] == 0.0
    assert quality["freshness_score"] == 0.0
    assert quality["overall_quality_score"] == 0.0
    assert quality["gaps_detected"] is False
    assert body["meta"]["rows_scanned"] == 0
    assert body["meta"]["rows_returned"] == 0


async def test_get_candles_meta_reports_execution(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles",
        params={"timeframe": "1h", "limit": 2, "offset": 1},
    )

    assert response.status_code == 200
    meta = response.json()["meta"]
    assert meta["execution_time_ms"] >= 0
    assert meta["database_time_ms"] >= 0
    assert meta["rows_scanned"] == 3
    assert meta["rows_returned"] == 2
    assert meta["cache_status"] == "disabled"
    assert meta["generated_at"].endswith("Z")


async def test_get_latest(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get("/api/v1/markets/ETHUSD/latest", params={"timeframe": "1h"})

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "ETHUSD"
    assert body["candle"]["open_time"] == "2026-01-01T04:00:00Z"


async def test_get_latest_no_candles(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get("/api/v1/markets/ETHUSD/latest", params={"timeframe": "1d"})

    assert response.status_code == 404
    assert response.json()["code"] == "candle_not_found"


async def test_get_latest_unknown_symbol(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get("/api/v1/markets/NOPE/latest", params={"timeframe": "1h"})

    assert response.status_code == 404
    assert response.json()["code"] == "market_not_found"


async def test_get_candle_stats(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles/stats",
        params={"timeframe": "1h"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "ETHUSD"
    assert body["timeframe"] == "1h"
    assert body["start"] is None
    assert body["end"] is None
    assert body["total_candles"] == 5
    assert body["highest_price"] == "3060"
    assert body["lowest_price"] == "3040"
    assert body["average_volume"] == "120.5"
    assert body["first_candle"]["open_time"] == "2026-01-01T00:00:00Z"
    assert body["last_candle"]["open_time"] == "2026-01-01T04:00:00Z"
    assert body["first_candle"]["close"] == "3055.25"


async def test_get_candle_stats_range(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles/stats",
        params={
            "timeframe": "1h",
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-01T03:00:00Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_candles"] == 3
    assert body["start"] == "2026-01-01T00:00:00Z"
    assert body["end"] == "2026-01-01T03:00:00Z"
    assert body["first_candle"]["open_time"] == "2026-01-01T00:00:00Z"
    assert body["last_candle"]["open_time"] == "2026-01-01T02:00:00Z"


async def test_get_candle_stats_no_candles(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles/stats",
        params={
            "timeframe": "1d",
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-02T00:00:00Z",
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "candle_not_found"


async def test_get_candle_stats_empty_range(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles/stats",
        params={
            "timeframe": "1h",
            "start": "2026-01-02T00:00:00Z",
            "end": "2026-01-03T00:00:00Z",
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "candle_not_found"


async def test_get_candle_stats_invalid_timeframe(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles/stats",
        params={"timeframe": "7d"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_timeframe"


async def test_get_candle_stats_invalid_range(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get(
        "/api/v1/markets/ETHUSD/candles/stats",
        params={
            "timeframe": "1h",
            "start": "2026-01-02T00:00:00Z",
            "end": "2026-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_range"


async def test_get_research_reports_coverage(client: httpx.AsyncClient, seeded: None) -> None:
    """Research metrics match the stored 1h range with no gaps."""
    response = await client.get("/api/v1/markets/ETHUSD/research")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "ETHUSD"
    assert body["total_candles"] == 5
    assert body["oldest_candle_at"] == "2026-01-01T00:00:00Z"
    assert body["newest_candle_at"] == "2026-01-01T04:00:00Z"
    assert body["coverage_days"] == 0.2
    assert len(body["timeframes"]) == 1
    entry = body["timeframes"][0]
    assert entry["timeframe"] == "1h"
    assert entry["stored_candles"] == 5
    assert entry["oldest_at"] == "2026-01-01T00:00:00Z"
    assert entry["newest_at"] == "2026-01-01T04:00:00Z"
    assert entry["expected_candles"] == 5
    assert entry["missing_candles"] == 0
    assert entry["completeness"] == 100.0
    assert entry["average_daily_candles"] == 25.0


async def test_get_research_counts_gaps(client: httpx.AsyncClient, seeded_with_gap: None) -> None:
    """Missing buckets inside the stored range are reported per timeframe."""
    response = await client.get("/api/v1/markets/BTCUSD/research")

    assert response.status_code == 200
    entry = response.json()["timeframes"][0]
    assert entry["stored_candles"] == 5
    assert entry["expected_candles"] == 6
    assert entry["missing_candles"] == 1
    assert entry["completeness"] == round(100.0 * 5 / 6, 1)
    assert entry["coverage_days"] == 0.2


async def test_get_research_unknown_symbol(client: httpx.AsyncClient, seeded: None) -> None:
    response = await client.get("/api/v1/markets/NOPE/research")

    assert response.status_code == 404
    assert response.json()["code"] == "market_not_found"


async def test_openapi_documents_endpoints_and_errors(
    client: httpx.AsyncClient,
) -> None:
    spec = (await client.get("/openapi.json")).json()
    paths = spec["paths"]
    assert "/api/v1/markets" in paths
    assert "/api/v1/markets/{symbol}/timeframes" in paths
    assert "/api/v1/markets/{symbol}/research" in paths
    assert "/api/v1/markets/{symbol}/candles" in paths
    assert "/api/v1/markets/{symbol}/candles/stats" in paths
    assert "/api/v1/markets/{symbol}/latest" in paths

    candles = paths["/api/v1/markets/{symbol}/candles"]["get"]
    param_names = [param["name"] for param in candles["parameters"]]
    assert "timeframe" in param_names
    assert "start" in param_names
    assert "end" in param_names
    assert "limit" in param_names
    assert "offset" in param_names
    assert "sort" in param_names
    assert "dir" in param_names
    assert "400" in candles["responses"]
    assert "404" in candles["responses"]
    assert candles["responses"]["400"]["content"]["application/json"]["examples"][
        "invalid_timeframe"
    ]
