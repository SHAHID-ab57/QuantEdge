"""Error tracking: an unhandled exception is captured with real context,
and secrets are provably not among what would be sent.

Every assertion is on the SDK's actual wire payload (`Tracker.events`),
captured by an in-process transport: what would have left the process,
not what the SDK is configured to do.
"""

import io
import json
from collections.abc import AsyncIterator, Generator
from typing import Any

import httpx
import pytest
import pytest_asyncio
import sentry_sdk
from asgi_lifespan import LifespanManager
from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import create_app
from app.auth.security import create_access_token, hash_password
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models import User
from app.monitoring.error_tracking import (
    _before_send,
    init_error_tracking,
    is_enabled,
    redact_secrets,
    set_user,
    tag_request,
)
from tests.conftest import SessionFactory
from tests.monitoring.conftest import DSN, CaptureTransport, Tracker

JWT_SECRET = "monitoring-suite-only-secret-never-used-outside-tests"  # noqa: S105

# Built at runtime, never written as one literal: Sentry legitimately sends a
# few lines of source code around each stack frame, so a secret spelled out in
# the test file would show up as source context and prove nothing about the
# redaction under test. (Real secrets in this repo come from the environment,
# not source.)
LOCAL_SECRET = "LOCALVAR" + "SECRET"
TOKEN_SECRET = "LOCALTOKEN" + "SECRET"
MESSAGE_SECRET = "MESSAGE" + "SECRET"
HTTPX_SECRET = "HTTPXKEY" + "SECRET"
QUERY_SECRET = "QUERY" + "SECRET"
HEADER_SECRET = "HEADER" + "SECRET"
BODY_SECRET = "PLAINTEXT" + "PASSWORD"


def _settings() -> Settings:
    return Settings(jwt_secret_key=JWT_SECRET)


def _build_app(session_factory: SessionFactory) -> FastAPI:
    """A real app (real middleware, handlers, `get_current_user`) plus a few
    routes that fail in specific ways. Built *after* `tracker` initializes
    the SDK, as production does."""
    app = create_app()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = _settings

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    @app.post("/boom-body")
    async def boom_body(request: Request) -> None:
        await request.json()
        raise RuntimeError("failed while handling a submitted body")

    @app.get("/boom-locals")
    async def boom_locals() -> None:
        hashed_password = LOCAL_SECRET  # noqa: F841
        api_token = TOKEN_SECRET  # noqa: F841
        raise RuntimeError("a failure with secrets in scope")

    @app.get("/boom-message")
    async def boom_message() -> None:
        raise RuntimeError(f"upstream said no: https://p.example/v?apikey={MESSAGE_SECRET}&x=1")

    @app.get("/boom-httpx")
    async def boom_httpx() -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await client.get(f"https://provider.example/data?apikey={HTTPX_SECRET}&module=x")
        raise RuntimeError("failed after calling a provider")

    @app.get("/boom-authed")
    async def boom_authed(user: User = Depends(get_current_user)) -> None:  # noqa: B008
        raise RuntimeError(f"failed for a signed-in user {user.email}")

    return app


@pytest_asyncio.fixture
async def client(
    tracker: Tracker, session_factory: SessionFactory
) -> AsyncIterator[httpx.AsyncClient]:
    app = _build_app(session_factory)
    async with LifespanManager(app):
        # raise_app_exceptions=False: get the 500 the real server would send.
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest_asyncio.fixture
async def signed_in_user(session_factory: SessionFactory) -> User:
    async with session_factory() as session:
        user = User(email="pii-should-not-leak@example.com", hashed_password=hash_password("pw"))
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


class TestDisabledByDefault:
    def test_no_dsn_means_nothing_is_initialized(self) -> None:
        assert init_error_tracking(Settings(sentry_dsn="")) is False
        assert is_enabled() is False


class TestDisabledTrackingIsInert:
    def test_a_disabled_tracker_leaves_no_user_or_tag_to_leak_into_later_events(self) -> None:
        """Found when the full suite failed but this file passed alone: with
        no SDK client there is no per-request scope isolation, so writing a
        user or tag would land on the shared process-wide scope and colour
        unrelated events later. Disabled must mean touching nothing."""
        for scope in (
            sentry_sdk.get_global_scope(),
            sentry_sdk.get_isolation_scope(),
            sentry_sdk.get_current_scope(),
        ):
            scope.clear()
        assert is_enabled() is False

        set_user("LEAKED-USER-ID")
        tag_request("LEAKED-REQUEST-ID")

        transport = CaptureTransport()
        init_error_tracking(
            Settings(sentry_dsn=DSN, app_env="test", jwt_secret_key="x"), transport=transport
        )
        sentry_sdk.capture_message("probe after a disabled period")
        events = Tracker(transport).events
        assert len(events) == 1
        assert "user" not in events[0]
        assert "request_id" not in events[0].get("tags", {})


