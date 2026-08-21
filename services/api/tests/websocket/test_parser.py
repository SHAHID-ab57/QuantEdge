"""Tests for the generic WebSocket message parser."""

import json
from typing import cast

import pytest

from app.ws.models import UnknownWSEvent, WSEvent
from app.ws.parser import MessageParser

TICKER = {"type": "ticker", "sy": "BTCUSD", "ts": 1775800367003029}


class TickerEvent(WSEvent):
    sy: str
    ts: int


class TradeEvent(WSEvent):
    p: str
    sy: str


@pytest.fixture
def parser() -> MessageParser:
    """A parser with a couple of registered models."""
    parser = MessageParser()
    parser.register("ticker", TickerEvent)
    parser.register("trade_*", TradeEvent)
    return parser


def test_parse_valid_exact_type(parser: MessageParser) -> None:
    parsed = parser.parse(json.dumps(TICKER))
    assert parsed.error is None
    event = cast(TickerEvent, parsed.event)
    assert event.type == "ticker"
    assert event.sy == "BTCUSD"
    assert event.ts == 1775800367003029
    assert event.received_at is not None


def test_parse_valid_pattern_type(parser: MessageParser) -> None:
    parsed = parser.parse(json.dumps({"type": "trade_1m", "p": "1.5", "sy": "ETHUSD"}))
    assert parsed.error is None
    event = cast(TradeEvent, parsed.event)
    assert event.type == "trade_1m"
    assert event.p == "1.5"


def test_parse_invalid_json(parser: MessageParser) -> None:
    parsed = parser.parse("{not json")
    assert parsed.event is None
    assert parsed.error is not None
    assert "invalid JSON" in parsed.error


def test_parse_non_object_json(parser: MessageParser) -> None:
    parsed = parser.parse("[1, 2, 3]")
    assert parsed.event is None
    assert parsed.error == "message is not a JSON object"


def test_parse_missing_type(parser: MessageParser) -> None:
    parsed = parser.parse(json.dumps({"sy": "BTCUSD"}))
    assert parsed.event is None
    assert parsed.error == "message has no string 'type' field"


def test_parse_non_string_type(parser: MessageParser) -> None:
    parsed = parser.parse(json.dumps({"type": 5}))
    assert parsed.event is None
    assert parsed.error == "message has no string 'type' field"


def test_parse_unknown_type_becomes_unknown_event(parser: MessageParser) -> None:
    parsed = parser.parse(json.dumps({"type": "future_channel", "k": "v"}))
    assert parsed.error is None
    assert isinstance(parsed.event, UnknownWSEvent)
    assert parsed.event.type == "future_channel"
    assert parsed.event.payload == {"type": "future_channel", "k": "v"}


def test_parse_validation_failure_rejected(parser: MessageParser) -> None:
    parsed = parser.parse(json.dumps({"type": "ticker", "sy": "BTCUSD"}))
    assert parsed.event is None
    assert parsed.error is not None
    assert "validation failed" in parsed.error


def test_parse_extra_fields_ignored(parser: MessageParser) -> None:
    payload = dict(TICKER)
    payload["unmodeled"] = "ignored"
    parsed = parser.parse(json.dumps(payload))
    assert parsed.error is None
    assert parsed.event is not None
    assert not hasattr(parsed.event, "unmodeled")


def test_exact_type_wins_over_pattern(parser: MessageParser) -> None:
    parsed = parser.parse(json.dumps({"type": "trade_", "p": "1.5", "sy": "ETHUSD"}))
    assert parsed.error is None
    assert parsed.event is not None