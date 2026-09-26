"""Scheduled retraining, with the drift monitor checked before promotion
(RETRAIN-WITH-MINIMUM-WINDOW).

Closes the loop FEATURE-DRIFT-MONITOR opened: that task could detect and
auto-pause a drifted model, but nothing retrained one. Left alone, the
platform would keep re-discovering the same problem by chance the way this
whole thread started. This scheduler periodically retrains each configured
model lineage on a fresh rolling window and, only if the fresh job itself
reads `healthy` against `app.prediction.feature_drift`, auto-swaps every
currently-enabled account pointed at that lineage onto it.

**The window width and retrain interval are hard floors, derived from real
data, not chosen by feel** — full analysis in
`docs/research/RETRAIN_WINDOW_ANALYSIS.md`. Both are checked once, at
construction, and a caller cannot build this scheduler with a narrower
window or a longer retrain gap than the floor at all; there is no warn-and-
continue path. Two real numbers matter here:

- `MIN_WINDOW_HOURS = 8760` (365 days). A dataset window's own *fit* split
  is only its chronologically first 70% (`ColumnNormalizer.fit` fits on
  the train split alone, never validation/test) — the exact mechanism that
  made this task's own first retrain attempt (`W=4320h`, chosen without
  this correction) immediately read `drifted` against itself
  (`sma_20` z=64) the moment it was checked. Measured on the real stored
  ETHUSD/1h history with that split correctly accounted for
  (fit on the first 70% of a window, checked `0.3*W + D_retrain` hours
  later — exactly what a freshly trained, then in-service, job actually
  experiences): 8,760 hours keeps price/SMA's 99th-percentile z at ~2.9-3.2
  and its historical worst case under 3.5, for a weekly retrain cadence.
- `MAX_RETRAIN_INTERVAL_SECONDS = 168 * 3600` (7 days). The same analysis,
  read the other way: at `W=8760h`, drift stays safely bounded (worst case
  under 6) for a retrain gap up to about a week; the margin below the 10σ
  alarm shrinks materially at longer gaps (a monthly cadence needs a
  noticeably wider window for the same safety margin).

**`volume` is deliberately not in the retrained feature set at all** — the
same analysis found raw volume cannot be kept safe under any practical
window/cadence combination checked (99th-percentile z in the teens to 40s,
worst case over 60, even at the widest, most-frequently-retrained
combination tried); `app/features/builtin/volume_log.py`'s own docstring
has the full numbers. Every job this scheduler creates uses `ohlc` +
`volume_log` + `sma`, never the bundled `ohlcv`.

**Promotion is auto-swap, chosen explicitly** (the one real judgment call
in this task, decided by the user rather than defaulted, the same way the
drift monitor's own auto-pause response policy was). A promotion never
re-enables a disabled account (human-disabled or still drift-paused) —
only an account already `strategy_enabled=True` and already pointed at
this lineage gets repointed, keeping the exact same "an explicit human
decision about `enabled` is never made for you" boundary
`update_strategy_config`'s own drift-pause-clearing logic already draws.
Like `PaperTradingStrategyScheduler`'s own auto-pause, a promotion is
**not** routed through the human-audited `update_strategy_config` path —
there is no human to attribute it to — it writes the account row directly
and alerts via `capture_model_promoted`
(`app/monitoring/error_tracking.py`), mirroring `capture_feature_drift`'s
own precedent exactly.

**A retrain that comes back drifted against itself is never promoted.**
This is the one property that actually closes the loop: without checking
the fresh job against the drift monitor first, a scheduler like this could
just as easily reproduce the original problem on a schedule instead of
fixing it. `capture_retrain_unhealthy` alerts when this happens — it should
be rare (the whole point of the enforced floors), and if it isn't, that is
itself worth knowing.
"""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import get_engine
from app.dependencies.prediction import get_prediction_service
from app.dependencies.training import get_training_job_service
from app.models.training import TrainingJob
from app.monitoring.error_tracking import capture_model_promoted, capture_retrain_unhealthy
from app.repositories.paper_trading import PaperAccountRepository
from app.repositories.training import TrainingJobFilters, TrainingJobRepository
from app.schemas.prediction import PredictionRunRequest
from app.schemas.training import TrainingJobCreateRequest

