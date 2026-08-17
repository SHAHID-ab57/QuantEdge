"""Configuration for the generic WebSocket connection machinery.

Timeouts follow the Delta Exchange recommendations (heartbeat every 30
seconds with a 35 second client timer, pings every 30 seconds with a 5
second pong timeout) but apply to any protocol.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WebSocketSettings:
    """Immutable, validated configuration for a WebSocket connection."""

    url: str
    reconnect_delay: float = 2.0
    max_retries: int = 0
    heartbeat_timeout: float = 35.0
    ping_interval: float = 30.0
    pong_timeout: float = 5.0
    connect_timeout: float = 10.0
    close_timeout: float = 5.0
    max_backoff: float = 60.0

    def __post_init__(self) -> None:
        """Fail fast on inconsistent or unusable values."""
        if self.reconnect_delay <= 0:
            raise ValueError("reconnect_delay must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0 (0 = unlimited)")
        if self.heartbeat_timeout <= 0:
            raise ValueError("heartbeat_timeout must be positive")
        if self.ping_interval <= 0:
            raise ValueError("ping_interval must be positive")
        if self.pong_timeout <= 0:
            raise ValueError("pong_timeout must be positive")
        if self.connect_timeout <= 0:
            raise ValueError("connect_timeout must be positive")
        if self.close_timeout <= 0:
            raise ValueError("close_timeout must be positive")
        if self.max_backoff <= 0:
            raise ValueError("max_backoff must be positive")
