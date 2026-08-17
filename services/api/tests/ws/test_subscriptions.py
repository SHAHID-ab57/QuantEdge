"""Tests for the subscription tracker and payload builder."""

import json

from app.ws.subscriptions import SubscriptionManager


def subscribe_payload(name: str, symbols: list[str] | None = None) -> str:
    channel: dict[str, object] = {"name": name}
    if symbols is not None:
        channel["symbols"] = symbols
    return json.dumps(
        {"type": "subscribe", "payload": {"channels": [channel]}},
        separators=(",", ":"),
    )


def unsubscribe_payload(name: str, symbols: list[str] | None = None) -> str:
    channel: dict[str, object] = {"name": name}
    if symbols is not None:
        channel["symbols"] = symbols
    return json.dumps(
        {"type": "unsubscribe", "payload": {"channels": [channel]}},
        separators=(",", ":"),
    )


def test_subscribe_whole_channel() -> None:
    manager = SubscriptionManager()
    assert manager.subscribe("funding_rate") == subscribe_payload("funding_rate")


def test_subscribe_with_symbols() -> None:
    manager = SubscriptionManager()
    payload = manager.subscribe("ticker", ["BTCUSD", "ETHUSD"])
    assert payload == subscribe_payload("ticker", ["BTCUSD", "ETHUSD"])


def test_subscribe_idempotent() -> None:
    manager = SubscriptionManager()
    assert manager.subscribe("ticker", ["BTCUSD"]) is not None
    assert manager.subscribe("ticker", ["BTCUSD"]) is None
    assert manager.subscribe("funding_rate") is not None
    assert manager.subscribe("funding_rate") is None


def test_subscribe_partial_delta() -> None:
    manager = SubscriptionManager()
    manager.subscribe("ticker", ["BTCUSD", "ETHUSD"])
    payload = manager.subscribe("ticker", ["ETHUSD", "SOLUSD"])
    assert payload == subscribe_payload("ticker", ["SOLUSD"])


def test_subscribe_symbols_after_whole_channel_is_noop() -> None:
    manager = SubscriptionManager()
    manager.subscribe("ticker")
    assert manager.subscribe("ticker", ["BTCUSD"]) is None


def test_unsubscribe_symbols_sends_only_removed() -> None:
    manager = SubscriptionManager()
    manager.subscribe("ticker", ["BTCUSD", "ETHUSD"])
    payload = manager.unsubscribe("ticker", ["ETHUSD", "SOLUSD"])
    assert payload == unsubscribe_payload("ticker", ["ETHUSD"])
    assert manager.requested == {"ticker": ["BTCUSD"]}


def test_unsubscribe_last_symbol_removes_channel() -> None:
    manager = SubscriptionManager()
    manager.subscribe("ticker", ["BTCUSD"])
    payload = manager.unsubscribe("ticker", ["BTCUSD"])
    assert payload == unsubscribe_payload("ticker", ["BTCUSD"])
    assert manager.requested == {}


def test_unsubscribe_whole_channel() -> None:
    manager = SubscriptionManager()
    manager.subscribe("ticker", ["BTCUSD"])
    payload = manager.unsubscribe("ticker")
    assert payload == unsubscribe_payload("ticker")
    assert manager.requested == {}


def test_unsubscribe_idempotent() -> None:
    manager = SubscriptionManager()
    assert manager.unsubscribe("ticker") is None
    manager.subscribe("ticker", ["BTCUSD"])
    assert manager.unsubscribe("ticker", ["ETHUSD"]) is None


def test_resubscribe_payload() -> None:
    manager = SubscriptionManager()
    manager.subscribe("ticker", ["ETHUSD", "BTCUSD"])
    manager.subscribe("funding_rate")
    raw_payload = manager.resubscribe_payload()
    assert raw_payload is not None
    payload = json.loads(raw_payload)
    assert payload["type"] == "subscribe"
    channels = payload["payload"]["channels"]
    assert channels == [
        {"name": "ticker", "symbols": ["BTCUSD", "ETHUSD"]},
        {"name": "funding_rate"},
    ]


def test_resubscribe_payload_empty() -> None:
    assert SubscriptionManager().resubscribe_payload() is None


def test_handle_ack_returns_errors() -> None:
    manager = SubscriptionManager()
    errors = manager.handle_ack(
        [
            {"name": "l2_orderbook", "symbols": ["BTCUSD"]},
            {"name": "trading_notifications", "error": "subscription forbidden"},
        ]
    )
    assert errors == ["trading_notifications: subscription forbidden"]


def test_handle_ack_ignores_non_error_entries() -> None:
    manager = SubscriptionManager()
    assert manager.handle_ack([{"name": "ticker"}]) == []