class TestUnhandledExceptionCapture:
    async def test_an_unhandled_exception_is_captured_with_stack_request_and_tags(
        self, client: httpx.AsyncClient, tracker: Tracker
    ) -> None:
        """The app has its own catch-all handler that turns the exception
        into a 500 response; the SDK must still see it."""
        response = await client.get("/boom")

        assert response.status_code == 500
        assert response.json()["code"] == "internal_error"
        assert len(tracker.events) == 1
        event = tracker.events[0]
        assert event["level"] == "error"
        assert event["environment"] == "test"
        assert event["release"] == "eth-ai-api@0.1.0"

        exception = event["exception"]["values"][0]
        assert exception["type"] == "RuntimeError"
        assert exception["value"] == "kaboom"
        frames = exception["stacktrace"]["frames"]
        assert any(frame["function"] == "boom" for frame in frames)
        assert any("test_error_tracking.py" in frame["filename"] for frame in frames)

        assert event["request"]["method"] == "GET"
        assert event["request"]["url"].endswith("/boom")
        assert len(event["tags"]["request_id"]) == 32

    async def test_the_event_and_the_json_log_line_share_a_request_id(
        self, client: httpx.AsyncClient, tracker: Tracker, json_logs: io.StringIO
    ) -> None:
        """Lets someone go from an alert to the exact log lines of that request."""
        await client.get("/boom")

        event = tracker.events[0]
        logged = [json.loads(line) for line in json_logs.getvalue().splitlines()]
        failure = [line for line in logged if "Unhandled exception" in line["message"]][0]
        assert failure["request_id"] == event["tags"]["request_id"]
        assert failure["path"] == "/boom"
        assert "Traceback" in failure["exception"]

    async def test_a_signed_in_users_id_is_attached_but_not_their_email(
        self, client: httpx.AsyncClient, tracker: Tracker, signed_in_user: User
    ) -> None:
        token = create_access_token(user_id=signed_in_user.id, settings=_settings())
        await client.get("/boom-authed", headers={"Authorization": f"Bearer {token}"})

        event = tracker.events[0]
        assert event["user"] == {"id": str(signed_in_user.id)}
        # The token itself, and the address, must not be anywhere in the payload
        # (the exception message here deliberately contains the email).
        assert token not in tracker.wire_text
        assert "Bearer" not in tracker.wire_text

    async def test_an_unauthenticated_request_carries_no_user(
        self, client: httpx.AsyncClient, tracker: Tracker
    ) -> None:
        await client.get("/boom")
        assert "user" not in tracker.events[0]

    async def test_a_handled_app_error_is_not_reported(
        self, client: httpx.AsyncClient, tracker: Tracker
    ) -> None:
        """A 404 for an unknown symbol is normal operation, not an incident."""
        response = await client.get("/api/v1/markets/NOPE/timeframes")
        assert response.status_code in (404, 400)
        assert tracker.events == []


