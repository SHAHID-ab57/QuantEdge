"""Processing metrics for the market data pipeline.

Plain counters (safe on a single event loop) plus processing latency
tracking. :meth:`ProcessingMetrics.snapshot` is the stable contract a
future Prometheus exporter (or a ``/metrics`` endpoint) will render, so
adding instrumentation later must not change the pipeline code.
"""

__all__ = ["ProcessingMetrics"]


class ProcessingMetrics:
    """Counters and latency aggregates for one pipeline instance."""

    def __init__(self) -> None:
        self.messages_received: int = 0
        self.messages_normalized: int = 0
        self.validation_failures: int = 0
        self.unsupported_messages: int = 0
        self.events_published: int = 0
        self._latency_total_seconds: float = 0.0
        self._latency_samples: int = 0

    def record_latency(self, seconds: float) -> None:
        """Record one pipeline processing time in seconds."""
        self._latency_total_seconds += seconds
        self._latency_samples += 1

    @property
    def average_latency_ms(self) -> float | None:
        """Mean pipeline processing time in ms, or ``None`` when empty."""
        if self._latency_samples == 0:
            return None
        return self._latency_total_seconds / self._latency_samples * 1000.0

    def snapshot(self) -> dict[str, int | float | None]:
        """Immutable view for observability tooling."""
        return {
            "messages_received": self.messages_received,
            "messages_normalized": self.messages_normalized,
            "validation_failures": self.validation_failures,
            "unsupported_messages": self.unsupported_messages,
            "events_published": self.events_published,
            "latency_samples": self._latency_samples,
            "average_latency_ms": self.average_latency_ms,
        }
