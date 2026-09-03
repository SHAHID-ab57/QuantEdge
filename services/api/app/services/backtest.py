"""Backtesting Engine service — plans a historical walk, and runs it.

This is the one place a `BacktestRun`/`Prediction` ORM row exists in this
feature's own code. Composes `PredictionService`/`TrainingJobService`
directly (never a second copy of either), the same reuse this platform's
other services layered over an existing one already established
(`app/services/prediction.py`'s own module docstring, describing its own
reuse of `TrainingJobService`/`FeatureService`).

The two properties this whole feature exists to guarantee both come from
*not* touching what's reused:

- `execute_run` calls `PredictionService.run` — completely unmodified,
  same `PredictionRunRequest` shape every live caller uses — once per
  planned step, and `PredictionService.grade_now` — also unmodified,
  itself calling the exact same `_grade_one` the periodic scheduler uses
  — immediately after. Neither method gained a `backtest_run_id`
  parameter or any other backtest-specific branch; tagging a resulting
  prediction as backtest-generated is a **separate**, additive
  `PredictionRepository.tag_backtest_run` write performed here, after
  `run` has already returned. A backtest using different logic than live
  prediction would test a hypothetical twin of the system, not the system.
- No-look-ahead is not re-verified here — it is a structural property of
  `PredictionService.run` itself (its candle fetch always ends at
  `reference_time + interval`, half-open, so a candle strictly after the
  requested `as_of` is never reachable; see that method's own docstring).
  Walking a `for as_of in plan.as_of_values` loop and calling `run`
  unmodified at each one *inherits* that guarantee automatically — this
  module does not, and must not, add any code that could reintroduce
  leakage (e.g. never widen the candle fetch itself, never pass a later
  `as_of` alongside an earlier one).

`app/backtest/engine.py`'s `plan_steps`/`aggregate` are the only two pure
computations genuinely new to this feature; both are called here, never
reimplemented.
"""

import logging
import uuid
from datetime import UTC, datetime

from app.backtest.base import GradedPredictionRow
from app.backtest.engine import aggregate, plan_steps
from app.backtest.errors import (
    BacktestRangeExceedsAvailableDataError,
    BacktestRunNotFoundError,
    InvalidBacktestRangeError,
    InvalidBacktestSortError,
    InvalidBacktestStepError,
)
from app.models.backtest_run import BacktestRun
from app.prediction.errors import LiveFeatureReconstructionNotSupportedError
from app.prediction.registry import get_model_adapter_registry
from app.repositories.backtest_runs import SORT_COLUMNS, BacktestRunFilters, BacktestRunRepository
from app.schemas.backtest import (
    BacktestListResponse,
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestSummaryDTO,
)
from app.schemas.prediction import PredictionRunRequest
from app.services.candle_ingest import resolution_duration
from app.services.market_query import CandleNotFoundError, MarketNotFoundError
from app.services.prediction import PredictionService
from app.services.training import TrainingJobService

logger = logging.getLogger("app.services.backtest")


