"""Track requested subscriptions and build subscribe/unsubscribe payloads.

Idempotent: ``subscribe``/``unsubscribe`` return the JSON payload to send,
or None when nothing changed. Symbol sets are tracked per channel so
partial subscribe/unsubscribe only sends the delta. A channel subscribed
without symbols covers the whole channel (the payload omits ``symbols``).
"""

import json


class SubscriptionManager:
    """Idempotent tracker of requested channel subscriptions."""

    def __init__(self) -> None:
        self._requested: dict[str, frozenset[str] | None] = {}

    @property
    def requested(self) -> dict[str, list[str] | None]:
        """Snapshot of requested subscriptions, symbols sorted."""
        return {
            name: None if symbols is None else sorted(symbols)
            for name, symbols in self._requested.items()
        }

    def subscribe(self, channel: str, symbols: list[str] | None = None) -> str | None:
        """Request a subscription; return the payload to send, or None."""
        if symbols is None:
            if channel in self._requested:
                return None
            self._requested[channel] = None
            return self._payload("subscribe", [{"name": channel}])
        if channel in self._requested and self._requested[channel] is None:
            return None
        current = self._requested.get(channel) or frozenset()
        new_symbols = frozenset(symbols) - current
        if not new_symbols:
            return None
        self._requested[channel] = current | new_symbols
        return self._payload("subscribe", [{"name": channel, "symbols": sorted(new_symbols)}])

    def unsubscribe(self, channel: str, symbols: list[str] | None = None) -> str | None:
        """Request a subscription removal; return the payload, or None."""
        if symbols is None:
            if channel not in self._requested:
                return None
            del self._requested[channel]
            return self._payload("unsubscribe", [{"name": channel}])
        if channel not in self._requested or self._requested[channel] is None:
            return None
        current = self._requested[channel] or frozenset()
        removed = frozenset(symbols) & current
        if not removed:
            return None
        remaining = current - removed
        if remaining:
            self._requested[channel] = remaining
        else:
            del self._requested[channel]
        return self._payload("unsubscribe", [{"name": channel, "symbols": sorted(removed)}])

    def resubscribe_payload(self) -> str | None:
        """Payload re-requesting every tracked subscription, or None."""
        channels = []
        for name, symbols in self._requested.items():
            entry: dict[str, object] = {"name": name}
            if symbols is not None:
                entry["symbols"] = sorted(symbols)
            channels.append(entry)
        if not channels:
            return None
        return self._payload("subscribe", channels)

    def handle_ack(self, channels: list[dict[str, object]]) -> list[str]:
        """Extract per-channel error strings from a ``subscriptions`` ack."""
        errors = []
        for entry in channels:
            name = entry.get("name")
            error = entry.get("error")
            if isinstance(name, str) and isinstance(error, str):
                errors.append(f"{name}: {error}")
        return errors

    @staticmethod
    def _payload(message_type: str, channels: list[dict[str, object]]) -> str:
        """Serialize a subscribe/unsubscribe message body."""
        return json.dumps(
            {"type": message_type, "payload": {"channels": channels}},
            separators=(",", ":"),
        )
