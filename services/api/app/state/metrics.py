"""Metrics for the market state manager.

Plain counters and latency aggregates (safe on a single event loop).
:meth:`StateMetrics.snapshot` is the stable contract a future Prometheus
exporter will render, so instrumentation can be added without touching
the manager code.
"""

__all__ = ["StateMetrics"]


class StateMetrics:
    """Counters and latency aggregates for one state manager instance."""

    def __init__(self) -> None:
        self.state_updates: int = 0
        self.invalid_events: int = 0
        self.symbols_tracked: int = 0
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self._latency_total_seconds: float = 0.0
        self._latency_samples: int = 0

    def record_latency(self, seconds: float) -> None:
        """Record one state update processing time in seconds."""
        self._latency_total_seconds += seconds
        self._latency_samples += 1

    @property
    def average_update_latency_ms(self) -> float | None:
        """Mean state update time in ms, or ``None`` when empty."""
        if self._latency_samples == 0:
            return None
        return self._latency_total_seconds / self._latency_samples * 1000.0

    def snapshot(self) -> dict[str, int | float | None]:
        """Immutable view for observability tooling."""
        return {
            "state_updates": self.state_updates,
            "invalid_events": self.invalid_events,
            "symbols_tracked": self.symbols_tracked,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "update_latency_samples": self._latency_samples,
            "average_update_latency_ms": self.average_update_latency_ms,
        }