logger = logging.getLogger("app.services.retraining")

#: See this module's own docstring for the real analysis behind both numbers.
MIN_WINDOW_HOURS = 8760
MAX_RETRAIN_INTERVAL_SECONDS = 168 * 3600

#: The feature set every currently-configured retraining target's own
#: experiment was created with — never the bundled `ohlcv`, whose `volume`
#: column the same analysis found cannot be kept safe. Documented here for
#: reference (what a new target's own experiment should be built with), not
#: read by this module: `symbol`/`timeframe`/`model_type`/`hyperparameters`
#: are all cloned from the lineage's own most recent completed job instead
#: of configured separately, so they can never drift out of sync with what
#: has actually been trained and verified working.
FEATURE_SET: tuple[dict[str, object], ...] = (
    {"feature": "ohlc", "params": {}},
    {"feature": "volume_log", "params": {}},
    {"feature": "sma", "params": {"period": "20", "source": "close"}},
)


@dataclass(frozen=True)
class RetrainingTarget:
    """One model lineage this scheduler keeps fresh.

    `experiment_id` is the lineage's own stable identity, and the *only*
    thing configured about it — every job this scheduler creates for a
    target reuses the experiment's own `feature_set`/`target_config`/
    `split_config`, and clones `symbol`/`timeframe`/`model_type`/
    `hyperparameters` from the lineage's own most recent completed job
    (never separately configured, so they can never drift out of sync with
    what has actually been trained and verified working). A lineage with no
    completed job yet has nothing to clone from and is skipped, logged, not
    an error — the same "bootstrap it once by hand, then let the scheduler
    keep it fresh" step this task's own Step 2 already did once, manually,
    for the very first job in this lineage.
    """

    experiment_id: uuid.UUID


@dataclass(frozen=True)
class RetrainingTickSummary:
    """Outcome of one retraining pass, across every configured target."""

    attempted: int
    not_due: int
    retrained: int
    promoted: int
    accounts_repointed: int
    unhealthy: int
    failed: int
    duration_seconds: float