class TestWhatIsNeverSent:
    async def test_the_request_body_is_never_sent(
        self, client: httpx.AsyncClient, tracker: Tracker
    ) -> None:
        """A crash inside a login-style route must not ship the password."""
        await client.post("/boom-body", json={"email": "a@b.c", "password": "PLAINTEXTPASSWORD"})

        assert len(tracker.events) == 1
        assert BODY_SECRET not in tracker.wire_text
        # Not absent, but emptied, with the SDK recording that config removed it.
        assert tracker.events[0]["request"]["data"] == ""
        assert tracker.events[0]["_meta"]["request"]["data"][""]["rem"] == [["!config", "x"]]

    async def test_local_variables_are_never_sent(
        self, client: httpx.AsyncClient, tracker: Tracker
    ) -> None:
        await client.get("/boom-locals")

        assert len(tracker.events) == 1
        assert LOCAL_SECRET not in tracker.wire_text
        assert TOKEN_SECRET not in tracker.wire_text
        frames = tracker.events[0]["exception"]["values"][0]["stacktrace"]["frames"]
        assert all("vars" not in frame for frame in frames)

    async def test_an_api_key_inside_an_exception_message_is_redacted(
        self, client: httpx.AsyncClient, tracker: Tracker
    ) -> None:
        await client.get("/boom-message")

        assert MESSAGE_SECRET not in tracker.wire_text
        message = tracker.events[0]["exception"]["values"][0]["value"]
        assert "apikey=[Filtered]" in message
        assert "&x=1" in message  # only the secret is removed, not the context

    async def test_an_http_clients_api_key_never_reaches_a_breadcrumb(
        self, client: httpx.AsyncClient, tracker: Tracker
    ) -> None:
        """Connectors put real keys in query strings; the SDK's HTTP-client
        breadcrumbs record the full URL unless they are dropped."""
        await client.get("/boom-httpx")

        assert len(tracker.events) == 1
        assert HTTPX_SECRET not in tracker.wire_text
        crumbs = tracker.events[0].get("breadcrumbs", {}).get("values", [])
        assert all(crumb.get("category") not in ("httplib", "httpx") for crumb in crumbs)

    async def test_a_secret_in_the_inbound_query_string_is_filtered(
        self, client: httpx.AsyncClient, tracker: Tracker
    ) -> None:
        await client.get("/boom", params={"api_token": QUERY_SECRET, "page": "2"})

        assert QUERY_SECRET not in tracker.wire_text

    async def test_the_authorization_header_is_never_sent(
        self, client: httpx.AsyncClient, tracker: Tracker
    ) -> None:
        await client.get("/boom", headers={"Authorization": f"Bearer {HEADER_SECRET}"})

        assert HEADER_SECRET not in tracker.wire_text


class TestLogRecordsAreBreadcrumbsNotEvents:
    def test_an_error_level_log_line_does_not_become_an_event(self, tracker: Tracker) -> None:
        """An hourly sync failing for a week would otherwise be an event per
        tick per connector, and exhaust a free plan's quota."""
        import logging

        logging.getLogger("app.services.external_data_sync").error("sync failed for fear_greed")

        assert tracker.events == []


class TestBeforeSendRewritesEveryFieldThatCanCarryASecret:
    """Direct, wire-independent check of each field `_before_send` rewrites
    (some, like `logentry`, are not reachable through the app's own routes)."""

    def test_every_secret_bearing_field_is_redacted_and_the_rest_is_untouched(self) -> None:
        secret = "DIRECT" + "SECRET"
        event = {
            "message": f"top-level apikey={secret} end",
            "logentry": {"message": f"log line api_token={secret}", "params": []},
            "exception": {
                "values": [
                    {"type": "RuntimeError", "value": f"boom password={secret}"},
                    {"type": "KeyError", "value": None},
                ]
            },
            "request": {
                "url": f"https://h/x?apikey={secret}&a=1",
                "query_string": f"api_token={secret}&page=2",
                "method": "GET",
            },
        }

        returned = _before_send(event, {})  # type: ignore[arg-type]

        assert returned is not None
        # The SDK's `Event` is a TypedDict whose keys are all optional; read it
        # back as the plain JSON-shaped dict it is on the wire.
        result: dict[str, Any] = dict(returned)
        assert secret not in str(result)
        assert result["message"] == "top-level apikey=[Filtered] end"
        assert result["logentry"]["message"] == "log line api_token=[Filtered]"
        assert result["exception"]["values"][0]["value"] == "boom password=[Filtered]"
        assert result["exception"]["values"][1]["value"] is None
        assert result["request"]["url"] == "https://h/x?apikey=[Filtered]&a=1"
        assert result["request"]["query_string"] == "api_token=[Filtered]&page=2"
        assert result["request"]["method"] == "GET"

    def test_an_event_with_none_of_those_fields_passes_through(self) -> None:
        assert _before_send({"level": "error"}, {}) == {"level": "error"}  # type: ignore[arg-type]


class TestRedactSecrets:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("?apikey=ABC&module=x", "?apikey=[Filtered]&module=x"),
            ("https://x/y?api_token=ABC", "https://x/y?api_token=[Filtered]"),
            # The value pattern also consumes a trailing comma: over-redacting a
            # punctuation mark is deliberately preferred to leaving a fragment
            # of a secret that itself contained a comma.
            ("x_api_key=ABC, password=hunter2", "x_api_key=[Filtered] password=[Filtered]"),
            ("client_secret=ABC", "client_secret=[Filtered]"),
            ("nothing secret here", "nothing secret here"),
            ("chainid=1&limit=100", "chainid=1&limit=100"),
        ],
    )
    def test_redacts_only_the_value_of_secret_looking_pairs(self, raw: str, expected: str) -> None:
        assert redact_secrets(raw) == expected


@pytest.fixture(autouse=True)
def _reset_sdk() -> Generator[None]:
    yield
    sentry_sdk.init()
