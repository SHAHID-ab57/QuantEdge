"""Structured logging: every line is genuinely parseable JSON.

These tests parse the real handler's output with `json.loads`, line by
line. "Looks structured" is not the bar; a log aggregator either parses a
line or it doesn't.
"""

import io
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from asgi_lifespan import LifespanManager

from app.application import create_app
from app.core.logging import configure_logging
from app.monitoring.json_logging import JsonFormatter


def _lines(stream: io.StringIO) -> list[dict]:
    raw = [line for line in stream.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in raw]  # raises if any line is not JSON


class TestJsonFormatter:
    def _format(self, **kwargs) -> dict:
        record = logging.LogRecord(
            name="app.test",
            level=kwargs.pop("level", logging.INFO),
            pathname=__file__,
            lineno=1,
            msg=kwargs.pop("msg", "hello %s"),
            args=kwargs.pop("args", ("world",)),
            exc_info=kwargs.pop("exc_info", None),
        )
        for key, value in kwargs.items():
            setattr(record, key, value)
        return json.loads(JsonFormatter().format(record))

    def test_core_fields(self) -> None:
        payload = self._format()
        assert payload["level"] == "INFO"
        assert payload["logger"] == "app.test"
        assert payload["message"] == "hello world"
        # A real, timezone-aware ISO-8601 timestamp, not just a string.
        parsed = datetime.fromisoformat(payload["timestamp"])
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == UTC.utcoffset(None)

    def test_a_multiline_message_is_still_one_line_of_valid_json(self) -> None:
        line = JsonFormatter().format(
            logging.LogRecord("app.test", logging.INFO, __file__, 1, "a\nb\r\nc", (), None)
        )
        assert "\n" not in line
        assert json.loads(line)["message"] == "a\nb\r\nc"

    def test_extra_fields_become_top_level_keys(self) -> None:
        payload = self._format(connector="fear_greed", attempts=3)
        assert payload["connector"] == "fear_greed"
        assert payload["attempts"] == 3

    def test_extra_values_json_cannot_encode_do_not_break_logging(self) -> None:
        payload = self._format(when=datetime(2026, 1, 2, tzinfo=UTC), amount=Decimal("1.50"))
        assert payload["when"].startswith("2026-01-02")
        assert payload["amount"] == "1.50"

    def test_an_extra_key_cannot_overwrite_a_reserved_field(self) -> None:
        payload = self._format(timestamp="spoofed", logger="spoofed", exception="spoofed")
        assert payload["timestamp"] != "spoofed"
        assert payload["logger"] == "app.test"
        assert "exception" not in payload

    def test_an_exception_traceback_is_included_as_a_string(self) -> None:
        try:
            raise ValueError("bad value")
        except ValueError:
            import sys

            payload = self._format(level=logging.ERROR, exc_info=sys.exc_info())
        assert "Traceback (most recent call last)" in payload["exception"]
        assert "ValueError: bad value" in payload["exception"]

    def test_non_ascii_survives(self) -> None:
        payload = self._format(msg="prix: %s", args=("€ 42 — ok",))
        assert payload["message"] == "prix: € 42 — ok"


class TestConfiguredHandler:
    def test_every_line_parses_including_uvicorn_loggers(self, json_logs: io.StringIO) -> None:
        """uvicorn brings its own plain-text handlers; left alone they would
        interleave non-JSON lines with the app's JSON lines."""
        logging.getLogger("app.something").info("app line")
        logging.getLogger("uvicorn.error").info("Started server process [1]")
        logging.getLogger("uvicorn.access").info('127.0.0.1:1 - "GET /x HTTP/1.1" 200')

        lines = _lines(json_logs)
        assert [line["logger"] for line in lines] == [
            "app.something",
            "uvicorn.error",
            "uvicorn.access",
        ]
        assert "GET /x" in lines[2]["message"]

    def test_text_format_is_the_opt_in_and_is_not_json(self) -> None:
        stream = io.StringIO()
        handler = configure_logging(level="INFO", log_format="text", stream=stream)
        try:
            logging.getLogger("app.text").info("plain")
        finally:
            logging.getLogger().removeHandler(handler)
        with pytest.raises(json.JSONDecodeError):
            json.loads(stream.getvalue())
        assert "INFO [app.text] plain" in stream.getvalue()

    def test_reconfiguring_replaces_rather_than_duplicates_the_handler(self) -> None:
        first = io.StringIO()
        second = io.StringIO()
        configure_logging(level="INFO", log_format="json", stream=first)
        handler = configure_logging(level="INFO", log_format="json", stream=second)
        try:
            logging.getLogger("app.once").info("only once")
        finally:
            logging.getLogger().removeHandler(handler)
        assert first.getvalue() == ""
        assert len(_lines(second)) == 1

    def test_httpx_request_logging_stays_silenced(self, json_logs: io.StringIO) -> None:
        """httpx logs full URLs at INFO, and connectors put API keys in the
        query string — this protection must survive the logging rewrite."""
        logging.getLogger("httpx").info('HTTP Request: GET https://x/y?apikey=SECRET "200"')
        assert "SECRET" not in json_logs.getvalue()


class TestRequestContextInLogs:
    async def test_log_lines_from_inside_a_request_carry_request_id_path_and_method(
        self, json_logs: io.StringIO
    ) -> None:
        app = create_app()

        @app.get("/logs-ctx")
        async def logs_ctx() -> dict[str, bool]:
            logging.getLogger("app.route").info("inside the handler")
            return {"ok": True}

        async with LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
                await client.get("/logs-ctx")
                await client.get("/logs-ctx")

        handler_lines = [line for line in _lines(json_logs) if line["logger"] == "app.route"]
        assert len(handler_lines) == 2
        first, second = handler_lines
        assert first["path"] == "/logs-ctx"
        assert first["method"] == "GET"
        assert len(first["request_id"]) == 32
        # Each request gets its own id; one request's id never leaks to the next.
        assert first["request_id"] != second["request_id"]
        assert "user_id" not in first  # unauthenticated route

    async def test_context_does_not_leak_into_logs_outside_a_request(
        self, json_logs: io.StringIO
    ) -> None:
        app = create_app()
        async with LifespanManager(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
                await client.get("/api/v1/health")
        logging.getLogger("app.after").info("after the request")
        after = [line for line in _lines(json_logs) if line["logger"] == "app.after"][0]
        assert "request_id" not in after
        assert "path" not in after
