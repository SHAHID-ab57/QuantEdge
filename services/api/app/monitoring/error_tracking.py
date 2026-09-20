"""Error tracking via the Sentry protocol (M5-E5-T2).

Speaks the Sentry wire protocol through `sentry-sdk`, which Sentry,
GlitchTip and Bugsink all accept: switching between them is a DSN change,
not a code change. With no `SENTRY_DSN` configured nothing is initialized
and every function here is a no-op, the same soft-dependency convention as
`redis_url`.

**What is deliberately never sent to a third party.** This platform
handles a login endpoint and holds connector API keys, so the defaults of
an error tracker are not acceptable as-is:

- request bodies (`max_request_body_size="never"`): a crash inside
  `POST /auth/login` would otherwise ship the submitted password;
- local variables in stack frames (`include_local_variables=False`): the
  built-in scrubber only matches a few exact key names, so a local named
  `hashed_password` or `api_token` would go out in the clear;
- default PII (`send_default_pii=False`);
- HTTP-client breadcrumbs: several connectors put their real API key in
  the query string (`apikey`, `api_key`, `api_token`), and the SDK's
  `httpx`/`http.client` breadcrumbs record it. Dropped outright, mirroring
  why `app.core.logging` silences httpx's own logger.
- any `key=value` secret inside an exception message or query string is
  redacted (`redact_secrets`) as a last line of defence.

Log records are breadcrumbs only, never events (`event_level=None`): an
hourly sync failing for a week would otherwise be one event per tick per
connector and exhaust a free plan's event quota. A persistent failure is
reported once, at the moment it starts, by `capture_connector_failing`.
"""

import logging
import re
from collections.abc import Sequence
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber
from sentry_sdk.types import Breadcrumb, BreadcrumbHint, Event, Hint

from app.core.config import Settings

logger = logging.getLogger("app.monitoring.error_tracking")

#: Breadcrumb categories the SDK's HTTP-client integrations emit; each
#: carries the full request URL, query string included.
_HTTP_CLIENT_BREADCRUMB_CATEGORIES = frozenset({"httplib", "httpx", "http", "requests"})

#: Names that mark a `name=value` pair as a secret.
_SECRET_PAIR = re.compile(
    r"(?i)\b([\w-]*(?:api[_-]?key|api[_-]?token|token|secret|password|passwd|access[_-]?key)"
    r"|key)=([^&\s'\"]+)"
)

REDACTED = "[Filtered]"

#: Extra key names for the SDK's own scrubber (which compares whole,
#: lower-cased dict keys), on top of its defaults.
_EXTRA_DENYLIST = [
    "api_token",
    "hashed_password",
    "jwt_secret_key",
    "delta_api_secret",
    "authorization",
    "cookie",
]


def redact_secrets(text: str) -> str:
    """Replace the value of any secret-looking `name=value` pair."""
    return _SECRET_PAIR.sub(lambda match: f"{match.group(1)}={REDACTED}", text)


def _before_breadcrumb(crumb: Breadcrumb, hint: BreadcrumbHint) -> Breadcrumb | None:
    if crumb.get("category") in _HTTP_CLIENT_BREADCRUMB_CATEGORIES:
        return None
    message = crumb.get("message")
    if isinstance(message, str):
        crumb["message"] = redact_secrets(message)
    return crumb


def _before_send(event: Event, hint: Hint) -> Event | None:
    for value in event.get("exception", {}).get("values", []) or []:
        if isinstance(value.get("value"), str):
            value["value"] = redact_secrets(value["value"])
    message = event.get("message")
    if isinstance(message, str):
        event["message"] = redact_secrets(message)
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        logged_message = logentry.get("message")
        if isinstance(logged_message, str):
            logentry["message"] = redact_secrets(logged_message)
    request = event.get("request")
    if isinstance(request, dict):
        for field in ("query_string", "url"):
            value = request.get(field)
            if isinstance(value, str):
                request[field] = redact_secrets(value)
    return event