class BacktestService:
    """The one entry point routers use for every backtest operation."""

    def __init__(
        self,
        repository: BacktestRunRepository,
        prediction_service: PredictionService,
        training_job_service: TrainingJobService,
        max_steps: int,
    ) -> None:
        self.repository = repository
        self.prediction_service = prediction_service
        self.training_job_service = training_job_service
        self.max_steps = max_steps

    async def start(self, request: BacktestRunRequest) -> BacktestRunResponse:
        """Plan and persist a new backtest run, and move it straight to 'running'.

        Unlike a training job (created 'pending', started separately by a
        second call), one `POST /backtests/run` call both creates and starts
        the run — there is no separate "register, then run later" step for a
        backtest. Returns once the row is persisted and transitioned;
        `app/dependencies/backtest.py`'s `schedule_backtest_run` (called by
        the router right after this) is what actually walks the range, in a
        background task the response does not wait for.

        Deliberately does **not** pre-validate that the job is 'completed'
        with a saved artifact the way `PredictionService.run` itself does —
        duplicating that check here would be a second copy of it. Instead,
        if the job cannot actually predict, the very first step inside
        `execute_run` raises exactly the error `PredictionService.run`
        already raises for a live caller, and this run is finalized as
        'failed' with that message, the same as any other in-loop failure.

        It **does** pre-validate the requested range against the market's
        own latest stored candle (see the dedicated check below) — this is
        not a duplicate of anything `PredictionService.run` already checks
        (that method only ever looks at one `as_of` at a time; nothing
        upstream of this validates a whole *range* against available data),
        and rejecting it before creating a run row is strictly better than
        letting it run and produce a misleadingly "completed" result.
        """
        if request.end <= request.start:
            # Cheap guard clause before any DB lookup — `plan_steps` would
            # raise this same error anyway, but only after the market/candle
            # lookups below, which would be pointless work for an obviously
            # malformed request.
            raise InvalidBacktestRangeError(request.start, request.end)

        job = await self.training_job_service.get(request.training_job_id)
        if not job.timeframe:
            # No recorded timeframe at all means there is nothing to plan a
            # walk over (not even a default step) — this is the one
            # precondition genuinely new to *planning* a range, so it is
            # checked upfront rather than deferred into the loop.
            raise LiveFeatureReconstructionNotSupportedError(request.training_job_id)

        step = request.step or job.timeframe
        try:
            step_interval = resolution_duration(step)
        except (KeyError, ValueError, IndexError) as exc:
            raise InvalidBacktestStepError(step, job.timeframe) from exc
        job_interval = resolution_duration(job.timeframe)
        if step_interval < job_interval:
            raise InvalidBacktestStepError(step, job.timeframe)

        # A backtest range that reaches past the latest real candle would,
        # left unchecked, let `PredictionService.run` — never
        # interpolating — resolve every step past that point to the exact
        # same last candle, collapsing them into repeated, identical
        # predictions folded silently into `aggregate_metrics`. Rejected
        # outright rather than truncated: unlike step-count capping (a
        # request that's merely too *long*), a request that's well within
        # `MAX_BACKTEST_STEPS` can still reach past available data, and a
        # partially-degenerate backtest is worse than a rejected one — it
        # looks like an ordinary completed result.
        market = await self.prediction_service.market_repository.get_by_symbol(request.symbol)
        if market is None:
            raise MarketNotFoundError(request.symbol)
        latest_candle = await self.prediction_service.candle_repository.get_latest_candle(
            market.id, job.timeframe
        )
        if latest_candle is None:
            raise CandleNotFoundError(request.symbol, job.timeframe)
        latest_open_time = (
            latest_candle.open_time
            if latest_candle.open_time.tzinfo
            else latest_candle.open_time.replace(tzinfo=UTC)
        )
        requested_end = request.end if request.end.tzinfo else request.end.replace(tzinfo=UTC)
        available_through = latest_open_time + job_interval
        if requested_end > available_through:
            raise BacktestRangeExceedsAvailableDataError(
                requested_end, latest_open_time, available_through
            )

        plan = plan_steps(
            start=request.start,
            end=request.end,
            step_interval=step_interval,
            max_steps=self.max_steps,
        )

        adapter_registry = get_model_adapter_registry()
        model_kind = (
            adapter_registry.get(job.model_type).metadata.model_kind
            if adapter_registry.has(job.model_type)
            else "unknown"
        )

        run = BacktestRun(
            training_job_id=request.training_job_id,
            experiment_id=uuid.UUID(job.experiment_id),
            symbol=request.symbol,
            timeframe=job.timeframe,
            step=step,
            requested_start=request.start,
            requested_end=request.end,
            effective_end=plan.effective_end,
            truncated=plan.truncated,
            status="pending",
            total_steps=len(plan.as_of_values),
            completed_steps=0,
            graded_count=0,
            model_kind=model_kind,
            aggregate_metrics=None,
        )
        created = await self.repository.create(run)
        started = await self.repository.try_transition_to_running(created.id)
        # Just created as 'pending' by this same call, above — nothing else
        # could have raced this row (see `BacktestRunRepository
        # .try_transition_to_running`'s own docstring).
        assert started is not None
        return BacktestRunResponse.from_model(started)

    async def get(self, run_id: uuid.UUID) -> BacktestRunResponse:
        run = await self._get_or_404(run_id)
        return BacktestRunResponse.from_model(run)

    async def search(
        self,
        *,
        training_job_id: uuid.UUID | None,
        experiment_id: uuid.UUID | None,
        symbol: str | None,
        status_filter: str | None,
        sort: str,
        direction: str,
        limit: int,
        offset: int,
    ) -> BacktestListResponse:
        """Backtest History's list view — every past run, most recent first by default."""
        if sort not in SORT_COLUMNS or direction not in {"asc", "desc"}:
            raise InvalidBacktestSortError(sort, direction, tuple(SORT_COLUMNS))

        filters = BacktestRunFilters(
            training_job_id=training_job_id,
            experiment_id=experiment_id,
            symbol=symbol,
            status=status_filter,
        )
        runs, total = await self.repository.search(
            filters, sort=sort, direction=direction, limit=limit, offset=offset
        )
        return BacktestListResponse(
            runs=[BacktestSummaryDTO.from_model(run) for run in runs],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def execute_run(self, run_id: uuid.UUID) -> BacktestRunResponse:
        """Walk every planned step for a run `start` already moved to 'running'.

        Split out from `start` exactly the way `TrainingJobService.execute_run`
        is split from `TrainingJobService.start` — so
        `app/dependencies/backtest.py`'s background task can call this on a
        *fresh* `BacktestService` instance (its own DB session) after `start`
        has already returned the response to the client. Re-derives the
        exact same `as_of` walk `start` planned (from this row's own
        `requested_start`/`effective_end`/`step` — `effective_end` already
        reflects any capping `start` applied, so replanning over
        `[requested_start, effective_end)` reproduces the identical,
        already-capped list without storing it anywhere) rather than
        threading it through in memory, since this runs in a separate
        process turn (possibly a separate process entirely) from `start`.

        One prediction, one grade, per step — both unmodified calls (see
        this module's own docstring) — aggregated at the end via
        `app.backtest.engine.aggregate`. Any exception, from any step,
        finalizes this run as 'failed' with the captured error, exactly
        mirroring `TrainingJobService.execute_run`'s own single
        try/except-the-whole-operation shape, not a per-step
        isolate-and-continue (that convention belongs to
        `PredictionService.grade_pending`, which isolates *many independent
        predictions* from one bad row; a backtest is *one* run, and a step
        that cannot predict at all — e.g. the job was never actually
        completed — means the whole run failed, not that it silently ran
        shorter than requested).
        """
        run = await self._get_or_404(run_id)
        step_interval = resolution_duration(run.step)
        plan = plan_steps(
            start=run.requested_start,
            end=run.effective_end,
            step_interval=step_interval,
            max_steps=self.max_steps,
        )

        graded_rows: list[GradedPredictionRow] = []
        completed_steps = 0
        graded_count = 0
        try:
            for as_of in plan.as_of_values:
                prediction = await self.prediction_service.run(
                    PredictionRunRequest(
                        training_job_id=run.training_job_id, symbol=run.symbol, as_of=as_of
                    )
                )
                prediction_id = uuid.UUID(prediction.id)
                # Additive tag, applied *after* `run` already persisted the
                # row exactly as any live caller's would — never a parameter
                # threaded into `run` itself. `PredictionService.repository`
                # is that service's own public attribute (not a private
                # reach-around), the same one every one of its own methods
                # already uses.
                await self.prediction_service.repository.tag_backtest_run(prediction_id, run.id)
                outcome = await self.prediction_service.grade_now(prediction_id)
                completed_steps += 1
                if outcome is not None:
                    graded_count += 1
                    graded_rows.append(
                        GradedPredictionRow(
                            predicted_value=prediction.predicted_value,
                            actual_outcome=outcome.actual_outcome,
                            classes=prediction.classes,
                            probabilities=prediction.probabilities,
                        )
                    )
        except Exception as exc:  # noqa: BLE001 - converted into a failed run, not re-raised
            logger.exception(
                "Backtest run %s crashed at step %s/%s",
                run_id,
                completed_steps + 1,
                len(plan.as_of_values),
            )
            failed = await self._get_or_404(run_id)
            failed = await self.repository.update(
                failed,
                {
                    "status": "failed",
                    "error_message": str(exc),
                    "completed_at": datetime.now(UTC),
                    "completed_steps": completed_steps,
                    "graded_count": graded_count,
                },
            )
            return BacktestRunResponse.from_model(failed)

        report = aggregate(run.model_kind, graded_rows) if graded_rows else None
        completed = await self._get_or_404(run_id)
        completed = await self.repository.update(
            completed,
            {
                "status": "completed",
                "completed_at": datetime.now(UTC),
                "completed_steps": completed_steps,
                "graded_count": graded_count,
                "aggregate_metrics": report.metrics if report is not None else None,
            },
        )
        logger.info(
            "Backtest run %s completed: %s/%s steps, %s graded",
            run_id,
            completed_steps,
            len(plan.as_of_values),
            graded_count,
        )
        return BacktestRunResponse.from_model(completed)

    async def _get_or_404(self, run_id: uuid.UUID) -> BacktestRun:
        run = await self.repository.get_by_id(run_id)
        if run is None:
            raise BacktestRunNotFoundError(run_id)
        return run
