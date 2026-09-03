"""Reusable assertion helpers for API and service tests."""

import httpx


def assert_domain_error(response: httpx.Response, code: str, status_code: int = 400) -> None:
    """Assert a domain error response with a stable error code."""
    assert response.status_code == status_code
    body = response.json()
    assert body["code"] == code
    assert "detail" in body or "message" in body


def assert_pagination(
    body: dict,
    *,
    total: int,
    returned: int,
    has_more: bool,
    limit: int | None = None,
    offset: int = 0,
) -> None:
    """Assert the canonical pagination envelope."""
    pagination = body["pagination"]
    assert pagination["total"] == total
    assert pagination["returned"] == returned
    assert pagination["has_more"] is has_more
    assert pagination["offset"] == offset
    if limit is not None:
        assert pagination["limit"] == limit


def assert_candle_item_shape(item: dict) -> None:
    """Assert a single serialized candle has every documented field."""
    for field in (
        "market_id",
        "timeframe",
        "open_time",
        "close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "trade_count",
        "source",
    ):
        assert field in item, f"candle item missing field {field!r}"


def assert_statistics_keys(statistics: dict) -> None:
    """Assert the candle statistics block carries every documented key."""
    for key in (
        "highest_price",
        "lowest_price",
        "highest_volume",
        "lowest_volume",
        "average_open",
        "average_close",
        "average_high",
        "average_low",
        "average_volume",
        "total_candles",
        "first_candle_at",
        "last_candle_at",
        "expected_candles",
        "missing_candles",
        "completeness",
    ):
        assert key in statistics, f"statistics missing key {key!r}"


def assert_quality_keys(quality: dict) -> None:
    """Assert the candle quality block carries every documented key."""
    for key in (
        "completeness_score",
        "freshness_score",
        "missing_interval_count",
        "missing_intervals",
        "duplicate_candles",
        "out_of_order_candles",
        "invalid_ohlc_candles",
        "gaps_detected",
        "overall_quality_score",
    ):
        assert key in quality, f"quality missing key {key!r}"


def assert_meta_keys(meta: dict) -> None:
    """Assert the query metadata block carries every documented key."""
    for key in (
        "execution_time_ms",
        "database_time_ms",
        "rows_scanned",
        "rows_returned",
        "cache_status",
        "generated_at",
    ):
        assert key in meta, f"meta missing key {key!r}"