class RetrainingScheduler:
    """Periodically retrains each configured model lineage and, only when
    the fresh job reads healthy, auto-swaps its currently-enabled accounts
    onto it. See this module's own docstring for the full design.

    Args:
        targets: The model lineages to keep fresh.
        window_hours: Candle-row ceiling for each retrain's own dataset
            build — rejected outright if narrower than `MIN_WINDOW_HOURS`.
        min_retrain_interval_seconds: How long a lineage's newest completed
            job may age before the next tick retrains it — rejected
            outright if wider than `MAX_RETRAIN_INTERVAL_SECONDS`.
        tick_interval_seconds: How often the loop itself wakes up to check
            whether anything is due — independent of, and typically much
            shorter than, `min_retrain_interval_seconds` (checking often is
            cheap; actually retraining only happens when due).
    """

    def __init__(
        self,
        *,
        targets: Sequence[RetrainingTarget],
        window_hours: int = MIN_WINDOW_HOURS,
        min_retrain_interval_seconds: int = MAX_RETRAIN_INTERVAL_SECONDS,
        tick_interval_seconds: int = 3600,
    ) -> None:
        if window_hours < MIN_WINDOW_HOURS:
            raise ValueError(
                f"window_hours={window_hours} is narrower than the enforced floor "
                f"({MIN_WINDOW_HOURS}h / {MIN_WINDOW_HOURS / 24:.0f} days) — see "
                "docs/research/RETRAIN_WINDOW_ANALYSIS.md for the real data behind it. "
                "This is a hard floor, not a default: it is not overridable narrower."
            )
        if min_retrain_interval_seconds > MAX_RETRAIN_INTERVAL_SECONDS:
            raise ValueError(
                f"min_retrain_interval_seconds={min_retrain_interval_seconds} exceeds the "
                f"enforced ceiling ({MAX_RETRAIN_INTERVAL_SECONDS}s / "
                f"{MAX_RETRAIN_INTERVAL_SECONDS / 3600:.0f}h) — see "
                "docs/research/RETRAIN_WINDOW_ANALYSIS.md for the real data behind it. "
                "This is a hard ceiling, not a default: it is not overridable wider."
            )
        self._targets = list(targets)
        self._window_hours = window_hours
        self._min_retrain_interval_seconds = min_retrain_interval_seconds
        self._tick_interval_seconds = max(tick_interval_seconds, 1)
        self._stopped = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return
        if get_engine() is None:
            logger.warning("Retraining scheduler not started: database not configured")
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._loop(), name="retraining-loop")
        logger.info(
            "Retraining scheduler started (targets=%d window_hours=%d "
            "min_retrain_interval_seconds=%d tick_interval_seconds=%d)",
            len(self._targets),
            self._window_hours,
            self._min_retrain_interval_seconds,
            self._tick_interval_seconds,
        )

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        self._stopped.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._task = None
        logger.info("Retraining scheduler stopped")

    async def _loop(self) -> None:
        while not self._stopped.is_set():
            summary = await self.run_retraining_tick()
            if summary.retrained > 0 or summary.failed > 0:
                logger.info(
                    "Retraining tick: retrained=%d promoted=%d unhealthy=%d failed=%d in %.2fs",
                    summary.retrained,
                    summary.promoted,
                    summary.unhealthy,
                    summary.failed,
                    summary.duration_seconds,
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=self._tick_interval_seconds)

    async def run_retraining_tick(self) -> RetrainingTickSummary:
        """Check every configured target, retraining and (if healthy)
        promoting whichever ones are due. Isolated per target — one
        lineage's failure never stops the rest, the same per-item isolation
        every other scheduler on this platform already applies."""
        started = perf_counter()
        not_due = retrained = promoted = accounts_repointed = unhealthy = failed = 0
        now = datetime.now(UTC)
        for target in self._targets:
            session = async_sessionmaker(bind=get_engine(), expire_on_commit=False)()
            try:
                latest = await self._latest_completed_job(session, target)
                if latest is None:
                    logger.warning(
                        "Retraining target experiment=%s has no completed job yet to clone "
                        "config from — skipped, not an error. Bootstrap it once by hand first.",
                        target.experiment_id,
                    )
                    not_due += 1
                    continue
                if not self._is_due(latest, now):
                    not_due += 1
                    continue
                if not latest.symbol or not latest.timeframe:
                    logger.warning(
                        "Retraining target experiment=%s's latest job (%s) has no recorded "
                        "symbol/timeframe to clone — skipped.",
                        target.experiment_id,
                        latest.id,
                    )
                    failed += 1
                    continue
                symbol = latest.symbol

                new_job_id = await self._retrain(session, target, latest, now)
                if new_job_id is None:
                    failed += 1
                    continue
                retrained += 1

                if not await self._is_healthy(session, target, new_job_id, symbol):
                    unhealthy += 1
                    continue

                repointed = await self._promote(session, target, new_job_id)
                promoted += 1
                accounts_repointed += repointed
            except Exception:  # noqa: BLE001 - isolated per target, never fatal to the tick
                failed += 1
                logger.exception("Retraining tick crashed for experiment=%s", target.experiment_id)
            finally:
                await session.close()

        return RetrainingTickSummary(
            attempted=len(self._targets),
            not_due=not_due,
            retrained=retrained,
            promoted=promoted,
            accounts_repointed=accounts_repointed,
            unhealthy=unhealthy,
            failed=failed,
            duration_seconds=perf_counter() - started,
        )

    @staticmethod
    async def _latest_completed_job(
        session: AsyncSession, target: "RetrainingTarget"
    ) -> TrainingJob | None:
        jobs, _total = await TrainingJobRepository(session).search(
            TrainingJobFilters(experiment_id=target.experiment_id, status="completed"),
            sort="completed_at",
            direction="desc",
            limit=1,
            offset=0,
        )
        return jobs[0] if jobs else None

    def _is_due(self, latest_job: TrainingJob, now: datetime) -> bool:
        if latest_job.completed_at is None:
            return True
        completed_at = latest_job.completed_at
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=UTC)
        age = now - completed_at
        return age >= timedelta(seconds=self._min_retrain_interval_seconds)

    async def _retrain(
        self,
        session: AsyncSession,
        target: "RetrainingTarget",
        latest_job: TrainingJob,
        now: datetime,
    ) -> uuid.UUID | None:
        symbol, timeframe = latest_job.symbol, latest_job.timeframe
        if not symbol or not timeframe:
            logger.warning(
                "Retraining target experiment=%s's latest job (%s) has no recorded "
                "symbol/timeframe to clone — skipped.",
                target.experiment_id,
                latest_job.id,
            )
            return None
        training_service = get_training_job_service(session)
        job = await training_service.create(
            TrainingJobCreateRequest(
                experiment_id=target.experiment_id,
                model_type=latest_job.model_type,
                dataset_version=f"scheduled-retrain-{now:%Y-%m-%dT%H%M%SZ}",
                symbol=symbol,
                timeframe=timeframe,
                limit=self._window_hours,
                hyperparameters=dict(latest_job.hyperparameters or {}),
                normalize_features=latest_job.normalize_features,
            )
        )
        completed = await training_service.run(uuid.UUID(job.id))
        if completed.status != "completed":
            logger.error(
                "Scheduled retrain failed for experiment=%s (job=%s): %s",
                target.experiment_id,
                job.id,
                completed.error_message,
            )
            return None
        logger.info(
            "Scheduled retrain completed for experiment=%s: job=%s", target.experiment_id, job.id
        )
        return uuid.UUID(job.id)

    async def _is_healthy(
        self, session: AsyncSession, target: "RetrainingTarget", job_id: uuid.UUID, symbol: str
    ) -> bool:
        prediction_service = get_prediction_service(session)
        prediction = await prediction_service.run(
            PredictionRunRequest(training_job_id=job_id, symbol=symbol)
        )
        if prediction.feature_drift_status == "healthy":
            return True
        logger.error(
            "Scheduled retrain for experiment=%s (job=%s) is itself %s (%s z=%s) — NOT promoted",
            target.experiment_id,
            job_id,
            prediction.feature_drift_status,
            prediction.feature_drift_worst_feature,
            prediction.feature_drift_worst_z,
        )
        capture_retrain_unhealthy(
            experiment_id=str(target.experiment_id),
            job_id=str(job_id),
            drift_status=prediction.feature_drift_status,
            worst_feature=prediction.feature_drift_worst_feature,
            worst_z=prediction.feature_drift_worst_z,
        )
        return False

    async def _promote(
        self, session: AsyncSession, target: RetrainingTarget, new_job_id: uuid.UUID
    ) -> int:
        """Auto-swap: repoint every *currently-enabled* account whose current
        job belongs to this lineage onto the fresh job. Never touches
        `strategy_enabled`/`strategy_paused_reason` — a disabled account
        (human-disabled or still drift-paused) is left exactly as it was;
        only an account a human has already opted in stays opted in, now on
        fresher data."""
        account_repository = PaperAccountRepository(session)
        job_repository = TrainingJobRepository(session)
        enabled_accounts = await account_repository.list_strategy_enabled()
        repointed = 0
        for account in enabled_accounts:
            if account.strategy_training_job_id is None:
                continue
            current_job = await job_repository.get_by_id(account.strategy_training_job_id)
            if current_job is None or current_job.experiment_id != target.experiment_id:
                continue
            if current_job.id == new_job_id:
                continue
            old_job_id = current_job.id
            await account_repository.update(account, {"strategy_training_job_id": new_job_id})
            logger.info(
                "Promoted account=%s from job=%s to job=%s (experiment=%s)",
                account.id,
                old_job_id,
                new_job_id,
                target.experiment_id,
            )
            repointed += 1
        if repointed > 0:
            capture_model_promoted(
                experiment_id=str(target.experiment_id),
                new_job_id=str(new_job_id),
                accounts_repointed=repointed,
            )
        return repointed


async def run_retraining_once(targets: Sequence[RetrainingTarget]) -> RetrainingTickSummary:
    """Run one retraining pass synchronously (CLI and manual verification)."""
    scheduler = RetrainingScheduler(targets=targets)
    return await scheduler.run_retraining_tick()
