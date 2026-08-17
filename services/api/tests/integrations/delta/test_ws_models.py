"""Tests for Delta WebSocket models, parser registry, and key-auth signing.

Wire samples mirror the payloads shown in the Delta Exchange WebSocket
documentation.
"""

import hashlib
import hmac
from datetime import UTC, datetime

from app.integrations.delta.websocket import models as events
from app.integrations.delta.websocket.auth import sign_key_auth
from app.integrations.delta.websocket.parser import DeltaMessageParser


def parse(raw: str) -> events.WSEvent:
    parsed = DeltaMessageParser().parse(raw)
    assert parsed.event is not None, parsed.error
    assert parsed.error is None
    return parsed.event


def test_subscriptions_ack() -> None:
    event = parse(
        '{"type":"subscriptions","channels":'
        '[{"name":"l2_orderbook","symbols":["BTCUSD"]},'
        '{"name":"trading_notifications","error":"subscription forbidden"}]}'
    )
    assert isinstance(event, events.SubscriptionsEvent)
    assert event.channels[0].symbols == ["BTCUSD"]
    assert event.channels[1].error == "subscription forbidden"


def test_key_auth_success() -> None:
    event = parse(
        '{"type":"key-auth","success":true,"status_code":200,"status":"authenticated"}'
    )
    assert isinstance(event, events.KeyAuthEvent)
    assert event.success
    assert event.status == "authenticated"


def test_key_auth_failure() -> None:
    event = parse(
        '{"type":"key-auth","success":false,"status_code":401,'
        '"status":"invalid_signature","message":"Invalid Signature"}'
    )
    assert isinstance(event, events.KeyAuthEvent)
    assert not event.success
    assert event.status == "invalid_signature"


def test_heartbeat_and_pong() -> None:
    assert isinstance(parse('{"type":"heartbeat"}'), events.HeartbeatEvent)
    assert isinstance(parse('{"type":"pong"}'), events.PongEvent)


def test_ticker_event() -> None:
    event = parse(
        '{"d":[{"i":27,"m":"72124.53970358","m24hc":"1.5902",'
        '"ohlc":[71009.0,73135.5,70495.0,72123.5],'
        '"oi":["537395","4457821.6900"],"pb":["68495.16304969","75705.18021281"],'
        '"q":["72101","822","72100","2123",null],"s":"BTCUSD",'
        '"to":[1153493034.0710223,1153493034.0710223]}],'
        '"sp":"72154.6","sy":"BTCUSD","ts":1775801092453559,"type":"ticker"}'
    )
    assert isinstance(event, events.TickerEvent)
    assert event.sy == "BTCUSD"
    assert event.sp == events.Decimal("72154.6")
    assert event.ts == 1775801092453559
    assert event.d is not None
    assert event.d[0].m == events.Decimal("72124.53970358")
    assert event.d[0].ohlc == [
        events.Decimal("71009.0"),
        events.Decimal("73135.5"),
        events.Decimal("70495.0"),
        events.Decimal("72123.5"),
    ]


def test_order_book_l1_event() -> None:
    event = parse(
        '{"ap":"68519.0","as":"285","bp":"68518.0","bs":"2452",'
        '"lts":1775037882675402,"sy":"BTCUSD","ts":1775037882748105,"type":"ob_l1"}'
    )
    assert isinstance(event, events.OrderBookL1Event)
    assert event.ap == events.Decimal("68519.0")
    assert event.ask_size == events.Decimal("285")
    assert event.bp == events.Decimal("68518.0")
    assert event.bid_size == events.Decimal("2452")


def test_order_book_l2_event() -> None:
    event = parse(
        '{"a":[["68525.0","3313"],["68526.0","512"]],'
        '"b":[["68524.0","900"]],"sy":"ETHUSD","ts":1775801092453559,'
        '"type":"ob_l2"}'
    )
    assert isinstance(event, events.OrderBookL2Event)
    assert event.a == [
        [events.Decimal("68525.0"), events.Decimal("3313")],
        [events.Decimal("68526.0"), events.Decimal("512")],
    ]
    assert event.b == [[events.Decimal("68524.0"), events.Decimal("900")]]


def test_trades_event() -> None:
    event = parse(
        '{"p":"72141.5","r":"m","s":1.0,"sy":"BTCUSD","t":1775800366578410,'
        '"ts":1775800367003029,"type":"trades"}'
    )
    assert isinstance(event, events.TradesEvent)
    assert event.p == events.Decimal("72141.5")
    assert event.r == "m"
    assert event.s == events.Decimal("1.0")
    assert event.t == 1775800366578410


def test_mark_price_event() -> None:
    event = parse(
        '{"p":"2296.3486551","sy":"MARK:C-BTC-69500-100426",'
        '"ts":1775814170680883,"type":"mark_price"}'
    )
    assert isinstance(event, events.MarkPriceEvent)
    assert event.sy == "MARK:C-BTC-69500-100426"
    assert event.p == events.Decimal("2296.3486551")


def test_candlestick_event() -> None:
    event = parse(
        '{"c":71748.0,"h":71751.5,"l":71737.0,"o":71737.0,"res":"1m",'
        '"sy":"BTCUSD","ts":1775814834503627,"type":"candlestick_1m","v":2826.0}'
    )
    assert isinstance(event, events.CandlestickEvent)
    assert event.res == "1m"
    assert event.sy == "BTCUSD"
    assert event.v == events.Decimal("2826.0")
    assert event.o == events.Decimal("71737.0")
    assert event.low == events.Decimal("71737.0")


