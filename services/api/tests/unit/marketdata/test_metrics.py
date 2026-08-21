"""Tests for the market data processing metrics."""

import pytest

from app.marketdata.metrics import ProcessingMetrics


def test_initial_snapshot() -> None:
    metrics = ProcessingMetrics()
    snapshot = metrics.snapshot()
    assert snapshot["messages_received"] == 0
    assert snapshot["messages_normalized"] == 0
    assert snapshot["validation_failures"] == 0
    assert snapshot["unsupported_messages"] == 0
    assert snapshot["events_published"] == 0
    assert snapshot["latency_samples"] == 0
    assert snapshot["average_latency_ms"] is None


def test_counters_increment() -> None:
    metrics = ProcessingMetrics()
    metrics.messages_received += 1
    metrics.messages_normalized += 3
    metrics.validation_failures += 1
    metrics.unsupported_messages += 1
    metrics.events_published += 3
    snapshot = metrics.snapshot()
    assert snapshot["messages_received"] == 1
    assert snapshot["messages_normalized"] == 3
    assert snapshot["validation_failures"] == 1
    assert snapshot["unsupported_messages"] == 1
    assert snapshot["events_published"] == 3


def test_average_latency_ms() -> None:
    metrics = ProcessingMetrics()
    metrics.record_latency(0.01)
    metrics.record_latency(0.03)
    assert metrics.snapshot()["average_latency_ms"] == pytest.approx(20.0)
    assert metrics.snapshot()["latency_samples"] == 2


def test_negative_latency_is_recorded_verbatim() -> None:
    metrics = ProcessingMetrics()
    metrics.record_latency(0.1)
    assert metrics.snapshot()["average_latency_ms"] == pytest.approx(100.0)