def init_error_tracking(settings: Settings, *, transport: Any = None) -> bool:
    """Initialize the SDK if a DSN is configured; return whether it is on.

    `transport` is a test seam: tests pass an in-process transport that
    records what would have been sent, so what leaves the process can be
    asserted on rather than assumed.

    Must run before the FastAPI app is created: the SDK's Starlette
    integration hooks the app's middleware stack, which is built on the
    first ASGI call, before the lifespan starts.
    """
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        transport=transport,
        environment=settings.sentry_environment or settings.app_env,
        release=f"{settings.app_name}@{settings.app_version}",
        # Errors only: no performance tracing, which would spend the
        # free-tier quota on data this feature does not need.
        traces_sample_rate=0.0,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        event_scrubber=EventScrubber(denylist=DEFAULT_DENYLIST + _EXTRA_DENYLIST),
        before_send=_before_send,
        before_breadcrumb=_before_breadcrumb,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=None),
        ],
    )
    logger.info(
        "Error tracking enabled (environment=%s)",
        settings.sentry_environment or settings.app_env,
    )
    return True


def set_user(user_id: str) -> None:
    """Attach the authenticated user's id (never email or name) to events.

    A no-op when error tracking is off. Not merely an optimization: with no
    SDK client there is also no per-request scope isolation, so this would
    write into the SDK's shared process-wide scope and leak one request's
    user onto later, unrelated events.
    """
    if is_enabled():
        sentry_sdk.set_user({"id": user_id})


def tag_request(request_id: str) -> None:
    """Tag the current request's events with its id (no-op when disabled,
    for the same shared-scope reason as `set_user`)."""
    if is_enabled():
        sentry_sdk.get_isolation_scope().set_tag("request_id", request_id)


def capture_connector_failing(source: str, *, recent_errors: Sequence[str], streak: int) -> None:
    """Report that a connector has just started failing.

    One event per transition into `failing`, grouped per connector by
    fingerprint, so a connector that keeps failing for a week is one issue,
    not one alert per tick.
    """
    errors = [redact_secrets(error) for error in recent_errors if error]
    logger.error(
        "Connector %s is failing: its last %d sync attempts all errored",
        source,
        streak,
        extra={"connector": source, "recent_errors": errors},
    )
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("connector", source)
        scope.set_context(
            "connector_health",
            {"source": source, "consecutive_failures": streak, "recent_errors": errors},
        )
        scope.fingerprint = ["connector-failing", source]
        sentry_sdk.capture_message(
            f"Connector {source} is failing: its last {streak} sync attempts all errored",
            level="error",
        )


def capture_trading_halted(
    account_id: str, *, equity: object, peak_equity: object, max_drawdown_pct: object
) -> None:
    """Alert that a paper account's drawdown limit just halted its trading.

    One event per halt, grouped per account by fingerprint, so an account
    that stays halted is one issue, not one alert per later order. The
    kill switch's alert (D4): the halt blocks new risk, this makes sure a
    person finds out it happened.
    """
    logger.error(
        "Paper trading halted for account %s: equity %s fell more than %s%% below its peak %s",
        account_id,
        equity,
        max_drawdown_pct,
        peak_equity,
        extra={"paper_account_id": account_id},
    )
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("paper_account_id", account_id)
        scope.set_context(
            "paper_trading_halt",
            {
                "account_id": account_id,
                "equity": str(equity),
                "peak_equity": str(peak_equity),
                "max_drawdown_pct": str(max_drawdown_pct),
            },
        )
        scope.fingerprint = ["paper-trading-halted", account_id]
        sentry_sdk.capture_message(
            f"Paper trading halted for account {account_id}: drawdown limit breached",
            level="error",
        )


def is_enabled() -> bool:
    """Whether events would actually be sent somewhere (a DSN is configured).

    Not `Client.is_active()`: that is true for any real client object,
    including the DSN-less one `sentry_sdk.init()` leaves behind.
    """
    return bool(sentry_sdk.get_client().dsn)


__all__ = [
    "REDACTED",
    "capture_connector_failing",
    "capture_trading_halted",
    "init_error_tracking",
    "is_enabled",
    "redact_secrets",
    "set_user",
    "tag_request",
]
