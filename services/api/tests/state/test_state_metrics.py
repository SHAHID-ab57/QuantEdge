"""Tests for the market state metrics."""

import pytest

from app.state.metrics import StateMetrics


def test_initial_snapshot() -> None:
    metrics = StateMetrics()
    snapshot = metrics.snapshot()
    assert snapshot["state_updates"] == 0
    assert snapshot["invalid_events"] == 0
    assert snapshot["symbols_tracked"] == 0
    assert snapshot["cache_hits"] == 0
    assert snapshot["cache_misses"] == 0
    assert snapshot["update_latency_samples"] == 0
    assert snapshot["average_update_latency_ms"] is None


def test_counters_increment() -> None:
    metrics = StateMetrics()
    metrics.state_updates += 10
    metrics.invalid_events += 2
    metrics.symbols_tracked += 4
    metrics.cache_hits += 7
    metrics.cache_misses += 3
    snapshot = metrics.snapshot()
    assert snapshot["state_updates"] == 10
    assert snapshot["invalid_events"] == 2
    assert snapshot["symbols_tracked"] == 4
    assert snapshot["cache_hits"] == 7
    assert snapshot["cache_misses"] == 3


def test_average_update_latency_ms() -> None:
    metrics = StateMetrics()
    metrics.record_latency(0.005)
    metrics.record_latency(0.015)
    snapshot = metrics.snapshot()
    assert snapshot["update_latency_samples"] == 2
    assert snapshot["average_update_latency_ms"] == pytest.approx(10.0)


def test_latency_is_none_without_samples() -> None:
    metrics = StateMetrics()
    assert metrics.snapshot()["average_update_latency_ms"] is None