def test_candlestick_event_without_volume() -> None:
    event = parse(
        '{"c":71748.0,"h":71751.5,"l":71737.0,"o":71737.0,"res":"1m",'
        '"sy":"MARK:BTCUSD","ts":1775814834503627,"type":"candlestick_1m"}'
    )
    assert isinstance(event, events.CandlestickEvent)
    assert event.v is None


def test_spot_price_event() -> None:
    event = parse(
        '{"p":"1","sy":".DEUSDTUSD","ts":1775818505952018,"type":"spot_price"}'
    )
    assert isinstance(event, events.SpotPriceEvent)
    assert event.p == events.Decimal("1")


def test_order_book_updates_snapshot_event() -> None:
    event = parse(
        '{"action":"snapshot","a":[["16919.0","1087"],["16919.5","1193"]],'
        '"b":[["16918.0","602"]],"ts":1671140718980723,"seq":6199,'
        '"sy":"BTCUSD","type":"ob_updates","cs":2178756498}'
    )
    assert isinstance(event, events.OrderBookUpdatesEvent)
    assert event.action == "snapshot"
    assert event.seq == 6199
    assert event.sy == "BTCUSD"


def test_spot_twap_price_event() -> None:
    event = parse(
        '{"symbol":".DEXBTUSD","price":"0.0014579",'
        '"type":"spot_30mtwap_price","timestamp":1561634049751430}'
    )
    assert isinstance(event, events.SpotTwapPriceEvent)
    assert event.symbol == ".DEXBTUSD"
    assert event.price == events.Decimal("0.0014579")
    assert event.timestamp == 1561634049751430


def test_funding_rate_event() -> None:
    event = parse(
        '{"fi":28800,"fr":0.010000000000000002,"nfr":1775836800000000,'
        '"sy":"BTCUSD","ts":1775817617666383,"type":"funding_rate"}'
    )
    assert isinstance(event, events.FundingRateEvent)
    assert event.fr == events.Decimal("0.010000000000000002")
    assert event.nfr == 1775836800000000


def test_product_updates_event() -> None:
    event = parse(
        '{"type":"product_updates","event":"market_disruption",'
        '"product":{"id":17,"symbol":"NEOUSDQ","trading_status":"disrupted_cancel_only"},'
        '"timestamp":1561634049751430}'
    )
    assert isinstance(event, events.ProductUpdatesEvent)
    assert event.event == "market_disruption"
    assert event.product is not None
    assert event.product.symbol == "NEOUSDQ"
    assert event.product.trading_status == "disrupted_cancel_only"


def test_system_status_event() -> None:
    event = parse(
        '{"type":"system_status","status":"live","event":"maintenance_scheduled",'
        '"maintenance_start_time":1765259125000000,"timestamp":1765239292000000}'
    )
    assert isinstance(event, events.SystemStatusEvent)
    assert event.status == "live"
    assert event.maintenance_start_time == 1765259125000000


def test_positions_update_event() -> None:
    event = parse(
        '{"type":"positions","action":"update","reason":"auto_topup",'
        '"symbol":"BTCUSD","product_id":1,"size":-100,"margin":"0.0121",'
        '"entry_price":"3500.0","liquidation_price":"3356.0",'
        '"bankruptcy_price":"3300.0","commission":"0.00001212"}'
    )
    assert isinstance(event, events.PositionsEvent)
    assert event.action == "update"
    assert event.size == -100
    assert event.entry_price == events.Decimal("3500.0")


def test_positions_snapshot_event() -> None:
    event = parse(
        '{"result":[{"adl_level":"4.3335","auto_topup":false,'
        '"bankruptcy_price":"261.82","commission":"17.6571408",'
        '"created_at":"2021-04-29T07:25:59Z","entry_price":"238.02",'
        '"liquidation_price":"260.63","margin":"4012.99","product_id":357,'
        '"product_symbol":"ZECUSD","size":-1686,"symbol":"ZECUSD","user_id":1}],'
        '"success":true,"type":"positions","action":"snapshot"}'
    )
    assert isinstance(event, events.PositionsEvent)
    assert event.action == "snapshot"
    assert event.result is not None
    assert event.result[0].product_symbol == "ZECUSD"


def test_orders_event() -> None:
    event = parse(
        '{"type":"orders","action":"create","reason":"","symbol":"BTCUSD",'
        '"product_id":27,"order_id":1234,"size":100,"unfilled_size":55,'
        '"average_fill_price":"8999.00","limit_price":"9000.00","side":"buy",'
        '"state":"open","seq_no":1,"timestamp":1594105083998848}'
    )
    assert isinstance(event, events.OrdersEvent)
    assert event.action == "create"
    assert event.order_id == 1234
    assert event.side == "buy"
    assert event.limit_price == events.Decimal("9000.00")


def test_unknown_delta_type_becomes_unknown_event() -> None:
    parsed = DeltaMessageParser().parse('{"type":"brand_new_channel","x":1}')
    assert parsed.event is not None
    assert parsed.event.type == "brand_new_channel"


def test_utc_from_micros() -> None:
    expected = datetime(2026, 4, 10, 6, 4, 52, 453559, tzinfo=UTC)
    assert events.utc_from_micros(1775801092453559) == expected


def test_sign_key_auth_matches_independent_hmac() -> None:
    secret = "test-secret"
    timestamp = "1775801092"
    expected = hmac.new(
        secret.encode(),
        f"GET{timestamp}/live".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert sign_key_auth(secret, timestamp) == expected


def test_sign_key_auth_uses_live_path() -> None:
    secret = "s"
    ts = "1"
    assert sign_key_auth(secret, ts) != hmac.new(
        secret.encode(), f"GET{ts}/".encode(), hashlib.sha256
    ).hexdigest()
