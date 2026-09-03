"""Shared fixtures for `tests/api/` — the ASGI-over-httpx endpoint test suites."""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

import app.dependencies.backtest as backtest_dependencies
import app.dependencies.training as training_dependencies


@pytest.fixture(autouse=True)
def _training_background_uses_the_test_engine(
    monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine
) -> None:
    """`POST /training-jobs/{id}/run` schedules its pipeline execution in a
    background `asyncio.Task` that opens its own DB session via
    `app.dependencies.training.get_engine()` — never through
    `get_db`/FastAPI's dependency overrides (see that module's own
    docstring for why). Point it at this test's own in-memory engine so it
    reads/writes the same database every `client`/`session_factory` fixture
    in `tests/api/` already does — the same convention
    `tests/services/test_candle_sync.py` uses for `CandleSyncScheduler`.

    Autouse and file-scoped to this directory: every suite under
    `tests/api/` that runs a training job (directly, or via a
    `train_completed_job`-style helper) needs this, not just
    `test_training_api.py` itself.
    """
    monkeypatch.setattr(training_dependencies, "get_engine", lambda: engine)


@pytest.fixture(autouse=True)
def _backtest_background_uses_the_test_engine(
    monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine
) -> None:
    """The same seam as `_training_background_uses_the_test_engine` above,
    for `POST /backtests/run`'s own background task
    (`app.dependencies.backtest.get_engine()`) — a separate imported name in
    a separate module, so it needs its own monkeypatch target even though
    both ultimately point at the identical in-memory test engine.
    """
    monkeypatch.setattr(backtest_dependencies, "get_engine", lambda: engine)
