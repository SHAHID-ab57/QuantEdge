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


def capture_feature_drift(
    account_id: str,
    *,
    training_job_id: str,
    worst_feature: str,
    worst_z: float,
    threshold: float,
) -> None:
    """Alert that a paper account's strategy was just auto-paused for feature drift.

    One event per pause, grouped per account by fingerprint — mirrors
    `capture_trading_halted` exactly (the drawdown kill switch's own
    alert): a halt/pause blocks new risk on its own, this makes sure a
    person finds out it happened. See
    `docs/research/FEATURE_DRIFT_INVESTIGATION.md` for the two real
    incidents that motivated this (both discovered only by directly
    checking the live system, with nothing having flagged either).
    """
    logger.error(
        "Paper trading strategy auto-paused for account %s: feature drift detected "
        "(job=%s, %s z=%.2f, threshold=%.1f)",
        account_id,
        training_job_id,
        worst_feature,
        worst_z,
        threshold,
        extra={"paper_account_id": account_id, "training_job_id": training_job_id},
    )
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("paper_account_id", account_id)
        scope.set_tag("training_job_id", training_job_id)
        scope.set_context(
            "feature_drift",
            {
                "account_id": account_id,
                "training_job_id": training_job_id,
                "worst_feature": worst_feature,
                "worst_z": worst_z,
                "threshold": threshold,
            },
        )
        scope.fingerprint = ["feature-drift-paused", account_id]
        sentry_sdk.capture_message(
            f"Paper trading strategy auto-paused for account {account_id}: "
            f"feature drift detected ({worst_feature} z={worst_z:.2f})",
            level="error",
        )


def capture_retrain_unhealthy(
    *,
    experiment_id: str,
    job_id: str,
    drift_status: str,
    worst_feature: str | None,
    worst_z: float | None,
) -> None:
    """Alert that a scheduled retrain came back drifted (or unavailable)
    against its own fresh data, and was therefore never promoted
    (RETRAIN-WITH-MINIMUM-WINDOW).

    Grouped per experiment by fingerprint. This should be rare — the whole
    point of `app.services.retraining`'s enforced window/cadence floors —
    so a recurring one is itself worth investigating, not routine noise.
    """
    logger.error(
        "Scheduled retrain for experiment %s (job %s) is itself %s (%s z=%s) — not promoted",
        experiment_id,
        job_id,
        drift_status,
        worst_feature,
        worst_z,
        extra={"experiment_id": experiment_id, "training_job_id": job_id},
    )
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("experiment_id", experiment_id)
        scope.set_tag("training_job_id", job_id)
        scope.set_context(
            "retrain_unhealthy",
            {
                "experiment_id": experiment_id,
                "job_id": job_id,
                "drift_status": drift_status,
                "worst_feature": worst_feature,
                "worst_z": worst_z,
            },
        )
        scope.fingerprint = ["retrain-unhealthy", experiment_id]
        sentry_sdk.capture_message(
            f"Scheduled retrain for experiment {experiment_id} is itself {drift_status} — "
            "not promoted",
            level="error",
        )


def capture_model_promoted(*, experiment_id: str, new_job_id: str, accounts_repointed: int) -> None:
    """Report that a scheduled retrain was promoted: real accounts are now
    trading on a different model than a moment ago (RETRAIN-WITH-MINIMUM-
    WINDOW's own auto-swap promotion policy).

    `info`, not `error` — a promotion is the system working as designed,
    not a failure — but still worth a visible record given what it changes:
    exactly the kind of live-account-configuration change
    LOG-ACCOUNT-CONFIG-CHANGES was built because a silent one went
    untraceable once already.
    """
    logger.info(
        "Scheduled retrain promoted for experiment %s: job %s now serving %d account(s)",
        experiment_id,
        new_job_id,
        accounts_repointed,
        extra={"experiment_id": experiment_id, "training_job_id": new_job_id},
    )
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("experiment_id", experiment_id)
        scope.set_tag("training_job_id", new_job_id)
        scope.set_context(
            "model_promoted",
            {
                "experiment_id": experiment_id,
                "new_job_id": new_job_id,
                "accounts_repointed": accounts_repointed,
            },
        )
        sentry_sdk.capture_message(
            f"Model promoted for experiment {experiment_id}: job {new_job_id} now serving "
            f"{accounts_repointed} account(s)",
            level="info",
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
